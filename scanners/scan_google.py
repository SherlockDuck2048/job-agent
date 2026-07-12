# -*- coding: utf-8 -*-
"""
Google Careers Job Scanner
- 站点: https://www.google.com/about/careers/applications/jobs/results/?location=Hongkong
- 方法: connect_over_cdp (SPA, 需点击展开详情)
- 结构: 列表页 h3 标题 → 点击展开详情面板 → 提取 JD
- 输出: JSON + 自动追加到 Excel
"""
import sys, os, time, json, re
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cco_scorer import score_job, get_priority
from job_scanner_base import append_scanner_to_excel

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

CDP_URL = "http://localhost:9222"
LISTING_URL = "https://www.google.com/about/careers/applications/jobs/results/?location=Hongkong"

# Google Careers 的筛选标签（不是职位）
FILTER_LABELS = ['Locations', 'Experience', 'Skills & qualifications', 'Degree', 'Job types', 'Organizations', 'Sort by']

def get_job_titles(page):
    """
    Stage 1: 从列表页获取所有职位标题和对应的 h3 元素
    返回: [{'title': ..., 'element': h3_element}, ...]
    """
    time.sleep(3)
    
    h3s = page.query_selector_all('h3')
    jobs = []
    for h3 in h3s:
        title = h3.inner_text().strip()
        if title not in FILTER_LABELS:
            jobs.append({'title': title, 'element': h3})
    
    return jobs

def extract_jd_from_page(page, title):
    """
    Stage 2: 从详情面板提取 JD 文本
    点击后面板显示在页面中，提取标题之后、导航元素之前的内容
    """
    body = page.inner_text('body')
    lines = body.split('\n')
    
    detail_start = False
    detail_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if line_stripped == title:
            detail_start = True
            continue
        if detail_start:
            # 遇到导航/操作元素时停止
            if line_stripped in ['search', 'arrow_back', 'help_outline', 'feedback', 'Sign in', 'Send feedback']:
                break
            if line_stripped.startswith('https://') or line_stripped == 'Jobs search results':
                continue
            detail_lines.append(line_stripped)
    
    return '\n'.join(detail_lines) if detail_lines else body[:5000]

def scan_google():
    """
    主函数：扫描 Google Careers 职位
    """
    timestamp = datetime.now().strftime('%Y-%m-%d')
    output_file = os.path.join(OUTPUT_DIR, f'google_{timestamp}.json')
    
    jobs_scored = []
    
    with sync_playwright() as p:
        print('[Stage 1] Connecting to CDP...', flush=True)
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.new_context()
        page = context.new_page()
        
        print(f'[Stage 1] Loading: {LISTING_URL}', flush=True)
        page.goto(LISTING_URL, timeout=30000, wait_until='networkidle')
        
        # Stage 1: 获取职位列表
        job_list = get_job_titles(page)
        print(f'[Stage 1] Found {len(job_list)} jobs', flush=True)
        
        if not job_list:
            print('[Stage 1] No jobs found!', flush=True)
            browser.close()
            return None, []
        
        # Stage 2: 逐个点击并提取 JD
        print('\n[Stage 2] Extracting JD and scoring...', flush=True)
        for i, job in enumerate(job_list, 1):
            title = job['title']
            print(f'[Stage 2] ({i}/{len(job_list)}) {title[:60]}', flush=True)
            
            # 通过 h3 定位并点击
            h3 = job['element']
            
            try:
                h3.click()
                time.sleep(2)
                
                # 提取 JD 文本
                jd_text = extract_jd_from_page(page, title)
                
                if not jd_text or len(jd_text) < 50:
                    print(f'  [WARN] JD too short ({len(jd_text) if jd_text else 0} chars)', flush=True)
                    continue
                
                print(f'  JD: {len(jd_text)} chars', flush=True)
                
                # 评分
                job_data = {
                    'title': title,
                    'description': jd_text[:10000]
                }
                scored = score_job(job_data)
                
                # 提取地点
                location = 'Hong Kong'
                loc_match = re.search(r'place\n([^\\n]+)', jd_text[:500])
                if loc_match:
                    location = loc_match.group(1).strip()
                
                # 提取经验等级
                experience = ''
                exp_match = re.search(r'bar_chart\n([^\\n]+)', jd_text[:300])
                if exp_match:
                    experience = exp_match.group(1).strip()
                
                job_scored = {
                    'title': title,
                    'company': 'Google',
                    'link': LISTING_URL,
                    'source': 'google',
                    'date': timestamp,
                    'location': location,
                    'experience': experience,
                    'jd': jd_text[:5000],
                    'score': scored['score'],
                    'priority': scored['priority'],
                    'recommend': scored['isRecommended'],
                    'comment': scored['comment']
                }
                
                jobs_scored.append(job_scored)
                print(f'  Score: {scored["priority"]} ({scored["score"]})', flush=True)
                
            except Exception as e:
                print(f'  [WARN] Failed: {e}', flush=True)
            
            time.sleep(1)
        
        browser.close()
    
    # 保存 JSON（按标准格式，含 jobs/source 包装）
    output_data = {
        'jobs': jobs_scored,
        'source': 'google',
        'date': timestamp
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    # 追加到 Excel
    print('\n[Stage 3] Appending to Excel...', flush=True)
    try:
        append_scanner_to_excel(output_file)
    except Exception as e:
        print(f'[WARN] Excel append failed: {e}', flush=True)
    
    print(f'\n[Done] Saved {len(jobs_scored)} scored jobs to {output_file}', flush=True)
    print(f'[Done] P0: {sum(1 for j in jobs_scored if j["priority"] == "P0")}, '
          f'P1: {sum(1 for j in jobs_scored if j["priority"] == "P1")}', flush=True)
    
    return output_file, jobs_scored

if __name__ == '__main__':
    scan_google()
