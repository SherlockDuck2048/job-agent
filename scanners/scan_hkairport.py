"""
HK Airport Scanner - 港机场管理局
URL: https://careers.hkairport.com/careersection/ex/jobsearch.ftl
配置来源: scan_strategies.py["hkairport"]

网站结构（2026-04-19 验证）:
- 表格渲染，共 9 个职位，1 页（无分页）
- 状态文字: "Job Openings X - Y of Z" (heading[@class='searchresultStatus'])
- 职位链接: /careersection/ex/jobdetail.ftl?job=XXX
- 搜索"AI"关键词无效果，改用 IT Function checkbox 过滤
"""
import sys, os, io, json, contextlib, re, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import CCOSCORER, score_job

# ── 从 scan_strategies.py 读取配置 ────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_strat_src = open(os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py"), encoding="utf-8").read()
_globals = {}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strat_src, "scan_strategies.py", "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("hkairport", {})
BASE_URL = _strategy.get(
    "url",
    "https://careers.hkairport.com/careersection/ex/jobsearch.ftl"
)
SELECTORS = _strategy.get("selectors", {})

# 基础配置
KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
SCRIPT_DIR_ABS = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(SCRIPT_DIR_ABS, "..", "candidates", "raw", f"hkairport_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR_ABS, "..", "candidates", "raw", f"hkairport_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT = os.path.join(SCRIPT_DIR_ABS, "..", "config", f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")

MAX_PAGES = 50


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _wait_table_stable(page, timeout=15):
    """等表格行数稳定（防止 SPA 异步渲染抖动）"""
    last_count = 0
    stable = 0
    for _ in range(timeout):
        time.sleep(1)
        rows = page.query_selector_all("table#jobs tbody tr")
        count = len(rows)
        if count == last_count and count > 0:
            stable += 1
            if stable >= 2:
                return True
        else:
            stable = 0
        last_count = count
    return True



def scan_hkairport():
    print("=== HK Airport Scanner ===")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_links = set()
    seen_titles = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"  URL: {BASE_URL}")

        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        # 等待表格稳定
        _wait_table_stable(page)

        # ── 尝试搜索关键词（对 HK Airport 无效果，保留逻辑备用）───────────
        try:
            page.fill("input[name='keyword']", "AI", timeout=5000)
            page.click("button:has-text('Search')", timeout=5000)
            time.sleep(3)
        except Exception:
            pass  # 搜索不生效就用全量

        _wait_table_stable(page)

        # ── 分页：状态文字稳定检测 ─────────────────────────────────────
        prev_status = ""
        stable_count = 0

        for page_num in range(1, MAX_PAGES + 1):
            print(f"\n  Page {page_num}...", end="", flush=True)

            # 收集表格行（实际结构: table#jobs tbody tr，不是 role=grid）
            rows = page.query_selector_all("table#jobs tbody tr")
            print(f" {len(rows)} rows", flush=True)

            # 状态文字
            status_el = page.query_selector("heading.searchresultStatus, [class*='resultCount'], "
                                            "table[role='grid']")
            body_text = page.inner_text("body")
            m = re.search(r'[Jj]ob\s+[Oo]penings\s+(\d+)\s*[-–]\s*(\d+)\s*[Oo]f\s+(\d+)', body_text)
            if m:
                current_status = f"Job Openings {m.group(1)}-{m.group(2)} of {m.group(3)}"
            else:
                current_status = body_text[:150]

            page_new = 0
            for row in rows:
                try:
                    title_a = row.query_selector("a[href*='/jobdetail.ftl']")
                    if not title_a:
                        continue
                    raw_href = title_a.get_attribute("href") or ""
                    title = title_a.inner_text().strip()

                    if not title or len(title) < 3:
                        continue

                    # 完整 URL
                    if raw_href.startswith("/"):
                        link = "https://careers.hkairport.com" + raw_href
                    elif raw_href.startswith("http"):
                        link = raw_href
                    else:
                        continue

                    # ── href 去重：保留 job ID（去掉 tz 时区参数）──────────
                    if raw_href.startswith("/"):
                        link = "https://careers.hkairport.com" + raw_href
                    elif raw_href.startswith("http"):
                        link = raw_href
                    else:
                        continue

                    # 只去掉 tz= 时区参数，保留 job=ID 作为去重键
                    import urllib.parse as urlparse
                    parsed = urlparse.urlparse(link)
                    clean_qs = "&".join(
                        p for p in parsed.query.split("&")
                        if not p.startswith("tz=") and not p.startswith("tzname=")
                    )
                    link_key = parsed.path + ("?" + clean_qs if clean_qs else "")
                    if link_key in seen_links:
                        continue
                    seen_links.add(link_key)
                    page_new += 1

                    job = {
                        "title": title,
                        "company": "HK Airport",
                        "location": LOCATION,
                        "link": link,
                        "keyword": "AI",
                        "source": "HK Airport",
                        "scraped_at": datetime.now().isoformat()
                    }
                    raw_jobs.append(job)

                    # ── 评分（参考 scan_kpmg.py 两阶段）──────────────
                    fr = scorer.quick_filter(job)
                    if not fr["passed"]:
                        print(f"    [FILTER] {title[:40]} - {fr['reason']}")
                        continue
                    print(f"    [PASS] {title[:55]}")

                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"    [MATCH] {title[:55]} (P{scored.get('priority')}, {scored.get('score')})")
                    else:
                        print(f"    [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})")

                except Exception as e:
                    continue

            print(f"    new={page_new}, href_dedup={len(seen_links)}, title_dedup={len(seen_titles)}")

            # 状态稳定检测
            if current_status == prev_status and page_new == 0:
                stable_count += 1
            else:
                stable_count = 0
            prev_status = current_status

            safe_status = current_status[:80].encode("ascii", "replace").decode("ascii")
            print(f"    Status: {safe_status} (stable={stable_count})")
            if stable_count >= 2:
                print("    [Stop] Status stable x2 - no more pages")
                break

            # ── 翻页 ────────────────────────────────────────────────
            if page_num >= MAX_PAGES:
                print("    [Stop] Max pages reached")
                break

            # 找 Next 按钮
            next_btn = None
            for sel in [
                "a[aria-label*='next']",
                "a:has-text('Next')",
                "a:has-text('next')",
                "a[class*='next']",
                "button[class*='next']",
                "a[class*='pager']:not([class*='prev'])",
            ]:
                candidates = page.query_selector_all(sel)
                for b in candidates:
                    t = b.inner_text().strip().lower()
                    if t and ("next" in t or ">" in t) and "previous" not in t:
                        next_btn = b
                        break
                if next_btn:
                    break

            if not next_btn:
                print("    [Stop] No next button found")
                break

            disabled = next_btn.get_attribute("disabled")
            aria_disabled = next_btn.get_attribute("aria-disabled")
            if disabled is not None or (aria_disabled and "true" in aria_disabled.lower()):
                print("    [Stop] Next button disabled / at last page")
                break

            try:
                next_href = next_btn.get_attribute("href")
                if next_href and next_href not in ("#", "javascript:void(0);"):
                    next_url = (next_href if next_href.startswith("http")
                                else "https://careers.hkairport.com" + next_href)
                    _safe_close(page)
                    page = context.new_page()
                    page.goto(next_url, wait_until="domcontentloaded", timeout=45000)
                    time.sleep(3)
                else:
                    next_btn.scroll_into_view_if_needed()
                    next_btn.click()
                    time.sleep(3)
                _wait_table_stable(page)
            except Exception as e:
                print(f"    [Stop] Next click failed: {str(e)[:60]}")
                break

        _safe_close(page)
        browser.close()

    # ── 保存 JSON ─────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "HK Airport",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "HK Airport",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}")
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
    print(f"[COMPLETE] Results: {RAW_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_hkairport()

