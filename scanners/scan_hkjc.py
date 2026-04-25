"""
HKJC Scanner - CDP + Table Parsing + Full Pagination
URL: https://careers.hkjc.com/search/?q=AI&locationsearch=hong+kong

架构: 两阶段
  Stage 1: 分页抓取所有职位链接（不离开列表页）
  Stage 2: 批量获取 JD 并评分（独立 page）+ Plan C/X
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import get_jd_from_url, append_scanner_to_excel  # Plan C + Excel 追加
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X
from cco_scorer import CCOSCORER, score_job

NAME = "HKJC"
KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_hkjc():
    print("=== HKJC Scanner ===")
    scorer = CCOSCORER()

    # ── Stage 1: 分页抓取全部职位链接 ────────────────────────────
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception:
            print("  [CDP] No Chrome at 9222, launching fresh browser")
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-dev-shm-usage",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            ])

        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        base_url = (
            "https://careers.hkjc.com/search/?createNewAlert=false"
            "&q=AI&locationsearch=hong+kong"
        )
        print(f"  [Stage 1] URL: {base_url}")

        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe(page)
            browser.close()
            return []

        # ── 翻页翻到底 ──────────────────────────────────────────────
        page_num = 0
        while True:
            page_num += 1
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            next_btn = None
            for sel in ["a[id*='nextPage']", "button.next", "a.next", "a[class*='next']",
                        "a[aria-label*='Next']", "button[aria-label*='next']"]:
                b = page.query_selector(sel)
                if b and b.is_enabled():
                    next_btn = b
                    break

            if next_btn:
                next_btn.scroll_into_view_if_needed()
                time.sleep(1)
                try:
                    next_btn.click()
                    time.sleep(3)
                    print(f"    Page {page_num} loaded")
                    continue
                except Exception:
                    pass
            break

        # ── 从表格中提取所有职位 ────────────────────────────────────
        all_entries = []
        seen_hrefs = set()

        rows = page.query_selector_all("table tr")
        print(f"  Table rows: {len(rows)} (header + {len(rows)-1} jobs)")

        for row in rows[1:]:
            try:
                cells = row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                title_cell = cells[0]
                title_el = title_cell.query_selector("a")
                if not title_el:
                    continue
                title = title_el.inner_text().strip()
                href = title_el.get_attribute("href") or ""
                if href and not href.startswith("http"):
                    href = f"https://careers.hkjc.com{href}"

                division = cells[1].inner_text().strip() if len(cells) > 1 else ""
                loc_cell = cells[2].inner_text().strip() if len(cells) > 2 else LOCATION

                if not title or not href:
                    continue

                href_key = href.split("?")[0].rstrip("/")
                if href_key in seen_hrefs:
                    continue
                seen_hrefs.add(href_key)

                all_entries.append({
                    "title": title,
                    "link": href,
                    "location": loc_cell,
                    "division": division,
                })
            except Exception:
                continue

        print(f"  [Stage 1 Done] {len(all_entries)} unique entries collected")
        _safe(page)

        # ── Stage 2: 批量获取 JD + 评分 ─────────────────────────
        all_matched = []
        raw_jobs = []
        jd_page = context.new_page()

        # Plan X: 加载去重索引
        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0

        try:
            for i, entry in enumerate(all_entries):
                title = entry["title"]
                link = entry["link"]
                job = {
                    "title": title,
                    "company": NAME,
                    "location": entry.get("location", LOCATION),
                    "division": entry.get("division", ""),
                    "link": link,
                    "keyword": KEYWORDS[0],
                    "source": NAME,
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

                # quick_filter 先过滤
                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"       FILTER -> {fr['reason']}")
                    update_job_entry(link, title, NAME, "", seen_data, job_status)
                    continue
                print(f"       PASS -> quick_filter passed")

                # Plan C: 获取 JD
                full_jd = get_jd_from_url(jd_page, link, platform='default')
                job["description"] = full_jd
                if full_jd:
                    print(f"       [JD] {len(full_jd)} chars")

                # Plan X: 保存 JD 文件并更新索引
                entry_x = update_job_entry(link, title, NAME, full_jd, seen_data, job_status)
                job["jd_file"] = entry_x.get("jd_file", "")
                job["jd_chars"] = entry_x.get("jd_chars", 0)

                scored = score_job(job)
                if scored.get("isRecommended") or scored.get("score", 0) >= 70:
                    all_matched.append(scored)
                    p_tag = scored.get("priority", "?")
                    s = scored.get("score", 0)
                    tag = "MATCH" if scored.get("isRecommended") else "P2"
                    print(f"  [{tag}] {title[:55]} → P{p_tag}/{s}")
                else:
                    print(f"  [SKIP] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            _safe(jd_page)
            browser.close()
            # Plan X: 保存去重索引
            save_seen_jobs(seen_data)
            print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")

    # ── 保存 ────────────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = os.path.join(RAW_DIR, f"hkjc_{today}.json")
    os.makedirs(RAW_DIR, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "source": NAME,
            "date": datetime.now().isoformat(),
            "total_found": len(all_matched),
            "raw_count": len(all_entries),
            "jobs": all_matched
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(all_matched)} matched / {len(all_entries)} raw")

    # 追加到 Excel
    append_scanner_to_excel(out_file)

    return all_matched


if __name__ == "__main__":
    scan_hkjc()
