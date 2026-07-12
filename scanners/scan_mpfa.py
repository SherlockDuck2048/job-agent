# -*- coding: utf-8 -*-
"""
MPFA Careers Job Scanner
- 站点: https://careers.mpfa.org.hk/view/personel/RecruitList?lang=en_US
- 方法: Direct API (urllib POST, base64 body) + list page scraping
- API: POST /api/recruit_jobpost/QueryRecruitList?base64encrypt=1
- Body: base64({"position":null,"orgnode_name":null})
- JD: recruit_job_description (HTML) - 含完整职位描述
- 标题: 从列表页提取，与 API 数据按日期匹配
- 输出: JSON + 自动追加到 Excel
"""
import sys, os, time, json, base64, re
from datetime import datetime
import urllib.request
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cco_scorer import score_job
from job_scanner_base import append_scanner_to_excel

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

LISTING_URL = "https://careers.mpfa.org.hk/view/personel/RecruitList?lang=en_US"
API_URL = "https://careers.mpfa.org.hk/api/recruit_jobpost/QueryRecruitList?base64encrypt=1"
CDP_URL = "http://localhost:9222"

def get_list_page_titles():
    """从列表页提取职位标题（与 API 数据按日期匹配）"""
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        page = browser.new_page()
        
        page.goto(LISTING_URL, timeout=20000, wait_until='networkidle')
        time.sleep(3)
        
        rows = page.query_selector_all('tr')
        titles_map = {}  # key: post_date -> title (use post_date only since close_date differs)
        
        for row in rows:
            cells = row.query_selector_all('td')
            if len(cells) >= 4:
                title_link = cells[0].query_selector('a')
                if title_link:
                    title = title_link.inner_text().strip()
                    company = cells[1].inner_text().strip()
                    posting = cells[2].inner_text().strip()
                    closing = cells[3].inner_text().strip()
                    # Parse dates like "8 June 2026" -> "2026-06-08"
                    post_date = parse_date(posting)
                    close_date = parse_date(closing)
                    
                    # Use post_date as key (close_date differs between list page and API by 1 day)
                    titles_map[post_date] = {'title': title, 'company': company, 'close': close_date}
        
        browser.close()
        return titles_map

def parse_date(date_str):
    """Parse date like '8 June 2026' -> '2026-06-08'"""
    date_str = date_str.strip()
    months = {'January': '01', 'February': '02', 'March': '03', 'April': '04',
              'May': '05', 'June': '06', 'July': '07', 'August': '08',
              'September': '09', 'October': '10', 'November': '11', 'December': '12'}
    try:
        parts = date_str.split()
        if len(parts) == 3:
            day = parts[0].zfill(2)
            month = months.get(parts[1], '01')
            year = parts[2]
            return f"{year}-{month}-{day}"
    except:
        pass
    return date_str

def html_to_text(html):
    """Convert HTML to plain text"""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove non-ASCII characters (Wingdings etc.)
    text = text.encode('ascii', errors='replace').decode('ascii')
    return text

def scan_mpfa():
    timestamp = datetime.now().strftime('%Y-%m-%d')
    output_file = os.path.join(OUTPUT_DIR, f'mpfa_{timestamp}.json')
    
    # Stage 1a: Get titles from list page
    print('[Stage 1a] Scraping list page for job titles...', flush=True)
    try:
        titles_map = get_list_page_titles()
        print(f'[Stage 1a] Got {len(titles_map)} titles', flush=True)
    except Exception as e:
        print(f'[Stage 1a] Error: {e}', flush=True)
        titles_map = {}
    
    # Stage 1b: Get full JD from API
    print('[Stage 1b] Fetching MPFA job list via API...', flush=True)
    
    body_b64 = base64.b64encode(json.dumps({"position": None, "orgnode_name": None}).encode('utf-8')).decode()
    headers = {
        'Authorization': 'token-',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Referer': LISTING_URL,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        req = urllib.request.Request(API_URL, data=body_b64.encode('utf-8'), headers=headers, method='POST')
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f'[Stage 1b] API error: {e}', flush=True)
        return None, []
    
    if data.get('status') != 0:
        print(f'[Stage 1b] API status={data.get("status")}, msg={data.get("msg")}', flush=True)
        return None, []
    
    api_jobs = data.get('datas', {}).get('data', [])
    print(f'[Stage 1b] API returned {len(api_jobs)} jobs', flush=True)
    
    if not api_jobs:
        return None, []
    
    jobs_scored = []
    
    print('\n[Stage 2] Scoring...', flush=True)
    
    for i, job in enumerate(api_jobs, 1):
        post_date = job.get('recruit_begin_date', '')[:10] if job.get('recruit_begin_date') else ''
        close_date = job.get('recruit_end_date', '')[:10] if job.get('recruit_end_date') else ''
        company_no = job.get('company_no', '').strip()
        
        # Match title from list page (use post_date only)
        title = None
        company = 'MPFA' if company_no == '20181' else 'eMPFPC'
        if post_date in titles_map:
            title = titles_map[post_date]['title']
            company = titles_map[post_date]['company']
            close_date = titles_map[post_date]['close']  # use list page close date
        
        if not title:
            title = f"[{company}] {job.get('recruit_position_no', '').strip()}"
        
        # Build job URL
        recruit_no = job.get('recruit_no', '').strip()
        job_url = (f"https://careers.mpfa.org.hk/view/personel/RecruitList/RecruitPositionDetails"
                   f"?lang=en_US&company_no={company_no}&recruit_no={recruit_no}&application_form_type=standard")
        
        # Extract JD text
        jd_html = job.get('recruit_job_description', '') or ''
        jd_text = html_to_text(jd_html)
        
        print(f'[Stage 2] ({i}/{len(api_jobs)}) {title[:60]}', flush=True)
        
        job_data = {'title': title, 'description': jd_text[:10000]}
        scored = score_job(job_data)
        
        jobs_scored.append({
            'title': title,
            'company': company,
            'link': job_url,
            'source': 'mpfa',
            'date': timestamp,
            'posted': post_date,
            'closing': close_date,
            'jd': jd_text[:5000],
            'score': scored['score'],
            'priority': scored['priority'],
            'recommend': scored['isRecommended'],
            'comment': scored['comment']
        })
        
        print(f'  Score: {scored["priority"]} ({scored["score"]})', flush=True)
        time.sleep(0.3)
    
    # Stage 3: Save + append
    print('\n[Stage 3] Saving...', flush=True)
    output_data = {'jobs': jobs_scored, 'source': 'mpfa', 'date': timestamp}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    try:
        append_scanner_to_excel(output_file)
    except Exception as e:
        print(f'[WARN] Excel append failed: {e}', flush=True)
    
    print(f'\n[Done] {len(jobs_scored)} jobs saved to {output_file}', flush=True)
    print(f'P0: {sum(1 for j in jobs_scored if j["priority"] == "P0")}, '
          f'P1: {sum(1 for j in jobs_scored if j["priority"] == "P1")}, '
          f'P2: {sum(1 for j in jobs_scored if j["priority"] == "P2")}, '
          f'P3: {sum(1 for j in jobs_scored if j["priority"] == "P3")}', flush=True)
    
    return output_file, jobs_scored

if __name__ == '__main__':
    scan_mpfa()
