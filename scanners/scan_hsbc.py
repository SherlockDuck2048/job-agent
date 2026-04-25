r"""
HSBC Scanner - M3: CDP URL (Eightfold platform)
URL: https://portal.careers.hsbc.com/careers?query=AI&location=Hong%20Kong&...
来源: CCO提供的验证URL (2026-04-10)
关键发现: 岗位用 [data-test-id="position-card-N"] 渲染
"""
import sys, os, json, time
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
BASE_URL = "https://portal.careers.hsbc.com/careers"
SCROLL_COUNT = 8
WAIT_MS = 6000

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"hsbc_{datetime.now().strftime('%Y-%m-%d')}.json")
RAW_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"hsbc_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "config", f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "HK_AI_Jobs_YYYY-MM-DD.xlsx")

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass





def scan_hsbc():
    print("=== HSBC Scanner ===")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        url = (f"{BASE_URL}?query=AI&location=Hong%20Kong"
               f"&pid=563774610187996&domain=hsbc.com&sort_by=relevance&triggerGoButton=false")
        print(f"  URL: {url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(WAIT_MS / 1000)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        for _ in range(SCROLL_COUNT):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

        # Eightfold 动态渲染，用 position-card-N 选择器
        seen = set()
        job_entries = []
        for n in range(50):
            card = page.query_selector(f'[data-test-id="position-card-{n}"]')
            if not card:
                break
            try:
                # 找链接：可能在卡片内的 <a> 或 onclick 事件
                link_el = card.query_selector("a")
                title_el = card.query_selector("h1, h2, h3, [class*='title'], [class*='headline']")

                title = title_el.inner_text().strip() if title_el else ""
                href = ""

                if link_el:
                    href = link_el.get_attribute("href") or ""

                # 如果 href 为空，尝试从 onclick 或 data 属性找
                if not href:
                    raw_html = card.inner_html()
                    import re as _re
                    # 找任何 URL
                    urls = _re.findall(r'https?://[^\s"\'<>]+', raw_html)
                    for u in urls:
                        if "jobs" in u.lower() or "careers" in u.lower() or "position" in u.lower():
                            href = u
                            break
                    if not href and urls:
                        href = urls[0]

                if not title or title in seen:
                    continue
                seen.add(title)

                # 标准化链接
                if href and not href.startswith("http"):
                    href = f"https://portal.careers.hsbc.com{href}"

                job_entries.append({"title": title, "link": href})
                print(f"  [{n}] {title[:60]}")
            except Exception as e:
                print(f"  [ERR] Card {n}: {e}")

        print(f"\n  Found {len(job_entries)} job entries")

        for job_data in job_entries:
            try:
                title = job_data["title"]
                link = job_data["link"]

                job = {
                    "title": title, "company": "HSBC", "location": LOCATION,
                    "link": link, "keyword": "AI", "source": "HSBC",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [FILTER] {title[:40]} - {fr['reason']}")
                    continue
                print(f"  [PASS] {title[:40]}")

                if link and link.startswith("http"):
                    # [Plan C] Using common JD fetch function`n                jd_page = new_page(context)`n                jd_text = get_jd_from_url(jd_page, link, platform=\"default\")`n                job[\"description\"] = jd_text`n                jd_page.close()
                    job["description"] = full_jd

                scored = score_job(job)
                if scored.get("isRecommended"):
                    all_jobs.append(scored)
                    print(f"  [MATCH] {title[:55]} (P{scored.get('priority')}, {scored.get('score')})")
                else:
                    print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})")
            except Exception as e:
                print(f"  [ERR] {e}")

        _safe_close(page)
        browser.close()

    # Deduplicate
    seen_links = set()
    unique = []
    for j in all_jobs:
        if j.get("link") not in seen_links:
            seen_links.add(j.get("link"))
            unique.append(j)
    all_jobs = unique

    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "HSBC", "date": datetime.now().isoformat(), "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": "HSBC", "date": datetime.now().isoformat(), "total_found": len(all_jobs), "jobs": all_jobs}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}")
    append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs

if __name__ == "__main__":
    scan_hsbc()

