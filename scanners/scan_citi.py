r"""
Citi Scanner - M3: CDP URL (Hong Kong SAR)
URL: https://jobs.citi.com/search-jobs/AI/Hong%20Kong%20SAR/287/1/2/1819730/...
来源: CCO提供的验证URL (2026-04-10)
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, check_job_status, update_job_entry, save_seen_jobs

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
# 用户提供的真实URL（Hong Kong SAR /287）
HK_URL = "https://jobs.citi.com/search-jobs/AI/Hong%20Kong%20SAR/287/1/2/1819730/22x25/114x16667175292969/50/2"
SCROLL_COUNT = 8
WAIT_MS = 6000

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"citi_{datetime.now().strftime('%Y-%m-%d')}.json")
RAW_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"citi_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "config", f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "HK_AI_Jobs_YYYY-MM-DD.xlsx")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass



def scan_citi():
    print("=== Citi Scanner ===")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_links = set()

    # [Plan X] Load seen jobs
    seen_data = load_seen_jobs()
    new_matched = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"  URL: {HK_URL}")
        try:
            page.goto(HK_URL, wait_until="networkidle", timeout=45000)
            time.sleep(WAIT_MS / 1000)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        for _ in range(SCROLL_COUNT):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

        # 提取 job 链接（/job/地点/职位名 格式，无末尾数字）
        all_links = page.query_selector_all("a")
        job_entries = []
        for l in all_links:
            try:
                href = l.get_attribute("href") or ""
                # Citi href格式: /job/kowloon/senior-low-latency-... （无末尾数字）
                if not re.match(r"/job/[^/]+/", href):
                    continue
                full_url = f"https://jobs.citi.com{href}"
                text = l.inner_text().strip()
                if full_url not in seen_links and text and len(text) > 3:
                    seen_links.add(full_url)
                    job_entries.append({"href": full_url, "title": text})
            except Exception:
                pass

        print(f"  Found {len(job_entries)} job links")

        for job_data in job_entries[:20]:
            try:
                title = job_data["title"]
                link = job_data["href"]
                job = {
                    "title": title, "company": "Citi", "location": LOCATION,
                    "link": link, "keyword": "AI", "source": "Citi",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [FILTER] {title[:50]} - {fr['reason']}")
                    continue
                print(f"  [PASS] {title[:50]}")

                # [Plan C] Using common JD fetch function
                jd_page = new_page(context)
                jd_text = get_jd_from_url(jd_page, link, platform="default")
                job["description"] = jd_text
                jd_page.close()

                # [Plan X] Check dedup status
                status = check_job_status(link, title, seen_data)
                if status == "unchanged":
                    print(f"  [SKIP] {title[:55]} (UNCHANGED)")
                    continue

                scored = score_job(job)
                if scored.get("isRecommended"):
                    # [Plan X] Update seen_jobs
                    update_job_entry(link, title, "Citi", jd_text, seen_data, status)
                    new_matched.append(scored)
                    all_jobs.append(scored)
                    print(f"  [MATCH] {title[:55]} (P{scored.get('priority')}, {scored.get('score')}) [{status.upper()}]")
                else:
                    print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})")
            except Exception as e:
                print(f"  [ERR] {e}")

        _safe_close(page)
        browser.close()

    # [Plan X] Save seen jobs
    if new_matched:
        save_seen_jobs(seen_data)
        print(f"  [Plan X] Saved {len(new_matched)} new entries to seen_jobs.json")

    # Deduplicate
    unique = {}
    for j in all_jobs:
        link = j.get("link", "")
        if link not in unique or j.get("score", 0) > unique[link].get("score", 0):
            unique[link] = j
    final = list(unique.values())

    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "Citi", "date": datetime.now().isoformat(), "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "Citi", "date": datetime.now().isoformat(), "total_found": len(final), "jobs": final}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(final)}")
    if final:
        append_scanner_to_excel(OUTPUT_FILE)
    return final

if __name__ == "__main__":
    scan_citi()


