r"""
EY Scanner - Mokahr platform
URL: https://app.mokahr.com/social-recruitment/ey/47410#/jobs?keyword=AI&location%5B0%5D=Hongkong
来源: CCO提供的验证URL (2026-04-10)
关键发现: SPA hash路由，a[href*='/job/']选择器，JD在[class*='description']
"""
import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, check_job_status, update_job_entry, save_seen_jobs

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
BASE_URL = "https://app.mokahr.com/social-recruitment/ey/47410"
SCROLL_COUNT = 3
WAIT_MS = 6000

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"ey_{datetime.now().strftime('%Y-%m-%d')}.json")
RAW_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"ey_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "config", f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass

def get_full_jd(page, job_href):
    """Mokahr SPA: 点击job链接，URL变为#/job/UUID，JD渲染在同一页面"""
    try:
        jd_url = BASE_URL + job_href
        jd_page = page._impl_obj._channel
        # 在当前page直接goto hash URL（SPAs支持）
        page.goto(jd_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        print(f"    [JD] URL: {page.url[:80]}")
        # 找JD内容
        for sel in ["[class*='description']", "[class*='detail']", ".jd-content", ".job-detail"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    print(f"    [JD] Found via {sel}: {len(text)} chars")
                    return text[:3000]
        body = page.inner_text("body")
        print(f"    [JD] Fallback body: {len(body)} chars")
        return body[:3000]
    except Exception as e:
        print(f"    [WARN] JD fetch failed: {e}")
        return ""


def scan_ey():
    print("=== ey Scanner ===")
    print("  [Plan C] Using common JD fetch function")
    print("  [Plan X] Cross-session dedup enabled")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    
    # [Plan X] Load seen jobs
    seen_data = load_seen_jobs()
    new_matched = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        search_url = f"{BASE_URL}#/jobs?keyword=AI&location%5B0%5D=Hongkong&page=1"
        print(f"  URL: {search_url}")

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(WAIT_MS / 1000)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        for _ in range(SCROLL_COUNT):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

        # 提取所有 job 链接
        seen = set()
        job_entries = []
        for a in page.query_selector_all("a[href*='/job/']"):
            try:
                href = a.get_attribute("href")
                text = a.inner_text().strip()
                # 过滤分割线/空行
                title = " ".join(text.split())[:100]
                if not title or title in seen or len(title) < 5:
                    continue
                seen.add(title)
                # 标准化链接
                full_link = BASE_URL + href if href.startswith("#") else href
                job_entries.append({"title": title, "link": full_link})
                print(f"  [{len(job_entries)}] {title[:60]}")
            except Exception as e:
                print(f"  [WARN] link error: {e}")

        print(f"\n  Found {len(job_entries)} job entries")

        # 获取每个职位的 JD（SPAs: 点击后URL变为#/job/UUID）
        for job_data in job_entries:
            try:
                title = job_data["title"]
                link = job_data["link"]

                job = {
                    "title": title, "company": "ey", "location": LOCATION,
                    "link": link, "keyword": "AI", "source": "EY",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [FILTER] {title[:40]} - {fr['reason']}")
                    continue
                print(f"  [PASS] {title[:40]}")

                # [Plan C] Get JD using common function
                jd_page = new_page(context)
                jd_text = get_jd_from_url(jd_page, link, platform='mokahr')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars")
                _safe_close(jd_page)

                scored = score_job(job)
                if scored.get("isRecommended"):
                    # [Plan X] Check if new/updated
                    link_key = job.get("link", "")
                    status = check_job_status(link_key, title, seen_data)
                    if status == "new":
                        update_job_entry(link_key, title, "EY", jd_text, seen_data, status)
                        new_matched.append(scored)
                    all_jobs.append(scored)
                    print(f"  [MATCH] {title[:55]} (P{scored.get('priority')}, {scored.get('score')}) [{status.upper()}]")
                else:
                    print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})")

            except Exception as e:
                print(f"  [ERR] {title[:40]}: {e}")

        _safe_close(page)
        browser.close()

    # [Plan X] Save seen jobs
    if new_matched:
        save_seen_jobs(seen_data)
        print(f"  [Plan X] Saved {len(new_matched)} new jobs to seen_jobs.json")
    
    # 去重
    seen_links = set()
    unique = []
    for j in all_jobs:
        if j.get("link") not in seen_links:
            seen_links.add(j.get("link"))
            unique.append(j)
    all_jobs = unique

    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "EY", "date": datetime.now().isoformat(), "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "EY", "date": datetime.now().isoformat(), "total_found": len(all_jobs), "jobs": all_jobs}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}")
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs

if __name__ == "__main__":
    scan_ey()


