"""
Accenture Scanner
URL: https://www.accenture.com/hk-en/careers/jobsearch?jk=AI
架构: 两阶段
  Stage 1: 分页抓取所有职位 (data-job-id)
  Stage 2: 批量获取 JD + 评分 (seen_jobs 去重, Plan C + Plan X)
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import score_job

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from job_scanner_base import get_jd_from_url, append_scanner_to_excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
from scan_strategies import SCAN_STRATEGIES

STRATEGY = SCAN_STRATEGIES.get("accenture", {})
NAME = STRATEGY.get("name", "Accenture")
BASE_URL = STRATEGY.get("url", "https://www.accenture.com/hk-en/careers/jobsearch?jk=AI")

KEYWORD = "AI"
LOCATION = "Hong Kong"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
OUTPUT_FILE = os.path.join(RAW_DIR, f"accenture_{datetime.now().strftime('%Y-%m-%d')}.json")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_accenture():
    print("=== Accenture Scanner ===")
    print(f"  Base URL: {BASE_URL}")

    parsed = urlparse(BASE_URL)
    params = parse_qs(parsed.query)
    base_params = {k: v[0] for k, v in params.items() if k not in ("pg", "jk", "sb")}
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def make_url(page_num):
        q_parts = []
        for k, v in {**base_params, "jk": KEYWORD, "pg": str(page_num), "sb": "0", "vw": "0", "is_rj": "0"}.items():
            q_parts.append(f"{k}={v}")
        return f"{base_path}?" + "&".join(q_parts)

    # Stage 1: 分页抓取全部职位链接
    all_entries = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("  [CDP] Connected to Chrome at 9222")
        except Exception:
            print("  [CDP] No Chrome at 9222, launching fresh browser")
            browser = p.chromium.launch(headless=True)

        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                   user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = ctx.new_page()

        page_num = 1
        prev_status_text = ""
        stable_count = 0
        MAX_PAGES = 20

        while page_num <= MAX_PAGES:
            url = make_url(page_num)
            print(f"\n  [Page {page_num}] URL: {url[:80]}...")

            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(4)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                break

            raw_cards = page.query_selector_all("[data-job-id]")
            print(f"    Cards found: {len(raw_cards)}")

            if len(raw_cards) == 0 and page_num > 1:
                print("  [Done] No cards, last page")
                break

            status_el = page.query_selector("[class*='count'], [class*='total'], [class*='results']")
            status_text = status_el.inner_text().strip() if status_el else ""
            if status_text == prev_status_text and page_num > 1:
                stable_count += 1
                if stable_count >= 2:
                    print("  [Done] Status stable - last page")
                    break
            else:
                stable_count = 0
                prev_status_text = status_text

            new_count = 0
            seen_hrefs_stage1 = {e["link"].split("?")[0] for e in all_entries}
            for card in raw_cards:
                try:
                    job_id = card.get_attribute("data-job-id") or ""
                    title = card.get_attribute("job-title") or ""
                    if not title or not job_id:
                        continue

                    href = f"https://www.accenture.com/hk-en/careers/jobdetails?id={job_id}"
                    href_key = href.split("?")[0]
                    if href_key in seen_hrefs_stage1:
                        continue

                    all_entries.append({"title": title, "link": href, "job_id": job_id})
                    seen_hrefs_stage1.add(href_key)
                    new_count += 1
                except Exception:
                    pass

            print(f"    +{new_count} new -> total: {len(all_entries)}")
            page_num += 1

        print(f"\n  [Stage 1 Done] {len(all_entries)} unique entries")

        # Stage 2: 批量获取 JD + 评分 (Plan C + Plan X)
        all_matched = []
        jd_page = ctx.new_page()

        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0

        for i, entry in enumerate(all_entries):
            title = entry["title"]
            link = entry["link"]

            # Plan X: 检查是否新岗位
            job_status = check_job_status(link, title, seen_data)
            if job_status == "unchanged":
                print(f"  [{i+1}/{len(all_entries)} SKIP] {title[:50]} -> unchanged")
                continue

            if job_status == "updated":
                print(f"  [{i+1}/{len(all_entries)} UPDATE] {title[:50]}")
                updated_jobs_count += 1
            else:
                print(f"  [{i+1}/{len(all_entries)} NEW] {title[:50]}")
                new_jobs_count += 1

            # Plan C: 获取 JD
            full_jd = get_jd_from_url(jd_page, link, platform="default")
            if full_jd:
                print(f"    [JD] {len(full_jd)} chars")
            else:
                print(f"    [JD] EMPTY - skipping detail fetch")

            # Plan X: 保存 JD 并更新索引
            entry_meta = update_job_entry(link, title, NAME, full_jd, seen_data, job_status)

            job = {
                "title": title,
                "company": NAME,
                "location": LOCATION,
                "link": link,
                "source": NAME,
                "keyword": KEYWORD,
                "description": full_jd,
                "jd_file": entry_meta.get("jd_file", ""),
                "jd_chars": entry_meta.get("jd_chars", 0),
                "scraped_at": datetime.now().isoformat(),
            }

            scored = score_job(job)
            if scored.get("isRecommended"):
                all_matched.append(scored)
                print(f"    [MATCH] P{scored.get('priority')} score={scored.get('score')}")
            elif scored.get("score", 0) >= 70:
                all_matched.append(scored)
                print(f"    [P2]    score={scored.get('score')}")

        _safe(jd_page)
        _safe(page)
        browser.close()

        save_seen_jobs(seen_data)
        print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")

    # 保存结果
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": NAME,
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(all_entries),
            "total_matched": len(all_matched),
            "jobs": all_matched,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(all_matched)} matched / {len(all_entries)} raw -> {OUTPUT_FILE}")

    # 追加到 Excel
    append_scanner_to_excel(OUTPUT_FILE)

    return all_matched


if __name__ == "__main__":
    scan_accenture()
