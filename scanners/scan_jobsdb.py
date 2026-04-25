r"""
JobsDB Scanner - M3: CDP URL
URL: https://hk.jobsdb.com/hk-en/search?keywords=AI
来源: CCO提供的验证URL (2026-04-10)
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import CCOSCORER, score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
SCROLL_COUNT = 5
WAIT_MS = 6000

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"jobsdb_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "config", f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "HK_AI_Jobs_YYYY-MM-DD.xlsx")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def get_full_jd(context, link):
    try:
        jd_page = context.new_page()
        jd_page.goto(link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        title = jd_page.title()
        print(f"    [JD] Page: {title[:60]}")
        for sel in ["[class*='description']", "article", "main", "body"]:
            el = jd_page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    print(f"    [JD] Found via: {sel} ({len(text)} chars)")
                    _safe_close(jd_page)
                    return text[:3000]
        body = jd_page.evaluate("document.body.innerText")
        _safe_close(jd_page)
        return body[:3000]
    except Exception as e:
        print(f"    [WARN] JD fetch failed: {e}")
        return ""

def scan_jobsdb():
    print("=== JobsDB Scanner ===")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            q_encoded = kw.replace(" ", "%20")
            url = f"https://hk.jobsdb.com/hk-en/search?keywords={q_encoded}"
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(WAIT_MS / 1000)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close(page)
                continue

            for _ in range(SCROLL_COUNT):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            # 抓所有 job card 元素
            job_cards = page.query_selector_all('[data-testid="job-card"], .job-card, article[data-automation="jobCard"]')
            print(f"  Found {len(job_cards)} job cards")

            for card in job_cards[:30]:
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
                        "title": title, "company": company, "location": LOCATION,
                        "link": link, "keyword": kw, "source": "JobsDB",
                        "scraped_at": datetime.now().isoformat()
                    }
                    raw_jobs.append(job)

                    fr = scorer.quick_filter(job)
                    if not fr["passed"]:
                        print(f"  [FILTER] {title[:40]} - {fr['reason']}")
                        continue
                    print(f"  [PASS] {title[:40]}")

                    full_jd = get_full_jd(context, link)
                    job["full_jd"] = full_jd

                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"  [MATCH] {title[:50]} (P{scored.get('priority')}, {scored.get('score')})")
                    else:
                        print(f"  [SKIP] {title[:50]} (score: {scored.get('score', 'N/A')})")
                except Exception as e:
                    print(f"  [ERR] {e}")

            _safe_close(page)

        browser.close()

    # Deduplicate
    seen_links = set()
    unique = []
    for j in all_jobs:
        if j.get("link") not in seen_links:
            seen_links.add(j.get("link"))
            unique.append(j)
    all_jobs = unique

    raw_file = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"jobsdb_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
    os.makedirs(os.path.dirname(raw_file), exist_ok=True)
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({"source": "JobsDB", "date": datetime.now().isoformat(), "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "JobsDB", "date": datetime.now().isoformat(), "total_found": len(all_jobs), "jobs": all_jobs}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}")
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs

if __name__ == "__main__":
    scan_jobsdb()

