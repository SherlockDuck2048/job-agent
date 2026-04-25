"""
Manulife Scanner - Workday + Full Pagination
URL: 从 config/scan_strategies.py 读取 (Manulife Workday HK filter)
参考 AIA/SunLife: 翻页到底 + href去重 + URL slug合并标题

完成后自动合并到 HK_AI_Jobs_All.xlsx
"""
import sys, os, json, time, re
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import score_job
from job_scanner_base import get_jd_from_url, append_scanner_to_excel  # Plan C + Excel 追加
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X

KEYWORDS = ["AI"]
OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "candidates", "raw",
    f"manulife_{datetime.now().strftime('%Y-%m-%d')}.json"
)

# 从 scan_strategies.py 读取正确 URL（包含 Location_Country 香港过滤）
_MANULIFE_CONFIG = SCAN_STRATEGIES["manulife"]
MANULIFE_URL = _MANULIFE_CONFIG["base_url"]   # 包含 Location_Country=d4afde...
MANULIFE_JOBS_HOST = urlparse(MANULIFE_URL).netloc  # 从 URL 提取 hostname


def _normalize_href(href, host=MANULIFE_JOBS_HOST) -> str:
    """标准化 href，返回无query的主干路径（含Job ID），用于去重"""
    if not href:
        return ""
    if not href.startswith("http"):
        href = f"https://{host}{href}"
    u = urlparse(href)
    # 保留 pathname（含 Job ID），去掉 query
    return f"{u.scheme}://{u.netloc}{u.path}"


def _title_for_filter(link_el) -> str:
    """
    合并可见标题 + URL slug 作为过滤用标题。
    URL slug 包含关键词（如 Learning---Development），
    纯 inner_text 可能丢失。
    """
    title = link_el.inner_text().strip()
    href = link_el.get_attribute("href") or ""
    slug = ""
    # 从 URL path 提取 slug（/en-US/MFCJH_Jobs/job/LOCATION/TITLE -> TITLE）
    if "/job/" in href:
        slug = href.split("/job/")[-1].split("/")[0]
        # 把 - 还原为空格（slug用-连接）
        slug = slug.replace("-", " ")
    # 合并：优先用更长的（通常slug包含更多词）
    combined = f"{title} {slug}".strip()
    return combined if combined else title


