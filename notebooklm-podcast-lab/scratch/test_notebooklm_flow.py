
import sys
import os
import json
import time
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import NetworkClient, logger, setup_logging, run_notebooklm, parse_notebook_id, parse_task_id, wait_for_task

setup_logging()

def test_flow(notebook_id=None):
    url = "https://www.meti.go.jp/shingikai/energy_environment/doji_shijo_kento/023.html"
    client = NetworkClient(use_proxy=False)
    
    try:
        # 1. Fetch page and get PDFs (Skip if notebook_id is provided and we just want to gen/dl)
        if not notebook_id:
            logger.info(f"Fetching page: {url}")
            res = client.fetch(url)
            if not res or res.status_code != 200:
                logger.error(f"Failed to fetch page: {res.status_code if res else 'No response'}")
                return

            from bs4 import BeautifulSoup
            from urllib.parse import urljoin
            soup = BeautifulSoup(res.content, "html.parser")
            links = soup.find_all("a", href=True)
            pdf_urls = []
            for link in links:
                href = link.get("href")
                if href and (href.lower().endswith(".pdf")):
                    pdf_urls.append(urljoin(url, href))
            
            pdf_urls = list(dict.fromkeys(pdf_urls))[:2] 
            logger.info(f"Found {len(pdf_urls)} PDFs: {pdf_urls}")

            # 2. Download PDFs
            temp_dir = Path("test_temp_pdfs")
            temp_dir.mkdir(exist_ok=True)
            local_pdfs = []
            for p_url in pdf_urls:
                fname = p_url.split("/")[-1]
                l_path = temp_dir / fname
                logger.info(f"Downloading {p_url} to {l_path}")
                res_pdf = client.fetch(p_url)
                if res_pdf and res_pdf.status_code == 200:
                    with open(l_path, "wb") as f:
                        f.write(res_pdf.content)
                    local_pdfs.append(str(l_path))
            
            if not local_pdfs:
                logger.error("No PDFs downloaded")
                return

            # 3. Create Notebook
            nb_name = f"Test_Flow_{int(time.time())}"
            logger.info(f"Creating notebook: {nb_name}")
            res_nb = run_notebooklm(["create", nb_name])
            if res_nb.returncode != 0:
                logger.error(f"Failed to create notebook: {res_nb.stderr}")
                return
            
            notebook_id = parse_notebook_id(res_nb.stdout)
            logger.info(f"Notebook ID: {notebook_id}")

            # 4. Add Sources
            for l_pdf in local_pdfs:
                logger.info(f"Adding source: {l_pdf}")
                run_notebooklm(["source", "add", l_pdf, "-n", notebook_id])

            # Wait for sources
            logger.info("Waiting for sources to be ready...")
            time.sleep(30) 

        # 5. Generate Audio
        prompt = "資料の内容を日本語で解説するポッドキャストを作成してください。"
        logger.info(f"Generating audio for notebook {notebook_id}...")
        res_gen = run_notebooklm(["generate", "audio", prompt, "-n", notebook_id, "--language", "ja"])
        if res_gen.returncode != 0:
            logger.error(f"Failed to start generation: {res_gen.stderr}")
            return

        task_id = parse_task_id(res_gen.stdout)
        logger.info(f"Task ID: {task_id}")

        if not task_id:
            logger.error(f"Could not parse task ID from: {res_gen.stdout}")
            return

        # 6. Wait for Task
        success = wait_for_task(task_id, notebook_id=notebook_id, timeout_seconds=1200)
        if not success:
            logger.error("Audio generation failed or timed out")
            return

        # 7. Download Audio
        output_mp3 = "test_output.mp3"
        logger.info(f"Downloading audio to {output_mp3}")
        res_dl = run_notebooklm(["download", "audio", output_mp3, "-n", notebook_id, "--latest", "--force"])
        if res_dl.returncode == 0:
            logger.info(f"SUCCESS: Audio downloaded to {output_mp3}")
        else:
            logger.error(f"Download FAILED: {res_dl.stderr}")

    finally:
        client.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Existing Notebook ID")
    args = parser.parse_args()
    test_flow(args.id)
