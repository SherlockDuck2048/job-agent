r"""JPMorgan Scanner - Oracle HCM
1. 翻页翻到底（scroll + Show More 按钮，直到无新职位加载）
2. href 去重（按 path 去重，JR ID 在路径里）
流程：初筛 -> 获取完整JD -> 完整评分 -> 写入Excel
Excel输出: config/HK_AI_Jobs_YYYY-MM-DD.xlsx"""
import sys, os, json, time, re
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import append_scanner_to_excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry

# 加载配置（静默执行，避免 Windows cp1252 中文报错）
from pathlib import Path
import io
CONFIG_PATH = Path(__file__).parent.parent / "config" / "scan_strategies.py"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config_content = f.read()
null_out = io.StringIO()
_exec_globals = {"__name__": "__main__", "print": lambda *a,**k: None}
exec(config_content, _exec_globals)
SCAN_STRATEGIES = _exec_globals["SCAN_STRATEGIES"]

JPMORGAN_CONFIG = SCAN_STRATEGIES.get("jpmorgan", {})

KEYWORDS = ["AI"]
LOCATION_NAME = JPMORGAN_CONFIG.get("location_name", "Hong Kong")
LOCATION_ID   = JPMORGAN_CONFIG.get("location_id",   "300000000289330")
LOCATION_LEVEL= JPMORGAN_CONFIG.get("location_level","country")
BASE_URL     = JPMORGAN_CONFIG.get("url", JPMORGAN_CONFIG.get("base_url", ""))
SELECTORS    = JPMORGAN_CONFIG.get("selectors", {})
JD_SELECTORS = JPMORGAN_CONFIG.get("jd_selectors", [])
WAIT_MS      = JPMORGAN_CONFIG.get("wait", 5000)

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "HK_AI_Jobs_YYYY-MM-DD.xlsx")
OUTPUT_FILE   = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"jpmorgan_{datetime.now().strftime('%Y-%m-%d')}.json")
EXCEL_OUTPUT  = os.path.join(os.path.dirname(__file__), "..", "config",     f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_close_page(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _normalize_href(href):
    """按 path 主干去重，去掉 query string 和 JR ID 后的版本号"""
    if not href:
        return ""
    # 完整绝对 URL
    if href.startswith("http"):
        parsed = re.sub(r'\?.*', '', href)          # 去掉 query string
        parsed = re.sub(r'-\d+$', '', parsed)         # 去掉末尾 -2 -3 等版本号
        return parsed
    # 相对路径
    parsed = re.sub(r'\?.*', '', href)
    parsed = re.sub(r'-\d+$', '', parsed)
    return parsed


def get_full_jd(context, link):
    """在新 page 中打开职位，提取结构化 JD"""
    try:
        jd_page = context.new_page()
        jd_page.goto(link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        page_title = jd_page.title()
        print(f"    [JD] Page loaded: {page_title[:60]}")

        content_el = None
        for sel in JD_SELECTORS:
            el = jd_page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    content_el = el
                    print(f"    [JD] Found via: {sel} ({len(text)} chars)")
                    break
        if not content_el:
            print(f"    [JD] No content element")
            _safe_close_page(jd_page)
            return ""

        full_text = content_el.inner_text()

        sections = {}
        section_headers = {
            'job_description': ['Job Description','About the Role','The Role','About Us'],
            'responsibilities': ['Responsibilities','Key Responsibilities','What You Will Do','Duties'],
            'qualifications':  ['Required Qualifications','Qualifications','Requirements',
                                 'What You Need','Minimum Requirements'],
            'skills':          ['Capabilities','Skills','Required Skills',
                                 'Preferred Qualifications','Technical Skills'],
            'benefits':        ['Benefits','What We Offer','Why Join']
        }

        current_section = 'job_description'
        current_content = []
        for line in full_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            found_section = None
            for sec_key, headers in section_headers.items():
                for header in headers:
                    if header.lower() in line.lower() and len(line) < 60:
                        found_section = sec_key
                        break
                if found_section:
                    break
            if found_section:
                if current_content:
                    sections[current_section] = '\n'.join(current_content)
                current_section = found_section
                current_content = []
            else:
                current_content.append(line)
        if current_content:
            sections[current_section] = '\n'.join(current_content)

        if sections:
            result = []
            for key in ['job_description','responsibilities','qualifications','skills','benefits']:
                if key in sections and len(sections[key]) > 10:
                    result.append(f"=== {key.replace('_',' ').title()} ===\n{sections[key][:800]}")
            output = '\n\n'.join(result)[:3000] if result else full_text[:3000]
        else:
            output = full_text[:3000]

        print(f"    [JD] {len(sections)} sections, {len(output)} chars")
        _safe_close_page(jd_page)
        return output

    except Exception as e:
        print(f"    [WARN] JD fetch failed: {e}")
        return ""


# ── main ─────────────────────────────────────────────────────────────────────

def scan_jpmorgan():
    print("=== JPMorgan Scanner (翻页翻到底 + href去重) ===\n")

    scorer  = CCOSCORER()
    matched = []   # 最终写入的结果（含完整 JD）
    raw_all = []   # 全部原始记录
    seen_data = load_seen_jobs()  # Plan X: 加载去重索引
    new_matched = []  # Plan X: 今日新匹配的职位

    with sync_playwright() as p:
        try:
            # 先尝试连接已有 CDP（Chrome 已开启调试端口）
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("  [CDP] Connected to existing Chrome (port 9222)")
        except Exception:
            # 没有就启动独立的 Playwright Chrome
            print("  [CDP] No Chrome at 9222, launching fresh browser")
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run", "--no-sandbox"
            ])
        context = browser.new_context(viewport={"width":1920,"height":1080})

        for kw in KEYWORDS:
            print(f"--- {kw} @ {LOCATION_NAME} ---")

            page = context.new_page()
            # scan_strategies 的 url 含 keyword=AI，直接用；多关键词时做替换
            url = BASE_URL.replace("keyword=AI", f"keyword={kw.replace(' ','+')}")
            print(f"  URL: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(WAIT_MS / 1000)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                _safe_close_page(page)
                continue

            # ── 1. 收集阶段：翻页翻到底 ───────────────────────────────────────
            seen_hrefs   = set()   # 用于去重
            seen_count   = 0       # 上一次抓到的有效职位数
            stale_rounds  = 0      # 连续无新职位的轮次
            MAX_STALE    = 4      # 连续 4 轮无新职位则停止

            sel_card  = SELECTORS.get("job_card",   "div.job-tile")
            sel_title = SELECTORS.get("title",       ".job-tile__title")
            sel_link  = SELECTORS.get("link",        "a[href*='/hcmUI/']")
            sel_desc  = SELECTORS.get("description", ".job-grid-item__description")
            sel_info  = SELECTORS.get("job_info",   ".job-list-item__job-info-value")

            page_num = 1

            while True:
                # 滚动到页面底部，触发懒加载
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(1)

                # 点击 Show More / Next 按钮（Oracle HCM 常用）
                show_more_clicked = False
                for btn_sel in [
                    "button[id*='showMore'], button[id*='ShowMore']",
                    "a[id*='showMore'], a[id*='ShowMore']",
                    "button[aria-label*='Show More'], button[aria-label*='show more']",
                    "button[aria-label*='Next'], a[aria-label*='Next']",
                    "[data-action='showMoreJobs']",
                ]:
                    try:
                        btn = page.query_selector(btn_sel)
                        if btn and btn.is_visible():
                            btn.scroll_into_view_if_needed()
                            btn.click()
                            show_more_clicked = True
                            page_num += 1
                            print(f"  翻页 #{page_num} ...", flush=True)
                            time.sleep(3)
                            break
                    except Exception:
                        pass

                # 统计当前有效职位数
                cards = page.query_selector_all(sel_card)
                new_this_round = 0
                for card in cards:
                    title_el = card.query_selector(sel_title)
                    if not title_el:
                        continue
                    title = title_el.inner_text().strip()
                    if not title or len(title) < 5 or 'Filter Results' in title:
                        continue
                    link_el = card.query_selector(sel_link)
                    href = link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://jpmc.fa.oraclecloud.com{href}"
                    norm = _normalize_href(href)
                    if norm and norm not in seen_hrefs:
                        seen_hrefs.add(norm)
                        new_this_round += 1

                print(f"  第{page_num}页: 本轮新增 {new_this_round}, 累计去重后 {len(seen_hrefs)}")

                if new_this_round == 0:
                    stale_rounds += 1
                    if stale_rounds >= MAX_STALE:
                        print(f"  翻页结束（连续{MAX_STALE}轮无新职位）")
                        break
                    if not show_more_clicked:
                        print(f"  翻页结束（无 Show More 按钮）")
                        break
                else:
                    stale_rounds = 0

                # Oracle HCM 保险阀：最多 50 页
                if page_num >= 50:
                    print("  翻页结束（已达50页上限）")
                    break

            print(f"  翻页完成: 去重后 {len(seen_hrefs)} 个有效职位\n")

            # ── 2. 逐个提取 + 评分阶段 ────────────────────────────────────────
            for card in page.query_selector_all(sel_card):
                try:
                    title_el = card.query_selector(sel_title)
                    if not title_el:
                        continue
                    title = title_el.inner_text().strip()
                    if not title or len(title) < 5 or 'Filter Results' in title:
                        continue

                    link_el = card.query_selector(sel_link)
                    href    = link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://jpmc.fa.oraclecloud.com{href}"
                    norm = _normalize_href(href)
                    if norm in seen_hrefs:
                        seen_hrefs.discard(norm)          # 标记为已处理
                    else:
                        continue                           # 已处理过

                    desc_el   = card.query_selector(sel_desc)
                    desc      = desc_el.inner_text().strip() if desc_el else ""
                    func_els  = card.query_selector_all(sel_info)
                    job_func  = func_els[1].inner_text().strip() if len(func_els) > 1 else ""

                    job = {
                        "title":       title,
                        "company":     JPMORGAN_CONFIG.get("name","JPMorgan Chase"),
                        "location":    LOCATION_NAME,
                        "link":        norm,
                        "description": desc,
                        "job_function": job_func,
                        "keyword":     kw,
                        "source":      "JPMorgan",
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
                    job['full_jd'] = get_full_jd(context, norm)

                    # Stage 3: Scored
                    scored = score_job(job)
                    if scored.get("isRecommended"):
                        matched.append(scored)
                        # Plan X: 更新去重索引
                        update_job_entry(norm, title, job.get('company', 'JPMorgan'), 
                                        job.get('full_jd', ''), seen_data, status)
                        new_matched.append(scored)
                        print(f"  [MATCH]  {title[:45]} ({scored.get('priority')}, {scored.get('score')}) [{status.upper()}]")
                    else:
                        print(f"  [SKIP]   {title[:45]} (score: {scored.get('score','N/A')})")

                except Exception as e:
                    print(f"  [ERR] {e}")
                    continue

            _safe_close_page(page)

        browser.close()

    # ── 保存结果 ─────────────────────────────────────────────────────────────
    raw_file = os.path.join(os.path.dirname(__file__),"..","candidates","raw",
                             f"jpmorgan_raw_{datetime.now().strftime('%Y-%m-%d')}.json")
    os.makedirs(os.path.dirname(raw_file), exist_ok=True)
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({"source":"JPMorgan","date":datetime.now().isoformat(),
                   "total_raw":len(raw_all),"jobs":raw_all}, f, ensure_ascii=False, indent=2)
    print(f"\n[RAW] {len(raw_all)} jobs -> {raw_file}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"source":"JPMorgan","date":datetime.now().isoformat(),
                   "total_found":len(matched),"jobs":matched}, f, ensure_ascii=False, indent=2)
    print(f"[JSON] {len(matched)} matched -> {OUTPUT_FILE}")

    # Plan X: 保存去重索引
    save_seen_jobs(seen_data)
    print(f"[Plan X] {len(new_matched)} new jobs recorded")

    append_scanner_to_excel(OUTPUT_FILE)

    print(f"\n=== Done ===  Raw={len(raw_all)}  Matched={len(matched)}")
    return matched


if __name__ == "__main__":
    scan_jpmorgan()
