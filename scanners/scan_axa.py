"""
AXA Scanner
Requirements: pagination to last page (status stable), href dedup > title dedup, URL from scan_strategies
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(SCRIPT_DIR)

# --- Load URL from scan_strategies ---
BASE_URL = None
try:
    cfg_path = os.path.join(PROJ_DIR, "config", "scan_strategies.py")
    with open(cfg_path, encoding="utf-8") as f:
        raw = f.read()
    # Suppress scan_strategies print statements
    import io, contextlib
    tmp = io.StringIO()
    g = {}
    with contextlib.redirect_stdout(tmp):
        exec(compile(raw, "scan_strategies.py", "exec"), g)
    strategies = g.get("SCAN_STRATEGIES", {})
    axa_cfg = strategies.get("axa", {})
    BASE_URL = axa_cfg.get(
        "url",
        "https://careers.axa.com/careers-home/jobs?sortBy=relevance&country=Hong%20Kong&keywords=AI"
    )
except Exception as e:
    BASE_URL = "https://careers.axa.com/careers-home/jobs?sortBy=relevance&country=Hong%20Kong&keywords=AI"

OUTPUT_FILE = os.path.join(PROJ_DIR, "candidates", "raw",
                          f"axa_{datetime.now().strftime('%Y-%m-%d')}.json")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _close(page):
    try:
        page.close()
    except Exception:
        pass


def _extract_jobs(page):
    """Extract unique job entries from page DOM."""
    seen = set()
    results = []
    for a in page.query_selector_all("a[href]"):
        href = a.get_attribute("href") or ""
        if (href in seen
                or "icims" in href
                or "login" in href
                or "talent" in href
                or "/jobs/" not in href):
            continue
        seen.add(href)
        try:
            title = a.inner_text().strip()
        except Exception:
            title = ""
        if title:
            full_url = (("https://careers.axa.com" + href)
                        if href.startswith("/") else href)
            results.append({"title": title, "href": full_url})
    return results


def scan_axa():
    print("=== AXA Scanner ===")
    print(f"  URL: {BASE_URL}")
    all_jobs = []
    raw_jobs = []  # track all raw jobs found
    seen_hrefs = set()
    seen_titles = set()
    page_num = 1

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA
        )

        while True:
            url = f"{BASE_URL}&page={page_num}"
            print(f"\n  Page {page_num}... ", end="", flush=True)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(5)
            except Exception as e:
                print(f"[load failed: {e}]")
                _close(page)
                break

            page_jobs = _extract_jobs(page)
            print(f"{len(page_jobs)} jobs", end="")

            if not page_jobs:
                print(" -- [Stop] no jobs on this page")
                _close(page)
                break

            new_count = 0
            for job in page_jobs:
                href = job["href"]
                title = job["title"]
                # href dedup first
                if href not in seen_hrefs:
                    seen_hrefs.add(href)
                    # title dedup second
                    if title.lower() not in seen_titles:
                        seen_titles.add(title.lower())
                        rec = {
                            "title": title,
                            "company": "AXA",
                            "location": "Hong Kong",
                            "link": href,
                            "source": "AXA",
                            "scraped_at": datetime.now().isoformat(),
                        }
                        raw_jobs.append(rec)  # track raw job
                        scored = score_job(rec)
                        all_jobs.append(scored)
                        new_count += 1
                        if scored.get("isRecommended"):
                            print(f"\n    [MATCH] {title[:60]} ({scored.get('priority')}, {scored.get('score')})")

            print(f", new={new_count}, total={len(all_jobs)}")
            _close(page)
            page_num += 1
            if page_num > 10:
                break

        browser.close()

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    result = {
        "source": "AXA",
        "url": BASE_URL,
        "date": datetime.now().isoformat(),
        "total_raw": len(raw_jobs),
        "total_matched": len([j for j in all_jobs if j.get("isRecommended")]),
        "jobs": all_jobs,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    matched = [j for j in all_jobs if j.get("isRecommended")]
    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(matched)} matched -> {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_axa()

