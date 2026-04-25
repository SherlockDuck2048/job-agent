"""Hays 完整扫描器 - 基于实际页面结构"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from playwright.sync_api import sync_playwright
from cco_scorer import score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "candidates", "raw", f"hays_{datetime.now().strftime('%Y-%m-%d')}.json")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

def scan_hays():
    print("=== Hays Scanner ===")
    all_jobs = []
    seen_links = set()
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        for kw in KEYWORDS:
            print(f"\n--- {kw} @ {LOCATION} ---")
            
            # 使用 q= 参数 + sortType=1 (Date 排序)
            kw_enc = kw.replace(" ", "%20")
            url = f"https://www.hays.com.hk/job-search?keywords=&location=Hong%20Kong&q={kw_enc}&sortType=1"
            print(f"  URL: {url[:100]}...")
            
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(5)
                
                # 滚动加载更多 (8次，获取更多职位)
                for _ in range(8):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                
                # 提取所有 job-detail 链接
                job_links = page.query_selector_all('a[href*="job-detail"]')
                print(f"  Found {len(job_links)} job links")
                
                # 提取每个 job 的信息
                for link_el in job_links[:30]:  # 最多30个
                    try:
                        href = link_el.get_attribute("href")
                        if not href or href in seen_links:
                            continue
                        seen_links.add(href)
                        
                        # 尝试获取标题 - 在当前元素或附近
                        # 先尝试获取元素的文本（通常包含职位名）
                        title = link_el.inner_text().strip()
                        if not title:
                            # 尝试往上找标题
                            parent = link_el.query_selector('xpath=..')
                            if parent:
                                # 查找包含职位名的子元素
                                title_el = parent.query_selector('h1, h2, h3, h4, [class*="title"], .job-title, a[href*="job-detail"]')
                                if title_el:
                                    title = title_el.inner_text().strip()
                        
                        # 清理标题中的多余信息
                        if "View details" in title:
                            title = title.replace("View details", "").strip()
                        title = title[:150]  # 限制长度
                        
                        if not title or len(title) < 3:
                            continue
                        
                        # 构建 job 对象
                        job = {
                            "title": title,
                            "company": "Hays",  # Hays 是猎头，不显示雇主公司
                            "location": LOCATION,
                            "link": href,
                            "keyword": kw,
                            "source": "Hays",
                            "scraped_at": datetime.now().isoformat()
                        }
                        
                        # 评分
                        scored = score_job(job)
                        if scored.get("isRecommended"):
                            all_jobs.append(scored)
                            print(f"  [MATCH] {title[:60]}... ({scored.get('priority')}, score: {scored.get('score')})")
                    
                    except Exception as e:
                        print(f"  ! Parse error: {e}")
                        continue
                        
            except Exception as e:
                print(f"  ! Load failed: {e}")
            finally:
                page.close()
        
        browser.close()
    
    # 保存结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Hays",
            "date": datetime.now().isoformat(),
            "total_found": len(all_jobs),
            "jobs": all_jobs
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n[COMPLETE] Saved {len(all_jobs)} matched jobs to {OUTPUT_FILE}")
    return all_jobs

if __name__ == "__main__":
    scan_hays()
