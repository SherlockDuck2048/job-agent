"""
CRC Capital Scanner (华润香港)
URL: https://www.crcapital.com.hk/shzp/index.html
来源: 用户验证 (2026-04-15)
选择器: ._newsItem.item > a[href*='/shzp/']
"""
import sys, os, json, time, io, contextlib, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"crc_{datetime.now().strftime('%Y-%m-%d')}.json")

# ─── 从 scan_strategies 读取配置（禁止 print 干扰）─────────────────────────
STRATEGIES_FILE = os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py")
_globals = {}
_strategies_src = open(STRATEGIES_FILE, encoding="utf-8").read()
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, STRATEGIES_FILE, "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("crcapital", {})
BASE_URL = _strategy.get("url", "https://www.crcapital.com.hk/shzp/index.html")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_crc():
    print("=== CRC Capital Scanner ===")
    print(f"  URL: {BASE_URL}")
    
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_links = {}   # href deduplication (primary)
    seen_titles = {}  # title deduplication (fallback)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        # 滚动加载所有职位
        for _ in range(8):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

        # ─── 分页：状态文字稳定检测 ─────────────────────────────────────
        stable_count = 0
        last_count = 0
        prev_status = ""
        max_pages = 10

        for page_num in range(1, max_pages + 1):
            print(f"\n  Page {page_num}...", end="", flush=True)

            # 收集职位卡片 - 使用正确选择器
            job_cards = page.query_selector_all("._newsItem.item")
            
            # 如果没找到，尝试其他选择器
            if not job_cards:
                job_cards = page.query_selector_all(".ejNewsBox .item")
            if not job_cards:
                job_cards = page.query_selector_all("a[href*='/shzp/']")

            print(f" {len(job_cards)} job cards", flush=True)

            page_new = 0
            for card in job_cards:
                try:
                    # 提取链接和标题
                    link_el = card if card.get_attribute("href") else card.query_selector("a[href*='/shzp/']")
                    if not link_el:
                        continue
                    
                    href = link_el.get_attribute("href") or ""
                    if not href or "/shzp/" not in href:
                        continue
                    
                    # 提取标题
                    title_el = card.query_selector(".title") if hasattr(card, 'query_selector') else link_el
                    if title_el:
                        title = title_el.inner_text().strip()
                    else:
                        title = link_el.inner_text().strip()
                    
                    if not title or len(title) < 3:
                        continue
                    
                    # 提取公司信息
                    txt_el = card.query_selector(".txt") if hasattr(card, 'query_selector') else None
                    txt = txt_el.inner_text().strip() if txt_el else ""
                    
                    # 解析位置信息
                    location = LOCATION
                    if "香港" in txt or "Hong Kong" in txt.lower():
                        location = "Hong Kong"
                    elif "深圳" in txt:
                        location = "Shenzhen"
                    elif any(city in txt for city in ["北京", "上海", "广州", "成都", "杭州"]):
                        location = txt.split("|")[0].strip() if "|" in txt else txt[:20]
                    
                    # 完整链接
                    if href.startswith("../"):
                        link = "https://www.crcapital.com.hk/" + href[3:]
                    elif href.startswith("/"):
                        link = "https://www.crcapital.com.hk" + href
                    elif href.startswith("http"):
                        link = href
                    else:
                        link = "https://www.crcapital.com.hk/shzp/" + href
                    
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
                        "company": "CRC Capital",
                        "location": location,
                        "link": link,
                        "keyword": "AI",
                        "source": "CRC Capital",
                        "scraped_at": datetime.now().isoformat(),
                        "txt": txt[:200]  # 保存额外信息
                    }
                    raw_jobs.append(job)

                    # 快速过滤
                    fr = scorer.quick_filter(job)
                    if not fr["passed"]:
                        safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                        safe_reason = fr['reason'][:30].encode('ascii', 'replace').decode('ascii')
                        print(f"    [FILTER] {safe_title} - {safe_reason}")
                        continue

                    # 评分
                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        safe_title = title[:55].encode('ascii', 'replace').decode('ascii')
                        print(f"    [MATCH] {safe_title} ({scored.get('priority')}, {scored.get('score')})")

                except Exception as e:
                    err_msg = str(e)[:40].encode('ascii', 'replace').decode('ascii')
                    print(f"    [ERR] {err_msg}")
                    continue

            print(f"    new={page_new}, total href={len(seen_links)}, matched={len(all_jobs)}")

            # ─── 分页翻页 ───────────────────────────────────────────────
            if page_num >= max_pages:
                break

            # 状态文字检测
            body_text = page.inner_text("body")
            status_match = re.search(r'[\u4e00-\u9fa5]?(\d+)[\u4e00-\u9fa5]?[- ]+(\d+)[\u4e00-\u9fa5]*(?:of|/|/u5171)?[\u4e00-\u9fa5]*(\d+)', body_text)
            current_status = status_match.group(0) if status_match else body_text[:100]

            if current_status == prev_status and page_new == 0:
                stable_count += 1
            else:
                stable_count = 0
            prev_status = current_status

            safe_status = current_status[:50].encode('ascii', 'replace').decode('ascii')
            print(f"    Status: {safe_status} (stable={stable_count})")
            if stable_count >= 2:
                print("    [Stop] Status stable x2 - no more pages")
                break

            # 找下一页按钮
            next_btn = None
            for sel in [
                "button[class*='next']", "a[class*='next']",
                "[aria-label*='next']", ".pagination a",
                "[class*='page'] a", "a[href*='page=']"
            ]:
                candidates = page.query_selector_all(sel)
                for b in candidates:
                    t = b.inner_text().strip().lower()
                    if any(x in t for x in ["next", ">", "\u203a", "\u4e0b\u4e00"]):
                        next_btn = b
                        break
                if next_btn:
                    break

            if not next_btn:
                print("    [Stop] No next button found")
                break

            disabled = next_btn.get_attribute("disabled")
            if disabled is not None:
                print("    [Stop] Next button disabled")
                break

            try:
                next_btn.scroll_into_view_if_needed()
                next_btn.click()
                time.sleep(4)
                # 滚动加载新内容
                for _ in range(4):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
            except Exception as e:
                err_msg = str(e)[:50].encode('ascii', 'replace').decode('ascii')
                print(f"    [Stop] Next click failed: {err_msg}")
                break

        _safe_close(page)
        browser.close()

    # ─── 保存 ──────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "CRC Capital",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched jobs saved to: {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_crc()


