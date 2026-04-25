# -*- coding: utf-8 -*-
"""
Sun Life Scanner - Workday平台 + 分页
URL: https://sunlife.wd3.myworkdayjobs.com/en-US/Experienced-Jobs?q=AI

[Plan C] 使用 job_scanner_base.get_jd_from_url() 统一 JD 抓取
[Plan X] 使用 seen_jobs 做跨会话去重
"""
import sys, os, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel  # Plan C + Excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X

NAME = "SunLife"
BASE_URL = "https://sunlife.wd3.myworkdayjobs.com/en-US/Experienced-Jobs"
LOCATION = "Hong Kong"
KEYWORDS = ["AI"]
SUNLIFE_URL = SCAN_STRATEGIES["sunlife"]["base_url"]
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
TODAY = datetime.now().strftime("%Y-%m-%d")
RAW_FILE = os.path.join(RAW_DIR, f"sunlife_raw_{TODAY}.json")
OUT_FILE = os.path.join(RAW_DIR, f"sunlife_{TODAY}.json")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_sunlife():
    print("=== Sun Life Scanner (Workday + Pagination) ===")
    print("  [Plan C] get_jd_from_url | [Plan X] seen_jobs dedup | [append] Excel")
    scorer = CCOSCORER()
    seen_data = load_seen_jobs()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        url = SUNLIFE_URL
        print(f"  [Stage 1] URL: {url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(7)
        except Exception as e:
            print(f"  [!] Load failed: {e}")
            _safe(page); browser.close(); return []

        all_entries = []
        TOTAL_EXPECTED = 41

        def get_status_text():
            for p in page.query_selector_all("p"):
                t = p.inner_text().strip()
                if "of" in t and "job" in t.lower():
                    return t
            return ""

        page_num = 0
        print(f"  [Page 0] status: {get_status_text()}")

        while True:
            page_num += 1
            if page_num > 10:
                print("  [Done] Max pages reached"); break

            try:
                page.wait_for_selector("a[href*='/job/']", timeout=15000)
            except Exception:
                pass
            time.sleep(3)

            for _ in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.0)

            seen_hrefs = set(); entries = []
            for a in page.query_selector_all("a[href*='/job/']"):
                try:
                    href = a.get_attribute("href") or ""
                    if not href or href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)
                    text = " ".join(a.inner_text().split()).strip()
                    slug = href.split("/job/")[-1].split("?")[0] if "/job/" in href else ""
                    slug_clean = slug.replace("-", " ").replace("_", " ")
                    if not text or len(text) < 5:
                        continue
                    link = href if href.startswith("http") else BASE_URL + href
                    title_for_filter = f"{text} {slug_clean}".strip()[:200]
                    entries.append({"title": text[:100], "title_for_filter": title_for_filter, "link": link})
                except Exception:
                    pass

            new_count = sum(1 for e in entries
                            if e["link"] not in {x["link"] for x in all_entries})
            status = get_status_text()
            print(f"  [Page {page_num}] {len(entries)} visible / +{new_count} new -> total: {len(all_entries) + new_count} | {status}")
            for e in entries:
                if e["link"] not in {x["link"] for x in all_entries}:
                    all_entries.append(e)

            if len(all_entries) >= TOTAL_EXPECTED:
                print(f"  [Done] All {TOTAL_EXPECTED} jobs collected"); break

            import re
            m = re.search(r'(\d+)\s*-\s*(\d+)\s*of\s*(\d+)', status)
            if m:
                _, end, total = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if end >= total:
                    print(f"  [Done] Last page reached ({end} of {total})"); break

            btn = page.query_selector('button[aria-label*="next"]')
            if not btn:
                print("  [Done] No Next button"); break
            if btn.get_attribute("disabled") is not None:
                print("  [Done] Next disabled"); break

            prev_start = int(m.group(1)) if m else 1
            print("  [->] Clicking Next...")
            try:
                btn.scroll_into_view_if_needed(); time.sleep(1); btn.click()
            except Exception as e:
                print(f"  [!] Next click failed: {e}"); break

            page_loaded = False
            for _ in range(20):
                time.sleep(1)
                status2 = get_status_text()
                m2 = re.search(r'(\d+)\s*-\s*(\d+)\s*of', status2)
                if m2:
                    new_start = int(m2.group(1))
                    if new_start != prev_start:
                        print(f"  [Page changed] {status2}")
                        page_loaded = True
                        break
            if not page_loaded:
                print("  [!] Status did not change -- continuing")

        print(f"\n  [Stage 1 Done] {len(all_entries)} unique entries")
        _safe(page)

        # ---- Stage 2: Plan C JD fetch + Plan X dedup ----
        all_matched = []; raw_jobs = []
        jd_page = new_page(ctx)

        try:
            for i, job_data in enumerate(all_entries):
                title = job_data["title"]; link = job_data["link"]
                title_for_filter = job_data.get("title_for_filter", title)
                job = {"title": title, "company": NAME, "location": LOCATION,
                       "link": link, "keyword": "AI", "source": NAME,
                       "scraped_at": datetime.now().isoformat()}
                raw_jobs.append(job)

                status = check_job_status(link, title, seen_data)
                if status == "unchanged":
                    prev_entry = seen_data.get("jobs", {}).get(link, {})
                    prev_score = prev_entry.get("score", "?")
                    print(f"  [{i+1}/{len(all_entries)} SKIP] {title[:45]} -> unchanged (score {prev_score})")
                    continue
                elif status == "updated":
                    print(f"  [{i+1}/{len(all_entries)} UPDATE] {title[:45]} -> JD changed (re-scoring)")
                else:
                    print(f"  [{i+1}/{len(all_entries)} NEW] {title[:45]}")

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    update_job_entry(link, title, NAME, "", seen_data, status)
                    print(f"  [{i+1}/{len(all_entries)} FILTER] {title[:45]} - {fr['reason']}")
                    continue
                print(f"  [{i+1}/{len(all_entries)} PASS] {title_for_filter[:55]}")

                # [Plan C] 统一 JD 抓取
                full_jd = get_jd_from_url(jd_page, link, platform='workday')
                job["description"] = full_jd
                if full_jd:
                    print(f"    [JD] {len(full_jd)} chars")

                scored = score_job(job)
                update_job_entry(link, title, NAME, full_jd or "", seen_data, status)
                if scored.get("isRecommended"):
                    all_matched.append(scored)
                    print(f"  [MATCH!] {title[:55]} -> P{scored.get('priority')} {scored.get('score')}")
                else:
                    print(f"  [SKIP ] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            _safe(jd_page)
            browser.close()

    save_seen_jobs(seen_data)

    # 去重
    seen_links = set()
    unique = [j for j in all_matched
              if j.get("link") not in seen_links and not seen_links.add(j.get("link"))]
    all_matched = unique

    os.makedirs(RAW_DIR, exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": NAME, "date": datetime.now().isoformat(),
                   "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source": NAME, "date": datetime.now().isoformat(),
                   "total_found": len(all_matched), "jobs": all_matched}, f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_matched)}")
    append_scanner_to_excel(OUT_FILE)
    return all_matched


if __name__ == "__main__":
    scan_sunlife()
