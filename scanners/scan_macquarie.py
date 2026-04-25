"""
Macquarie Scanner
URL: from scan_strategies.py
特点：自研招聘系统，分页为数字页码 1,2,3...
架构: 两阶段
  Stage 1: 分页抓取所有职位链接（不离开列表页）
  Stage 2: 批量获取 JD 并评分（独立 page）+ Plan C/X
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import get_jd_from_url, append_scanner_to_excel  # Plan C + Excel 追加
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X
from cco_scorer import CCOSCORER, score_job

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
from scan_strategies import SCAN_STRATEGIES

STRATEGY = SCAN_STRATEGIES.get("macquarie", {})
# 不用关键词搜（Macquarie AI搜0结果），改为HK全量抓取后quick_filter筛选
BASE_URL = "https://recruitment.macquarie.com/en_US/careers/SearchJobs?10671=%5B871432%5D&10671_format=21337&listFilterMode=1&jobRecordsPerPage=25&"

NAME = "Macquarie"
KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_macquarie():
    print("=== Macquarie Scanner ===")
    scorer = CCOSCORER()

    # ── Stage 1: 分页抓取全部职位链接 ────────────────────────────
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("  [CDP] Connected to Chrome at 9222")
        except Exception:
            print("  [CDP] No Chrome at 9222, launching fresh browser")
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-dev-shm-usage",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            ])

        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"  [Stage 1] URL: {BASE_URL}")
        try:
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            time.sleep(3)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe(page)
            browser.close()
            return []

        # Accept cookies弹窗
        try:
            accept_btn = page.query_selector('button:has-text("Accept all cookies")')
            if accept_btn:
                accept_btn.click()
                time.sleep(2)
                print("  [Cookie] Accepted")
        except Exception:
            pass

        # ── 翻页翻到底 ──────────────────────────────────────────
        all_entries = []
        seen_hrefs = set()
        page_num = 1
        max_pages = 60

        while page_num <= max_pages:
            print(f"    Page {page_num}")
            time.sleep(3)

            items = page.query_selector_all('article a[href*="JobDetail"]')
            # 每个article内含一个JobDetail链接，用链接数量判断
            # 先找到所有含JobDetail链接的article
            all_articles = page.query_selector_all('article')
            items = []
            for art in all_articles:
                link_el = art.query_selector('a[href*="JobDetail"]')
                if link_el:
                    items.append(art)
            print(f"      Found {len(items)} job items (with JobDetail link)")

            for item in items:
                try:
                    text = item.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if not lines or len(lines) < 3:
                        continue

                    title = lines[0]
                    if len(title) > 200 or len(title) < 5:
                        continue

                    # URL已按HK过滤（10671=871432），所有职位都是HK
                    # 无需再按location过滤
                    # 保留location字段用于记录
                    location = ""
                    for line in lines:
                        if "Office" in line or "Hong Kong" in line:
                            location = line
                            break
                    if not location:
                        location = "Hong Kong"

                    # 找链接
                    link_el = item.query_selector('a[href*="JobDetail"]')
                    if not link_el:
                        link_el = item.query_selector('a[href*="/careers/"]')
                    link = link_el.get_attribute("href") if link_el else ""
                    # 上面已确认每个item都有JobDetail链接，这里不该走到fallback
                    if link and not link.startswith("http"):
                        link = f"https://recruitment.macquarie.com{link}"
                    if not link:
                        continue

                    # href去重：保留jobId参数，否则所有链接变成同一个key
                    href_key = link.rstrip("/")
                    if href_key in seen_hrefs:
                        continue
                    seen_hrefs.add(href_key)

                    all_entries.append({
                        "title": title,
                        "link": link,
                        "location": location,
                    })
                except Exception:
                    continue

            # 找下一页
            has_next = False
            try:
                next_page = page_num + 1
                next_link = page.query_selector(f'a.list-controls__pagination__item:has-text("{next_page}")')
                if next_link and next_link.is_enabled():
                    next_link.click()
                    time.sleep(4)
                    page_num += 1
                    has_next = True
                else:
                    next_btn = page.query_selector('a[rel="next"], a:has-text("Next"), [class*="pagination"][class*="next"]')
                    if next_btn and next_btn.is_enabled():
                        next_btn.click()
                        time.sleep(4)
                        page_num += 1
                        has_next = True
            except Exception as e:
                print(f"      ! Pagination error: {e}")

            if not has_next:
                print(f"      -> No more pages")
                break

        print(f"  [Stage 1 Done] {len(all_entries)} unique entries collected")
        _safe(page)

        # ── Stage 2: 批量获取 JD + 评分 ─────────────────────────
        all_matched = []
        raw_jobs = []
        jd_page = context.new_page()

        # Plan X: 加载去重索引
        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0

        try:
            for i, entry in enumerate(all_entries):
                title = entry["title"]
                link = entry["link"]
                job = {
                    "title": title,
                    "company": NAME,
                    "location": entry.get("location", LOCATION),
                    "link": link,
                    "keyword": KEYWORDS[0],
                    "source": NAME,
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                # Plan X: 检查是否新岗位
                job_status = check_job_status(link, title, seen_data)
                if job_status == "unchanged":
                    existing = seen_data.get("jobs", {}).get(link, {})
                    print(f"  [{i+1}/{len(all_entries)} SKIP] {title[:50]} -> unchanged (seen {existing.get('first_seen', '?')})")
                    continue

                if job_status == "updated":
                    print(f"  [{i+1}/{len(all_entries)} UPDATE] {title[:50]} -> title changed")
                    updated_jobs_count += 1
                else:
                    print(f"  [{i+1}/{len(all_entries)} NEW] {title[:50]}")
                    new_jobs_count += 1

                # quick_filter 先过滤
                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"       FILTER -> {fr['reason']}")
                    update_job_entry(link, title, NAME, "", seen_data, job_status)
                    continue
                print(f"       PASS -> quick_filter passed")

                # Plan C: 获取 JD
                full_jd = get_jd_from_url(jd_page, link, platform='default')
                job["description"] = full_jd
                if full_jd:
                    print(f"       [JD] {len(full_jd)} chars")

                # Plan X: 保存 JD 文件并更新索引
                entry_x = update_job_entry(link, title, NAME, full_jd, seen_data, job_status)
                job["jd_file"] = entry_x.get("jd_file", "")
                job["jd_chars"] = entry_x.get("jd_chars", 0)

                scored = score_job(job)
                if scored.get("isRecommended") or scored.get("score", 0) >= 70:
                    all_matched.append(scored)
                    p_tag = scored.get("priority", "?")
                    s = scored.get("score", 0)
                    tag = "MATCH" if scored.get("isRecommended") else "P2"
                    print(f"  [{tag}] {title[:55]} → P{p_tag}/{s}")
                else:
                    print(f"  [SKIP] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            _safe(jd_page)
            browser.close()
            # Plan X: 保存去重索引
            save_seen_jobs(seen_data)
            print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")

    # ── 保存 ────────────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = os.path.join(RAW_DIR, f"macquarie_{today}.json")
    os.makedirs(RAW_DIR, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "source": NAME,
            "date": datetime.now().isoformat(),
            "total_found": len(all_matched),
            "raw_count": len(all_entries),
            "jobs": all_matched
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(all_matched)} matched / {len(all_entries)} raw")

    # 追加到 Excel
    append_scanner_to_excel(out_file)

    return all_matched


if __name__ == "__main__":
    scan_macquarie()
