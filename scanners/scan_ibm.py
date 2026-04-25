r"""
IBM Scanner - M2: CDP Single Page + wait_for_selector
URL: https://www.ibm.com/careers/search?q=AI&field_keyword_05[0]=Hong%20Kong
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"ibm_{datetime.now().strftime('%Y-%m-%d')}.json")

def scan_ibm():
    print("=== IBM Scanner ===")
    all_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            kw_encoded = kw.replace(" ", "%20")
            url = f"https://www.ibm.com/careers/search?q={kw_encoded}&field_keyword_05[0]=Hong%20Kong"
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(8)  # Wait for SPA to render

                # Wait for job links to appear
                try:
                    page.wait_for_selector("a[href*='JobDetail']", timeout=15000)
                    print("  SPA rendered, job links visible")
                except:
                    print("  No job links found on page")

                # Scroll to load all
                for _ in range(10):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)

            except Exception as e:
                print(f"  ! Load failed: {e}")
                page.close()
                continue

            # Extract job links
            job_links = []
            seen_ids = set()
            links = page.query_selector_all("a[href*='JobDetail']")
            for l in links:
                href = l.get_attribute("href") or ""
                mid = re.search(r'[Jj]ob[Ii]d=(\d+)', href)
                if mid:
                    job_id = mid.group(1)
                    if job_id not in seen_ids:
                        seen_ids.add(job_id)
                        full_url = f"https://careers.ibm.com/careers/JobDetail?jobId={job_id}&source=WEB_Search_NA"
                        job_links.append(full_url)

            print(f"  Found {len(job_links)} unique jobs")

            for job_url in job_links[:15]:
                try:
                    job_page = context.new_page()
                    job_page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(3)

                    # Extract title
                    title_el = job_page.query_selector("h1, h2")
                    title = title_el.inner_text().strip() if title_el else "N/A"

                    # Extract location
                    loc_els = job_page.query_selector_all("[class*='location'], [class*='region'], [class*='city'], [class*='country']")
                    loc_parts = []
                    for le in loc_els:
                        try:
                            t = le.inner_text().strip()
                            if t and len(t) < 100:
                                loc_parts.append(t)
                        except:
                            pass
                    loc = " | ".join(dict.fromkeys(loc_parts)) or LOCATION

                    # Extract description
                    desc_el = job_page.query_selector("[class*='description'], [class*='detail'], article, main, [class*='content']")
                    desc = desc_el.inner_text().strip()[:2000] if desc_el else ""

                    job = {
                        "title": title,
                        "company": "IBM",
                        "location": loc,
                        "link": job_url,
                        "keyword": kw,
                        "source": "IBM",
                        "description": desc,
                        "scraped_at": datetime.now().isoformat()
                    }

                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"  [MATCH] {title[:50]}... (P{scored.get('priority', '?')}, score: {scored.get('score', 0)})")

                    job_page.close()
                except Exception as e:
                    try:
                        job_page.close()
                    except:
                        pass
                    continue

            page.close()

        browser.close()

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "IBM",
            "date": datetime.now().isoformat(),
            "total_found": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] Saved {len(all_jobs)} jobs to {OUTPUT_FILE}")
    return all_jobs

if __name__ == "__main__":
    scan_ibm()


