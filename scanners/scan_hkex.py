# -*- coding: utf-8 -*-
"""
HKEX Scanner - Workday平台 + 分页
URL: https://hkex.wd3.myworkdayjobs.com/zh-CN/HKEXCareerPage?q=AI

[Plan C] 使用 job_scanner_base.get_jd_from_url() 统一 JD 抓取
[Plan X] 使用 seen_jobs 做跨会话去重
[append] 每次运行都调用 append_scanner_to_excel
"""
import sys, os, json, time, io
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel  # Plan C + Excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X

HKEX_URL = SCAN_STRATEGIES["hkex"]["base_url"]
KEYWORDS = ["AI"]
LOCATION = "Hong Kong"

TODAY = datetime.now().strftime("%Y-%m-%d")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
RAW_FILE = os.path.join(RAW_DIR, f"hkex_raw_{TODAY}.json")
OUT_FILE = os.path.join(RAW_DIR, f"hkex_{TODAY}.json")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _get_job_links_from_page(page):
    links = page.query_selector_all('a[href*="/job/"]')
    seen = set()
    jobs = []
    for link in links:
        href = link.get_attribute("href") or ""
        title = link.inner_text().strip()
        if not href or not title or len(title) < 3:
            continue
        key = href.split('?')[0]
        if key not in seen:
            seen.add(key)
            full_url = f"https://hkex.wd3.myworkdayjobs.com{href}" if href.startswith("/") else href
            jobs.append({"title": title, "href": full_url})
    return jobs


def scan_hkex():
    print("=== HKEX Scanner (Workday + Pagination) ===")
    print("  [Plan C] get_jd_from_url | [Plan X] seen_jobs dedup | [append] Excel")
    scorer = CCOSCORER()
    seen_data = load_seen_jobs()
    all_matched = []
    raw_jobs = []
    seen_links = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        url = HKEX_URL
        print(f"  [Stage 1] Loading: {url}")

        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(6)

        for _ in range(10):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

        # ---- Page 1 ----
        page1_jobs = _get_job_links_from_page(page)
        print(f"  [Page 1] {len(page1_jobs)} jobs")

        # ---- 分页抓取 ----
        all_page_jobs = list(page1_jobs)
        page_num = 2
        max_pages = 10

        while page_num <= max_pages:
            next_btn = page.query_selector(f'button[aria-label="page {page_num}"]')
            if not next_btn:
                next_btn = page.query_selector('button[aria-label="next"]')

            if not next_btn:
                print(f"  [Done] No page {page_num} button found"); break

            try:
                visible = next_btn.is_visible()
            except Exception:
                visible = False

            if not visible:
                print(f"  [Done] Page {page_num} button not visible"); break

            print(f"  [->] Clicking page {page_num}")
            next_btn.scroll_into_view_if_needed()
            time.sleep(1)
            next_btn.click()
            time.sleep(6)

            for _ in range(8):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

            jobs = _get_job_links_from_page(page)
            new_count = len([j for j in jobs if j["href"] not in seen_links])
            print(f"  [Page {page_num}] {len(jobs)} jobs ({new_count} new)")
            all_page_jobs.extend(jobs)
            page_num += 1

        print(f"\n  [Stage 1 Done] {len(all_page_jobs)} unique entries")
        _safe_close(page)

        # ---- Stage 2: Plan C JD Fetch + Plan X Dedup ----
        jd_page = new_page(context)

        try:
            for i, job_data in enumerate(all_page_jobs):
                href = job_data["href"]
                title = job_data["title"]

                if href in seen_links:
                    continue

                job = {
                    "title": title, "company": "HKEX", "location": LOCATION,
                    "link": href, "keyword": KEYWORDS[0], "source": "HKEX",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                status = check_job_status(href, title, seen_data)
                if status == "unchanged":
                    prev_entry = seen_data.get("jobs", {}).get(href, {})
                    prev_score = prev_entry.get("score", "?")
                    print(f"  [{i+1}/{len(all_page_jobs)} SKIP] {title[:45]} -> unchanged (score {prev_score})")
                    continue
                elif status == "updated":
                    print(f"  [{i+1}/{len(all_page_jobs)} UPDATE] {title[:45]} -> JD changed (re-scoring)")
                else:
                    print(f"  [{i+1}/{len(all_page_jobs)} NEW] {title[:45]}")

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    update_job_entry(href, title, "HKEX", "", seen_data, status)
                    print(f"  [{i+1}/{len(all_page_jobs)} FILTER] {title[:45]} - {fr['reason']}")
                    continue
                print(f"  [{i+1}/{len(all_page_jobs)} PASS] {title[:55]}")

                # [Plan C] 统一 JD 抓取
                jd_text = get_jd_from_url(jd_page, href, platform='workday')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars")

                scored = score_job(job)
                update_job_entry(href, title, "HKEX", jd_text or "", seen_data, status)
                if scored.get("isRecommended"):
                    all_matched.append(scored)
                    print(f"  [MATCH!] {title[:55]} -> P{scored.get('priority')} {scored.get('score')}")
                else:
                    print(f"  [SKIP ] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            _safe_close(jd_page)
            browser.close()

    save_seen_jobs(seen_data)

    # ---- 保存 ----
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "HKEX", "date": datetime.now().isoformat(),
                   "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)

    # 去重
    seen_links2 = set()
    unique = [j for j in all_matched
              if j.get("link") not in seen_links2 and not seen_links2.add(j.get("link"))]
    all_matched = unique

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "HKEX", "date": datetime.now().isoformat(),
                   "total_found": len(all_matched), "jobs": all_matched}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_matched)}")
    append_scanner_to_excel(OUT_FILE)
    return all_matched


if __name__ == "__main__":
    scan_hkex()
