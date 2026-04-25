r"""
CCB Asia (中国建设银行亚洲) Scanner - SSR 页面
URL: https://online.asia.ccb.com/PersonalHKWeb/careeropportunity/webForm/actShowList.do
特点: 所有职位直接渲染在 HTML 中，无分页，无需 JS 渲染
参考: scan_kpmg.py (评分逻辑) + scan_dbs.py (Excel格式)
"""
import sys, os, json, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
import urllib.request
import openpyxl

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 从 scan_strategies.py 动态读取
_strategies_src = open(os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py"), encoding="utf-8").read()
_globals = {}
exec(compile(_strategies_src, "scan_strategies.py", "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("ccb", {})
BASE_URL = _strategy.get("url", "")
SC_NAME = _strategy.get("name", "CCB Asia")
if not BASE_URL:
    raise ValueError("scan_strategies.py 中 ccb 条目缺少 URL")

OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"ccb_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_FILE = os.path.join(SCRIPT_DIR, "..", "config", "HK_AI_jobs_all.xlsx")
PREFIX = "https://online.asia.ccb.com"

print(f"=== {SC_NAME} Scanner ===")
print(f"  URL: {BASE_URL}")


def _fetch_page(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Referer": url
    })
    r = urllib.request.urlopen(req, timeout=30)
    return r.read().decode("utf-8", errors="replace")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass



def scan_ccbasia():
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_hrefs = set()
    seen_titles = set()

    # ── 抓取 HTML ──────────────────────────────────────────────
    try:
        html = _fetch_page(BASE_URL)
    except Exception as e:
        print(f"  ! Fetch failed: {e}")
        return []

    # ── 解析 SSR 表格 ─────────────────────────────────────────
    # 结构: <table><tr><td>title</td><td>dept</td><td>loc</td><td>status</td><td><a href="javascript:OpenDetailWindow('posno')"></td></tr>...
    table_m = re.search(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    if not table_m:
        print("  ! No table found")
        return []

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_m.group(1), re.DOTALL)
    print(f"  Table rows: {len(rows)}")

    for ri, row_html in enumerate(rows[1:], 1):  # 跳过 header
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        if not cells:
            continue

        # 提取 title: 第一个 <a> 标签内的纯文本
        title_m = re.search(r"<a[^>]+href=[^>]+>([^<]+)</a>", row_html)
        if not title_m:
            continue
        title = re.sub(r"\s+", " ", title_m.group(1).strip())[:120]
        if not title or len(title) < 5:
            continue

        # 提取部门/地点: 从 cell 中找 DisplayValue("text")
        def _dv(text):
            m = re.search(r'DisplayValue\("([^"]+)"\)', text)
            return m.group(1) if m else ""

        # cells[1]=部门, cells[2]=地点, cells[3]=状态
        dept = _dv(cells[1]) if len(cells) > 1 else ""
        dept = dept.strip()[:60]

        # 提取职位编号和详情链接
        posno_list = re.findall(r"javascript:OpenDetailWindow\(['\"]([^'\"]+)['\"]\)", row_html)
        posno = posno_list[0] if posno_list else ""
        raw_link = f"/PersonalHKWeb/careeropportunity/webForm/actGetCareerJobList.do?posno={posno}" if posno else ""
        full_link = PREFIX + raw_link

        # 跳过不合条件
        if not posno:
            continue

        # href 去重
        if full_link in seen_hrefs:
            continue
        seen_hrefs.add(full_link)

        # title 去重
        tkey = title.lower()
        if tkey in seen_titles:
            continue
        seen_titles.add(tkey)

        job = {
            "title": title,
            "company": SC_NAME,
            "location": "Hong Kong",
            "link": full_link,
            "keyword": "AI",
            "source": SC_NAME,
            "scraped_at": datetime.now().isoformat(),
        }
        raw_jobs.append(job)
        print(f"  [{ri}] {title[:60]} | {dept}")

        # ── 评分 ──────────────────────────────────────────────
        fr = scorer.quick_filter(job)
        if not fr["passed"]:
            print(f"       [FILTER] {fr['reason']}")
            continue
        scored = score_job(job)
        if scored.get("isRecommended"):
            all_jobs.append(scored)
            print(f"       [MATCH] P{scored.get('priority')} ({scored.get('score')}) - {scored.get('reason', '')[:60]}")
        else:
            print(f"       [SKIP ] score={scored.get('score')} reason={scored.get('reason', '')[:50]}")

    # ── 保存 ──────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
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
        _append_scanner_to_excel(OUTPUT_FILE)
    return all_jobs


if __name__ == "__main__":
    scan_ccbasia()


