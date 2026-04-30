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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from job_scanner_base import append_scanner_to_excel, get_jd_from_url, new_page
from cco_scorer import score_job
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"pccw_{datetime.now().strftime('%Y-%m-%d')}.json")

# ─── 从 scan_strategies 读取配置（禁止 print 干扰）─────────────────────────
import io as _io, contextlib as _ctx
STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "scan_strategies.py")
_site_config = {}
_strategies_src = open(STRATEGIES_FILE, encoding="utf-8").read()
# 静默 exec，禁止 scan_strategies 里的 print 语句产生输出
with _ctx.redirect_stdout(_io.StringIO()):
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

    # ── Plan C: 抓取 JD ────────────────────────────────────────────────────
    print(f"\n=== Plan C: Fetching JDs ({len(all_jobs)} matched jobs) ===")
    if all_jobs:
        with sync_playwright() as p2:
            b2 = p2.chromium.launch(headless=True)
            ctx2 = b2.new_context(viewport={"width": 1920, "height": 1080})
            for job in all_jobs:
                link = job.get("link", "")
                if not link:
                    continue
                pg2 = ctx2.new_page()
                jd_text = get_jd_from_url(pg2, link, "taleo")
                pg2.close()
                job["full_jd"] = jd_text
                jd_len = len(jd_text) if jd_text else 0

                # 保存 JD 文件
                m = re.search(r'/(\d+)/?$', link) or re.search(r'/(\d+)\??', link)
                if m and jd_text:
                    safe_id = m.group(1)
                    jd_dir = os.path.join(os.path.dirname(OUTPUT_FILE), "..", "jd_store", "pccw")
                    os.makedirs(jd_dir, exist_ok=True)
                    jd_path = os.path.join(jd_dir, f"{safe_id}.txt")
                    with open(jd_path, "w", encoding="utf-8") as f:
                        f.write(jd_text)
                    job["jd_file"] = f"pccw/{safe_id}.txt"

                print(f"  JD [{jd_len} chars] {job.get('title', '')[:50]}  →  jd_file={job.get('jd_file', 'N/A')}")
            b2.close()

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

    # ── Plan X: 跨会话去重 ─────────────────────────────────────────────────
    print("\n=== Plan X: Cross-session deduplication ===")
    seen_data = load_seen_jobs()
    for job in all_jobs:
        link = job.get("link", "")
        title = job.get("title", "")
        company = job.get("company", "")
        jd_text = job.get("full_jd", "") or job.get("description", "")
        status = check_job_status(link, title, seen_data)
        update_job_entry(link, title, company, jd_text, seen_data, status)
        print(f"  [{status.upper()}] {title[:50]}")
    save_seen_jobs(seen_data)

    # ── 写入 Excel ─────────────────────────────────────────────────────────
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
        print("[EXCEL] Updated")

    return all_jobs


if __name__ == "__main__":
    scan_pccw()
