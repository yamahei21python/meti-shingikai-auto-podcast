#!/usr/bin/env python3
"""Sync the VM-master NotebookLM storage_state to the GitHub Actions secret.

Uses the custom.github-cli helper (surrogate PAT; the real token is never
visible here). Encrypts the file bytes with the repo's Actions public key
(libsodium sealed box) and PUTs the secret only when the file hash changed
since the last successful sync. Prints a one-line result; never prints the
secret contents (only ciphertext is passed to the helper, as its API body).
"""
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HELPER = "/home/hatch/workspace/custom-connectors/custom.github-cli/bin/github_api.py"
OWNER, REPO, NAME = "yamahei21python", "meti-shingikai-auto-podcast", "NOTEBOOKLM_AUTH_JSON"
STATE = Path("/home/hatch/.notebooklm-kenta/profiles/default/storage_state.json")
HASH_FILE = Path("/home/hatch/nblm-vm/.secret_synced_hash")


def api(method, path, body=None):
    cmd = ["python3", HELPER, "api", method, path]
    if body is not None:
        cmd += ["--body", json.dumps(body)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"helper {method} {path} failed: {r.stderr.strip()[-300:]} {r.stdout.strip()[-300:]}")
    out = r.stdout.strip()
    return json.loads(out) if out else {}


def main():
    data = STATE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if "--force" not in sys.argv and HASH_FILE.exists() and HASH_FILE.read_text().strip() == digest:
        print(f"UNCHANGED hash={digest[:12]}")
        return 0
    pk = api("GET", f"/repos/{OWNER}/{REPO}/actions/secrets/public-key")
    from nacl.encoding import Base64Encoder
    from nacl.public import PublicKey, SealedBox

    box = SealedBox(PublicKey(pk["key"], encoder=Base64Encoder))
    encrypted = base64.b64encode(box.encrypt(data)).decode()
    api("PUT", f"/repos/{OWNER}/{REPO}/actions/secrets/{NAME}",
        {"encrypted_value": encrypted, "key_id": pk["key_id"]})
    HASH_FILE.write_text(digest)
    print(f"SYNCED hash={digest[:12]} key_id={pk['key_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
