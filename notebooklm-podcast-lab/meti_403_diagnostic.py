"""
METI 403 Diagnostic - Determine root cause on GitHub Actions.

Tests multiple approaches to identify why METI returns 403:
1. Raw curl (no impersonation, with/without proxy)
2. curl-cffi with various impersonation profiles (with/without WARP proxy)
3. requests library (with/without proxy)
4. Header combinations
5. Check response body for WAF clues
6. Summary: which profile+proxy combo works

Usage:
    python meti_403_diagnostic.py
"""

import os
import sys
import subprocess
import json
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import setup_logging, logger

setup_logging()

METI_URL = "https://www.meti.go.jp/shingikai/index.html"
METI_PRESS = "https://www.meti.go.jp/press/index.html"
# Specific pages that previously returned 403
ENECHO_URL = "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/jisedai_kiban/gas_business_wg/007.html"
ENERGY_ENV_URL = "https://www.meti.go.jp/shingikai/energy_environment/sogo_energy/2025_001.html"

SOCKS5_PROXY = os.getenv("SOCKS5_PROXY", "").strip()

# All profiles to test (legacy + current)
PROFILES = [
    # Legacy profiles that worked with WARP in the past
    "safari17_0",
    "firefox133",
    # Current profiles in shared/network.py
    "firefox135",
    "safari18_0",
    "chrome133a",
    # Chrome profiles (known to timeout/block on GHA)
    "chrome120",
    "chrome131",
]

SPECIFIC_PAGES = [
    ("ENECHO page", ENECHO_URL),
    ("Energy Environment page", ENERGY_ENV_URL),
]


@dataclass
class TestResult:
    """Single test result: profile, proxy mode, status, size, error, URL."""
    profile: str
    use_proxy: bool
    status: int = -1
    size: int = 0
    error: str = ""
    url: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200


@dataclass
class MatrixResults:
    """Collects all test results for final summary."""
    results: list = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)

    def get_passing(self, use_proxy: bool) -> list[TestResult]:
        return [r for r in self.results if r.ok and r.use_proxy == use_proxy]

    def print_summary(self):
        print("\n" + "=" * 60)
        print("SUMMARY: Working profile + proxy combinations")
        print("=" * 60)

        passing_direct = self.get_passing(use_proxy=False)
        passing_warp = self.get_passing(use_proxy=True)

        if passing_direct:
            print(f"\n  Direct (no proxy) - {len(passing_direct)} OK:")
            for r in passing_direct:
                print(f"    {r.profile}: {r.url} (size={r.size})")
        else:
            print("\n  Direct (no proxy): NONE passed")

        if passing_warp:
            print(f"\n  WARP proxy - {len(passing_warp)} OK:")
            for r in passing_warp:
                print(f"    {r.profile}: {r.url} (size={r.size})")
        else:
            print("\n  WARP proxy: NONE passed")

        # Recommendation
        print("\n  --- Recommendation ---")
        if passing_warp:
            print("  Use WARP proxy with one of these profiles:")
            for r in passing_warp:
                print(f"    - {r.profile}")
        elif passing_direct:
            print("  WARP is NOT helping. Use direct access with:")
            for r in passing_direct:
                print(f"    - {r.profile}")
        else:
            print("  NO profile worked. Consider:")
            print("    - Playwright headless browser")
            print("    - Different proxy provider (Japanese residential)")
            print("    - Increase wait intervals between requests")

        print("=" * 60)


matrix = MatrixResults()


