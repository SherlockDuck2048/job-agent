# -*- coding: utf-8 -*-
"""
Microsoft Careers Job Scanner (Optimized)
- 站点: https://apply.careers.microsoft.com/careers?location=Hong+Kong
- 方法: connect_over_cdp
- 分页: start=0, 15 (最多2页，约24个HK职位)
- 详情: 直接访问 /careers/job/{id}?domain=microsoft.com
- 优化: 按 job_id 去重，避免重复访问
- 输出: JSON + 自动追加到 Excel
"""
import sys, os, time, json, re
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cco_scorer import score_job
from job_scanner_base import append_scanner_to_excel

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

CDP_URL = "http://localhost:9222"
BASE_URL = "https://apply.careers.microsoft.com/careers"
SEARCH_URL = f"{BASE_URL}?domain=microsoft.com&location=Hong+Kong&sort_by=distance&filter_include_remote=1"
PAGESTEP = 15

def get_jobs_from_listing(page):
    """从列表页提取职位，按 job_id 去重"""
    time.sleep(2)
    
    links = page.query_selector_all('a[href*="/careers/job/"]')
    
    jobs = {}  # dict: job_id -> {title, href, job_id, posted}
    for link in links:
        href = link.get_attribute('href') or ''
        text = (link.inner_text() or '').strip()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        if not lines:
            continue
        title = lines[0]
        
        # 过滤非职位链接
        skip_titles = {'Jobs', 'Sign in', 'Add to cart', 'Apply now', 'View All Jobs', 
                       'Single Position', 'Upload your resume', 'Find out how well you match'}
        if title in skip_titles:
            continue
        
        # 提取 job_id
        m = re.search(r'/job/(\d+)', href)
        if not m:
            continue
        job_id = m.group(1)
        
        # 提取 posted 时间
        posted = None
        for line in lines:
            if 'Posted' in line or 'ago' in line.lower():
                posted = line
                break
        
        # 只保留第一个匹配（列表页第一个匹配最准确）
        if job_id not in jobs:
            jobs[job_id] = {
                'title': title,
                'href': href,
                'job_id': job_id,
                'posted': posted
            }
    
    return list(jobs.values())

def get_jd_from_url(page, job_id):
    """从职位详情页提取 JD"""
    url = f"https://apply.careers.microsoft.com/careers/job/{job_id}?domain=microsoft.com"
    
    try:
        page.goto(url, timeout=15000, wait_until='domcontentloaded')
        time.sleep(1.5)
        
        body = page.inner_text('body')
        return body[:5000] if body else None
    except Exception as e:
        print(f'[WARN] JD fetch failed: {job_id} -> {e}', flush=True)
        return None

def scan_microsoft():
    """主函数"""
    timestamp = datetime.now().strftime('%Y-%m-%d')
    output_file = os.path.join(OUTPUT_DIR, f'microsoft_{timestamp}.json')
    
    all_jobs = []
    jobs_scored = []
    
    with sync_playwright() as p:
        print('[Stage 1] Connecting to CDP...', flush=True)
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.new_context()
        page = context.new_page()
        
        # 收集所有职位（最多2页，按 job_id 自动去重）
        for page_idx in range(2):
            start = page_idx * PAGESTEP
            list_url = f"{SEARCH_URL}&start={start}"
            print(f'\n[Stage 1] Page {page_idx+1} (start={start})', flush=True)
            
            page.goto(list_url, timeout=25000, wait_until='domcontentloaded')
            
            jobs_on_page = get_jobs_from_listing(page)
            print(f'[Stage 1] Found {len(jobs_on_page)} unique jobs', flush=True)
            
            if not jobs_on_page:
                print('[Stage 1] No more jobs, stopping', flush=True)
                break
            
            for job in jobs_on_page:
                if job['job_id'] not in [j['job_id'] for j in all_jobs]:
                    all_jobs.append(job)
            
            time.sleep(1)
        
        total_raw = len(all_jobs)
        print(f'\n[Stage 1] Total unique jobs: {total_raw}', flush=True)
        
        if not all_jobs:
            browser.close()
            return None, []
        
        # Stage 2: 逐个获取 JD 并评分
        print('\n[Stage 2] Fetching JD and scoring...', flush=True)
        
        for i, job in enumerate(all_jobs, 1):
            title = job['title']
            job_id = job['job_id']
            
            print(f'[Stage 2] ({i}/{total_raw}) {title[:60]}', flush=True)
            
            jd_text = get_jd_from_url(page, job_id)
            if not jd_text or len(jd_text) < 100:
                print(f'  [WARN] JD too short or empty', flush=True)
                continue
            
            print(f'  JD: {len(jd_text)} chars', flush=True)
            
            job_data = {'title': title, 'description': jd_text[:10000]}
            scored = score_job(job_data)
            
            location = 'Hong Kong'
            loc_m = re.search(r'(Hong Kong[^\\n]{0,30})', jd_text[:500])
            if loc_m:
                location = loc_m.group(1).strip()[:50]
            
            jobs_scored.append({
                'title': title,
                'company': 'Microsoft',
                'link': f'https://apply.careers.microsoft.com/careers/job/{job_id}?domain=microsoft.com',
                'source': 'microsoft',
                'date': timestamp,
                'location': location,
                'posted': job['posted'],
                'jd': jd_text[:5000],
                'score': scored['score'],
                'priority': scored['priority'],
                'recommend': scored['isRecommended'],
                'comment': scored['comment']
            })
            
            print(f'  Score: {scored["priority"]} ({scored["score"]})', flush=True)
            time.sleep(0.8)
        
        browser.close()
    
    # 保存 JSON
    output_data = {'jobs': jobs_scored, 'source': 'microsoft', 'date': timestamp}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    # 追加到 Excel
    print('\n[Stage 3] Appending to Excel...', flush=True)
    try:
        append_scanner_to_excel(output_file)
    except Exception as e:
        print(f'[WARN] Excel append failed: {e}', flush=True)
    
    print(f'\n[Done] {len(jobs_scored)} scored jobs saved to {output_file}', flush=True)
    print(f'P0: {sum(1 for j in jobs_scored if j["priority"] == "P0")}, '
          f'P1: {sum(1 for j in jobs_scored if j["priority"] == "P1")}, '
          f'P2: {sum(1 for j in jobs_scored if j["priority"] == "P2")}, '
          f'P3: {sum(1 for j in jobs_scored if j["priority"] == "P3")}', flush=True)
    
    return output_file, jobs_scored

if __name__ == '__main__':
    scan_microsoft()
