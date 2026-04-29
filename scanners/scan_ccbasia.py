r"""
CCB Asia (中国建设银行亚洲) Scanner - SSR 页面
URL: https://online.asia.ccb.com/PersonalHKWeb/careeropportunity/webForm/actShowList.do
特点: 所有职位直接渲染在 HTML 中，无分页，无需 JS 渲染
参考: scan_kpmg.py (评分逻辑) + scan_dbs.py (Excel格式)
"""
import sys, os, json, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import get_jd_from_url, append_scanner_to_excel
from cco_scorer import CCOSCORER, score_job
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"ccbasia_{datetime.now().strftime('%Y-%m-%d')}.json")

BASE_URL = "https://online.asia.ccb.com/PersonalHKWeb/careeropportunity/webForm/actShowList.do"
SC_NAME = "CCB Asia"
PREFIX = "https://online.asia.ccb.com"

print(f"=== {SC_NAME} Scanner ===")
print(f"  URL: {BASE_URL}")


def _fetch_page(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Referer": url
    })
    r = urllib.request.urlopen(req, timeout=30)
    return r.read().decode("utf-8", errors="replace")


def scan_ccbasia():
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_hrefs = set()
    seen_titles = set()

    # ── Plan X: 加载去重索引 ─────────────────────────────────
    seen_data = load_seen_jobs()

    # ── Plan C: 启动浏览器用于 JD 抓取 ──────────────────────
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context()
    jd_page = context.new_page()
    jd_page.set_default_timeout(30000)

    try:
        # ── 抓取 HTML ──────────────────────────────────────
        try:
            html = _fetch_page(BASE_URL)
        except Exception as e:
            print(f"  ! Fetch failed: {e}")
            return []

        # ── 解析 SSR 表格 ─────────────────────────────────
        table_m = re.search(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
        if not table_m:
            print("  ! No table found")
            return []

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_m.group(1), re.DOTALL)
        print(f"  Table rows: {len(rows)}")

        for ri, row_html in enumerate(rows[1:], 1):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            if not cells:
                continue

            title_m = re.search(r"<a[^>]+href=[^>]+>([^<]+)</a>", row_html)
            if not title_m:
                continue
            title = re.sub(r"\s+", " ", title_m.group(1).strip())[:120]
            if not title or len(title) < 5:
                continue

            raw_cells = re.findall(r"DisplayValue\([^)]+\)|([^<\n]+)", "".join(cells), re.DOTALL)
            dept = next((re.sub(r"[^\w\s\-]", "", p).strip() for p in raw_cells if p.strip() and re.sub(r"[^\w\s]", "", p).strip() != title and "Hong Kong" not in p and "Full Time" not in p and "Contract" not in p and "Part Time" not in p), "")
            dept = dept[:60]

            posno_list = re.findall(r"javascript:OpenDetailWindow\(['\"]([^'\"]+)['\"]\)", row_html)
            posno = posno_list[0] if posno_list else ""
            raw_link = f"/PersonalHKWeb/careeropportunity/webForm/actGetCareerJobList.do?posno={posno}" if posno else ""
            full_link = PREFIX + raw_link

            if not posno:
                continue

            if full_link in seen_hrefs:
                continue
            seen_hrefs.add(full_link)

            tkey = title.lower()
            if tkey in seen_titles:
                continue
            seen_titles.add(tkey)

            job = {
                "title": title,
                "company": SC_NAME,
                "location": "Hong Kong",
                "link": full_link,
                "keyword": "AI",
                "source": SC_NAME,
                "scraped_at": datetime.now().isoformat(),
            }
            raw_jobs.append(job)
            print(f"  [{ri}] {title[:60]} | {dept}")

            # ── 评分 ──────────────────────────────────────
            fr = scorer.quick_filter(job)
            if not fr["passed"]:
                print(f"       [FILTER] {fr['reason']}")
                continue

            # ── Plan C: 抓取完整 JD ──────────────────────
            jd_text = get_jd_from_url(jd_page, full_link, platform="default")
            if jd_text:
                job["description"] = jd_text
                job["full_jd"] = jd_text

            # ── Plan X: 去重检查 ─────────────────────────
            status = check_job_status(full_link, title, seen_data)
            if status == "unchanged":
                print(f"       [SEEN  ] already in seen_jobs, skipping")
                continue

            scored = score_job(job)
            scored["status"] = status

            if scored.get("isRecommended"):
                all_jobs.append(scored)
                print(f"       [MATCH] P{scored.get('priority')} ({scored.get('score')}) - {scored.get('reason', '')[:60]}")
            else:
                print(f"       [SKIP ] score={scored.get('score')} reason={scored.get('reason', '')[:50]}")

            # ── Plan X: 更新去重索引 ─────────────────────
            update_job_entry(full_link, title, SC_NAME, jd_text, seen_data, status)

    finally:
        jd_page.close()
        context.close()
        browser.close()
        pw.stop()
        # ── Plan X: 保存去重索引 ─────────────────────────
        save_seen_jobs(seen_data)

    # ── 保存 JSON ──────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": SC_NAME,
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched -> {OUTPUT_FILE}")
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs


if __name__ == "__main__":
    scan_ccbasia()
