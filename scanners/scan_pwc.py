"""
PwC Scanner - Launch Own Browser
URL: https://www.pwccn.com/en/careers/experienced-jobs.html
搜索 "AI"，逐页抓取全部职位
"""
import sys, os, json, time, re
from datetime import datetime
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

BASE_URL = "https://www.pwccn.com/en/careers/experienced-jobs.html"
COMPANY = "PwC"
KEYWORDS = ["AI"]
MAX_PAGES = 50
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"pwc_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_FILE = os.path.join(OUTPUT_DIR, "..", "HK_AI_Jobs_All.xlsx")
DEBUG = True


def _extract_jobs_from_table(page):
    jobs = []
    try:
        rows = page.query_selector_all("table tr")
        for row in rows[1:]:
            cells = row.query_selector_all("td")
            if len(cells) < 3:
                continue
            title_el = cells[0].query_selector("a")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            href = title_el.get_attribute("href") or ""
            if not title or len(title) < 3:
                continue
            if "description.html" not in href and "/job/" not in href:
                continue
            link = ("https://www.pwccn.com" + href) if href.startswith("/") else href
            location = cells[2].inner_text().strip()
            job = {
                "title": title,
                "company": COMPANY,
                "location": location,
                "link": link,
                "source": COMPANY,
                "scraped_at": datetime.now().isoformat(),
                "_extra": {
                    "job_id": cells[1].inner_text().strip(),
                    "line": cells[3].inner_text().strip(),
                    "specialism": cells[4].inner_text().strip(),
                    "grade": cells[5].inner_text().strip(),
                },
            }
            jobs.append(job)
    except Exception as e:
        print(f"    [extract] error: {e}")
    return jobs


def _get_showing(page):
    """提取 'Showing X to Y of Z jobs' 中的 X（当前页起始行号）"""
    try:
        body = page.inner_text("body")
        m = re.search(r"Showing\s+(\d+)\s+to\s+\d+\s+of\s+\d+\s+jobs", body, re.I)
        return m.group(1) if m else ""  # 返回 '1', '11', '21' 等起始行号
    except Exception:
        return ""


def scan_pwc():
    print("=== PwC Scanner ===")
    print(f"  URL: {BASE_URL}")
    all_jobs = []
    seen_hrefs = {}
    seen_titles = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
            ]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        for kw in KEYWORDS:
            print(f"\n--- {kw} ---")
            try:
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                continue

            # 隐私弹窗
            try:
                btn = page.get_by_text("I understand")
                if btn.count() > 0:
                    btn.first.click()
                    time.sleep(1)
            except Exception:
                pass

            # 搜索
            try:
                search_box = page.get_by_role("textbox", name="Search")
                search_box.wait_for(state="visible", timeout=10000)
                search_box.fill(kw)
                time.sleep(0.5)
                search_box.press("Enter")
                time.sleep(4)
                print(f"  [search] '{kw}' applied")
            except Exception as e:
                print(f"  [search] failed: {e}")
                try:
                    page.evaluate(
                        """(kw) => {
                            const inputs = Array.from(document.querySelectorAll('input'));
                            for (const inp of inputs) {
                                if (inp.offsetParent !== null && inp.name !== 'country') {
                                    inp.value = kw;
                                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                                    inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
                                    break;
                                }
                            }
                        }""", kw
                    )
                    time.sleep(4)
                    print(f"  [search] '{kw}' (JS)")
                except Exception as e2:
                    print(f"  [search] JS failed: {e2}")

            # 等表格
            table_ok = False
            for _ in range(20):
                if page.query_selector("table"):
                    table_ok = True
                    break
                time.sleep(1.5)
            if not table_ok:
                print("  [table] never appeared")
                continue

            total = _get_showing(page)
            print(f"  [{total} jobs total]" if total else "  [total unknown]")

            page_num = 0

            while page_num < MAX_PAGES:
                page_num += 1
                print(f"  Page {page_num}...", end="", flush=True)

                page_jobs = _extract_jobs_from_table(page)
                print(f" {len(page_jobs)} rows", end="", flush=True)

                page_new = 0
                for job in page_jobs:
                    link_stem = job["link"]  # 保留完整 URL（包含 wdjobreqid），不同职位 wdjobreqid 不同
                    if link_stem in seen_hrefs:
                        continue
                    seen_hrefs[link_stem] = True
                    title_key = job["title"].lower()
                    if title_key in seen_titles:
                        continue
                    seen_titles[title_key] = True

                    page_new += 1
                    all_jobs.append(job)

                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        matched_count = sum(1 for j in all_jobs if score_job(j).get("isRecommended"))
                        print(f"\n    [MATCH {matched_count}] P{scored.get('priority','?')}/{scored.get('score','?')} {job['title'][:60]}")

                print(f" | new={page_new} total={len(all_jobs)}")

                # 翻页：用 JS 直接调用 click()，Playwright locator.click 对 SPA 无效
                try:
                    clicked = page.evaluate("""
                    () => {
                        const allAs = Array.from(document.querySelectorAll('a'));
                        const nextA = allAs.find(a => a.innerText.trim() === 'Next');
                        if (nextA) {
                            nextA.click();
                            return 'ok';
                        }
                        return 'not_found';
                    }
                    """)
                    if clicked != 'ok':
                        print("  [Done] No Next button")
                        break
                    # 等表格重新渲染
                    table_reloaded = False
                    for _ in range(30):  # 最多 45s
                        time.sleep(1.5)
                        rows_now = page.query_selector_all("table tr")
                        if len(rows_now) >= 2:
                            table_reloaded = True
                            break
                    if not table_reloaded:
                        print("  [Done] Table never reloaded")
                        break
                except Exception as e:
                    print(f"  [Done] Next failed: {e}")
                    break

                if page_num >= MAX_PAGES:
                    break

        browser.close()

    # 保存 JSON（包含评分字段）
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    matched_jobs = []
    for j in all_jobs:
        scored = score_job(j)
        if scored.get("isRecommended"):
            j.update({k: v for k, v in scored.items() if k not in j})
            matched_jobs.append(j)
    output = {
        "source": COMPANY,
        "url": BASE_URL,
        "date": datetime.now().isoformat(),
        "total_raw": len(all_jobs),
        "total_matched": len(matched_jobs),
        "jobs": matched_jobs,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[JSON] {OUTPUT_FILE}")

    if output["total_matched"] > 0:
        try:
            import subprocess
            excel_script = os.path.join(os.path.dirname(__file__), "write_excel.py")
            if os.path.exists(excel_script):
                result = subprocess.run(
                    ["python", excel_script, OUTPUT_FILE, EXCEL_FILE],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    print(f"  [Excel] Updated")
        except Exception as e:
            print(f"  [Excel] Failed: {e}")

    print(f"\n[Done] {output['total_raw']} raw / {output['total_matched']} matched")
    return output


if __name__ == "__main__":
    scan_pwc()


