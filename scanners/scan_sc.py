r"""
Standard Chartered Scanner - 完整重写
URL来源: scan_strategies.py 动态读取 ("sc" key)
参考: scan_ubs.py (分页结构) + scan_dbs.py (Excel格式)
"""
import sys, os, json, time, io, contextlib, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"sc_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_FILE = os.path.join(SCRIPT_DIR, "..", "config", "HK_AI_jobs_all.xlsx")

# 从 scan_strategies.py 动态读取配置
_strategies_src = open(os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py"), encoding="utf-8").read()
_globals = {}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, "scan_strategies.py", "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("sc", {})
BASE_URL = _strategy.get("url", "")
SC_NAME = _strategy.get("name", "Standard Chartered")
if not BASE_URL:
    raise ValueError("scan_strategies.py 中 sc 条目没有 URL，请提供后保存")

print(f"=== {SC_NAME} Scanner ===")
print(f"  URL: {BASE_URL[:80]}...")

# 非职位 skip 词（页面导航、按钮等）
SKIP_WORDS = {
    "Skills Matching", "Get Job Alerts", "Find your next role", "Use your CV",
    "Sign In", "Search Jobs", "Get Started", "Job Details", "Refine your search",
    "Region", "Market", "City", "Sort by", "Clear All", "Create a better",
    "Language", "Employee Login", "Posting Date", "Posting End Date",
    "Requisition Number", "Corporate & Commercial"
}


def _normalize_link(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return "https://jobs.standardchartered.com" + href
    return "https://jobs.standardchartered.com/" + href


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _status_text(page):
    try:
        body = page.inner_text("body")
        safe = body.encode("ascii", "replace").decode("ascii")
        m = re.search(r'(\d+)\s*to\s*(\d+)\s*of\s*(\d+)\s*results?', safe)
        if m:
            return f"{m.group(1)}-{m.group(2)} of {m.group(3)} results"
        # 备选：找显示总结果数的文字
        m2 = re.search(r'(?:Showing|displaying|found)\s+(\d+)\s*(?:result|job|position)', safe, re.I)
        if m2:
            return f"found {m2.group(1)} results"
        return safe[:100]
    except Exception:
        return ""


def _accept_cookies(page):
    selectors = [
        "#onetrust-accept-btn-handler",
        ".onetrust-accept-btn-handler",
        "button[id*='accept']",
        "button[id*='cookie']",
        "[aria-label*='Accept']",
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn:
                btn.scroll_into_view_if_needed()
                btn.click()
                time.sleep(2)
                return True
        except Exception:
            pass
    return False


def _extract_jobs(page, seen_hrefs, seen_titles):
    """从当前页面提取职位列表，返回 (new_count, list_of_jobs)"""
    jobs = []

    # SC 搜索结果页面: a[href*="/job/"] 在主容器内
    # 调试已知: 在 .jobsSearchContainer 内有 2 个职位
    all_links = page.query_selector_all("a[href*='/job/']")

    # 过滤：去掉 cookie/alerts 等非职位链接
    job_links = []
    for lnk in all_links:
        try:
            href = lnk.get_attribute("href") or ""
            txt_full = re.sub(r"\s+", " ", lnk.inner_text()).strip()
            if not href or "mailto:" in href[:20]:
                continue
            if not txt_full:
                continue
            # 过滤非职位
            is_skip = any(sw in txt_full for sw in SKIP_WORDS)
            if is_skip:
                continue
            # 必须是 "/job/职位名" 格式
            if not re.search(r'/job/[A-Z]', href, re.I):
                continue
            job_links.append((lnk, href, txt_full))
        except Exception:
            continue

    new_count = 0
    for lnk, href, txt_full in job_links:
        # 标题取第一行
        title = txt_full.split("\n")[0].strip()[:120]
        if not title or len(title) < 5:
            continue

        # 完整 URL
        link = _normalize_link(href)

        # href 去重（优先）
        if link in seen_hrefs:
            continue
        seen_hrefs.add(link)

        # title 去重（兜底）
        tkey = title.lower()
        if tkey in seen_titles:
            continue
        seen_titles.add(tkey)

        new_count += 1
        job = {
            "title": title,
            "company": SC_NAME,
            "location": "Hong Kong",
            "link": link,
            "keyword": "AI",
            "source": SC_NAME,
            "scraped_at": datetime.now().isoformat(),
        }
        jobs.append(job)

    return new_count, jobs



def scan_sc():
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_hrefs = set()
    seen_titles = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
        )

        # ── 第 1 页 ───────────────────────────────────────────────
        page = context.new_page()
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            _accept_cookies(page)
            time.sleep(3)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close(page)
            browser.close()
            return []

        print(f"  Page loaded: {page.url[:80]}")

        # ── 分页循环 ─────────────────────────────────────────────
        stable_count = 0
        prev_status = ""
        max_pages = 20

        for page_num in range(1, max_pages + 1):
            print(f"\n  --- Page {page_num} ---", flush=True)
            time.sleep(3)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

            # 提取职位
            page_new, page_jobs = _extract_jobs(page, seen_hrefs, seen_titles)
            print(f"  new={page_new}, total href={len(seen_hrefs)}", flush=True)

            # 评分
            for job in page_jobs:
                raw_jobs.append(job)
                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"    [FILTER] {job['title'][:50]} - {fr['reason']}")
                    continue
                scored = score_job(job)
                if scored.get("isRecommended"):
                    all_jobs.append(scored)
                    print(f"    [MATCH] {job['title'][:60]} (P{scored.get('priority')}, {scored.get('score')})")
                else:
                    print(f"    [SKIP ] {job['title'][:60]} (score: {scored.get('score', 'N/A')})")

            # 状态文字 + 分页检测
            status = _status_text(page)
            print(f"  Status: {status[:80]}", flush=True)

            # 判断是否有下一页: 找 next button / pagination
            has_next = False
            next_btn = None
            for sel in [
                "a[aria-label*='next']", "button[aria-label*='next']",
                "a[aria-label*='Next']",
                "[class*='pagination'] a", "[class*='pagination'] button",
                "a[rel='next']",
            ]:
                cands = page.query_selector_all(sel)
                for b in cands:
                    t = (b.inner_text() or "").strip().lower()
                    if any(x in t for x in ["next", ">"]):
                        next_btn = b
                        has_next = True
                        break
                if has_next:
                    break

            if page_new == 0 and not has_next:
                stable_count += 1
            else:
                stable_count = 0
            if stable_count >= 2:
                print(f"  [STOP] No more jobs + no next button")
                break
            if page_num >= max_pages:
                print(f"  [STOP] Max pages ({max_pages})")
                break

            # ── 翻页 ───────────────────────────────────────────
            # SC 使用 URL 参数 pageNumber=N
            from urllib.parse import urlparse, parse_qs, urlencode
            parsed = urlparse(page.url)
            params = parse_qs(parsed.query)
            next_num = int(params.get("pageNumber", [page_num - 1])[0]) + 1
            params["pageNumber"] = [next_num]
            next_query = urlencode(params, doseq=True)
            next_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{next_query}"

            _safe_close(page)

            # 创建新 page 对象，避免 stale element
            page = context.new_page()
            try:
                page.goto(next_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"  [STOP] Failed to load next page: {e}")
                break

        _safe_close(page)
        browser.close()

    # ── 保存 ────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": SC_NAME,
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched -> {OUTPUT_FILE}")
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs


if __name__ == "__main__":
    scan_sc()


