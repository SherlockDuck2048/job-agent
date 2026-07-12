# -*- coding: utf-8 -*-
"""
Alibaba Cloud Careers Job Scanner
- 站点: https://careers.alibabacloud.com/en/off-campus/position-list?lang=en
- 方法: Browser API (CDP + Playwright fetch inside browser context)
- API: POST /position/search (via CDP evaluate fetch)
- 分页: pageIndex=1,2,... pageSize=100
- JD 包含在 API 响应中（requirement + description）
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
LISTING_URL = "https://careers.alibabacloud.com/en/off-campus/position-list?lang=en"

def scan_alibaba_cloud():
    """
    通过 Playwright 浏览器上下文发起内部 API 请求
    - 自动携带 CSRF token + cookies
    - 获取所有职位（pageSize=100 分页）
    """
    timestamp = datetime.now().strftime('%Y-%m-%d')
    output_file = os.path.join(OUTPUT_DIR, f'alibaba_cloud_{timestamp}.json')
    
    all_jobs = []
    jobs_scored = []
    
    with sync_playwright() as p:
        print('[Stage 1] Connecting to CDP...', flush=True)
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.new_context()
        page = context.new_page()
        
        # 先访问页面以获取 CSRF token 和 cookies
        print(f'[Stage 1] Loading: {LISTING_URL}', flush=True)
        page.goto(LISTING_URL, timeout=30000, wait_until='domcontentloaded')
        time.sleep(5)
        
        # 从 cookies 获取 CSRF token
        csrf = None
        cookies = context.cookies()
        for c in cookies:
            if c['name'] == 'XSRF-TOKEN':
                csrf = c['value']
                break
        
        # 备选：从页面 URL 重新导航触发 API 获取
        if not csrf:
            # 强制触发 /user/getUser API 调用
            page.evaluate('fetch("https://careers.alibabacloud.com/user/getUser")')
            time.sleep(2)
            cookies = context.cookies()
            for c in cookies:
                if c['name'] == 'XSRF-TOKEN':
                    csrf = c['value']
                    break
        
        print(f'[Stage 1] CSRF: {csrf[:20] if csrf else "NOT FOUND"}...', flush=True)
        
        if not csrf:
            print('[Stage 1] ERROR: No CSRF token found', flush=True)
            browser.close()
            return None, []
        
        # 通过 CDP fetch 发起 API 请求（保持浏览器上下文）
        api_url = f'https://careers.alibabacloud.com/position/search?_csrf={csrf}'
        
        print('[Stage 1] Fetching total count...', flush=True)
        
        # Stage 1: 收集所有职位
        total_jobs = 0
        page_index = 1
        
        while True:
            # 构建 POST 请求
            request_body = {
                "channel": "group_overseas_official_site",
                "language": "en",
                "batchId": "",
                "categories": "",
                "deptCodes": [],
                "key": "",
                "pageIndex": page_index,
                "pageSize": 100,
                "regions": "",
                "subCategories": ""
            }
            
            # 通过 browser.new_context() 的 API 请求（CDP 代理）
            # 使用 page.evaluate 来发起 fetch，保持 cookie/csrf
            response_data = page.evaluate(f"""async () => {{
                const resp = await fetch('{api_url}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Referer': '{LISTING_URL}'
                    }},
                    body: JSON.stringify({json.dumps(request_body)})
                }});
                return await resp.json();
            }}""")
            
            if not response_data.get('success'):
                print(f'[Stage 1] API error: {response_data.get("errorMsg")}', flush=True)
                break
            
            content = response_data.get('content', {})
            jobs_batch = content.get('datas', [])
            total_count = content.get('totalCount', 0)
            
            if page_index == 1:
                print(f'[Stage 1] Total positions: {total_count}', flush=True)
            
            print(f'[Stage 1] Page {page_index}: {len(jobs_batch)} jobs', flush=True)
            
            if not jobs_batch:
                break
            
            for job in jobs_batch:
                # 提取地点
                locations = job.get('workLocations', [])
                location = locations[0] if locations else ''
                
                # 过滤香港职位
                if 'Hong Kong' not in location and 'hong kong' not in location.lower():
                    continue
                
                # 合并 requirement + description 作为 JD
                requirement = job.get('requirement') or ''
                description = job.get('description') or ''
                jd_text = f"{description}\n{requirement}".strip()
                
                if not jd_text:
                    continue
                
                # 解析发布时间
                publish_time = job.get('publishTime')
                post_date = ''
                if publish_time:
                    try:
                        dt = datetime.fromtimestamp(publish_time / 1000)
                        post_date = dt.strftime('%Y-%m-%d')
                    except:
                        post_date = str(publish_time)
                
                all_jobs.append({
                    'id': job.get('id'),
                    'name': job.get('name'),
                    'location': location,
                    'jd': jd_text,
                    'experience': job.get('experience'),
                    'degree': job.get('degree'),
                    'department': job.get('department'),
                    'positionType': job.get('positionType'),
                    'categoryName': job.get('categoryName'),
                    'post_date': post_date,
                    'positionUrl': job.get('positionUrl'),
                    'requirement': requirement[:2000],
                    'description': description[:2000]
                })
            
            total_jobs += len(jobs_batch)
            
            # 如果返回数量 < pageSize，说明到最后一页了
            if len(jobs_batch) < 100:
                break
            
            page_index += 1
            time.sleep(1)
        
        print(f'\n[Stage 1] Total raw: {total_jobs}, Hong Kong only: {len(all_jobs)}', flush=True)
        
        if not all_jobs:
            browser.close()
            return None, []
        
        # Stage 2: 评分
        print('\n[Stage 2] Scoring...', flush=True)
        
        for i, job in enumerate(all_jobs, 1):
            title = job['name']
            jd_text = job['jd']
            
            print(f'[Stage 2] ({i}/{len(all_jobs)}) {title[:60]}', flush=True)
            
            job_data = {'title': title, 'description': jd_text[:10000]}
            scored = score_job(job_data)
            
            position_url = job['positionUrl']
            full_link = f'https://careers.alibabacloud.com{position_url}' if position_url.startswith('/') else position_url
            
            jobs_scored.append({
                'title': title,
                'company': 'Alibaba Cloud',
                'link': full_link,
                'source': 'alibaba_cloud',
                'date': timestamp,
                'location': job['location'],
                'posted': job['post_date'],
                'experience': job['experience'],
                'degree': job['degree'],
                'department': job['department'],
                'jd': jd_text[:5000],
                'score': scored['score'],
                'priority': scored['priority'],
                'recommend': scored['isRecommended'],
                'comment': scored['comment']
            })
            
            print(f'  Score: {scored["priority"]} ({scored["score"]})', flush=True)
            time.sleep(0.3)
        
        browser.close()
    
    # 保存 JSON
    output_data = {'jobs': jobs_scored, 'source': 'alibaba_cloud', 'date': timestamp}
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
    scan_alibaba_cloud()
