r"""
FWD Scanner - Workday 平台 + 分页
URL: https://fwd.wd3.myworkdayjobs.com/en-US/FWDcareersite?q=AI&locationCountry=...
来源: CCO提供的验证URL (2026-04-13)

架构: 两阶段
  Stage 1: 分页抓取所有职位链接（不离开列表页）
  Stage 2: 批量获取 JD 并评分（独立 page）

[Plan C] Integrated: Using common JD fetch function
[Plan X] Integrated: Unified field name to description
"""
import sys, os, json, time, io
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X

NAME = "FWD"
LOCATION = "Hong Kong"
KEYWORDS = ["AI"]

FWD_URL = SCAN_STRATEGIES["fwd"]["base_url"]
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "config",
                          f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass



def scan_fwd():
    print("=== FWD Scanner (Workday + Pagination) ===")
    print("  [Plan C] Using common JD fetch function")
    print("  [Plan X] Unified field name to description")
    print(f"  URL: {FWD_URL}")
    scorer = CCOSCORER()

    # ── Stage 1: 分页抓取全部职位链接 ────────────────────────────
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        try:
            page.goto(FWD_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(7)
        except Exception as e:
            print(f"  [!] Load failed: {e}")
            _safe(page)
            browser.close()
            return []

        all_entries = []
        MAX_PAGES = 10
        PAGE_WAIT_S = 4

        for page_num in range(1, MAX_PAGES + 1):
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.0)

            seen_hrefs = set()
            entries = []
            for a in page.query_selector_all("a[href*='/job/']"):
                try:
                    href = a.get_attribute("href") or ""
                    text = " ".join(a.inner_text().split()).strip()
                    href_key = href.split("?")[0]
                    if not text or len(text) < 5 or href_key in seen_hrefs:
                        continue
                    seen_hrefs.add(href_key)
                    link = href if href.startswith("http") else FWD_URL.split("/en-US")[0] + href
                    entries.append({"title": text[:100], "link": link})
                except Exception:
                    pass

            new_links = {e["link"].split("?")[0] for e in entries}
            prev_links = {e["link"].split("?")[0] for e in all_entries}
            new_count = len(new_links - prev_links)

            print(f"  [Page {page_num}] {len(entries)} visible / +{new_count} new "
                  f"-> total: {len(all_entries) + new_count}")

            for e in entries:
                e["page_num"] = page_num
                link_key = e["link"].split("?")[0]
                if link_key not in prev_links:
                    all_entries.append(e)

            btn = page.query_selector("button[aria-label*='next']")
            if not btn:
                print(f"  [Done] No Next button")
                break
            disabled = btn.get_attribute("disabled")
            if disabled is not None:
                print(f"  [Done] Next button disabled")
                break

            print(f"  [→] Clicking Next...")
            try:
                btn.scroll_into_view_if_needed()
                time.sleep(0.8)
                btn.click()
                time.sleep(PAGE_WAIT_S)
            except Exception as e:
                print(f"  [!] Next click failed: {e}")
                break

        print(f"\n  [Stage 1 Done] {len(all_entries)} unique entries collected")
        _safe(page)

        # ── Stage 2: 批量获取 JD + 评分 ─────────────────────────
        all_matched = []
        raw_jobs = []
        # [Plan C] 创建独立 jd_page
        jd_page = new_page(ctx)

        # Plan X: 加载去重索引
        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0

        try:
            for i, job_data in enumerate(all_entries):
                title = job_data["title"]
                link = job_data["link"]
                job = {
                    "title": title, "company": NAME, "location": LOCATION,
                    "link": link, "keyword": "AI", "source": NAME,
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                # Plan X: 检查是否新岗位
                job_status = check_job_status(link, title, seen_data)
                if job_status == "unchanged":
                    existing = seen_data.get("jobs", {}).get(link, {})
                    print(f"  [{i+1}/{len(all_entries)} SKIP] {title[:50]} -> unchanged (seen {existing.get('first_seen', '?')})")
                    continue

                if job_status == "updated":
                    print(f"  [{i+1}/{len(all_entries)} UPDATE] {title[:50]} -> title changed")
                    updated_jobs_count += 1
                else:
                    print(f"  [{i+1}/{len(all_entries)} NEW] {title[:50]}")
                    new_jobs_count += 1

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"       FILTER -> {fr['reason']}")
                    update_job_entry(link, title, NAME, "", seen_data, job_status)
                    continue
                print(f"       PASS -> quick_filter passed")

                # [Plan C] 使用公共函数获取 JD
                jd_text = get_jd_from_url(jd_page, link, platform='workday')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars")

                # Plan X: 保存 JD 文件并更新索引
                entry = update_job_entry(link, title, NAME, jd_text, seen_data, job_status)
                job["jd_file"] = entry.get("jd_file", "")
                job["jd_chars"] = entry.get("jd_chars", 0)

                scored = score_job(job)
                if scored.get("isRecommended"):
                    all_matched.append(scored)
                    print(f"  [MATCH!] {title[:55]} -> P{scored.get('priority')} {scored.get('score')}")
                else:
                    print(f"  [SKIP ] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            _safe(jd_page)
            browser.close()
            # Plan X: 保存去重索引
            save_seen_jobs(seen_data)
            print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")

    # ── 保存 ─────────────────────────────────────────────────────
    os.makedirs(RAW_DIR, exist_ok=True)
    raw_file = os.path.join(RAW_DIR, f"fwd_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
    out_file = os.path.join(RAW_DIR, f"fwd_{datetime.now().strftime('%Y-%m-%d')}.json")

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
    scan_fwd()