def scan_manulife():
    print("=== Manulife Scanner (Workday + Pagination) ===")

    all_entries = []   # Stage 1 raw entries (href去重)
    all_jobs = []       # Stage 2 matched jobs
    raw_jobs = []       # Plan C: 所有原始岗位（含JD）
    seen_hrefs = set()  # href主干去重

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        # 搜索 URL - 从 scan_strategies.py 读取（包含香港 Location_Country 过滤）
        url = MANULIFE_URL
        print(f"\n[Stage 1] URL: {url}")

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            browser.close()
            return []

        # 接受 cookie
        try:
            accept = page.query_selector('button:has-text("Accept Cookies")')
            if accept:
                accept.click()
                time.sleep(1)
        except:
            pass

        # 等待初始加载
        time.sleep(3)

        # === 分页抓取 Stage 1 ===
        page_num = 0
        prev_status = ""
        max_pages = 50

        while page_num < max_pages:
            # 等待 job cards 出现
            try:
                page.wait_for_selector(
                    'a[href*="/MFCJH_Jobs/job/"]',
                    timeout=15000
                )
            except:
                pass

            time.sleep(2)  # 等待 JS 渲染

            # 找分页状态文字
            status = ""
            try:
                body = page.inner_text("body")
                # 找 "X - Y of Z jobs" 模式
                match = re.search(r'(\d[\d,]*)\s*-\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)\s*job', body, re.IGNORECASE)
                if match:
                    status = f"{match.group(1)} - {match.group(2)} of {match.group(3)} jobs"
            except:
                pass

            # 收集本页面所有职位链接
            link_els = page.query_selector_all('a[href*="/MFCJH_Jobs/job/"]')
            new_count = 0

            for el in link_els:
                try:
                    href = el.get_attribute("href") or ""
                    if not href:
                        continue

                    # href主干去重
                    norm_href = _normalize_href(href)
                    if norm_href in seen_hrefs:
                        continue
                    seen_hrefs.add(norm_href)

                    # 标题：可见文字优先，合并URL slug
                    title = el.inner_text().strip()
                    if not title or len(title) < 3:
                        continue

                    slug = ""
                    if "/job/" in href:
                        slug_part = href.split("/job/")[-1].split("/")[0]
                        slug = slug_part.replace("-", " ")

                    combined_title = f"{title} {slug}".strip()
                    display_title = combined_title if len(combined_title) > len(title) else title

                    entry = {
                        "title": display_title,
                        "raw_title": title,
                        "href": norm_href,
                        "slug": slug,
                        "link": norm_href,
                        "source": "Manulife",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    all_entries.append(entry)
                    new_count += 1

                except Exception as e:
                    continue

            total = len(all_entries)
            # Use stdout.write to avoid cp1252 encoding issues
            import sys as _sys
            _sys.stdout.write(f"  [Page {page_num}] {len(link_els)} visible / +{new_count} new -> total: {total} | status: {status or 'n/a'}\n")
            _sys.stdout.flush()

            # 最后一页判断：状态文字到达末尾（如 "668 - 668 of 668 jobs"）
            if status:
                m = re.search(r'(\d+)\s*-\s*(\d+)\s*of\s*(\d+)', status, re.IGNORECASE)
                if m and int(m.group(2)) >= int(m.group(3)):
                    print(f"  [Done] Reached last page: {status}")
                    break

            # 点击下一页
            page_num += 1
            next_clicked = False

            try:
                # 方式1: aria-label=next 按钮
                next_btn = page.query_selector('button[aria-label="next"]')
                if next_btn and next_btn.is_enabled():
                    next_btn.click()
                    next_clicked = True
                else:
                    # 方式2: 找数字页码按钮（如 page 2）
                    page.wait_for_selector('button[aria-label="page 2"]', timeout=5000)
                    btn2 = page.query_selector('button[aria-label="page 2"]')
                    if btn2 and btn2.is_enabled():
                        btn2.click()
                        next_clicked = True
            except Exception as e:
                pass

            if not next_clicked:
                print(f"  [Stop] No next button found after page {page_num - 1}")
                break

            # 等待页面变化
            time.sleep(3)

        print(f"\n[Stage 1 Done] {len(all_entries)} unique entries (href-deduped)")

        # === Stage 2: JD 抓取 + 评分 (Plan C + Plan X) ===
        jd_page = context.new_page()
        
        # 加载 Plan X 去重索引
        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0
        
        try:
            for i, entry in enumerate(all_entries, 1):
                title = entry["title"]
                link = entry["link"]

                job = {
                    "title": title,
                    "company": "Manulife",
                    "location": "Hong Kong",
                    "link": link,
                    "source": "Manulife",
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                # Plan X: 检查是否新岗位
                job_status = check_job_status(link, title, seen_data)
                if job_status == "unchanged":
                    # 已存在且无变化，跳过 JD 抓取
                    existing_entry = seen_data.get("jobs", {}).get(link, {})
                    sys.stdout.write(f"  [{i}/{len(all_entries)} SKIP] {title[:50]} -> unchanged (seen {existing_entry.get('first_seen', '?')})\n")
                    sys.stdout.flush()
                    continue
                
                if job_status == "updated":
                    sys.stdout.write(f"  [{i}/{len(all_entries)} UPDATE] {title[:50]} -> title changed\n")
                    sys.stdout.flush()
                    updated_jobs_count += 1
                else:
                    sys.stdout.write(f"  [{i}/{len(all_entries)} NEW] {title[:50]}\n")
                    sys.stdout.flush()
                    new_jobs_count += 1

                # 先做 quick filter（基于 title）
                scored = score_job(job)
                if not scored.get("isRecommended"):
                    sys.stdout.write(f"       FILTER -> {scored.get('reason', '')[:40]}\n")
                    sys.stdout.flush()
                    # 仍然保存到 seen_jobs（记录已处理）
                    update_job_entry(link, title, "Manulife", "", seen_data, job_status)
                    continue

                sys.stdout.write(f"       PASS -> quick_filter passed\n")
                sys.stdout.flush()

                # Plan C: 获取完整 JD
                full_jd = get_jd_from_url(jd_page, link, platform='workday')
                job["description"] = full_jd
                if full_jd:
                    sys.stdout.write(f"       [JD] {len(full_jd)} chars\n")
                    sys.stdout.flush()

                # Plan X: 保存 JD 文件并更新索引
                entry = update_job_entry(link, title, "Manulife", full_jd, seen_data, job_status)
                job["jd_file"] = entry.get("jd_file", "")
                job["jd_chars"] = entry.get("jd_chars", 0)

                # 带 JD 重新评分
                scored_with_jd = score_job(job)
                if scored_with_jd.get("isRecommended"):
                    all_jobs.append(scored_with_jd)
                    sys.stdout.write(f"  [MATCH!] {title[:55]} -> {scored_with_jd.get('priority')} {scored_with_jd.get('score')}\n")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"  [SKIP ] {title[:55]} ({scored_with_jd.get('priority')} {scored_with_jd.get('score')})\n")
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
            "source": "Manulife",
            "date": datetime.now().isoformat(),
            "total_raw": len(all_entries),
            "total_matched": len(all_jobs),
            "jobs": all_jobs,
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matched_out, f, ensure_ascii=False, indent=2)

        # 同时写 raw 文件（包含所有条目，方便调试）
        raw_out = {
            "source": "Manulife",
            "date": datetime.now().isoformat(),
            "total_raw": len(all_entries),
            "jobs": all_entries,
        }
        raw_file = OUTPUT_FILE.replace("_raw_", "_raw_").replace(".json", "_raw.json")
        # 如果文件名不含 raw，加上 raw
        if "raw" not in os.path.basename(OUTPUT_FILE):
            raw_file = OUTPUT_FILE.replace(".json", "_raw.json")
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_out, f, ensure_ascii=False, indent=2)

        print(f"\n[MATCHED] {len(all_jobs)} jobs -> {OUTPUT_FILE}")
        print(f"[RAW] {len(all_entries)} entries -> {raw_file}")

        browser.close()
        return all_jobs


if __name__ == "__main__":
    results = scan_manulife()
    # 只追加本次扫描的数据到 Excel（不处理其他扫描器）
    append_scanner_to_excel(OUTPUT_FILE)