def run_curl(url: str, extra_args: list[str] = None) -> dict:
    """Run raw curl command."""
    cmd = ["curl", "-s", "-o", "/dev/null", "-w",
           '{"status":%{http_code},"size":%{size_download},"time":%{time_total},"ssl":%{ssl_verify_result}}',
           "-L", "--max-time", "15"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": str(e)}


def run_curl_body(url: str, extra_args: list[str] = None) -> tuple[int, str]:
    """Run curl and return (status_code, first_500_chars_of_body)."""
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "-L", "--max-time", "15"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        output = result.stdout.strip()
        if "\n" in output:
            body, code = output.rsplit("\n", 1)
            return int(code), body[:500]
        return -1, output[:500]
    except Exception as e:
        return -1, str(e)


def get_proxies() -> dict | None:
    """Return SOCKS5 proxy dict if available, else None."""
    if SOCKS5_PROXY:
        return {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    return None


def test_curl_cffi(profile: str, url: str = METI_URL, proxies: dict | None = None) -> TestResult:
    """Test with curl-cffi impersonation."""
    use_proxy = proxies is not None
    try:
        from curl_cffi import requests
        session = requests.Session(impersonate=profile)
        resp = session.get(url, timeout=15, proxies=proxies)
        r = TestResult(
            profile=profile, use_proxy=use_proxy,
            status=resp.status_code, size=len(resp.content), url=url,
        )
    except Exception as e:
        r = TestResult(
            profile=profile, use_proxy=use_proxy,
            error=str(e), url=url,
        )
    matrix.add(r)
    return r


def test_requests_lib(proxies: dict | None = None) -> TestResult:
    """Test with standard requests library."""
    use_proxy = proxies is not None
    try:
        import requests as req
        resp = req.get(METI_URL, timeout=15, proxies=proxies)
        r = TestResult(
            profile="requests", use_proxy=use_proxy,
            status=resp.status_code, size=len(resp.content), url=METI_URL,
        )
    except Exception as e:
        r = TestResult(
            profile="requests", use_proxy=use_proxy,
            error=str(e), url=METI_URL,
        )
    matrix.add(r)
    return r


def test_with_headers(url: str, headers: dict, proxies: dict | None = None) -> TestResult:
    """Test curl-cffi with custom headers."""
    use_proxy = proxies is not None
    try:
        from curl_cffi import requests
        session = requests.Session(impersonate="chrome120")
        session.headers.update(headers)
        resp = session.get(url, timeout=15, proxies=proxies)
        r = TestResult(
            profile="chrome120+headers", use_proxy=use_proxy,
            status=resp.status_code, size=len(resp.content), url=url,
        )
    except Exception as e:
        r = TestResult(
            profile="chrome120+headers", use_proxy=use_proxy,
            error=str(e), url=url,
        )
    return r


def print_result(result: TestResult, indent: int = 2) -> None:
    """Print a single test result."""
    prefix = " " * indent
    if result.ok:
        print(f"{prefix}  {result.profile}: status={result.status}, size={result.size}")
    else:
        err = f" ERR:{result.error[:80]}" if result.error else ""
        print(f"{prefix}  {result.profile}: status={result.status}{err}")


def main():
    proxies = get_proxies()

    print("=" * 60)
    print("METI 403 DIAGNOSTIC")
    print("=" * 60)
    print(f"  SOCKS5_PROXY: {SOCKS5_PROXY or '(not set)'}")
    print(f"  GITHUB_ACTIONS: {os.getenv('GITHUB_ACTIONS', 'not set')}")
    print(f"  Runner OS: {os.getenv('RUNNER_OS', 'not set')}")
    print(f"  Profiles to test: {len(PROFILES)}")

    # ------------------------------------------------------------------
    # [1] Raw curl tests (direct only — curl CLI doesn't easily do SOCKS5)
    # ------------------------------------------------------------------
    print("\n--- [1] Raw curl tests (direct, no proxy) ---")
    curl_tests = [
        ("default UA", []),
        ("Chrome UA", ["-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"]),
        ("Japanese lang", ["-H", "Accept-Language: ja,en-US;q=0.9,en;q=0.8"]),
        ("Full browser headers", [
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "-H", "Accept-Language: ja,en-US;q=0.9,en;q=0.8",
            "-H", "Accept-Encoding: gzip, deflate, br",
        ]),
        ("METI press (different path)", []),
    ]
    for label, args in curl_tests:
        url = METI_PRESS if "different path" in label else METI_URL
        result = run_curl(url, args)
        status = result.get("status", "?")
        size = result.get("size", "?")
        mark = "OK" if status == 200 else "FAIL"
        print(f"  [{mark}] {label}: status={status}, size={size}")

    # ------------------------------------------------------------------
    # [2] 403 response body analysis (direct)
    # ------------------------------------------------------------------
    print("\n--- [2] 403 response body analysis (direct) ---")
    for label, args in [("METI index", []), ("METI press", [])]:
        url = METI_PRESS if "press" in label else METI_URL
        code, body = run_curl_body(url, args)
        print(f"  {label}: status={code}")
        if code == 403:
            waf_clues = []
            body_lower = body.lower()
            for keyword, sig in [
                ("cloudflare", "CLOUDFLARE"), ("akamai", "AKAMAI"),
                ("incapsula", "IMPerva"), ("distil", "DISTIL"),
                ("challenge", "JS_CHALLENGE"),
                ("access denied", "ACCESS_DENIED"),
                ("403 forbidden", "FORBIDDEN"),
            ]:
                if keyword in body_lower:
                    waf_clues.append(sig)
            if waf_clues:
                print(f"    WAF signatures: {', '.join(waf_clues)}")
            else:
                print(f"    No known WAF signature found")
            print(f"    Body preview: {body[:200]}")

    # If proxy available, also test 403 body through proxy
    if proxies:
        print("\n--- [2b] 403 response body analysis (WARP proxy) ---")
        for label, url in [("METI index", METI_URL), ("METI press", METI_PRESS)]:
            try:
                from curl_cffi import requests as cffi_req
                session = cffi_req.Session(impersonate="firefox135", proxies=proxies)
                resp = session.get(url, timeout=15)
                print(f"  {label}: status={resp.status_code}")
                if resp.status_code == 403:
                    body_lower = resp.text[:300].lower()
                    waf_clues = []
                    for keyword, sig in [
                        ("cloudflare", "CLOUDFLARE"), ("akamai", "AKAMAI"),
                        ("incapsula", "IMPerva"), ("distil", "DISTIL"),
                        ("challenge", "JS_CHALLENGE"),
                        ("access denied", "ACCESS_DENIED"),
                        ("403 forbidden", "FORBIDDEN"),
                    ]:
                        if keyword in body_lower:
                            waf_clues.append(sig)
                    if waf_clues:
                        print(f"    WAF signatures: {', '.join(waf_clues)}")
                    else:
                        print(f"    No known WAF signature found")
                    print(f"    Body preview: {resp.text[:200]}")
            except Exception as e:
                print(f"  {label}: ERROR {e}")

    # ------------------------------------------------------------------
    # [3] curl-cffi MATRIX: all profiles × (direct, WARP)
    # ------------------------------------------------------------------
    print("\n--- [3] curl-cffi impersonation matrix ---")
    print("  Testing all profiles with and without WARP proxy\n")

    # Direct (no proxy)
    print("  [Direct (no proxy)]")
    for profile in PROFILES:
        r = test_curl_cffi(profile, proxies=None)
        print_result(r)

    # WARP proxy
    if proxies:
        print("\n  [WARP proxy]")
        for profile in PROFILES:
            r = test_curl_cffi(profile, proxies=proxies)
            print_result(r)
    else:
        print("\n  [WARP proxy] SKIPPED — SOCKS5_PROXY not set")

    # ------------------------------------------------------------------
    # [4] requests library (direct + WARP)
    # ------------------------------------------------------------------
    print("\n--- [4] requests library ---")
    r = test_requests_lib(proxies=None)
    print_result(r)
    if proxies:
        r = test_requests_lib(proxies=proxies)
        print_result(r)

    # ------------------------------------------------------------------
    # [5] Header combination tests
    # ------------------------------------------------------------------
    print("\n--- [5] Header combinations (chrome120) ---")
    header_tests = [
        ("Accept-Language: ja", {"Accept-Language": "ja"}),
        ("Full JA headers", {
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }),
    ]
    for label, headers in header_tests:
        r = test_with_headers(METI_URL, headers, proxies=None)
        print_result(r, indent=0)
        if proxies:
            r = test_with_headers(METI_URL, headers, proxies=proxies)
            print_result(r, indent=0)

    # ------------------------------------------------------------------
    # [6] Specific pages (ENECHO, energy_environment) — quick check
    # ------------------------------------------------------------------
    print("\n--- [6] Specific pages (quick check) ---")
    # Pick top 2 profiles from each category
    quick_profiles = ["safari17_0", "firefox133", "firefox135", "safari18_0"]
    for label, url in SPECIFIC_PAGES:
        print(f"\n  {label} ({url})")
        for profile in quick_profiles:
            r = test_curl_cffi(profile, url, proxies=None)
            print_result(r)
            if proxies:
                r = test_curl_cffi(profile, url, proxies=proxies)
                print_result(r)

    # ------------------------------------------------------------------
    # [7] Summary
    # ------------------------------------------------------------------
    matrix.print_summary()

    print("\nDIAGNOSTIC COMPLETE")


if __name__ == "__main__":
    main()
