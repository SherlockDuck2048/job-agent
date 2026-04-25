"""
DBS Scanner - Workday SPA + Pagination
URL: https://dbs.wd3.myworkdayjobs.com/zh-CN/DBS_Careers?q=AI&locationCountry=...
来源: CCO提供 (2026-04-16)

架构: 两阶段
  Stage 1: 分页抓取所有职位链接（不离开列表页）
  Stage 2: 批量获取 JD 并评分（独立 jd_page）

[Plan C] Integrated: Using common JD fetch function
[Plan X] Integrated: Unified field name to description
"""
import sys, os, json, time, re, io
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, save_seen_jobs, check_job_status, update_job_entry  # Plan X

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_strategy():
    cfg = os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py")
    ns = {}
    with open(cfg, "r", encoding="utf-8") as f:
        exec(f.read(), ns)
    return ns.get("SCAN_STRATEGIES", {}).get("dbs", {})

def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def scan_dbs():
    strat = load_strategy()
    name = strat.get("name", "DBS")
    base_url = strat.get("url", "https://dbs.wd3.myworkdayjobs.com/zh-CN/DBS_Careers?q=AI")
    
    print(f"=== {name} Scanner (Workday + Pagination) ===")
    print("  [Plan C] Using common JD fetch function")
    print("  [Plan X] Unified field name to description")
    print(f"  URL: {base_url}")
    
    scorer = CCOSCORER()
    all_entries = []
    seen_hrefs = set()
    
    # ── Stage 1: 分页抓取职位链接 ───────────────────────────
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(base_url, wait_until="networkidle", timeout=60000)
            time.sleep(8)
        except Exception as e:
            print(f"  [!] Load failed: {e}")
            browser.close()
            return []
        
        page_num = 1
        prev_status = ""
        stable_count = 0
        
        while page_num <= 30:
            print(f"\n  --- Page {page_num} ---")
            
            # 关闭 Cookie 弹窗
            for sel in ["#onetrust-accept-btn-handler", "button[class*='accept']", "button[class*='close']"]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(1)
                        break
                except:
                    pass
            
            # 滚动加载
            for _ in range(6):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1)
            
            # 状态文字检测
            body_text = page.inner_text("body")
            status_match = re.search(r'[Ss]howing\s+(\d+)\s*[-–]\s*(\d+)\s*(?:of|of\s*)?(\d+)', body_text)
            current_status = status_match.group(0) if status_match else body_text[:300]
            
            if current_status == prev_status and page_num > 1:
                stable_count += 1
                if stable_count >= 2:
                    print("  [STOP] Last page reached")
                    break
            else:
                stable_count = 0
            prev_status = current_status
            print(f"  Status: {current_status[:60]}")
            
            # 提取职位链接
            raw_links = page.query_selector_all("a[href*='/job/']")
            page_jobs = 0
            
            for link_el in raw_links:
                try:
                    href = link_el.get_attribute("href") or ""
                    if not href or "/search" in href:
                        continue
                    href = href.split("?")[0].rstrip("/")
                    
                    if href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)
                    
                    title = link_el.inner_text().strip()
                    if not title or len(title) < 5:
                        slug = href.rstrip("/").split("/")[-1].replace("-", " ")
                        title = slug
                    if not title or len(title) < 3:
                        continue
                    
                    location = ""
                    loc_el = link_el.query_selector("[data-automation-id='secondaryLocation']")
                    if loc_el:
                        location = loc_el.inner_text().strip()
                    
                    all_entries.append({
                        "title": title,
                        "href": href if href.startswith("http") else f"https://dbs.wd3.myworkdayjobs.com{href}",
                        "location": location or "Hong Kong"
                    })
                    page_jobs += 1
                    
                except Exception:
                    continue
            
            print(f"  Page {page_num}: {page_jobs} new, total entries: {len(all_entries)}")
            
            # 翻页
            next_btn = None
            for sel in ["button[aria-label*='next']", "button[class*='pagination']:not([disabled])"]:
                try:
                    candidates = page.query_selector_all(sel)
                    for b in candidates:
                        if not b.is_disabled():
                            next_btn = b
                            break
                    if next_btn:
                        break
                except:
                    pass
            
            if not next_btn or next_btn.is_disabled():
                print("  [STOP] No next button")
                break
            
            try:
                next_btn.scroll_into_view_if_needed()
                next_btn.click()
                time.sleep(5)
            except Exception as e:
                print(f"  [STOP] Click next failed: {e}")
                break
            
            page_num += 1
        
        _safe_close(page)
        
        # ── Stage 2: 批量获取 JD + 评分 ───────────────────────
        all_matched = []
        raw_jobs = []
        # [Plan C] 创建独立 jd_page
        jd_page = new_page(context)

        # Plan X: 加载去重索引
        seen_data = load_seen_jobs()
        new_jobs_count = 0
        updated_jobs_count = 0

        try:
            for i, job_data in enumerate(all_entries):
                title = job_data["title"]
                href = job_data["href"]
                location = job_data["location"]

                job = {
                    "title": title, "company": name, "location": location,
                    "link": href, "keyword": "AI", "source": name,
                    "scraped_at": datetime.now().isoformat()
                }
                raw_jobs.append(job)

                # Plan X: 检查是否新岗位
                job_status = check_job_status(href, title, seen_data)
                if job_status == "unchanged":
                    existing = seen_data.get("jobs", {}).get(href, {})
                    print(f"  [{i+1}/{len(all_entries)} SKIP] {title[:50]} -> unchanged (seen {existing.get('first_seen', '?')})")
                    continue

                if job_status == "updated":
                    print(f"  [{i+1}/{len(all_entries)} UPDATE] {title[:50]} -> title changed")
                    updated_jobs_count += 1
                else:
                    print(f"  [{i+1}/{len(all_entries)} NEW] {title[:50]}")
                    new_jobs_count += 1

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"       FILTER -> {fr['reason']}")
                    update_job_entry(href, title, name, "", seen_data, job_status)
                    continue
                print(f"       PASS -> quick_filter passed")

                # [Plan C] 使用公共函数获取 JD
                jd_text = get_jd_from_url(jd_page, href, platform='workday')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars")

                # Plan X: 保存 JD 文件并更新索引
                entry = update_job_entry(href, title, name, jd_text, seen_data, job_status)
                job["jd_file"] = entry.get("jd_file", "")
                job["jd_chars"] = entry.get("jd_chars", 0)

                scored = score_job(job)
                if scored.get("isRecommended"):
                    all_matched.append(scored)
                    print(f"  [MATCH!] {title[:55]} → P{scored.get('priority')} {scored.get('score')}")
                else:
                    print(f"  [SKIP ] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            _safe_close(jd_page)
            browser.close()
            # Plan X: 保存去重索引
            save_seen_jobs(seen_data)
            print(f"\n[Plan X] New: {new_jobs_count}, Updated: {updated_jobs_count}, Total seen: {len(seen_data.get('jobs', {}))}")
    
    # ── 保存 ───────────────────────────────────────────────────
    out_dir = os.path.join(SCRIPT_DIR, "..", "candidates", "raw")
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    raw_file = os.path.join(out_dir, f"dbs_raw_{date_str}.json")
    out_file = os.path.join(out_dir, f"dbs_{date_str}.json")
    
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({"source": name, "date": datetime.now().isoformat(),
                   "total_raw": len(raw_jobs), "jobs": raw_jobs}, f, ensure_ascii=False, indent=2)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"source": name, "date": datetime.now().isoformat(),
                   "total_found": len(all_matched), "jobs": all_matched}, f, ensure_ascii=False, indent=2)
    
    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_matched)}")
    if all_matched:
        excel_path = os.path.join(SCRIPT_DIR, "..", "config", "HK_AI_jobs_all.xlsx")
        append_scanner_to_excel(out_file)
    
    return all_matched


if __name__ == "__main__":
    scan_dbs()

