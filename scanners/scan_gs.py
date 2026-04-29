"""
Goldman Sachs Scanner
URL: from scan_strategies.py
特点: Next.js SPA, 职位列表在页面文本中
架构: 两阶段
  Stage 1: 分页提取所有职位条目
  Stage 2: 点击卡片获取 JD + 评分 (Plan C + Plan X)
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import score_job

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from job_scanner_base import append_scanner_to_excel, get_jd_from_url
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
from scan_strategies import SCAN_STRATEGIES

STRATEGY = SCAN_STRATEGIES.get("goldman", {})
NAME = "Goldman Sachs"
BASE_URL = STRATEGY.get("url", "https://higher.gs.com/results?LOCATION=Hong%20Kong&page=1&search=AI&sort=RELEVANCE")

KEYWORD = "AI"
LOCATION = "Hong Kong"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
OUTPUT_FILE = os.path.join(RAW_DIR, f"gs_{datetime.now().strftime('%Y-%m-%d')}.json")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _normalize_href(href):
    if not href:
        return ""
    href = href.split("?")[0]
    href = href.rstrip("/")
    return href.lower()


def extract_gs_jobs_from_text(page_text):
    """从 GS 页面文本提取职位"""
    jobs = []
    lines = [l.strip() for l in page_text.split('\n') if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        is_title = False
        if any(k in line for k in ['Investment Banking', 'Wealth Management', 'Compliance', 'Asset Management',
                                      'Global Banking', 'Private Wealth', 'Control Room', 'Risk', 'Finance']):
            if 20 < len(line) < 200 and chr(183) not in line and not line.startswith('Hong Kong'):
                is_title = True

        if not is_title:
            i += 1
            continue

        title = line
        loc = LOCATION
        level = ""
        function = ""

        for j in range(i+1, min(i+6, len(lines))):
            next_line = lines[j]
            if next_line == "Hong Kong" or next_line == "Beijing/Hong Kong":
                loc = next_line
            if chr(183) + 'Associate' in next_line or next_line == 'Associate':
                level = "Associate"
            elif chr(183) + 'Vice President' in next_line or next_line == 'Vice President':
                level = "Vice President"
            elif chr(183) + 'Analyst' in next_line or next_line == 'Analyst':
                level = "Analyst"
            if level and not function:
                if any(k in next_line for k in ['Banker', 'Sales', 'Control', 'Management', 'Support', 'Coverage']):
                    function = next_line
                    break
            if 'share' in next_line.lower() or 'bookmark' in next_line.lower():
                break
            if any(k in next_line for k in ['Investment Banking', 'Wealth Management', 'Compliance']) and len(next_line) > 30:
                break

        jobs.append({
            "title": title,
            "href": "",
            "location": loc,
            "level": level,
            "function": function
        })
        i += 1

    return jobs


def scan_gs():
    print("=== Goldman Sachs Scanner ===")
    print(f"  Base URL from scan_strategies: {BASE_URL[:80]}...")

    # Stage 1: 分页提取全部职位
    all_entries = []
    all_raw_jobs = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("  [CDP] Connected to Chrome at 9222")
        except Exception:
            print("  [CDP] No Chrome at 9222, launching fresh browser")
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"]
            )

        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        seen_hrefs = set()
        seen_titles = set()
        page_num = 1
        prev_status_text = ""
        stable_count = 0

        while True:
            url = re.sub(r'page=\d+', f'page={page_num}', BASE_URL)
            url = re.sub(r'search=[^&]*', f'search={KEYWORD.replace(" ", "%20")}', url)

            print(f"  [Page {page_num}] {url[:80]}...")

            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(5)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                break

            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            page_text = page.inner_text('body')
            raw_jobs = extract_gs_jobs_from_text(page_text)
            print(f"    Found {len(raw_jobs)} jobs from text")

            status_match = re.search(r'Showing\s+(\d+)\s+of\s+(\d+)\s+matches', page_text)
            status_text = status_match.group(0) if status_match else ""

            if status_text == prev_status_text:
                stable_count += 1
                if stable_count >= 2:
                    print(f"    -> Status stable ({status_text}), no more pages")
                    break
            else:
                stable_count = 0
                prev_status_text = status_text

            page_count = 0
            for rj in raw_jobs:
                title = rj["title"]
                href = rj["href"]

                href_key = _normalize_href(href)
                if href_key and href_key in seen_hrefs:
                    continue
                if href_key:
                    seen_hrefs.add(href_key)

                title_key = (title[:80] + rj["location"]).lower()
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                job = {
                    "title": title,
                    "company": NAME,
                    "location": rj["location"],
                    "level": rj.get("level", ""),
                    "function": rj.get("function", ""),
                    "link": href if href else url,
                    "keyword": KEYWORD,
                    "source": NAME,
                    "scraped_at": datetime.now().isoformat()
                }
                all_raw_jobs.append(job)
                page_count += 1

            print(f"    +{page_count} new on page, total raw: {len(all_raw_jobs)}")
            page_num += 1
            if page_num > 20:
                print(f"    -> Max pages reached (20)")
                break

        print(f"\n  [Stage 1 Done] {len(all_raw_jobs)} raw entries collected")

        # Stage 2: JD 提取 + 评分 (Plan C + Plan X)
        all_matched = []
        jd_page = context.new_page()

        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0

        for i, job_data in enumerate(all_raw_jobs):
            title = job_data["title"]
            link = job_data["link"]

            # Plan X: 用 title+company 组合去重（GS 没有稳定的 detail URL）
            dedup_key = f"gs|{title[:80]}|{job_data.get('location','')}"
            import hashlib
            dedup_hash = hashlib.md5(dedup_key.encode()).hexdigest()[:16]
            dedup_link = f"gs://{dedup_hash}"

            job_status = check_job_status(dedup_link, title, seen_data)
            if job_status == "unchanged":
                print(f"  [{i+1}/{len(all_raw_jobs)} SKIP] {title[:50]} -> unchanged")
                continue

            if job_status == "updated":
                print(f"  [{i+1}/{len(all_raw_jobs)} UPDATE] {title[:50]}")
                updated_jobs_count += 1
            else:
                print(f"  [{i+1}/{len(all_raw_jobs)} NEW] {title[:50]}")
                new_jobs_count += 1

            # Plan C: 获取 JD（GS 使用页面 URL，尝试点击卡片获取详情）
            full_jd = ""
            if link and "http" in link and "gs.com" in link:
                full_jd = get_jd_from_url(jd_page, link, platform="default")
            if not full_jd:
                # fallback: 用 job 的基本信息组合
                parts = []
                if job_data.get("function"):
                    parts.append(f"Function: {job_data['function']}")
                if job_data.get("level"):
                    parts.append(f"Level: {job_data['level']}")
                parts.append(f"Title: {title}")
                parts.append(f"Location: {job_data['location']}")
                full_jd = " | ".join(parts)

            if full_jd:
                print(f"    [JD] {len(full_jd)} chars")

            # Plan X: 保存 JD 并更新索引
            entry_meta = update_job_entry(dedup_link, title, NAME, full_jd, seen_data, job_status)

            job = {
                "title": title,
                "company": NAME,
                "location": job_data["location"],
                "link": link,
                "source": NAME,
                "keyword": KEYWORD,
                "description": full_jd,
                "jd_file": entry_meta.get("jd_file", ""),
                "jd_chars": entry_meta.get("jd_chars", 0),
                "scraped_at": datetime.now().isoformat(),
            }

            scored = score_job(job)
            if scored.get("isRecommended"):
                all_matched.append(scored)
                print(f"    [MATCH] P{scored.get('priority')} score={scored.get('score')}")
            elif scored.get("score", 0) >= 70:
                all_matched.append(scored)
                print(f"    [P2]    score={scored.get('score')}")

        _safe(jd_page)
        _safe(page)
        browser.close()

        save_seen_jobs(seen_data)
        print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")

    # 保存结果
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": NAME,
            "date": datetime.now().isoformat(),
            "total_raw": len(all_raw_jobs),
            "total_matched": len(all_matched),
            "jobs": all_matched
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(all_matched)} matched / {len(all_raw_jobs)} raw -> {OUTPUT_FILE}")

    # 追加到 Excel
    append_scanner_to_excel(OUTPUT_FILE)

    return all_matched


if __name__ == "__main__":
    scan_gs()
