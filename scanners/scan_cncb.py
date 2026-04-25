# -*- coding: utf-8 -*-
"""
CNCB Scanner - Workday + Full Pagination
从 config/scan_strategies.py 读取 base_url
遵循：翻页翻到底 + href去重 + URL slug+标题合并过滤 + 先dry-run
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from job_scanner_base import append_scanner_to_excel, get_jd_from_url, new_page
from seen_jobs import load_seen_jobs, update_job_entry, save_seen_jobs
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import score_job

CNCBI_URL = SCAN_STRATEGIES["cncbi"]["base_url"]
CNCB_HOST = urlparse(CNCBI_URL).netloc

KEYWORDS = ["AI"]
OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "candidates", "raw",
    f"cncb_{datetime.now().strftime('%Y-%m-%d')}.json"
)


def _normalize_href(href: str) -> str:
    if not href:
        return ""
    if not href.startswith("http"):
        href = f"https://{CNCB_HOST}{href}"
    u = urlparse(href)
    return f"{u.scheme}://{u.netloc}{u.path}"


def _extract_location_from_url(href: str) -> str:
    """从 URL path 提取地点。格式: /zh-CN/CNCBIExternalCareerSite/job/{LOCATION}/{TITLE}_JR..."""
    try:
        if not href.startswith("http"):
            href = f"https://{CNCB_HOST}{href}"
        u = urlparse(href)
        parts = [p for p in u.path.split("/") if p]
        # parts[0]=zh-CN, [1]=CNCBIExternalCareerSite, [2]=job, [3]=LOCATION, [4]=TITLE_JR...
        if len(parts) >= 4 and parts[2] == "job":
            return parts[3].replace("-", " ")
    except Exception:
        pass
    return "Unknown"


def scan_cncb():
    print("=== CNCB Scanner (Workday + Pagination) ===")

    all_entries = []
    all_jobs = []
    seen_hrefs = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        print(f"\n[Stage 1] URL: {CNCBI_URL}")

        try:
            page.goto(CNCBI_URL, wait_until="networkidle", timeout=30000)
            time.sleep(3)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            browser.close()
            return []

        # Accept cookies
        try:
            page.get_by_text("Accept", exact=False).first.click()
            time.sleep(1)
        except Exception:
            pass
        time.sleep(3)

        # === Pagination Stage 1 ===
        page_num = 0
        max_pages = 50

        while page_num < max_pages:
            try:
                page.wait_for_selector('a[href*="/job/"]', timeout=10000)
            except Exception:
                break
            time.sleep(2)

            body = page.inner_text("body")
            m = re.search(r'(\d[\d,]*)\s*-\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)\s*job', body, re.IGNORECASE)
            status = f"Showing {m.group(1)}-{m.group(2)} of {m.group(3)}" if m else "n/a"

            link_els = page.query_selector_all('a[href*="/job/"]')
            new_count = 0

            for el in link_els:
                try:
                    href = el.get_attribute("href") or ""
                    if not href:
                        continue

                    norm = _normalize_href(href)
                    if norm in seen_hrefs:
                        continue
                    seen_hrefs.add(norm)

                    title = el.inner_text().strip()
                    if not title or len(title) < 3:
                        continue

                    location = _extract_location_from_url(href)

                    slug = ""
                    if "/job/" in href:
                        slug_part = href.split("/job/")[-1].split("/")[0]
                        slug = slug_part.replace("-", " ")

                    combined_title = f"{title} {slug}".strip()
                    display_title = combined_title if len(combined_title) > len(title) else title

                    entry = {
                        "title": display_title,
                        "raw_title": title,
                        "href": norm,
                        "location": location,
                        "slug": slug,
                        "link": norm,
                        "source": "CNCB",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    all_entries.append(entry)
                    new_count += 1
                except Exception:
                    continue

            print(f"  [Page {page_num}] +{new_count} new -> total: {len(all_entries)} | {status}")

            if m and int(m.group(2)) >= int(m.group(3)):
                print(f"  [Done] Last page reached")
                break

            page_num += 1
            clicked = False
            try:
                nb = page.query_selector('button[aria-label="next"]')
                if nb and nb.is_enabled():
                    nb.click(); clicked = True
            except Exception:
                pass
            if not clicked:
                print(f"  [Stop] No next button after page {page_num - 1}")
                break
            time.sleep(3)

        print(f"\n[Stage 1 Done] {len(all_entries)} unique entries")

        # === Stage 2: [Plan C] JD + [Plan X] 去重 + 评分 ===
        seen_data = load_seen_jobs()
        new_matched = []

        for i, entry in enumerate(all_entries, 1):
            title = entry["title"]
            link = entry["link"]

            # [Plan C] 抓取 JD
            jd_pg = new_page(context)
            try:
                jd_text = get_jd_from_url(jd_pg, link, platform="workday")
            finally:
                jd_pg.close()

            job_for_score = {
                "title": title,
                "href": link,
                "description": jd_text,
                "location": entry["location"],
            }
            scored = score_job(job_for_score)

            if scored.get("isRecommended"):
                # [Plan X] 去重检查
                link_key = scored.get("link", link)
                title_hash = hash(scored.get("title", title).lower().strip())
                is_new = True
                status = "new"
                if link_key in seen_data.get("jobs", {}):
                    prev = seen_data["jobs"][link_key]
                    if prev.get("title_hash") == title_hash:
                        is_new = False
                        status = "unchanged"
                    else:
                        status = "updated"
                if is_new:
                    update_job_entry(link_key, scored.get("title", ""), "CNCB", scored.get("description", ""), seen_data, status)
                    scored["location"] = entry["location"]
                    scored["raw_title"] = entry["raw_title"]
                    new_matched.append(scored)
                    sys.stdout.write(f"  [{i}/{len(all_entries)} MATCH! {status.upper()}] {title[:55]} -> {scored.get('priority')} {scored.get('score')}\n")
                else:
                    sys.stdout.write(f"  [{i}/{len(all_entries)} MATCH! UNCHANGED] {title[:55]}\n")
            else:
                reason = scored.get("reason", "")[:40]
                sys.stdout.write(f"  [{i}/{len(all_entries)} FILTER] {title[:50]} -> {reason}\n")
            sys.stdout.flush()

        browser.close()

        # [Plan X] 保存去重索引
        save_seen_jobs(seen_data)
        all_jobs = new_matched

    # === Write output ===
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    matched_out = {
        "source": "CNCB", "date": datetime.now().isoformat(),
        "total_raw": len(all_entries), "total_matched": len(all_jobs),
        "jobs": all_jobs,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(matched_out, f, ensure_ascii=False, indent=2)

    raw_file = OUTPUT_FILE.replace(".json", "_raw.json")
    raw_out = {
        "source": "CNCB", "date": datetime.now().isoformat(),
        "total_raw": len(all_entries), "jobs": all_entries,
    }
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(raw_out, f, ensure_ascii=False, indent=2)

    print(f"\n[MATCHED] {len(all_jobs)} jobs -> {OUTPUT_FILE}")
    print(f"[RAW]     {len(all_entries)} entries -> {raw_file}")

    # [Excel] 追加到汇总文件
    append_scanner_to_excel(OUTPUT_FILE)

    return all_jobs


if __name__ == "__main__":
    scan_cncb()

