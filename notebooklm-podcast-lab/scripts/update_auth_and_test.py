"""
Update GitHub Secrets with local NotebookLM auth, trigger the remote test workflow,
and monitor the test run until completion.
"""

import subprocess
import os
import sys
import time
from pathlib import Path

def run_command(cmd, capture=True):
    try:
        res = subprocess.run(
            cmd,
            capture_output=capture,
            text=True
        )
        return res
    except Exception as e:
        print(f"Error running command {' '.join(cmd)}: {e}")
        return None

def main():
    # 1. Locate storage_state.json
    storage_path = Path.home() / ".notebooklm" / "storage_state.json"
    if not storage_path.exists():
        print(f"[-] Error: Local storage state not found at {storage_path}")
        print("Please run 'notebooklm login' to authenticate locally first.")
        sys.exit(1)
        
    print(f"[+] Found local authentication state at {storage_path}")
    
    # 2. Check gh CLI
    gh_check = run_command(["gh", "--version"])
    if not gh_check or gh_check.returncode != 0:
        print("[-] Error: GitHub CLI ('gh') is not installed or not in PATH.")
        print("Please install gh CLI and run 'gh auth login' to authenticate.")
        sys.exit(1)
        
    # 3. Update secret
    print("[+] Updating GitHub secret 'NOTEBOOKLM_AUTH_JSON'...")
    storage_content = storage_path.read_text(encoding="utf-8")
    
    res_secret = subprocess.run(
        ["gh", "secret", "set", "NOTEBOOKLM_AUTH_JSON"],
        input=storage_content,
        capture_output=True,
        text=True
    )
    if res_secret.returncode != 0:
        print(f"[-] Failed to update GitHub secret: {res_secret.stderr}")
        sys.exit(1)
    print("[+] Successfully updated NOTEBOOKLM_AUTH_JSON secret on GitHub.")

    # 4. Trigger workflow
    print("[+] Triggering remote authentication test workflow on GitHub Actions...")
    res_run = run_command(["gh", "workflow", "run", "test_auth.yml"])
    if not res_run or res_run.returncode != 0:
        print(f"[-] Failed to trigger workflow: {res_run.stderr if res_run else 'Unknown error'}")
        sys.exit(1)
        
    print("[+] Workflow triggered successfully!")
    print("[+] Monitoring the run progress. Please wait (this may take 1-2 minutes)...")
    
    # Wait for the run to appear and show status
    time.sleep(5)
    for i in range(36):  # 36 attempts, 10s interval = 6 minutes max
        res_status = run_command(["gh", "run", "list", "--workflow=test_auth.yml", "--limit", "1", "--json", "status,conclusion,url"])
        if res_status and res_status.returncode == 0:
            try:
                import json
                runs = json.loads(res_status.stdout)
                if runs:
                    run = runs[0]
                    status = run.get("status")
                    conclusion = run.get("conclusion")
                    url = run.get("url")
                    
                    if status == "completed":
                        if conclusion == "success":
                            print(f"\n[🎉 SUCCESS] GitHub Actions authentication test passed!")
                            print(f"Run URL: {url}")
                            sys.exit(0)
                        else:
                            print(f"\n[❌ FAILED] GitHub Actions authentication test failed (Conclusion: {conclusion}).")
                            print(f"Check logs here: {url}")
                            sys.exit(1)
                    else:
                        print(f"Current status: {status}... (Checking again in 10s)")
                else:
                    print("Waiting for run to start...")
            except Exception as e:
                print(f"Error parsing status: {e}")
        time.sleep(10)
        
    print("\n[-] Monitoring timed out. You can check the run status manually at:")
    print("https://github.com/yamahei21python/meti-shingikai-auto-podcast/actions")

if __name__ == "__main__":
    main()
