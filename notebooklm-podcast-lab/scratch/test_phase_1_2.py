
import sys
import os
import time
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import NetworkClient, logger, setup_logging, run_notebooklm, parse_notebook_id

setup_logging()

def run_test():
    url = "https://www.meti.go.jp/shingikai/energy_environment/doji_shijo_kento/023.html"
    client = NetworkClient(use_proxy=False)
    
    try:
        # Phase 1: Scraping & Download
        logger.info(f"=== Phase 1: Scraping & Download ===")
        logger.info(f"Fetching page: {url}")
        res = client.fetch(url)
        if not res or res.status_code != 200:
            logger.error(f"Failed to fetch page: {res.status_code if res else 'No response'}")
            return

        soup = BeautifulSoup(res.content, "html.parser")
        links = soup.find_all("a", href=True)
        pdf_urls = []
        for link in links:
            href = link.get("href")
            if href and (href.lower().endswith(".pdf")):
                pdf_urls.append(urljoin(url, href))
        
        pdf_urls = list(dict.fromkeys(pdf_urls))[:2] 
        logger.info(f"Found {len(pdf_urls)} PDFs to download.")

        temp_dir = Path("temp_pdfs_test")
        temp_dir.mkdir(exist_ok=True)
        local_pdfs = []
        for p_url in pdf_urls:
            fname = p_url.split("/")[-1]
            l_path = temp_dir / fname
            logger.info(f"Downloading {p_url}")
            res_pdf = client.fetch(p_url)
            if res_pdf and res_pdf.status_code == 200:
                with open(l_path, "wb") as f:
                    f.write(res_pdf.content)
                local_pdfs.append(str(l_path))
        
        if not local_pdfs:
            logger.error("No PDFs downloaded. Aborting.")
            return
        
        logger.info("Phase 1 Successful.")

        # Phase 2: Notebook Setup
        logger.info(f"=== Phase 2: Notebook Setup ===")
        nb_name = f"DEBUG_TEST_WORKFLOW_{time.strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Creating notebook: {nb_name}")
        res_nb = run_notebooklm(["create", nb_name])
        if res_nb.returncode != 0:
            logger.error(f"Failed to create notebook: {res_nb.stderr}")
            return
        
        notebook_id = parse_notebook_id(res_nb.stdout)
        logger.info(f"Notebook ID Created: {notebook_id}")

        for l_pdf in local_pdfs:
            logger.info(f"Adding source: {l_pdf}")
            run_notebooklm(["source", "add", l_pdf, "-n", notebook_id])

        logger.info("Waiting for sources to reach 'Ready' status...")
        # Polling for source status
        start_wait = time.time()
        while time.time() - start_wait < 300: # 5 min timeout
            time.sleep(10)
            res_list = run_notebooklm(["source", "list", "-n", notebook_id, "--json"])
            if res_list.returncode == 0:
                import json
                try:
                    data = json.loads(res_list.stdout)
                    sources = data.get("sources", [])
                    # status_id 2 means Ready
                    ready_count = sum(1 for s in sources if s.get("status_id") == 2)
                    logger.info(f"Sources ready: {ready_count}/{len(sources)}")
                    if ready_count == len(sources) and len(sources) > 0:
                        logger.info("All sources are READY.")
                        break
                except:
                    pass
        
        logger.info(f"Phase 2 Complete. Notebook ID is: {notebook_id}")
        print(f"\nFINAL_NOTEBOOK_ID={notebook_id}")

    finally:
        client.close()

if __name__ == "__main__":
    run_test()
