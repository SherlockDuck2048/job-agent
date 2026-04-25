"""
UBS Scanner - Taleo-like TGnewUI SPA
URL: https://jobs.ubs.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=25008&siteid=5012&PageType=searchResults&SearchType=linkquery&LinkID=15231
关键词通过搜索表单填入（hash参数不会持久化）
"""
import sys, os, json, time, io, contextlib, re, io

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
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"ubs_{datetime.now().strftime('%Y-%m-%d')}.json")

# 从 scan_strategies.py 读取配置（禁止 print 干扰）
_strategies_src = open(os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py"), encoding="utf-8").read()
_globals = {}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, "scan_strategies.py", "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("ubs", {})
BASE_URL = _strategy.get("url", "https://jobs.ubs.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=25008&siteid=5012&PageType=searchResults&SearchType=linkquery&LinkID=15231")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_ubs():
    print("=== UBS Scanner ===")
    all_jobs = []
    raw_jobs = []  # track all raw jobs found
    seen_links = {}
    seen_titles = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page = context.new_page()
            print(f"  URL: {BASE_URL[:80]}...")

            try:
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
                time.sleep(6)

                # 找搜索表单并填入关键词
                # UBS TGnewUI 用动态 ID (searchContainer_keyWordSearch_N)，用 JS 直接操作 hash 更稳定
                kw_filled = False

                # 方案 A: JS 直接操作 hash 并 reload
                page.evaluate(f"""
                    () => {{
                        // Set hash params
                        var url = new URL(window.location.href);
                        url.hash = '#keyWordSearch={kw}&locationSearch=';
                        window.history.pushState(null, '', url.toString());
                    }}
                """)
                time.sleep(1)
                page.evaluate("() => window.dispatchEvent(new Event('hashchange'))")
                time.sleep(3)

                # 检查 hash 是否生效
                new_hash = page.url.split('#')[1] if '#' in page.url else ''
                if f'keyWordSearch={kw}' in new_hash:
                    print(f"  [JS hash] keyword set: {new_hash[:50]}")
                    kw_filled = True
                    # reload 触发搜索
                    page.goto(page.url, wait_until="domcontentloaded", timeout=45000)
                    time.sleep(6)
                else:
                    # 方案 B: 找到动态 ID 的输入框并 fill
                    visible_inps = page.evaluate("""
                        () => Array.from(document.querySelectorAll('input'))
                            .filter(el => el.offsetParent !== null && el.type !== 'hidden')
                            .map(el => ({ sel: el.id ? '#'+el.id : el.name || el.type, id: el.id }))
                    """)
                    for inp in visible_inps:
                        if inp['id'] and 'keyword' in inp['id'].lower():
                            try:
                                page.fill(f"#{inp['id']}", kw, timeout=5000)
                                page.press(f"#{inp['id']}", "Enter")
                                time.sleep(5)
                                kw_filled = True
                                print(f"  [Input fill] keyword set via #{inp['id']}")
                                break
                            except Exception:
                                continue

                if not kw_filled:
                    print("  [WARN] No keyword input found, using full page")

                # 滚动加载所有可见职位
                for _ in range(8):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)

            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close(page)
                continue

            # 当前 URL（检查 hash 是否更新）
            current_url = page.url
            print(f"  Current URL: {current_url[:100]}")
            print(f"  URL hash: {current_url.split('#')[1][:50] if '#' in current_url else 'none'}")

            # ── 分页：状态文字稳定检测 ─────────────────────────────────────
            stable_count = 0
            last_count = 0
            prev_status = ""
            max_pages = 20

            for page_num in range(1, max_pages + 1):
                print(f"\n  Page {page_num}...", end="", flush=True)

                # 收集所有 <LI class="job"> 卡片
                raw_cards = page.query_selector_all("li.job")
                print(f" {len(raw_cards)} job cards", flush=True)

                # 从卡片提取职位信息
                page_new = 0
                for card in raw_cards:
                    try:
                        # 标题链接
                        title_a = card.query_selector("a.jobProperty.jobtitle")
                        if not title_a:
                            continue
                        title = title_a.inner_text().strip()
                        raw_href = title_a.get_attribute("href") or ""

                        # 地点：第一个 .position3 就是国家/城市
                        location = ""
                        pos3_els = card.query_selector_all(".position3")
                        if pos3_els:
                            location = pos3_els[0].inner_text().strip()

                        if not title or len(title) < 5:
                            continue
                        # mailto 过滤
                        if "mailto:" in raw_href[:30]:
                            continue

                        # 完整 URL
                        if raw_href.startswith("/"):
                            link = "https://jobs.ubs.com" + raw_href
                        elif raw_href.startswith("http"):
                            link = raw_href
                        else:
                            continue

                        # href 去重（优先）
                        if link in seen_links:
                            continue
                        seen_links[link] = True
                        page_new += 1

                        # title 去重兜底
                        title_key = title.lower()
                        if title_key in seen_titles:
                            continue
                        seen_titles[title_key] = True

                        job = {
                            "title": title,
                            "company": "UBS",
                            "location": location or LOCATION,
                            "link": link,
                            "keyword": kw,
                            "source": "UBS",
                            "scraped_at": datetime.now().isoformat()
                        }
                        raw_jobs.append(job)  # track raw job

                        scored = score_job(job)
                        if scored.get("isRecommended"):
                            all_jobs.append(scored)
                            print(f"    [MATCH] {title[:60]}... ({scored.get('priority')}, {scored.get('score')})")

                    except Exception:
                        continue

                print(f"    new={page_new}, total href={len(seen_links)}, total title={len(seen_titles)}")

                # ── 分页翻页 ───────────────────────────────────────────────
                if page_num >= max_pages:
                    print("    [Stop] Max pages reached")
                    break

                # 状态文字检测
                body_text = page.inner_text("body")
                status_match = re.search(
                    r'[Ss]howing\s*(\d+)\s*[- ]+(\d+)\s*(?:of|of\s*)?(\d+)',
                    body_text
                )
                if status_match:
                    showing_from, showing_to, total = status_match.groups()
                    current_status = f"Showing {showing_from}-{showing_to} of {total}"
                else:
                    current_status = body_text[:200]

                # 稳定检测
                if current_status == prev_status and page_new == 0:
                    stable_count += 1
                else:
                    stable_count = 0
                prev_status = current_status
                last_count = page_new

                print(f"    Status: {str(current_status)[:60]} (stable={stable_count})".encode("ascii", "replace").decode("ascii"))
                if stable_count >= 2:
                    print("    [Stop] Status stable x2 - no more pages")
                    break

                # 找下一页按钮
                next_btn = None
                for sel in [
                    "button[aria-label*='next i']",
                    "a[aria-label*='next i']",
                    "[class*='pagination'] button",
                    "[class*='pager'] button",
                    "[class*='pager'] a",
                    "button[class*='next']",
                    "a[class*='next']"
                ]:
                    candidates = page.query_selector_all(sel)
                    for b in candidates:
                        t = b.inner_text().strip().lower()
                        if any(x in t for x in ["next", ">"]):
                            next_btn = b
                            break
                    if next_btn:
                        break

                if not next_btn:
                    print("    [Stop] No next button")
                    break

                disabled = next_btn.get_attribute("disabled")
                ng_disabled = next_btn.get_attribute("ng-disabled")
                if disabled is not None or (ng_disabled and "true" in ng_disabled.lower()):
                    print("    [Stop] Next button disabled")
                    break

                try:
                    next_href = next_btn.get_attribute("href")
                    if next_href:
                        next_url = next_href if next_href.startswith("http") else "https://jobs.ubs.com" + next_href
                        _safe_close(page)
                        page = context.new_page()
                        page.goto(next_url, wait_until="networkidle", timeout=45000)
                        time.sleep(5)
                        for _ in range(6):
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            time.sleep(1.5)
                    else:
                        next_btn.scroll_into_view_if_needed()
                        next_btn.click()
                        time.sleep(4)
                except Exception as e:
                    print(f"    [Stop] Next failed: {str(e)[:60]}")
                    break

            _safe_close(page)

        browser.close()

    # 保存
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "UBS",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched jobs saved to: {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_ubs()


