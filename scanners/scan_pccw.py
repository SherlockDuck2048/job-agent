"""
PCCW/HKT Scanner - Taleo CMS
URL: https://job.pccw.com/hkt/search/?createNewAlert=false&q=AI
结果: 19 jobs (all HK, no pagination)
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"pccw_{datetime.now().strftime('%Y-%m-%d')}.json")

# ─── 从 scan_strategies 读取配置（禁止 print 干扰）─────────────────────────
import io, contextlib
STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "scan_strategies.py")
_site_config = {}
_strategies_src = open(STRATEGIES_FILE, encoding="utf-8").read()
# 静默 exec，禁止 scan_strategies 里的 print 语句产生输出
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, STRATEGIES_FILE, "exec"))
_strategy = _site_config.get("hkt") or _site_config.get("pccw", {})
BASE_URL = _strategy.get("url", "https://job.pccw.com/hkt/search/?createNewAlert=false&q=AI")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_pccw():
    print("=== PCCW/HKT Scanner ===")
    all_jobs = []
    seen_links = {}   # href → True  (href deduplication)
    seen_titles = {}  # title_lower → True  (title deduplication fallback)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")

            # keyword 替换到 URL
            url = BASE_URL.replace("q=AI", f"q={kw}")

            page = context.new_page()
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                time.sleep(3)
                for _ in range(4):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close(page)
                continue

            # ── 收集 job links ─────────────────────────────────────────────
            raw_links = page.query_selector_all("a[href*='/hkt/job/']")
            print(f"  Raw links: {len(raw_links)}")

            for a in raw_links:
                try:
                    href = a.get_attribute("href") or ""
                    title = a.inner_text().strip()

                    if not href or not title or len(title) < 3:
                        continue

                    # mailto / share links 过滤
                    if "mailto:" in href[:20] or "PipelineDetail" in href:
                        continue

                    # href 去重
                    if href in seen_links:
                        continue
                    seen_links[href] = True

                    # title 去重兜底
                    title_key = title.lower()
                    if title_key in seen_titles:
                        continue
                    seen_titles[title_key] = True

                    # 构造完整 URL
                    if href.startswith("/"):
                        link = "https://job.pccw.com" + href
                    elif href.startswith("http"):
                        link = href
                    else:
                        continue

                    # location 来自 URL slug（hk=香港, ph=菲律宾等）
                    slug_lower = href.lower()
                    job_loc = LOCATION  # 默认香港
                    if "/ph/" in slug_lower or "/manila/" in slug_lower or "/riz/" in slug_lower:
                        job_loc = "Philippines"
                    elif "/sg/" in slug_lower or "/singapore/" in slug_lower:
                        job_loc = "Singapore"
                    elif "/cn/" in slug_lower or "/shanghai/" in slug_lower or "/guangzhou/" in slug_lower:
                        job_loc = "China"

                    job = {
                        "title": title,
                        "company": "HKT",
                        "location": job_loc,
                        "link": link,
                        "keyword": kw,
                        "source": "PCCW/HKT",
                        "scraped_at": datetime.now().isoformat()
                    }

                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"  [MATCH] {title[:50]} ({scored.get('priority')}, {scored.get('score')})")

                except Exception as e:
                    continue

            _safe_close(page)

        browser.close()

    # ── 保存 ───────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "PCCW/HKT",
            "date": datetime.now().isoformat(),
            "total_found": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(all_jobs)} matched jobs saved to: {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_pccw()


