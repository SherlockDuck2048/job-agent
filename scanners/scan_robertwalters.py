r"""
Robert Walters Scanner - HK AI Jobs
URL: https://www.robertwalters.com.hk/jobs.html?q=AI&location=hong-kong
来源: 用户验证URL (2026-05-06)
关键发现: PerimeterX反爬，启用反检测参数硬闯

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
SCROLL_COUNT = 8
WAIT_MS = 8000
STABLE_WAIT = 5000
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "robert_walters.json")
RAW_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"robert_walters_raw_{datetime.now().strftime('%Y-%m-%d')}.json")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_robertwalters():
    print("=== Robert Walters Scanner ===")
    print("  [!] PerimeterX anti-bot protection enabled")
    print("  [Plan C] Using common JD fetch function")
    print("  [Plan X] Cross-session dedup enabled")

    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    new_matched = []

    # [Plan X] Load seen jobs
    seen_data = load_seen_jobs()

    # 反检测启动参数
    launch_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-blink-features=AutomatedHeadlessQuestionMark",
        "--exclude-switches=enable-automation",
        "--disable-infobars",
        "--disable-browser-side-navigation",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=launch_args
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Hong_Kong",
            permissions=["geolocation"],
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            }
        )

        # 移除 webdriver 属性
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        search_url = "https://www.robertwalters.com.hk/jobs.html?q=AI&location=hong-kong"
        print(f"  URL: {search_url}")

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            print(f"  Page loaded (status: {page.title()[:50]})")
            time.sleep(3)

            # 检测 PerimeterX 拦截
            page_title = page.title()
            if "PerimeterX" in page_title or "access denied" in page_title.lower() or page_title == "Access to this page has been denied":
                print("  [!] BLOCKED by PerimeterX - page shows bot detection page")
                _safe_close(page)
                browser.close()
                return []
            
            # 关闭 Cookie 弹窗
            try:
                for selector in ["#onetrust-accept-btn-handler", "#onetrust-consent-sdk .onetrust-close-btn-handler",
                                 "button[aria-label='Accept cookies']", ".cookie-accept"]:
                    btn = page.query_selector(selector)
                    if btn:
                        btn.click()
                        print(f"  [Cookie] Accepted via {selector}")
                        time.sleep(1)
                        break
            except Exception as e:
                print(f"  [Cookie] Dialog skip: {e}")

            # 滚动加载更多职位
            print(f"  [Scroll] Loading jobs...")
            last_height = 0
            scroll_stable_count = 0
            for i in range(SCROLL_COUNT):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                # 点击 Load More 按钮
                try:
                    for load_more in ["button[class*='load-more']", "a[class*='load-more']",
                                       "button[data-action='load-more']", ".load-more"]:
                        lm_btn = page.query_selector(load_more)
                        if lm_btn and lm_btn.is_visible():
                            lm_btn.click()
                            print(f"  [Load More] clicked via {load_more}")
                            time.sleep(2)
                            break
                except:
                    pass
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    scroll_stable_count += 1
                    if scroll_stable_count >= 2:
                        print(f"  [Stable] No more content after {i+1} scrolls")
                        break
                else:
                    scroll_stable_count = 0
                last_height = new_height
                print(f"  Scroll {i+1}/{SCROLL_COUNT}: height={new_height}")

        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        # 尝试多种选择器抓职位
        selectors_to_try = [
            ("a[href*='/job/']", "job-card link"),
            (".job-results-card", "job-card class"),
            ("[data-job-id]", "job-id attr"),
            (".job-card", "job-card generic"),
            ("article", "article tag"),
        ]
        
        seen_links = set()
        seen_titles = set()
        job_entries = []
        
        for sel, name in selectors_to_try:
            elements = page.query_selector_all(sel)
            if elements:
                print(f"  [Selector '{name}'] Found {len(elements)} elements")
                for el in elements:
                    try:
                        href = el.get_attribute("href") if el.get_attribute("href") else \
                               (el.query_selector("a") or el.query_selector("a[href*='/job/']")).get_attribute("href") if (el.query_selector("a") or el.query_selector("a[href*='/job/']")) else None
                        if not href:
                            continue
                        # 标准化链接
                        if href.startswith("/"):
                            link = "https://www.robertwalters.com.hk" + href
                        elif not href.startswith("http"):
                            link = "https://www.robertwalters.com.hk/" + href
                        else:
                            link = href
                        # 提取标题
                        title_el = el.query_selector(".job-title") or el.query_selector("h2") or el.query_selector("h3") or el.query_selector("a[href*='/job/']")
                        title = title_el.inner_text().strip() if title_el else el.inner_text().split("\n")[0].strip()
                        title = " ".join(title.split())[:150]
                        if not title or len(title) < 3:
                            continue
                        # 去重
                        if link in seen_links or title in seen_titles:
                            continue
                        seen_links.add(link)
                        seen_titles.add(title)
                        job_entries.append({"title": title, "link": link})
                        print(f"    [{len(job_entries)}] {title[:60]}")
                    except Exception as e:
                        continue
                if job_entries:
                    break

        print(f"\n  Found {len(job_entries)} unique job entries")

        # [Plan C] 创建独立 jd_page
        jd_page = new_page(context)

        # 获取每个职位的 JD
        for idx, job_data in enumerate(job_entries):
            try:
                title = job_data["title"]
                link = job_data["link"]
                print(f"\n  [{idx+1}/{len(job_entries)}] {title[:50]}")

                job = {
                    "title": title,
                    "company": "Robert Walters",
                    "location": LOCATION,
                    "link": link,
                    "keyword": "AI",
                    "source": "Robert Walters",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                # [Stage 1 快速过滤]
                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"    [FILTER] {fr['reason']}")
                    continue
                print(f"    [PASS filter]")

                # [Plan C] 获取 JD
                jd_text = get_jd_from_url(jd_page, link, platform='default')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars")
                else:
                    print(f"    [JD] empty/failed")

                # 完整评分
                scored = score_job(job)
                if scored.get("isRecommended"):
                    link_key = job.get("link", "")
                    status = check_job_status(link_key, title, "Robert Walters", jd_text, seen_data)
                    if status == "new":
                        update_job_entry(link_key, title, "Robert Walters", jd_text, seen_data, status)
                        new_matched.append(scored)
                    all_jobs.append(scored)
                    print(f"    [MATCH!] P{scored.get('priority')} ({scored.get('score')}分) [{status.upper()}]")
                else:
                    print(f"    [SKIP] score: {scored.get('score', 'N/A')}")

            except Exception as e:
                print(f"    [ERR] {e}")

        _safe_close(jd_page)
        _safe_close(page)
        browser.close()

    # [Plan X] 保存新职位
    if new_matched:
        save_seen_jobs(seen_data)
        print(f"\n  [Plan X] Saved {len(new_matched)} new jobs")

    # JSON 输出
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Robert Walters",
            "url": search_url,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": raw_jobs
        }, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Robert Walters",
            "url": search_url,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n=== RESULT ===")
    print(f"  RAW: {len(raw_jobs)} | MATCHED: {len(all_jobs)}")
    if all_jobs:
        print(f"  Recommended jobs:")
        for j in all_jobs:
            print(f"    - [{j.get('priority')}] {j.get('title')} ({j.get('score')}分)")
    else:
        print(f"  [!] No jobs found - likely PerimeterX blocked all requests")
        print(f"  [!] If blocked, try: Connect Chrome with --remote-debugging-port=9222 and use CDP session")

    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)

    return all_jobs


if __name__ == "__main__":
    scan_robertwalters()
