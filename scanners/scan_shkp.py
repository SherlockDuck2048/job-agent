"""
SHKP Scanner - M2: CDP Single Page
URL: https://www.shkp.com/zh-HK/work-with-us/job-vacancies?jobtitle=AI
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
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"shkp_{datetime.now().strftime('%Y-%m-%d')}.json")

def scan_shkp():
    print("=== SHKP Scanner ===")
    all_jobs = []
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            q_encoded = kw.replace(" ", "%20")
            url = "https://www.shkp.com/zh-HK/work-with-us/job-vacancies?jobtitle=AI".replace("AI", q_encoded)
            print(f"  URL: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(5)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                self._safe_close_page(page)
                continue
            
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
            
            job_cards = page.query_selector_all('.job-card, .job-listing, article, [class*="job"]')
            print(f"  Found {len(job_cards)} job cards")
            
            for card in job_cards[:15]:
                try:
                    title_el = card.query_selector('h1, h2, h3, .job-title, a')
                    if not title_el:
                        continue
                    title = title_el.inner_text().strip()
                    
                    company_el = card.query_selector('.company, .employer')
                    company = company_el.inner_text().strip() if company_el else ""
                    
                    link_el = card.query_selector('a[href]')
                    link = link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.shkp.com{{link}}"
                    
                    job = {{
                        "title": title,
                        "company": company,
                        "location": LOCATION,
                        "link": link,
                        "keyword": kw,
                        "source": "SHKP",
                        "scraped_at": datetime.now().isoformat()
                    }}
                    
                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"  [MATCH] {title[:50]}... ({scored.get('priority')}, score: {scored.get('score')})")
                    
                except Exception as e:
                    continue
            
            self._safe_close_page(page)
        
        browser.close()
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({{"source": "SHKP", "date": datetime.now().isoformat(), "total_found": len(all_jobs), "jobs": all_jobs}}, f, ensure_ascii=False, indent=2)
    
    print(f"\n[COMPLETE] Saved {len(all_jobs)} jobs to {OUTPUT_FILE}")
    return all_jobs

if __name__ == "__main__":
    scan_shkp()

