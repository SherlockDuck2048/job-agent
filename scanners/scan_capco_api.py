# -*- coding: utf-8 -*-
"""
Capco Scanner - 使用 Playwright CDP 模式
方法: 打开页面 → 拦截 API 响应 → 直接获取职位数据
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from scanners.cco_scorer import CCOSCORER, score_job

NAME = "Capco"
LOCATION = "Hong Kong"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_capco():
    print("=== Capco Scanner (CDP + API Intercept) ===")

    scorer = CCOSCORER()
    base_url = "https://www.capco.com/Careers/Job-Search"
    hk_location_id = "9f1ff0b2c4164244b0294437c3f1bd35"

    captured_jobs = []

    def handle_response(response):
        """拦截 getjobs API 响应"""
        if "api/jobs/getjobs" in response.url:
            try:
                data = response.json()
                jobs = data.get('JobPosts') or data.get('Jobs') or []
                if jobs:
                    captured_jobs.extend(jobs)
                    print(f"  [Intercepted] {len(jobs)} jobs from API")
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        page.on("response", handle_response)

        try:
            print(f"  Loading: {base_url}")
            page.goto(base_url, wait_until="networkidle", timeout=60000)
            time.sleep(2)
        except Exception as e:
            print(f"  [!] Load failed: {e}")
            _safe(page); browser.close(); return []

        # ── Step 0: 关闭 Cookie 弹窗 ────────────────────────────────────
        try:
            for sel in ["#onetrust-accept-btn-handler", "button:has-text('Accept')"]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(1)
                        print("  [OK] Accepted cookies")
                        break
                except Exception:
                    pass
        except Exception:
            pass

        # ── Step 1: 等待初始职位加载 ───────────────────────────────────
        time.sleep(3)
        if captured_jobs:
            print(f"  [OK] Initial jobs: {len(captured_jobs)}")

        # ── Step 2: 选择 Hong Kong ─────────────────────────────────────
        try:
            # 操作隐藏的 select 元素
            result = page.evaluate(f"""() => {{
                const sel = document.querySelectorAll('select')[0];
                if (!sel) return false;
                sel.value = '{hk_location_id}';
                sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                sel.dispatchEvent(new Event('input', {{bubbles: true}}));
                return true;
            }}""")

            if result:
                print("  [OK] Selected Hong Kong")
                time.sleep(5)  # 等待 API 响应
            else:
                print("  [!] Failed to select Hong Kong")

        except Exception as e:
            print(f"  [!] Location selection error: {e}")

        # ── Step 2.5: 点击 Load More 直到加载所有 Hong Kong 职位 ─────────
        max_clicks = 20  # 最多点击 20 次（约 200 个职位）
        click_count = 0

        while click_count < max_clicks:
            # 检查是否有 Load More 按钮
            load_more = None
            for sel in ["button:has-text('Load More')",
                        "button:has-text('LOAD MORE')",
                        "button:has-text('More')",
                        "[class*='load-more']"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        load_more = el
                        break
                except Exception:
                    pass

            if not load_more:
                print("  [Done] No more Load More button")
                break

            # 检查按钮是否禁用
            disabled = load_more.get_attribute("disabled")
            if disabled is not None:
                print("  [Done] Load More button disabled")
                break

            # 点击加载更多
            try:
                load_more.scroll_into_view_if_needed()
                time.sleep(0.5)
                load_more.click()
                click_count += 1
                print(f"  [Load More] Click #{click_count}, jobs so far: {len(captured_jobs)}")
                time.sleep(3)  # 等待 API 响应
            except Exception as e:
                print(f"  [!] Load More click failed: {e}")
                break

        print(f"  [OK] Loaded {len(captured_jobs)} jobs after {click_count} clicks")

        # ── Step 3: 检查拦截到的 Hong Kong 职位 ───────────────────────
        print(f"\n  [Stage 1 Done] Captured {len(captured_jobs)} jobs from API")

        # 如果没有拦截到，尝试从页面 DOM 提取
        if not captured_jobs:
            print("  [Fallback] Extracting from DOM...")
            try:
                # 等待职位卡片出现
                page.wait_for_selector("a[href*='/Careers/']", timeout=5000)

                # 提取职位链接
                job_els = page.query_selector_all("a[href*='/Careers/']")
                for el in job_els:
                    try:
                        href = el.get_attribute("href") or ""
                        title = el.inner_text().strip().split('\n')[0]  # 第一行是标题

                        if not title or len(title) < 5:
                            continue

                        # 检查是否是职位链接（包含 Job ID）
                        if not re.search(r'/\d+', href):
                            continue

                        captured_jobs.append({
                            "Title": title,
                            "Url": href if href.startswith("http") else f"https://www.capco.com{href}",
                            "Location": "Hong Kong"
                        })
                    except Exception:
                        continue

                print(f"  [DOM Extracted] {len(captured_jobs)} jobs")
            except Exception as e:
                print(f"  [!] DOM extraction failed: {e}")

        _safe(page)
        browser.close()

    # ── Step 4: 数据清洗与评分 ───────────────────────────────────────
    if not captured_jobs:
        print("  [!] No jobs captured")
        return []

    all_matched = []
    raw_jobs = []

    for job in captured_jobs:
        title = job.get('Title') or job.get('title', '')
        link = job.get('Url') or job.get('Link') or job.get('url', '')
        location = job.get('Location') or job.get('Country', '')

        if not title:
            continue

        job_data = {
            "title": title,
            "company": NAME,
            "location": location,
            "link": link,
            "keyword": "AI",
            "source": NAME,
            "scraped_at": datetime.now().isoformat()
        }
        raw_jobs.append(job_data)

        # Quick filter
        fr = scorer.quick_filter(job_data)
        if not fr["passed"]:
            continue

        print(f"  [{len(raw_jobs)}/{len(captured_jobs)}] {title[:50]}")

        # 评分
        scored = score_job(job_data)
        if scored.get("isRecommended"):
            all_matched.append(scored)
            print(f"    → P{scored.get('priority')} Score: {scored.get('score')}")
        else:
            print(f"    → P{scored.get('priority')} (skip)")

    # ── Step 5: 保存 ───────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = os.path.join(RAW_DIR, f"capco_raw_{today}.json")
    out_file = os.path.join(RAW_DIR, f"capco_{today}.json")
    os.makedirs(RAW_DIR, exist_ok=True)

    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({"source": NAME, "date": datetime.now().isoformat(),
                   "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"source": NAME, "date": datetime.now().isoformat(),
                   "total_found": len(all_matched), "jobs": all_matched}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_matched)}")

    if all_matched:
        append_scanner_to_excel(out_file)

    return all_matched


if __name__ == "__main__":
    scan_capco()
