r"""
LinkedIn Scanner
从 scan_strategies.py 读取 URL 配置，支持分页翻到底

来源: scan_strategies.py 动态读取
评分: cco_scorer (同 scan_kpmg.py)
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

# 强制 UTF-8 输出，避免 cp1252 编码崩溃
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def _p(text, length=None):
    """安全打印：移除无法用cp1252编码的字符（如emoji），避免PowerShell崩溃"""
    if not isinstance(text, str):
        text = str(text)
    # cp1252无法编码的字符（主要是emoji）直接移除
    try:
        text = text.encode('cp1252', errors='ignore').decode('cp1252')
    except Exception:
        text = text.encode('utf-8', errors='ignore').decode('utf-8')
    if length:
        text = text[:length]
    return text

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from job_scanner_base import append_scanner_to_excel
from config.scan_strategies import SCAN_STRATEGIES
from scanners.cco_scorer import CCOSCORER, score_job

NAME = "LinkedIn"
LOCATION = "Hong Kong"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "config",
                         f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def get_status_text(page):
    """提取 LinkedIn 页面状态文字（职位数量）"""
    try:
        for p in page.query_selector_all("p"):
            t = p.inner_text().strip()
            if re.search(r'\d+[\s\-–]+\d+\s*(jobs?|results?)', t, re.I):
                return t
        for span in page.query_selector_all("span"):
            t = span.inner_text().strip()
            if re.search(r'\d+[\s\-–]+\d+\s*(jobs?|results?)', t, re.I):
                return t
    except Exception:
        pass
    return ""



def scan_linkedin():
    print("=== LinkedIn Scanner ===")

    # ── 1. 读取 URL 配置 ────────────────────────────────────
    cfg = SCAN_STRATEGIES.get("linkedin", {})
    if not cfg or cfg.get("method") == "skip":
        print("  [!] LinkedIn not configured in scan_strategies.py or is skip")
        return []

    base_url = cfg.get("url", "")
    if not base_url:
        print("  [!] No URL found for LinkedIn in scan_strategies.py")
        return []

    print(f"  URL: {base_url}")

    scorer = CCOSCORER()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        except Exception as e:
            print(f"  [!] Load failed: {e}")
            _safe(page); browser.close(); return []

        # ── 2. Stage 1: 分页抓取全部职位链接 ───────────────────
        all_entries = []

        while True:
            # 滚动触发懒加载
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.0)

            # 提取所有 job 链接（href 去重）
            seen_hrefs = set()
            entries = []
            for a in page.query_selector_all("a[href*='/jobs/view']"):
                try:
                    href = a.get_attribute("href") or ""
                    if not href or href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)
                    text = " ".join(a.inner_text().split()).strip()
                    if not text or len(text) < 5:
                        continue
                    full_link = href if href.startswith("http") else f"https://www.linkedin.com{href}"
                    entries.append({"title": text[:100], "link": full_link})
                except Exception:
                    pass

            new_count = sum(1 for e in entries
                            if e["link"] not in {x["link"] for x in all_entries})
            status = get_status_text(page)
            prev_total = len(all_entries)
            for e in entries:
                if e["link"] not in {x["link"] for x in all_entries}:
                    all_entries.append(e)
            print(f"  [scroll] +{new_count} new -> total: {len(all_entries)} | status: {status}")

            # 检查 "Show more results" 按钮
            btn = None
            for sel in [
                "button[aria-label*='Show more results']",
                "button[data-control-name*='pagingButton']",
                ".infinite-scroller__show-more-button",
                "button:has-text('Show more results')",
                ".jobs-search-results-list__pagination"
            ]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        btn = el; break
                except Exception:
                    pass

            if not btn:
                print("  [Done] No more results button found")
                break

            disabled = btn.get_attribute("disabled")
            if disabled is not None:
                print("  [Done] Show more button disabled")
                break

            print("  [>] Loading more results...")
            try:
                btn.scroll_into_view_if_needed()
                time.sleep(0.5)
                btn.click()
                time.sleep(3)
            except Exception as e:
                print(f"  [!] Click failed: {e}")
                break

        print(f"\n  [Stage 1 Done] {len(all_entries)} unique entries")

        # ── 3. Stage 2: 评分 ─────────────────────────────────
        all_matched = []; raw_jobs = []

        for i, job_data in enumerate(all_entries):
            title = job_data["title"]; link = job_data["link"]
            job = {"title": title, "company": NAME, "location": LOCATION,
                   "link": link, "keyword": "AI", "source": NAME,
                   "scraped_at": datetime.now().isoformat()}
            raw_jobs.append(job)

            fr = scorer.quick_filter(job)
            if not fr["passed"]:
                reason_text = fr.get("reason", "")[:40]
                print(f"  [{i+1}/{len(all_entries)} FILTER] {_p(title,45)} - {reason_text}")
                continue
            print(f"  [{i+1}/{len(all_entries)} PASS] {_p(title,55)}")

            scored = score_job(job)
            if scored.get("isRecommended"):
                all_matched.append(scored)
                print(f"  [MATCH!] {_p(title,55)} -> P{scored.get('priority')} {scored.get('score')}")
            else:
                print(f"  [SKIP ] {_p(title,55)} (P{scored.get('priority')} {scored.get('score')})")

        _safe(page); browser.close()

    # ── 4. 保存 ──────────────────────────────────────────
    seen_links = set()
    unique = [j for j in all_matched
              if j.get("link") not in seen_links and not seen_links.add(j.get("link"))]
    all_matched = unique

    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = os.path.join(RAW_DIR, f"linkedin_raw_{today}.json")
    out_file = os.path.join(RAW_DIR, f"linkedin_{today}.json")
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
    scan_linkedin()


