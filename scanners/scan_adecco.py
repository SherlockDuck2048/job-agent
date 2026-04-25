r"""
Adecco Scanner - M4: CDP URL (Keyword param)
URL: https://www.adecco.com/en-hk/jobs/?keyword={keyword}&location=Hong+Kong
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
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"adecco_{datetime.now().strftime('%Y-%m-%d')}.json")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except:
        pass

def scan_adecco():
    print("=== Adecco Scanner ===")
    all_jobs = []
    seen_links = set()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            url = f"https://www.adecco.com/en-hk/jobs/?keyword={kw.replace(' ', '+')}&location=Hong+Kong"
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                time.sleep(4)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close(page)
                continue

            for _ in range(5):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            # Get all links, filter only job detail pages
            all_links = page.query_selector_all("a")
            job_detail_links = []
            for l in all_links:
                try:
                    href = l.get_attribute("href") or ""
                    # Job detail URLs: /en-hk/jobs/34k-tier-3-support-ba-project-engineer... (no query params, >30 chars)
                    if "/en-hk/jobs/" in href and "?" not in href and len(href) > 30:
                        full_url = href if href.startswith("http") else f"https://www.adecco.com{href}"
                        if full_url not in seen_links:
                            seen_links.add(full_url)
                            job_detail_links.append(full_url)
                except:
                    pass

            print(f"  Found {len(job_detail_links)} unique job links")

            for job_url in job_detail_links[:15]:
                try:
                    job_page = context.new_page()
                    job_page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)

                    # Get title
                    title_el = (job_page.query_selector("h1") or
                                job_page.query_selector("[class*='job-title']") or
                                job_page.query_selector("title"))
                    job_title = (title_el.inner_text().strip().split("|")[0].split("-")[0].strip()
                                  if title_el else "N/A")[:100]

                    # Get company
                    company_el = job_page.query_selector("[class*='company'], [class*='employer'], [class*='hiring-company']")
                    company = company_el.inner_text().strip() if company_el else "Adecco HK"

                    # Get location
                    loc_el = job_page.query_selector("[class*='location'], [class*='region']")
                    job_loc = loc_el.inner_text().strip() if loc_el else LOCATION

                    # Get description
                    desc_el = (job_page.query_selector("[class*='description']") or
                               job_page.query_selector("[class*='details']") or
                               job_page.query_selector("article") or
                               job_page.query_selector("main") or
                               job_page.query_selector("body"))
                    desc = desc_el.inner_text().strip()[:3000] if desc_el else ""

                    job = {
                        "title": job_title,
                        "company": company,
                        "location": job_loc,
                        "link": job_url,
                        "keyword": kw,
                        "source": "Adecco",
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

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Adecco",
            "date": datetime.now().isoformat(),
            "total_found": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] Saved {len(all_jobs)} jobs to {OUTPUT_FILE}")
    return all_jobs

if __name__ == "__main__":
    scan_adecco()

