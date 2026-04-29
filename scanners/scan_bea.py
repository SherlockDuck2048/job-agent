"""
BEA Scanner (东亚银行) - PeopleSoft System
URL: https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL
来源: 用户验证 (2026-04-15)
特点: PeopleSoft SPA，职位数据在 iframe 的表格中
"""
import sys, os, json, time, re, io, contextlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"bea_{datetime.now().strftime('%Y-%m-%d')}.json")

# 从 scan_strategies 读取配置
STRATEGIES_FILE = os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py")
_globals = {}
_strategies_src = open(STRATEGIES_FILE, encoding="utf-8").read()
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, STRATEGIES_FILE, "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("bea", {})
BASE_URL = _strategy.get("url", "https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL?Page=HRS_APP_SCHJOB&FOCUS=Applicant&FolderPath=PORTAL_ROOT_OBJECT.HC_HRS_CE_GBL2&IsFolder=false&IgnoreParamTempl=FolderPath%252cIsFolder")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except:
        pass


def scan_bea():
    print("=== BEA Scanner ===")
    print(f"  URL: {BASE_URL}")

    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_links = {}
    seen_titles = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("\n  Loading page...")
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            print("  Waiting 15s for iframe content...")
            time.sleep(15)

            # 找到 TargetContent iframe
            target_frame = None
            for frame in page.frames:
                if frame.name == "TargetContent":
                    target_frame = frame
                    break

            if not target_frame:
                print("  ! TargetContent frame not found")
                _safe_close(page)
                browser.close()
                return []

            print("  TargetContent frame found")

            # 等待 frame 内容加载
            time.sleep(5)

            # ─── 分页处理 ───────────────────────────────────────────────
            max_pages = 10
            stable_count = 0
            prev_job_count = 0

            for page_num in range(1, max_pages + 1):
                print(f"\n  Page {page_num}...", end="", flush=True)

                job_rows = target_frame.query_selector_all("tr")

                page_new = 0
                for row in job_rows:
                    try:
                        row_html = row.evaluate("el => el.outerHTML")
                        if "HRS_CE_JO_EXT_I" not in row_html:
                            continue

                        cells = row.query_selector_all("td")
                        if len(cells) < 5:
                            continue

                        title_cell = cells[1]
                        title_link = title_cell.query_selector("a")
                        if title_link:
                            title = title_link.inner_text().strip()
                            onclick = title_link.get_attribute("onclick") or ""
                            if "HRS_CE_JO_EXT_I" in onclick:
                                match = re.search(r'HRS_CE_JO_EXT_I\$?(\d+)', onclick)
                                job_id_from_onclick = match.group(1) if match else ""
                            else:
                                job_id_from_onclick = ""
                        else:
                            title = title_cell.inner_text().strip()

                        if not title or len(title) < 5:
                            continue

                        job_id = cells[2].inner_text().strip() if len(cells) > 2 else ""
                        if not job_id and job_id_from_onclick:
                            job_id = job_id_from_onclick

                        location = cells[3].inner_text().strip() if len(cells) > 3 else LOCATION
                        posted_date = cells[4].inner_text().strip() if len(cells) > 4 else ""

                        if job_id:
                            link = f"https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL?Page=HRS_APP_JSPST&JobOpeningId={job_id}"
                        else:
                            link = BASE_URL

                        if link in seen_links:
                            continue
                        seen_links[link] = True
                        page_new += 1

                        title_key = title.lower()
                        if title_key in seen_titles:
                            continue
                        seen_titles[title_key] = True

                        job = {
                            "title": title,
                            "company": "BEA",
                            "location": location,
                            "link": link,
                            "keyword": "AI",
                            "source": "BEA",
                            "scraped_at": datetime.now().isoformat(),
                            "job_id": job_id,
                            "posted_date": posted_date
                        }
                        raw_jobs.append(job)

                        # 快速过滤
                        fr = scorer.quick_filter(job)
                        if not fr["passed"]:
                            safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                            safe_reason = fr['reason'][:30].encode('ascii', 'replace').decode('ascii')
                            print(f"\n    [FILTER] {safe_title} - {safe_reason}")
                            continue

                        # 评分
                        scored = score_job(job)
                        if scored.get("isRecommended"):
                            all_jobs.append(scored)
                            safe_title = title[:50].encode('ascii', 'replace').decode('ascii')
                            print(f"\n    [MATCH] {safe_title} ({scored.get('priority')}, {scored.get('score')})")

                    except Exception as e:
                        err = str(e)[:40].encode('ascii', 'replace').decode('ascii')
                        print(f"\n    [ERR] {err}")
                        continue

                print(f"  new={page_new}, total={len(raw_jobs)}, matched={len(all_jobs)}")

                if len(raw_jobs) == prev_job_count:
                    stable_count += 1
                else:
                    stable_count = 0
                prev_job_count = len(raw_jobs)

                if stable_count >= 2:
                    print("    [Stop] No new jobs for 2 consecutive pages")
                    break

                # ─── 翻页 ───────────────────────────────────────────────────
                next_btn = None
                for sel in [
                    "a[title*='Next']",
                    "a[aria-label*='Next']",
                    "a:has-text('>')",
                    "a.PSLEVEL1SCROLLNEXT",
                    "a[href*='scroll']"
                ]:
                    candidates = target_frame.query_selector_all(sel)
                    for btn in candidates:
                        text = btn.inner_text().strip()
                        if text in [">", "Next", ">"]:
                            next_btn = btn
                            break
                    if next_btn:
                        break

                if not next_btn:
                    print("    [Stop] No next button found")
                    break

                try:
                    next_btn.click()
                    time.sleep(5)
                except Exception as e:
                    print(f"    [Stop] Next click failed: {str(e)[:40]}")
                    break

            _safe_close(page)
            browser.close()

        except Exception as e:
            err = str(e)[:80].encode('ascii', 'replace').decode('ascii')
            print(f"  ! Error: {err}")
            _safe_close(page)
            browser.close()
            return []

    # ── 保存 JSON ─────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "BEA",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched jobs saved")
    print(f"  Output: {OUTPUT_FILE}")

    # ── Plan C: 抓取 JD ────────────────────────────────────────────────────
    print(f"\n=== Plan C: Fetching JDs ({len(all_jobs)} matched jobs) ===")
    for job in all_jobs:
        link = job.get("link", "")
        if link:
            with sync_playwright() as p2:
                b2 = p2.chromium.launch(headless=True)
                ctx2 = b2.new_context(viewport={"width": 1920, "height": 1080})
                pg2 = ctx2.new_page()
                jd_text = get_jd_from_url(pg2, link, "peoplesoft")
                pg2.close()
                b2.close()
            job["full_jd"] = jd_text
            jd_len = len(jd_text) if jd_text else 0
            safe_title = job.get("title", "")[:50].encode('ascii', 'replace').decode('ascii')
            print(f"  [{jd_len} chars] {safe_title}")

    # 重新保存含 JD 的版本
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "BEA",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

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
        safe_title = title[:50].encode('ascii', 'replace').decode('ascii')
        print(f"  [{status.upper()}] {safe_title}")
    save_seen_jobs(seen_data)

    # ── 写入 Excel ─────────────────────────────────────────────────────────
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
        print("[EXCEL] Updated")

    return all_jobs


if __name__ == "__main__":
    scan_bea()
