
import sys
import subprocess
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import run_notebooklm

def find_audio():
    res = run_notebooklm(["list", "--json"])
    if res.returncode != 0:
        print("Failed to list notebooks")
        return
    
    import json
    try:
        data = json.loads(res.stdout)
        notebooks = data.get("notebooks", [])
        ids = [nb.get("notebook_id") for nb in notebooks if nb.get("notebook_id")]
    except Exception as e:
        print(f"Failed to parse JSON: {e}")
        return
    
    for nb_id in ids:
        print(f"Checking notebook: {nb_id}")
        res_art = run_notebooklm(["artifact", "list", "-n", nb_id])
        print(res_art.stdout)
        if "Audio" in res_art.stdout:
            print(f"!!! FOUND AUDIO IN {nb_id} !!!")

if __name__ == "__main__":
    find_audio()
