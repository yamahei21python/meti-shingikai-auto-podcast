"""
METI 403 Diagnostic - Determine root cause on GitHub Actions.

Tests multiple approaches to identify why METI returns 403:
1. Raw curl (no impersonation)
2. curl-cffi with various impersonation profiles
3. requests library
4. Different headers / user agents
5. Check response body for WAF clues

Usage:
    python meti_403_diagnostic.py
"""

import os
import sys
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import setup_logging, logger

setup_logging()

METI_URL = "https://www.meti.go.jp/shingikai/index.html"
METI_PRESS = "https://www.meti.go.jp/press/index.html"


def run_curl(url: str, extra_args: list[str] = None) -> dict:
    """Run raw curl command."""
    cmd = ["curl", "-s", "-o", "/dev/null", "-w",
           '{"status":%{http_code},"size":%{size_download},"time":%{time_total},"ssl":%{ssl_verify_result}}',
           "-L", "--max-time", "10"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": str(e)}


def run_curl_body(url: str, extra_args: list[str] = None) -> tuple[int, str]:
    """Run curl and return (status_code, first_500_chars_of_body)."""
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "-L", "--max-time", "10"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
        if "\n" in output:
            body, code = output.rsplit("\n", 1)
            return int(code), body[:500]
        return -1, output[:500]
    except Exception as e:
        return -1, str(e)


def test_curl_cffi(profile: str) -> dict:
    """Test with curl-cffi impersonation."""
    try:
        from curl_cffi import requests
        session = requests.Session(impersonate=profile)
        resp = session.get(METI_URL, timeout=10)
        return {"profile": profile, "status": resp.status_code, "size": len(resp.content),
                "headers": dict(list(resp.headers.items())[:10])}
    except Exception as e:
        return {"profile": profile, "error": str(e)}


def test_requests_lib() -> dict:
    """Test with standard requests library."""
    try:
        import requests as req
        resp = req.get(METI_URL, timeout=10)
        return {"library": "requests", "status": resp.status_code, "size": len(resp.content)}
    except Exception as e:
        return {"library": "requests", "error": str(e)}


def test_with_headers(url: str, headers: dict) -> dict:
    """Test curl-cffi with custom headers."""
    try:
        from curl_cffi import requests
        session = requests.Session(impersonate="chrome120")
        session.headers.update(headers)
        resp = session.get(url, timeout=10)
        return {"status": resp.status_code, "size": len(resp.content)}
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 60)
    print("METI 403 DIAGNOSTIC")
    print("=" * 60)

    # 1. Raw curl tests
    print("\n--- [1] Raw curl tests ---")
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
        mark = "✅" if status == 200 else "❌"
        print(f"  {mark} {label}: status={status}, size={size}")

    # 2. Check 403 response body for WAF clues
    print("\n--- [2] 403 response body analysis ---")
    for label, args in [("METI index", []), ("METI press", [])]:
        url = METI_PRESS if "press" in label else METI_URL
        code, body = run_curl_body(url, args)
        print(f"  {label}: status={code}")
        if code == 403:
            # Check for known WAF signatures
            waf_clues = []
            body_lower = body.lower()
            if "cloudflare" in body_lower:
                waf_clues.append("CLOUDFLARE")
            if "akamai" in body_lower:
                waf_clues.append("AKAMAI")
            if "incapsula" in body_lower:
                waf_clues.append("IMPerva")
            if "distil" in body_lower:
                waf_clues.append("DISTIL")
            if "jschallenge" in body_lower or "challenge" in body_lower:
                waf_clues.append("JS_CHALLENGE")
            if "denied by" in body_lower or "access denied" in body_lower:
                waf_clues.append("ACCESS_DENIED")
            if "403 forbidden" in body_lower:
                waf_clues.append("FORBIDDEN")
            if waf_clues:
                print(f"    WAF signatures: {', '.join(waf_clues)}")
            else:
                print(f"    No known WAF signature found")
            print(f"    Body preview: {body[:200]}")

    # 3. curl-cffi impersonation tests
    print("\n--- [3] curl-cffi impersonation tests ---")
    profiles = ["chrome120", "chrome131", "safari17_0", "firefox133", "edge131"]
    for profile in profiles:
        try:
            result = test_curl_cffi(profile)
            status = result.get("status", "?")
            size = result.get("size", "?")
            mark = "✅" if status == 200 else "❌"
            err = result.get("error", "")
            print(f"  {mark} {profile}: status={status}, size={size}" + (f" ERR:{err}" if err else ""))
        except ImportError:
            print(f"  ❌ {profile}: curl_cffi not available")
            break

    # 4. requests library test
    print("\n--- [4] requests library test ---")
    result = test_requests_lib()
    status = result.get("status", "?")
    size = result.get("size", "?")
    mark = "✅" if status == 200 else "❌"
    err = result.get("error", "")
    print(f"  {mark} requests: status={status}, size={size}" + (f" ERR:{err}" if err else ""))

    # 5. Header combination tests
    print("\n--- [5] Header combination tests (curl-cffi chrome120) ---")
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
        result = test_with_headers(METI_URL, headers)
        status = result.get("status", "?")
        mark = "✅" if status == 200 else "❌"
        err = result.get("error", "")
        print(f"  {mark} {label}: status={status}" + (f" ERR:{err}" if err else ""))

    # 6. Environment info
    print("\n--- [6] Environment info ---")
    print(f"  GITHUB_ACTIONS: {os.getenv('GITHUB_ACTIONS', 'not set')}")
    print(f"  Runner OS: {os.getenv('RUNNER_OS', 'not set')}")
    print(f"  USE_PROXY: {os.getenv('USE_PROXY', 'not set')}")
    print(f"  SOCKS5_PROXY: {os.getenv('SOCKS5_PROXY', 'not set')}")

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
