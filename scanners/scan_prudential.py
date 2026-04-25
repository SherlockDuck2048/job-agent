# -*- coding: utf-8 -*-
"""
Prudential Scanner - Workday platform
修复：
  1. 翻页翻到底 — 等状态文字稳定
  2. href 去重 > title 去重
  3. URL slug + 标题合并作为过滤依据
  4. 先 dry-run — 打印数量，和网站对比，差得多必有漏
从 config/scan_strategies.py 读取 base_url
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from job_scanner_base import get_jd_from_url, append_scanner_to_excel  # Plan C + Excel 追加
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import score_job

PRUDENTIAL_URL = SCAN_STRATEGIES["prudential"]["base_url"]
PRUD_HOST = urlparse(PRUDENTIAL_URL).netloc
LOCATION = "Hong Kong"

KEYWORDS = ["AI"]
OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "candidates", "raw",
    f"prudential_{datetime.now().strftime('%Y-%m-%d')}.json"
)


def _normalize_href(href: str) -> str:
    """去除 query string，按完整 path 去重（JR ID 在 path 里）"""
    if not href:
        return ""
    if not href.startswith("http"):
        href = f"https://{PRUD_HOST}{href}"
    u = urlparse(href)
    return f"{u.scheme}://{u.netloc}{u.path}"


def _extract_location_from_url(href: str) -> str:
    """从 URL path 提取地点。格式: /en-US/prudential/job/{LOCATION}/{TITLE}_JR..."""
    try:
        if not href.startswith("http"):
            href = f"https://{PRUD_HOST}{href}"
        u = urlparse(href)
        parts = [p for p in u.path.split("/") if p]
        # parts[0]=en-US, [1]=prudential, [2]=job, [3]=LOCATION, [4]=TITLE_JR...
        if len(parts) >= 4 and parts[2] == "job":
            return parts[3].replace("-", " ")
    except Exception:
        pass
    return "Unknown"


def scan_prudential(dry_run=True):
    """dry_run=True: 只收集数量不评分；dry_run=False: 完整评分"""
    mode = "DRY RUN" if dry_run else "FULL SCAN"
    print(f"=== Prudential Scanner ({mode}) ===")

    all_entries = []
    seen_hrefs = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        print(f"\n[Stage 1] URL: {PRUDENTIAL_URL}")
        try:
            page.goto(PRUDENTIAL_URL, wait_until="networkidle", timeout=30000)
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
            # 等待卡片加载
            try:
                page.wait_for_selector('a[href*="/job/"]', timeout=10000)
            except Exception:
                break
            time.sleep(2)

            # 状态文字
            body = page.inner_text("body")
            m = re.search(
                r'(\d[\d,]*)\s*-\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)\s*job',
                body, re.IGNORECASE
            )
            if m:
                cur_start, cur_end, total = int(m.group(1)), int(m.group(2)), int(m.group(3))
                status = f"Showing {cur_start}-{cur_end} of {total}"
            else:
                status = "n/a"
                cur_start = cur_end = total = -1

            # 收集本页面所有职位链接
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

                    # === URL slug + 标题合并作为过滤依据 ===
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
                        "slug": slug,
                        "location": LOCATION,
                        "link": norm,
                        "source": "Prudential",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    all_entries.append(entry)
                    new_count += 1
                except Exception:
                    continue

            print(f"  [Page {page_num}] +{new_count} new -> total: {len(all_entries)} | {status}")

            # === 翻页翻到底：状态文字稳定则停止 ===
            if m:
                if cur_end >= total:
                    print(f"  [Done] Last page reached ({cur_end}/{total})")
                    break

            page_num += 1
            clicked = False
            try:
                nb = page.query_selector('button[aria-label="next"]')
                if nb and nb.is_enabled():
                    nb.click()
                    clicked = True
                    time.sleep(3)
                    # 等状态文字变化（下一页加载完）
                    for _ in range(15):
                        time.sleep(1)
                        body2 = page.inner_text("body")
                        m2 = re.search(
                            r'(\d[\d,]*)\s*-\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)\s*job',
                            body2, re.IGNORECASE
                        )
                        if m2 and int(m2.group(2)) != (cur_end if m else -1):
                            break
            except Exception:
                pass
            if not clicked:
                print(f"  [Stop] No next button after page {page_num - 1}")
                break

        print(f"\n[Stage 1 Done] {len(all_entries)} unique entries")

        if dry_run:
            browser.close()
            return all_entries

        # === Stage 2: 完整评分 (Plan C + Plan X) ===
        # Plan X: 加载去重索引
        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0
        
        all_jobs = []
        jd_page = context.new_page()
        
        try:
            for i, entry in enumerate(all_entries, 1):
                title = entry["title"]
                link = entry["link"]

                # Plan X: 检查是否新岗位
                job_status = check_job_status(link, title, seen_data)
                if job_status == "unchanged":
                    existing = seen_data.get("jobs", {}).get(link, {})
                    print(f"  [{i}/{len(all_entries)} SKIP] {title[:50]} -> unchanged (seen {existing.get('first_seen', '?')})")
                    continue
                
                if job_status == "updated":
                    print(f"  [{i}/{len(all_entries)} UPDATE] {title[:50]} -> title changed")
                    updated_jobs_count += 1
                else:
                    print(f"  [{i}/{len(all_entries)} NEW] {title[:50]}")
                    new_jobs_count += 1

                job = {
                    "title": title, 
                    "company": "Prudential",
                    "location": entry["location"],
                    "link": link, 
                    "keyword": "AI", 
                    "source": "Prudential",
                    "scraped_at": datetime.now().isoformat()
                }

                # 先 quick filter
                job_for_filter = {"title": title, "href": link}
                scored = score_job(job_for_filter)

                if not scored.get("isRecommended"):
                    reason = scored.get("reason", "")[:40]
                    print(f"       FILTER -> {reason}")
                    # 仍然保存到 seen_jobs（记录已处理）
                    update_job_entry(link, title, "Prudential", "", seen_data, job_status)
                    continue
                
                print(f"       PASS -> quick_filter passed")

                # Plan C: 获取完整 JD
                full_jd = get_jd_from_url(jd_page, link, platform='workday')
                job["description"] = full_jd
                if full_jd:
                    print(f"       [JD] {len(full_jd)} chars")
                else:
                    print(f"       [JD] empty (使用 title-only 评分)")

                # Plan X: 保存 JD 文件并更新索引
                entry_data = update_job_entry(link, title, "Prudential", full_jd, seen_data, job_status)
                job["jd_file"] = entry_data.get("jd_file", "")
                job["jd_chars"] = entry_data.get("jd_chars", 0)

                # 有 JD 时用完整评分；无 JD 但 title 通过 quick_filter 时直接推荐
                if full_jd:
                    scored_with_jd = score_job(job)
                else:
                    # 无 JD → 直接用 title 推荐（quick_filter 已通过，说明 title 够好）
                    scored_with_jd = {
                        "isRecommended": True,
                        "priority": "P1",
                        "score": 75,
                        "reason": "title-only (JD为空)",
                        "title": title,
                        "link": link,
                    }
                if scored_with_jd.get("isRecommended"):
                    scored_with_jd["location"] = entry["location"]
                    scored_with_jd["raw_title"] = entry["raw_title"]
                    all_jobs.append(scored_with_jd)
                    print(f"  [MATCH!] {title[:55]} -> {scored_with_jd.get('priority')} {scored_with_jd.get('score')}")
                else:
                    print(f"  [SKIP ] {title[:55]} ({scored_with_jd.get('priority')} {scored_with_jd.get('score')})")
                sys.stdout.flush()
        finally:
            try:
                jd_page.close()
            except:
                pass
            # Plan X: 保存去重索引
            save_seen_jobs(seen_data)
            print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")

    # === 写文件 ===
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    matched_out = {
        "source": "Prudential", "date": datetime.now().isoformat(),
        "total_raw": len(all_entries), "total_matched": len(all_jobs),
        "jobs": all_jobs,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(matched_out, f, ensure_ascii=False, indent=2)

    raw_file = OUTPUT_FILE.replace(".json", "_raw.json")
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Prudential", "date": datetime.now().isoformat(),
            "total_raw": len(all_entries), "jobs": all_entries,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[MATCHED] {len(all_jobs)} jobs -> {OUTPUT_FILE}")
    print(f"[RAW]     {len(all_entries)} entries -> {raw_file}")
    
    # 追加到 Excel
    append_scanner_to_excel(OUTPUT_FILE)
    
    return all_jobs


if __name__ == "__main__":
    import sys as _sys
    dry_run = "--no-dry-run" not in _sys.argv
    scan_prudential(dry_run=dry_run)

