r"""
Randstad Scanner - M4: HTTP (CDP)
URL: https://www.randstad.com.hk/jobs/ (main listing with keyword search)
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"randstad_{datetime.now().strftime('%Y-%m-%d')}.json")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except:
        pass

def scan_randstad():
    print("=== Randstad Scanner ===")
    all_jobs = []
    seen_links = set()  # Global dedupe
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            url = f"https://www.randstad.com.hk/jobs/?q={kw.replace(' ', '+')}&l={LOCATION.replace(' ', '+')}"
            print(f"  URL: {url}")
            
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                time.sleep(5)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close(page)
                continue
            
            # Scroll to load more jobs
            for _ in range(8):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
            
            # Find all job links
            all_links = page.query_selector_all("a")
            job_urls = []
            
            for el in all_links:
                try:
                    href = el.get_attribute("href") or ""
                    text = el.inner_text().strip() if el.inner_text() else ""
                    # Job detail URLs: /jobs/xxx_yyy_zzzznnnnn/
                    if "/jobs/" in href and len(href.split("/")) >= 4:
                        if href.startswith("/"):
                            full_url = f"https://www.randstad.com.hk{href}"
                        else:
                            full_url = href
                        # Skip category pages (q-, s-, permanent, contract, temporary)
                        if any(x in full_url.lower() for x in ["q-", "s-", "/permanent/", "/contract/", "/temporary/"]):
                            continue
                        if text and len(text) > 3 and full_url not in seen_links:
                            seen_links.add(full_url)
                            job_urls.append((text, full_url))
                except:
                    pass
            
            print(f"  Found {len(job_urls)} unique job links")
            
            # Process first 10 jobs per keyword
            for title, job_url in job_urls[:10]:
                try:
                    job_page = context.new_page()
                    job_page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                    
                    # Get title - try multiple selectors
                    title_el = job_page.query_selector("h1") or job_page.query_selector("[class*='job-title']") or job_page.query_selector("title")
                    job_title = title_el.inner_text().strip() if title_el else title
                    # Clean up title
                    job_title = job_title.split("|")[0].split("-")[0].strip()[:100]
                    
                    # Get company - Randstad acts as agent, so company might be in the job details
                    company_el = job_page.query_selector("[class*='company'], [class*='employer'], [class*='hiring']")
                    company = company_el.inner_text().strip() if company_el else "Randstad"
                    
                    # Get location
                    loc_el = job_page.query_selector("[class*='location'], [class*='job-location'], [class*='region']")
                    job_location = loc_el.inner_text().strip() if loc_el else LOCATION
                    
                    # Get full description - try to get all text content from main job area
                    desc_el = job_page.query_selector("[class*='description'], [class*='details'], [class*='content'], article, main, .job-details, #main-content")
                    if desc_el:
                        desc = desc_el.inner_text().strip()[:3000]
                    else:
                        # Fallback: get all text
                        desc = job_page.evaluate("document.body.innerText")[:3000]
                    
                    job = {
                        "title": job_title,
                        "company": company,
                        "location": job_location,
                        "link": job_url,
                        "keyword": kw,
                        "source": "Randstad",
                        "description": desc,
                        "scraped_at": datetime.now().isoformat()
                    }
                    
                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"  [MATCH] {job_title[:50]}... (P{scored.get('priority')}, score: {scored.get('score')})")
                    
                    _safe_close(job_page)
                except Exception as e:
                    _safe_close(job_page)
                    continue
            
            _safe_close(page)
        
        browser.close()
    
    # Global dedupe by link
    unique_jobs = {}
    for j in all_jobs:
        link = j.get("link", "")
        if link and link not in unique_jobs:
            unique_jobs[link] = j
        elif link in unique_jobs:
            # Keep higher score
            if j.get("score", 0) > unique_jobs[link].get("score", 0):
                unique_jobs[link] = j
    
    final_jobs = list(unique_jobs.values())
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "Randstad", "date": datetime.now().isoformat(), "total_found": len(final_jobs), "jobs": final_jobs}, f, ensure_ascii=False, indent=2)
    
    print(f"\n[COMPLETE] Saved {len(final_jobs)} unique jobs to {OUTPUT_FILE}")
    return final_jobs

if __name__ == "__main__":
    scan_randstad()

