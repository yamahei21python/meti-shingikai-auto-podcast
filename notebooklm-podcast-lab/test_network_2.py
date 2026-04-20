
import sys
import os
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent))

from shared import NetworkClient, setup_logging, logger
from generate_podcast_from_article import fetch_article_page, extract_pdf_urls, download_pdf_locally

setup_logging()

def test_full_fetch():
    url = "https://www.meti.go.jp/shingikai/energy_environment/sogo_energy/2025_001.html"
    client = NetworkClient(use_proxy=False) # ローカルではプロキシなしで試行
    
    print(f"\n--- Testing Page Fetch: {url} ---")
    soup = fetch_article_page(client, url)
    if not soup:
        print("FAILED: Could not fetch article page (403 or other)")
        return
    
    print("SUCCESS: Article page fetched.")
    
    pdf_urls = extract_pdf_urls(url, soup)
    print(f"Found {len(pdf_urls)} PDF links.")
    
    if pdf_urls:
        temp_dir = Path("test_temp_pdfs")
        temp_dir.mkdir(exist_ok=True)
        
        # Test downloading the first PDF
        first_pdf = pdf_urls[0]
        local_path = download_pdf_locally(client, first_pdf, temp_dir)
        
        if local_path and local_path.exists():
            print(f"SUCCESS: PDF downloaded to {local_path}")
            # cleanup
            local_path.unlink()
            temp_dir.rmdir()
        else:
            print("FAILED: PDF download failed.")
    
    client.close()

if __name__ == "__main__":
    test_full_fetch()
