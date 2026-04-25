"""
JobsDB Scanner with Stealth Mode - M2: CDP Single Page
URL: https://hk.jobsdb.com/hk-en/search?keywords=AI
Stealth args to bypass Cloudflare
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
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"jobsdb_{datetime.now().strftime('%Y-%m-%d')}.json")

STEALTH_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-web-security',
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-site-isolation-trials',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-accelerated-2d-canvas',
    '--disable-gpu',
    '--window-size=1920,1080',
    '--start-maximized',
    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def scan_jobsdb():
    print("=== JobsDB Scanner (Stealth Mode) ===")
    all_jobs = []
    
    with sync_playwright() as p:
        # Launch browser with stealth args
        browser = p.chromium.launch(
            headless=False,
            args=STEALTH_ARGS
        )
        
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Hong_Kong"
        )
        
        # Add stealth scripts
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """)
        
        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            q_encoded = kw.replace(" ", "%20")
            url = f"https://hk.jobsdb.com/hk-en/search?keywords={q_encoded}"
            print(f"  URL: {url}")
            
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(8)  # Wait for Cloudflare challenge
                
                # Check if we passed the challenge
                title = page.title()
                print(f"  Page title: {title}")
                
                if "Just a moment" in title or "Checking your browser" in title:
                    print("  ! Still on Cloudflare challenge page")
                    page.close()
                    continue
                    
            except Exception as e:
                print(f"  ! Load failed: {e}")
                page.close()
                continue
            
            # Scroll to load more
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
            
            # Try multiple selectors for job cards
            job_cards = []
            selectors = [
                '[data-testid="job-card"]',
                'article[data-automation="jobCard"]',
                '[data-automation*="job"]',
                '.job-card',
                'article'
            ]
            
            for sel in selectors:
                cards = page.query_selector_all(sel)
                if len(cards) > 0:
                    job_cards = cards
                    print(f"  Found {len(cards)} cards with: {sel}")
                    break
            
            if not job_cards:
                print("  No job cards found")
                page.close()
                continue
            
            for card in job_cards[:15]:
                try:
                    title_el = card.query_selector('h1, h2, h3, .job-title, [data-testid="job-title"]')
                    if not title_el:
                        continue
                    title = title_el.inner_text().strip()
                    
                    company_el = card.query_selector('.company, [data-testid="company-name"], .job-company')
                    company = company_el.inner_text().strip() if company_el else ""
                    
                    link_el = card.query_selector('a[href*="/job/"]')
                    link = link_el.get_attribute("href") if link_el else ""
                    if link and not link.startswith("http"):
                        link = f"https://hk.jobsdb.com{link}"
                    
                    job = {
                        "title": title,
                        "company": company,
                        "location": LOCATION,
                        "link": link,
                        "keyword": kw,
                        "source": "JobsDB",
                        "scraped_at": datetime.now().isoformat()
                    }
                    
                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"  [MATCH] {title[:50]}... ({scored.get('priority')}, score: {scored.get('score')})")
                    
                except Exception as e:
                    continue
            
            page.close()
        
        browser.close()
    
    # Save results
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "JobsDB", "date": datetime.now().isoformat(), "total_found": len(all_jobs), "jobs": all_jobs}, f, ensure_ascii=False, indent=2)
    
    print(f"\n[COMPLETE] Saved {len(all_jobs)} jobs to {OUTPUT_FILE}")
    return all_jobs

if __name__ == "__main__":
    scan_jobsdb()

