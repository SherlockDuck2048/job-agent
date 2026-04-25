"""
BOCHK Scanner - PageUp People CMS
URL: https://careers.pageuppeople.com/798/cw/en/search/?search-keyword=AI
结果: 15 jobs, 单页无分页
"""
import sys, os, json, time, io, contextlib, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"bochk_{datetime.now().strftime('%Y-%m-%d')}.json")

# ─── 从 scan_strategies 读取配置（禁止 print 干扰）─────────────────────────
STRATEGIES_FILE = os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py")
_site_config = {}
_strategies_src = open(STRATEGIES_FILE, encoding="utf-8").read()
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, STRATEGIES_FILE, "exec"))
_strategy = _site_config.get("bochk", {})
BASE_URL = _strategy.get("url", "https://careers.pageuppeople.com/798/cw/en/search/?search-keyword=AI")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_bochk():
    print("=== BOCHK Scanner ===")
    all_jobs = []
    raw_jobs = []  # track all raw jobs found
    seen_links = {}   # href deduplication (primary)
    seen_titles = {}  # title deduplication (fallback)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            url = BASE_URL.replace("search-keyword=AI", f"search-keyword={kw}")

            page = context.new_page()
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                time.sleep(5)
                for _ in range(6):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close(page)
                continue

            # ── 分页检测（PageUp People 通常单页）────────────────────────────
            stable_count = 0
            last_count = 0
            prev_status = ""
            max_pages = 10

            for page_num in range(1, max_pages + 1):
                print(f"  Page {page_num}...", end="", flush=True)

                # 收集 job links
                raw_links = page.query_selector_all("a[href*='/job/']")
                print(f" {len(raw_links)} links", flush=True)

                # href 去重
                page_new_links = 0
                for a in raw_links:
                    try:
                        href = a.get_attribute("href") or ""
                        title = a.inner_text().strip()
                        if not href or not title or len(title) < 5:
                            continue
                        # mailto/share 过滤
                        if "mailto:" in href[:20] or "PipelineDetail" in href:
                            continue
                        # href 去重
                        if href in seen_links:
                            continue
                        seen_links[href] = True
                        page_new_links += 1

                        # title 去重兜底
                        title_key = title.lower()
                        if title_key in seen_titles:
                            continue
                        seen_titles[title_key] = True

                        # 完整 URL
                        if href.startswith("/"):
                            link = "https://careers.pageuppeople.com" + href
                        elif href.startswith("http"):
                            link = href
                        else:
                            continue

                        job = {
                            "title": title,
                            "company": "BOCHK",
                            "location": LOCATION,
                            "link": link,
                            "keyword": kw,
                            "source": "BOCHK",
                            "scraped_at": datetime.now().isoformat()
                        }
                        raw_jobs.append(job)  # track raw job

                        scored = score_job(job)
                        if scored.get("isRecommended"):
                            all_jobs.append(scored)

                    except Exception:
                        continue

                # ── 分页翻页 ───────────────────────────────────────────────
                if page_num >= max_pages:
                    break

                # 状态文字：找 "Showing X-Y of Z"
                import re
                body_text = page.inner_text("body")
                status_match = re.search(r'[Ss]howing\s*(\d+)[- ]+(\d+)\s*(?:of|共)?\s*(\d+)', body_text)
                current_status = status_match.group(0) if status_match else body_text[:200]

                # 状态文字稳定检测
                if current_status == prev_status and last_count == page_new_links == 0:
                    stable_count += 1
                else:
                    stable_count = 0
                prev_status = current_status
                last_count = page_new_links

                print(f"  Status: {current_status[:80]} (stable={stable_count})".encode("ascii", "replace").decode("ascii"))
                if stable_count >= 2:
                    print("  [Stop] Status stable x2 - no more pages")
                    break

                # 尝试找下一页按钮
                next_btn = None
                for sel in [
                    "button[class*='next']", "a[class*='next']",
                    "[aria-label*='next']", ".pagination a",
                    "[class*='paging'] a", "[class*='page-item'] a"
                ]:
                    candidates = page.query_selector_all(sel)
                    for b in candidates:
                        t = b.inner_text().strip().lower()
                        if any(x in t for x in ["next", ">", "\u203a", "下一"]):
                            next_btn = b
                            break
                    if next_btn:
                        break

                if not next_btn:
                    print("  [Stop] No next button found")
                    break

                disabled = next_btn.get_attribute("disabled")
                if disabled is not None:
                    print("  [Stop] Next button disabled")
                    break

                try:
                    next_href = next_btn.get_attribute("href")
                    if next_href:
                        next_url = next_href if next_href.startswith("http") else "https://careers.pageuppeople.com" + next_href
                        _safe_close(page)
                        page = context.new_page()
                        page.goto(next_url, wait_until="networkidle", timeout=45000)
                        time.sleep(4)
                        for _ in range(4):
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            time.sleep(1)
                    else:
                        next_btn.click()
                        page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"  [Stop] Next click failed: {e}".encode("ascii", "replace").decode("ascii"))
                    break

            _safe_close(page)

        browser.close()

    # ── 保存 ──────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "BOCHK",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched jobs saved to: {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_bochk()


