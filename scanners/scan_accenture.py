"""
Accenture Scanner
URL: https://www.accenture.com/hk-en/careers/jobsearch?jk=AI
从 scan_strategies.py 动态读取配置。
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job


def load_strategies():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "scan_strategies.py")
    with open(cfg_path, "r", encoding="utf-8") as f:
        content = f.read()
    ns = {}
    exec(content, ns)
    strategies = ns.get("SCAN_STRATEGIES", {})
    return strategies.get("accenture", None)


def run():
    strat = load_strategies()
    if not strat:
        print("accenture not found in scan_strategies.py")
        return []

    name = strat["name"]
    base_url = strat["url"]

    parsed = urlparse(base_url)
    params = parse_qs(parsed.query)
    base_params = {k: v[0] for k, v in params.items() if k != "pg"}
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    keyword = "AI"
    base_params["jk"] = keyword

    def make_url(page_num):
        q = "&".join(f"{k}={v}" for k, v in {**base_params, "pg": str(page_num)}.items())
        return f"{base_path}?{q}"

    print(f"=== {name} Scanner ===")
    print(f"  Base URL: {base_url}")

    all_jobs = []
    seen_hrefs = set()
    seen_titles = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        page_number = 1
        prev_status_text = ""
        stable_count = 0
        max_pages = 20

        while page_number <= max_pages:
            url = make_url(page_number)
            print(f"\n  --- Page {page_number} ---")

            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                break

            # [data-job-id] 元素：job-title 属性 = 职位名，data-job-id = job ID
            raw_cards = page.query_selector_all("[data-job-id]")
            print(f"  Cards found: {len(raw_cards)}")

            status_el = page.query_selector(
                "[class*='count'], [class*='total'], [class*='results'], "
                "[class*='status'], p[class*='muted']"
            )
            status_text = status_el.inner_text().strip() if status_el else ""
            print(f"  Status: {status_text}")

            if status_text == prev_status_text and page_number > 1:
                stable_count += 1
                print(f"  Status stable x{stable_count}")
                if stable_count >= 2:
                    print("  [STOP] Status stable 2x — last page")
                    break
            else:
                stable_count = 0
            prev_status_text = status_text

            if len(raw_cards) == 0 and page_number > 1:
                print("  [STOP] No cards on this page")
                break

            page_jobs = 0
            for btn in raw_cards:
                try:
                    job_id = btn.get_attribute("data-job-id") or ""
                    title = btn.get_attribute("job-title") or ""
                    if not title:
                        continue

                    # href 直接由 job_id 构造
                    href = f"https://www.accenture.com/hk-en/careers/jobdetails?id={job_id}"
                    href_main = href.rstrip("/")

                    if href_main in seen_hrefs:
                        print(f"    [DUP href] {title[:60]}")
                        continue
                    seen_hrefs.add(href_main)

                    title_lower = title.lower()
                    if title_lower in seen_titles:
                        print(f"    [DUP title] {title[:60]}")
                        continue
                    seen_titles.add(title_lower)

                    job = {
                        "title": title,
                        "company": name,
                        "location": "Hong Kong",
                        "link": href,
                        "source": name,
                        "keyword": keyword,
                        "job_id": job_id,
                        "scraped_at": datetime.now().isoformat(),
                    }

                    scored = score_job(job)
                    print(
                        f"    {'[MATCH]' if scored.get('isRecommended') else '[skip]'} "
                        f"{title[:60]} ({scored.get('score')})"
                    )
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)

                    page_jobs += 1

                except Exception as e:
                    print(f"    ! Card error: {e}")
                    continue

            print(f"  Page {page_number}: {page_jobs} processed, "
                  f"total raw={len(seen_hrefs)}, matched={len(all_jobs)}")
            page_number += 1

        browser.close()

    out_dir = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"accenture_{datetime.now().strftime('%Y-%m-%d')}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "source": name,
            "url": base_url,
            "date": datetime.now().isoformat(),
            "total_raw": len(seen_hrefs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] raw={len(seen_hrefs)} matched={len(all_jobs)} -> {out_file}")
    return all_jobs


if __name__ == "__main__":
    run()


