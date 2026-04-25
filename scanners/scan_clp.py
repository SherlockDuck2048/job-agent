r"""CLP Scanner - Oracle HCM
策略：不搜关键词（keyword=AI 搜不到任何职位），抓全部再评分
流程：收集全部 href -> 逐个提取 JD + 评分 -> 写入 Excel
Excel: config/HK_AI_Jobs_YYYY-MM-DD.xlsx"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import CCOSCORER, score_job
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

KEYWORDS     = ["AI"]
LOCATION     = "Hong Kong"
BASE_URL     = "https://iabhtj.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CLP-Recruitment-System/jobs"
OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"clp_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUT    = os.path.join(os.path.dirname(__file__), "..", "config",    f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
TEMPLATE     = os.path.join(os.path.dirname(__file__), "..", "config",    "HK_AI_Jobs_YYYY-MM-DD.xlsx")

# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_close_page(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _normalize_href(href):
    """按 path 主干去重，去掉 query string 和末尾版本号"""
    if not href:
        return ""
    if href.startswith("http"):
        p = re.sub(r'\?.*', '', href)
        p = re.sub(r'-\d+$',  '', p)
        return p
    p = re.sub(r'\?.*', '', href)
    p = re.sub(r'-\d+$',  '', p)
    return p


def get_full_jd(context, link):
    """在新 page 中提取结构化 JD"""
    try:
        jd_page = context.new_page()
        jd_page.goto(link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        page_title = jd_page.title()
        print(f"    [JD] {page_title[:60]}")

        # Oracle HCM JD 选择器
        for sel in [
            "[class*='job-description']",
            "[class*='description']",
            "[class*='qualification']",
            "section[class*='detail']",
            "div[class*='content']",
        ]:
            el = jd_page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 80:
                    print(f"    [JD] Found via: {sel} ({len(text)} chars)")
                    _safe_close_page(jd_page)
                    return text[:3000]

        _safe_close_page(jd_page)
        return ""
    except Exception as e:
        print(f"    [WARN] JD fetch failed: {e}")
        return ""



def scan_clp():
    print("=== CLP Scanner ===\n")

    scorer   = CCOSCORER()
    matched  = []
    raw_all  = []
    seen_data = load_seen_jobs()  # Plan X: 加载去重索引
    new_matched = []  # Plan X: 今日新匹配的职位

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("  [CDP] Connected (port 9222)")
        except Exception:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-blink-features=AutomationControlled"])
            print("  [CDP] Launched fresh Chrome")

        ctx = browser.new_context(viewport={"width":1920,"height":1080})
        page = ctx.new_page()

        # 策略：不加 keyword（keyword=AI 搜到 0 职位），抓全部再评分
        print(f"  URL: {BASE_URL}")
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
        except Exception as e:
            print(f"  ! Load failed: {e}")
            _safe_close_page(page)
            browser.close()
            return

        # ── 1. 收集阶段：翻页翻到底 ─────────────────────────────────────────
        seen_hrefs  = set()
        page_num    = 0
        MAX_STALE   = 4
        stale_rounds= 0

        while True:
            page_num += 1
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            # 尝试点击 Show More / Next
            btn_clicked = False
            for btn_sel in [
                "button[id*='showMore'], button[id*='ShowMore']",
                "button[aria-label*='Show More'], button[aria-label*='show more']",
                "button[aria-label*='Next'], a[aria-label*='Next']",
                "[data-action='showMoreJobs']",
            ]:
                try:
                    btn = page.query_selector(btn_sel)
                    if btn and btn.is_visible():
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        btn_clicked = True
                        print(f"  翻页 #{page_num} (Show More clicked)", flush=True)
                        time.sleep(3)
                        break
                except Exception:
                    pass

            # 统计本轮新增有效 href
            tiles = page.query_selector_all("div.job-tile")
            new_this = 0
            for tile in tiles:
                try:
                    link_el = tile.query_selector("a[href*='/hcmUI/']")
                    if not link_el:
                        continue
                    href = link_el.get_attribute("href")
                    if href and not href.startswith("http"):
                        href = f"https://iabhtj.fa.ocs.oraclecloud.com{href}"
                    norm = _normalize_href(href)
                    if norm and norm not in seen_hrefs:
                        seen_hrefs.add(norm)
                        new_this += 1
                except Exception:
                    continue

            total = len(seen_hrefs)
            print(f"  第{page_num}页: 新增 {new_this}, 累计去重后 {total}")

            if new_this == 0:
                stale_rounds += 1
                if stale_rounds >= MAX_STALE:
                    print(f"  翻页结束（连续{MAX_STALE}轮无新职位）")
                    break
                if not btn_clicked:
                    print(f"  翻页结束（无 Show More 按钮）")
                    break
            else:
                stale_rounds = 0

            if page_num >= 50:
                print(f"  翻页结束（已达50页上限）")
                break

        print(f"\n  翻页完成: 去重后 {len(seen_hrefs)} 个有效职位\n")

        # ── 2. 逐个提取 + 评分阶段 ─────────────────────────────────────────
        # 重新遍历 tile，提取详情（已去重）
        processed = set()
        tiles = page.query_selector_all("div.job-tile")

        for tile in tiles:
            try:
                link_el = tile.query_selector("a[href*='/hcmUI/']")
                if not link_el:
                    continue
                href = link_el.get_attribute("href")
                if href and not href.startswith("http"):
                    href = f"https://iabhtj.fa.ocs.oraclecloud.com{href}"
                norm = _normalize_href(href)
                if norm in processed or norm not in seen_hrefs:
                    continue
                processed.add(norm)

                # 提取标题
                title_el = tile.query_selector("[class*='title'], h1, h2, h3")
                title = title_el.inner_text().strip() if title_el else ""
                if not title or len(title) < 5:
                    continue

                # 提取位置
                loc_els = tile.query_selector_all("[class*='location'], [class*='district']")
                location = ""
                for le in loc_els:
                    t = le.inner_text().strip()
                    if t and len(t) < 60:
                        location = t
                        break

                job = {
                    "title":       title,
                    "company":     "CLP",
                    "location":    location or LOCATION,
                    "link":        norm,
                    "keyword":     "AI",
                    "source":      "CLP",
                    "scraped_at":  datetime.now().isoformat()
                }
                raw_all.append(job)

                # Stage 1: Quick Filter
                fresult = scorer.quick_filter(job)
                if not fresult['passed']:
                    print(f"  [FILTER] {title[:45]} — {fresult['reason']}")
                    continue
                print(f"  [PASS]   {title[:45]}")

                # Plan X: 检查去重状态
                status = check_job_status(norm, title, seen_data)
                if status == "unchanged":
                    print(f"  [SKIP]   {title[:45]} (UNCHANGED)")
                    continue

                # Stage 2: Full JD
                job['full_jd'] = get_full_jd(ctx, norm)

                # Stage 3: Scored
                scored = score_job(job)
                if scored.get("isRecommended"):
                    matched.append(scored)
                    # Plan X: 更新去重索引
                    update_job_entry(norm, title, "CLP", 
                                    job.get('full_jd', ''), seen_data, status)
                    new_matched.append(scored)
                    print(f"  [MATCH]  {title[:45]} ({scored.get('priority')}, {scored.get('score')}) [{status.upper()}]")
                else:
                    print(f"  [SKIP]   {title[:45]} (score: {scored.get('score','N/A')})")

            except Exception as e:
                continue

        _safe_close_page(page)
        browser.close()

    # ── 保存结果 ─────────────────────────────────────────────────────────────
    raw_path = os.path.join(os.path.dirname(__file__),"..","candidates","raw",
                            f"clp_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"source":"CLP","date":datetime.now().isoformat(),
                   "total_raw":len(raw_all),"jobs":raw_all}, f, ensure_ascii=False, indent=2)
    print(f"\n[RAW] {len(raw_all)} jobs -> {raw_path}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source":"CLP","date":datetime.now().isoformat(),
                   "total_found":len(matched),"jobs":matched}, f, ensure_ascii=False, indent=2)
    print(f"[JSON] {len(matched)} matched -> {OUTPUT_FILE}")

    # Plan X: 保存去重索引
    save_seen_jobs(seen_data)
    print(f"[Plan X] {len(new_matched)} new jobs recorded")

    if matched:
        append_scanner_to_excel(OUTPUT_FILE)
    else:
        print("[Excel] No matched jobs")

    print(f"\n=== Done ===  Raw={len(raw_all)}  Matched={len(matched)}  New={len(new_matched)}")
    return matched


if __name__ == "__main__":
    scan_clp()

