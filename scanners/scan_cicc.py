"""
CICC Scanner - Zhiye Platform (智联招聘)
URL: https://cicc.zhiye.com/custom/social?&hideMenu=1
Pagination: layui-laypage, 21 pages, 203 total jobs
"""
import sys, os, json, time, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw", f"cicc_{datetime.now().strftime('%Y-%m-%d')}.json")

def _safe_close(page):
    """Safely close a page"""
    try:
        if page and not page.is_closed():
            page.close()
    except:
        pass

def get_url_from_config():
    """Read URL from scan_strategies.py"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "scan_strategies.py")
    with open(config_path, encoding='utf-8') as f:
        content = f.read()
    import re
    match = re.search(r'"cicc"[^}]*"base_url":\s*"([^"]+)"', content, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback URL if config not found
    return "https://cicc.zhiye.com/custom/social?&hideMenu=1"

def extract_jobs_from_page(page):
    """Extract jobs from current page"""
    jobs = []
    
    # Wait for job list to load
    time.sleep(3)
    
    # Find all job rows
    rows = page.query_selector_all('tr.tr_dom')
    print(f"    Found {len(rows)} job rows")
    
    for row in rows:
        try:
            # Extract job ID from link
            link_el = row.query_selector('a[href*="jobAdId="]')
            if not link_el:
                continue
            
            href = link_el.get_attribute('href') or ''
            
            # Extract jobAdId
            import re
            id_match = re.search(r'jobAdId=([a-f0-9\-]{36})', href)
            if not id_match:
                continue
            job_id = id_match.group(1)
            
            # Extract title - in <a class="w280 hidden-text"> <b>title</b>
            title_el = row.query_selector('a.w280 b')
            if not title_el:
                title_el = row.query_selector('b')
            title = title_el.inner_text().strip() if title_el else ""
            
            if not title or len(title) < 3:
                continue
            
            # Extract category
            cate_el = row.query_selector('span.cate_name')
            category = cate_el.inner_text().strip() if cate_el else ""
            
            # Extract post date
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', row.inner_text())
            post_date = date_match.group(1) if date_match else ""
            
            # Build full link
            full_link = f"https://cicc.zhiye.com{href}" if href.startswith('/') else href
            
            job = {
                "title": title,
                "company": "CICC",
                "location": LOCATION if "Hong Kong" in title or "HK" in title else "China",
                "link": full_link,
                "keyword": "AI",
                "source": "CICC",
                "scraped_at": datetime.now().isoformat(),
                "category": category,
                "post_date": post_date,
                "job_id": job_id
            }
            jobs.append(job)
            
        except Exception as e:
            err_msg = str(e)[:50].encode('ascii', 'replace').decode('ascii')
            print(f"    [WARN] Row error: {err_msg}")
            continue
    
    return jobs

def scan_cicc():
    """Main scanner function"""
    print("=== CICC Scanner ===")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []
    seen_links = set()
    seen_titles = set()
    
    url = get_url_from_config()
    print(f"  URL: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            # Load first page
            print("\n  Loading page 1...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            
            page_num = 1
            max_pages = 25  # Safety limit
            
            while page_num <= max_pages:
                print(f"\n  === Page {page_num} ===")
                
                # Extract jobs from current page
                jobs = extract_jobs_from_page(page)
                
                for job in jobs:
                    link = job.get('link', '')
                    title = job.get('title', '')

                    # Dedup: href first, then title
                    if link in seen_links:
                        continue
                    if title in seen_titles:
                        continue

                    seen_links.add(link)
                    seen_titles.add(title)
                    raw_jobs.append(job)

                    # Safe print
                    safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                    print(f"    Job: {safe_title}")
                    
                    # Quick filter
                    fr = scorer.quick_filter(job)
                    if not fr['passed']:
                        safe_title = title[:40].encode('ascii', 'replace').decode('ascii')
                        print(f"    [FILTER] {safe_title} - {fr['reason']}")
                        continue

                    # Score job
                    scored = score_job(job)
                    if scored.get('isRecommended'):
                        all_jobs.append(scored)
                        safe_title = title[:50].encode('ascii', 'replace').decode('ascii')
                        print(f"    [MATCH] {safe_title} (P{scored.get('priority')}, {scored.get('score')})")
                    else:
                        safe_title = title[:50].encode('ascii', 'replace').decode('ascii')
                        print(f"    [SKIP] {safe_title} (score: {scored.get('score', 'N/A')})")
                
                # Check for next page
                try:
                    next_btn = page.query_selector('a.layui-laypage-next:not(.layui-disabled)')
                    if next_btn:
                        print(f"    Going to page {page_num + 1}...")
                        next_btn.click()
                        time.sleep(5)  # Wait for page load
                        page_num += 1
                    else:
                        print("    No more pages")
                        break
                except Exception as e:
                    err_msg = str(e)[:50].encode('ascii', 'replace').decode('ascii')
                    print(f"    Pagination error: {err_msg}")
                    break
            
        except Exception as e:
            err_msg = str(e)[:100].encode('ascii', 'replace').decode('ascii')
            print(f"  ! Error: {err_msg}")
        
        finally:
            _safe_close(page)
            browser.close()
    
    # Save results
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    result = {
        "source": "CICC",
        "url": url,
        "date": datetime.now().isoformat(),
        "total_raw": len(raw_jobs),
        "total_matched": len(all_jobs),
        "jobs": all_jobs
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n[COMPLETE] Raw: {len(raw_jobs)} | Matched: {len(all_jobs)}")
    print(f"  Saved to: {OUTPUT_FILE}")
    
    return all_jobs

if __name__ == "__main__":
    scan_cicc()


