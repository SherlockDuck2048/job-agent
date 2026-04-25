"""
Goldman Sachs Scanner
URL: from scan_strategies.py
特点：Next.js SPA，职位列表在 gs-card 容器内
要求：翻页翻到底 + href去重（优先）+ title去重（兜底）
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import score_job

# 从 scan_strategies 读取配置
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
from job_scanner_base import append_scanner_to_excel
from scan_strategies import SCAN_STRATEGIES

STRATEGY = SCAN_STRATEGIES.get("goldman", {})
BASE_URL = STRATEGY.get("url", "https://higher.gs.com/results?LOCATION=Hong%20Kong&page=1&search=AI&sort=RELEVANCE")

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"gs_{datetime.now().strftime('%Y-%m-%d')}.json")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _normalize_href(href):
    """标准化 href 用于去重"""
    if not href:
        return ""
    # 去掉 query 参数
    href = href.split("?")[0]
    # 去掉末尾斜杠
    href = href.rstrip("/")
    # 转小写
    return href.lower()


def extract_gs_jobs_from_text(page_text):
    """从 GS 页面文本提取职位（GS 职位信息直接嵌在文本中）"""
    jobs = []

    # GS 职位格式: 标题行 + 地点·级别 + 职能描述
    # 示例:
    # Global Banking Markets - Investment Banking Associate - TMT - Beijing/Hong Kong
    # Hong Kong
    # ·Associate
    # Banker - Industry/Country Coverage

    lines = [l.strip() for l in page_text.split('\n') if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # 检测职位标题（包含关键词且长度合适）
        is_title = False
        if any(k in line for k in ['Investment Banking', 'Wealth Management', 'Compliance', 'Asset Management',
                                      'Global Banking', 'Private Wealth', 'Control Room', 'Risk', 'Finance']):
            if 20 < len(line) < 200 and '·' not in line and not line.startswith('Hong Kong'):
                is_title = True

        if not is_title:
            i += 1
            continue

        title = line

        # 找地点（下一行或下几行）
        location = LOCATION
        level = ""
        function = ""

        # 向后查找最多 5 行
        for j in range(i+1, min(i+6, len(lines))):
            next_line = lines[j]

            # 地点
            if next_line == "Hong Kong" or next_line == "Beijing/Hong Kong":
                location = next_line

            # 级别
            if '·Associate' in next_line or next_line == 'Associate':
                level = "Associate"
            elif '·Vice President' in next_line or next_line == 'Vice President':
                level = "Vice President"
            elif '·Analyst' in next_line or next_line == 'Analyst':
                level = "Analyst"

            # 职能描述（在级别之后）
            if level and not function:
                if any(k in next_line for k in ['Banker', 'Sales', 'Control', 'Management', 'Support', 'Coverage']):
                    function = next_line
                    break

            # 遇到下一个职位标题或分隔符就停止
            if 'share' in next_line.lower() or 'bookmark' in next_line.lower():
                break
            if any(k in next_line for k in ['Investment Banking', 'Wealth Management', 'Compliance']) and len(next_line) > 30:
                break

        jobs.append({
            "title": title,
            "href": "",  # GS 页面没有直接链接，用页面 URL
            "location": location,
            "level": level,
            "function": function
        })

        i += 1

    return jobs


def scan_gs():
    print("=== Goldman Sachs Scanner ===")
    print(f"  Base URL from scan_strategies: {BASE_URL[:80]}...")

    all_jobs = []
    seen_hrefs = set()  # href 去重（优先）
    seen_titles = set()  # title 去重（兜底）

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

        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            page_num = 1
            prev_status_text = ""
            stable_count = 0

            while True:
                # 构建 URL（从 scan_strategies 的 base 修改 page 参数）
                url = re.sub(r'page=\d+', f'page={page_num}', BASE_URL)
                url = re.sub(r'search=[^&]*', f'search={kw.replace(" ", "%20")}', url)

                print(f"  Page {page_num}: {url}")

                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    time.sleep(5)  # 等待 SPA 渲染
                except Exception as e:
                    print(f"  ! Load failed: {e}")
                    break

                # 滚动触发懒加载
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)

                # 从文本提取职位（GS 页面结构特殊）
                page_text = page.inner_text('body')
                raw_jobs = extract_gs_jobs_from_text(page_text)
                print(f"    Found {len(raw_jobs)} jobs from text")

                # 获取状态文字用于翻页检测
                status_match = re.search(r'Showing\s+(\d+)\s+of\s+(\d+)\s+matches', page_text)
                status_text = status_match.group(0) if status_match else ""

                # 检测状态文字是否稳定（翻到底的标志）
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

                    # 去重策略 1: href 去重（优先）
                    href_key = _normalize_href(href)
                    if href_key and href_key in seen_hrefs:
                        continue
                    if href_key:
                        seen_hrefs.add(href_key)

                    # 去重策略 2: title + location 去重（兜底）
                    title_key = (title[:80] + rj["location"]).lower()
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)

                    job = {
                        "title": title,
                        "company": "Goldman Sachs",
                        "location": rj["location"],
                        "level": rj["level"],
                        "link": href if href else url,
                        "keyword": kw,
                        "source": "Goldman Sachs",
                        "scraped_at": datetime.now().isoformat()
                    }

                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        all_jobs.append(scored)
                        print(f"    [MATCH] {title[:55]} ({scored.get('priority')}, {scored.get('score')})")
                    elif scored.get("score", 0) >= 70:
                        all_jobs.append(scored)
                        print(f"    [P2]    {title[:55]} (P{scored.get('priority')}, {scored.get('score')})")
                    page_count += 1

                print(f"    -> {page_count} new jobs on this page")
                print(f"    -> Total unique: {len(seen_hrefs)} by href, {len(seen_titles)} by title")

                if status_match:
                    shown, total = int(status_match.group(1)), int(status_match.group(2))
                    print(f"    Pagination: {shown} of {total}")

                # 翻页
                page_num += 1

                # 安全限制
                if page_num > 20:
                    print(f"    -> Max pages reached (20)")
                    break

        _safe_close(page)
        browser.close()

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Goldman Sachs",
            "date": datetime.now().isoformat(),
            "total_found": len(all_jobs),
            "raw_count": len(seen_titles),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(all_jobs)} matched / {len(seen_titles)} raw -> {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_gs()

