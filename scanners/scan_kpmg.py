r"""
KPMG Scanner - Mokahr platform
URL: https://app.mokahr.com/social-recruitment/kpmg/74216#/jobs?keyword=AI&location%5B0%5D=Hongkong
来源: CCO提供的验证URL (2026-04-10)
关键发现: SPA hash路由，a[href*='/job/']选择器，JD在[class*='description']

[Plan C] Integrated: Using common JD fetch function
[Plan X] Integrated: Unified field name to description
"""
import sys, os, json, time, io
from datetime import datetime
from playwright.sync_api import sync_playwright

# Windows 控制台 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, check_job_status, update_job_entry, save_seen_jobs

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
BASE_URL = "https://app.mokahr.com/social-recruitment/kpmg/74216"
SCROLL_COUNT = 3
WAIT_MS = 6000

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"kpmg_{datetime.now().strftime('%Y-%m-%d')}.json")
RAW_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"kpmg_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "config", f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_kpmg():
    print("=== KPMG Scanner ===")
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

        # 提取筛选结果区域的 job 链接（排除 Hot 推荐）
        seen = set()
        job_entries = []
        for a in page.query_selector_all("a[href*='/job/']"):
            try:
                href = a.get_attribute("href")
                text = a.inner_text().strip()
                # 过滤 Hot 推荐职位
                if text.startswith("Hot") or "Hot" in text.split("\n")[0]:
                    print(f"  [SKIP HOT] {text[:50]}")
                    continue
                # 检查 grandparent class 是否为 jobs-*
                gp_class = a.evaluate("el => el.parentElement?.parentElement?.className || ''")
                if not gp_class.startswith("jobs-"):
                    print(f"  [SKIP NON-FILTER] {text[:50]}")
                    continue
                # 标准化标题
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

        # [Plan C] 创建独立 jd_page
        jd_page = new_page(context)
        
        # 获取每个职位的 JD
        for job_data in job_entries:
            try:
                title = job_data["title"]
                link = job_data["link"]

                job = {
                    "title": title, "company": "KPMG", "location": LOCATION,
                    "link": link, "keyword": "AI", "source": "KPMG",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [FILTER] {title[:40]} - {fr['reason']}")
                    continue
                print(f"  [PASS] {title[:40]}")

                # [Plan C] 使用公共函数获取 JD
                jd_text = get_jd_from_url(jd_page, link, platform='mokahr')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars")

                scored = score_job(job)
                if scored.get("isRecommended"):
                    # [Plan X] Check if new/updated
                    link_key = job.get("link", "")
                    status = check_job_status(link_key, title, seen_data)
                    if status == "new":
                        update_job_entry(link_key, title, "KPMG", jd_text, seen_data, status)
                        new_matched.append(scored)
                    all_jobs.append(scored)
                    print(f"  [MATCH] {title[:55]} (P{scored.get('priority')}, {scored.get('score')}) [{status.upper()}]")
                else:
                    print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})")

            except Exception as e:
                print(f"  [ERR] {title[:40]}: {e}")

        _safe_close(jd_page)
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
        json.dump({"source": "KPMG", "date": datetime.now().isoformat(), "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "KPMG", "date": datetime.now().isoformat(), "total_found": len(all_jobs), "jobs": all_jobs}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}")
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs

if __name__ == "__main__":
    scan_kpmg()

