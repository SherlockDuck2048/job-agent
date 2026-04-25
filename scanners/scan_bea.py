"""
BEA Scanner (东亚银行) - PeopleSoft System
URL: https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL
来源: 用户验证 (2026-04-15)
特点: PeopleSoft SPA，职位数据在 iframe 的表格中
"""
import sys, os, json, time, re, io, contextlib, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "candidates", "raw", f"bea_{datetime.now().strftime('%Y-%m-%d')}.json")

# 从 scan_strategies 读取配置
STRATEGIES_FILE = os.path.join(SCRIPT_DIR, "..", "config", "scan_strategies.py")
_globals = {}
_strategies_src = open(STRATEGIES_FILE, encoding="utf-8").read()
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, STRATEGIES_FILE, "exec"), _globals)
_strategy = _globals.get("SCAN_STRATEGIES", {}).get("bea", {})
BASE_URL = _strategy.get("url", "https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL?Page=HRS_APP_SCHJOB&FOCUS=Applicant&FolderPath=PORTAL_ROOT_OBJECT.HC_HRS_CE_GBL2&IsFolder=false&IgnoreParamTempl=FolderPath%252cIsFolder")


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except:
        pass


def scan_bea():
    print("=== BEA Scanner ===")
    print(f"  URL: {BASE_URL}")
    
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_links = {}
    seen_titles = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("\n  Loading page...")
            page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            print("  Waiting 15s for iframe content...")
            time.sleep(15)
            
            # 找到 TargetContent iframe
            target_frame = None
            for frame in page.frames:
                if frame.name == "TargetContent":
                    target_frame = frame
                    break
            
            if not target_frame:
                print("  ! TargetContent frame not found")
                _safe_close(page)
                browser.close()
                return []
            
            print("  TargetContent frame found")
            
            # 等待 frame 内容加载
            time.sleep(5)
            
            # ─── 分页处理 ───────────────────────────────────────────────
            max_pages = 10
            stable_count = 0
            prev_job_count = 0
            
            for page_num in range(1, max_pages + 1):
                print(f"\n  Page {page_num}...", end="", flush=True)
                
                # 从 frame 提取职位行
                # PeopleSoft 的数据行通常有 HRS_CE_JO_EXT_I 标识
                job_rows = target_frame.query_selector_all("tr")
                
                page_new = 0
                for row in job_rows:
                    try:
                        # 检查是否是数据行（包含 HRS_CE_JO_EXT_I）
                        row_html = row.evaluate("el => el.outerHTML")
                        if "HRS_CE_JO_EXT_I" not in row_html:
                            continue
                        
                        # 提取单元格
                        cells = row.query_selector_all("td")
                        if len(cells) < 5:
                            continue
                        
                        # Cell 0: 行号（忽略）
                        # Cell 1: Job Title（里面有链接）
                        # Cell 2: Job Opening ID
                        # Cell 3: Location
                        # Cell 4: Posted Date
                        
                        # 提取 Job Title
                        title_cell = cells[1]
                        title_link = title_cell.query_selector("a")
                        if title_link:
                            title = title_link.inner_text().strip()
                            # PeopleSoft 链接是 JavaScript，需要提取 onclick 或构造链接
                            onclick = title_link.get_attribute("onclick") or ""
                            # 从 onclick 提取参数
                            if "HRS_CE_JO_EXT_I" in onclick:
                                # 提取 job opening ID
                                match = re.search(r'HRS_CE_JO_EXT_I\$?(\d+)', onclick)
                                if match:
                                    job_id_from_onclick = match.group(1)
                                else:
                                    job_id_from_onclick = ""
                            else:
                                job_id_from_onclick = ""
                        else:
                            title = title_cell.inner_text().strip()
                        
                        if not title or len(title) < 5:
                            continue
                        
                        # 提取 Job Opening ID
                        job_id = cells[2].inner_text().strip() if len(cells) > 2 else ""
                        
                        # 如果 onclick 里有 ID，用那个
                        if not job_id and job_id_from_onclick:
                            job_id = job_id_from_onclick
                        
                        # 提取 Location
                        location = cells[3].inner_text().strip() if len(cells) > 3 else LOCATION
                        
                        # 提取 Posted Date
                        posted_date = cells[4].inner_text().strip() if len(cells) > 4 else ""
                        
                        # 构造链接（PeopleSoft 使用 JavaScript 导航，这里用 job ID 构造直接链接）
                        if job_id:
                            link = f"https://careers.hkbea.com/psp/hcmprd/EMPLOYEE/HRMS/c/HRS_HRAM.HRS_APP_SCHJOB.GBL?Page=HRS_APP_JSPST&JobOpeningId={job_id}"
                        else:
                            link = BASE_URL
                        
                        # 去重（用 href）
                        if link in seen_links:
                            continue
                        seen_links[link] = True
                        page_new += 1
                        
                        # 标题去重兜底
                        title_key = title.lower()
                        if title_key in seen_titles:
                            continue
                        seen_titles[title_key] = True
                        
                        job = {
                            "title": title,
                            "company": "BEA",
                            "location": location,
                            "link": link,
                            "keyword": "AI",
                            "source": "BEA",
                            "scraped_at": datetime.now().isoformat(),
                            "job_id": job_id,
                            "posted_date": posted_date
                        }
                        raw_jobs.append(job)
                        
                        # 快速过滤
                        fr = scorer.quick_filter(job)
                        if not fr["passed"]:
                            safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                            safe_reason = fr['reason'][:30].encode('ascii', 'replace').decode('ascii')
                            print(f"\n    [FILTER] {safe_title} - {safe_reason}")
                            continue
                        
                        # 评分
                        scored = score_job(job)
                        if scored.get("isRecommended"):
                            all_jobs.append(scored)
                            safe_title = title[:50].encode('ascii', 'replace').decode('ascii')
                            print(f"\n    [MATCH] {safe_title} ({scored.get('priority')}, {scored.get('score')})")
                        
                    except Exception as e:
                        err = str(e)[:40].encode('ascii', 'replace').decode('ascii')
                        print(f"\n    [ERR] {err}")
                        continue
                
                print(f"  new={page_new}, total={len(raw_jobs)}, matched={len(all_jobs)}")
                
                # 检查是否稳定（没有新职位）
                if len(raw_jobs) == prev_job_count:
                    stable_count += 1
                else:
                    stable_count = 0
                prev_job_count = len(raw_jobs)
                
                if stable_count >= 2:
                    print("    [Stop] No new jobs for 2 consecutive pages")
                    break
                
                # ─── 翻页 ───────────────────────────────────────────────────
                # PeopleSoft 分页：找 "Next" 或 ">" 按钮
                next_btn = None
                for sel in [
                    "a[title*='Next']",
                    "a[aria-label*='Next']",
                    "a:has-text('>')",
                    "a.PSLEVEL1SCROLLNEXT",
                    "a[href*='scroll']"
                ]:
                    candidates = target_frame.query_selector_all(sel)
                    for btn in candidates:
                        text = btn.inner_text().strip()
                        if text in [">", "Next", ">"]:
                            next_btn = btn
                            break
                    if next_btn:
                        break
                
                if not next_btn:
                    print("    [Stop] No next button found")
                    break
                
                try:
                    next_btn.click()
                    time.sleep(5)
                except Exception as e:
                    print(f"    [Stop] Next click failed: {str(e)[:40]}")
                    break
            
            _safe_close(page)
            browser.close()
            
        except Exception as e:
            err = str(e)[:80].encode('ascii', 'replace').decode('ascii')
            print(f"  ! Error: {err}")
            _safe_close(page)
            browser.close()
            return []
    
    # 保存结果
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "BEA",
            "url": BASE_URL,
            "date": datetime.now().isoformat(),
            "total_raw": len(raw_jobs),
            "total_matched": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n[COMPLETE] {len(raw_jobs)} raw / {len(all_jobs)} matched jobs saved")
    print(f"  Output: {OUTPUT_FILE}")
    return all_jobs


if __name__ == "__main__":
    scan_bea()


