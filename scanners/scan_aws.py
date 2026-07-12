# -*- coding: utf-8 -*-
r"""
AWS Scanner - Amazon Jobs for AWS Hong Kong positions
URL: https://www.amazon.jobs/en/search?offset=0&result_limit=10&sort=relevant&country%5B%5D=HKG&business_category%5B%5D=amazon-web-services

架构: 两阶段
  Stage 1: 分页提取所有职位条目（标题、链接、位置）
  Stage 2: 获取JD并评分 (Plan C + Plan X)
"""
import sys, os, json, time, re, io
from datetime import datetime
from urllib.parse import urljoin

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from seen_jobs import load_seen_jobs, update_job_entry, save_seen_jobs
from cco_scorer import score_job

NAME = "AWS"
BASE_URL = "https://www.amazon.jobs/en/search?offset={}&result_limit=10&sort=relevant&country%5B%5D=HKG&business_category%5B%5D=amazon-web-services"
RAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'candidates', 'raw')
os.makedirs(RAW_DIR, exist_ok=True)

def get_aws_jd(page, url):
    """
    从AWS职位详情页获取JD内容
    AWS页面结构: <div class="section"> 包含各个部分 (Description, Basic Qualifications等)
    """
    try:
        page.goto(url, timeout=30000, wait_until='domcontentloaded')
        time.sleep(2)  # 等待JS加载
        
        # 方法1: 提取所有 section div 的内容
        sections = page.query_selector_all('div.section')
        if sections:
            jd_parts = []
            for section in sections:
                text = section.inner_text().strip()
                if text:
                    jd_parts.append(text)
            return '\n\n'.join(jd_parts)
        
        # 方法2: 提取 content div 的内容
        content_div = page.query_selector('div.content')
        if content_div:
            return content_div.inner_text()
        
        # 方法3: 提取 main 标签的内容
        main = page.query_selector('main')
        if main:
            return main.inner_text()
        
        return ""
    except Exception as e:
        print(f"    [get_aws_jd] Error: {e}")
        return ""

def scan_aws():
    print("=== AWS Scanner ===")
    
    all_jobs = []
    seen_data = load_seen_jobs()
    offset = 0
    page_size = 10
    
    # Stage 1: 抓取职位列表
    print(f"\n  [Stage 1] Fetching job list...")
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        while True:
            url = BASE_URL.format(offset)
            print(f"  [Stage 1] Fetching offset={offset}: {url}")
            
            try:
                page.goto(url, timeout=30000, wait_until='domcontentloaded')
                time.sleep(3)
                
                # 查找职位卡片
                job_cards = page.query_selector_all('.job-tile')
                if not job_cards:
                    print(f"  [Stage 1] No job cards found at offset={offset}")
                    break
                
                print(f"  [Stage 1] Found {len(job_cards)} job cards")
                
                for card in job_cards:
                    try:
                        # 提取标题和链接
                        title_elem = card.query_selector('h3.job-title a') or \
                                     card.query_selector('h3 a') or \
                                     card.query_selector('a[href*="/jobs/"]')
                        if not title_elem:
                            continue
                        
                        title = title_elem.inner_text().strip()
                        link = title_elem.get_attribute('href')
                        if link and not link.startswith('http'):
                            link = urljoin('https://www.amazon.jobs', link)
                        
                        # 提取位置
                        location_elem = card.query_selector('li')
                        location = 'Hong Kong'
                        if location_elem:
                            loc_text = location_elem.inner_text().strip()
                            if loc_text:
                                location = loc_text
                        
                        # 去重检查
                        link_key = re.sub(r'\?.*$', '', link)
                        if seen_data.get('jobs', {}).get(link_key):
                            print(f"  [Stage 1] Skipping (seen): {title[:50]}")
                            continue
                        
                        all_jobs.append({
                            'title': title,
                            'link': link,
                            'location': location,
                            'company': 'Amazon AWS',
                        })
                        
                    except Exception as e:
                        print(f"  [Stage 1] Error parsing card: {e}")
                        continue
                
                # 检查是否还有更多页面 (通过offset判断)
                offset += page_size
                if offset >= 100:  # 最多抓10页
                    print(f"  [Stage 1] Reached max pages")
                    break
                    
            except Exception as e:
                print(f"  [Stage 1] Error fetching page offset={offset}: {e}")
                break
        
        browser.close()
    
    print(f"\n  [Stage 1] Total jobs found: {len(all_jobs)}")
    
    # Stage 2: 获取JD并评分
    print(f"\n  [Stage 2] Fetching JD and scoring...")
    matched_jobs = []
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for idx, job in enumerate(all_jobs, 1):
            print(f"  [{idx}/{len(all_jobs)}] {job['title'][:60]}")
            
            try:
                # 获取JD
                jd_text = get_aws_jd(page, job['link'])
                
                if not jd_text:
                    print(f"    [Stage 2] No JD found, skipping")
                    continue
                
                print(f"    [Stage 2] JD length: {len(jd_text)} chars")
                
                # 评分
                job['description'] = jd_text
                result = score_job(job)
                
                score = result.get('score', 0)
                priority = result.get('priority', '')
                match_reason = result.get('match_reason', '')
                
                print(f"    [Stage 2] Score: {score}, Priority: {priority}")
                
                if priority in ('P0', 'P1'):
                    matched_jobs.append({
                        'Company': job['company'],
                        'Title': job['title'],
                        'Location': job['location'],
                        'Score': score,
                        'Priority': priority,
                        'Match Reason': match_reason,
                        'Link': job['link'],
                        'Keyword': 'AI',
                        'Scraped At': datetime.now().isoformat(),
                    })
                    
                    # 更新seen_jobs
                    link_key = re.sub(r'\?.*$', '', job['link'])
                    update_job_entry(
                        link=link_key,
                        title=job['title'],
                        company=job['company'],
                        jd_text=jd_text,
                        seen_data=seen_data,
                        status='matched'
                    )
                
                time.sleep(1)
                
            except Exception as e:
                print(f"    [Stage 2] Error processing job: {e}")
                continue
        
        browser.close()
    
    # 保存seen_data
    save_seen_jobs(seen_data)
    
    # 写入Excel
    if matched_jobs:
        json_path = os.path.join(RAW_DIR, f'aws_{datetime.now().strftime("%Y-%m-%d")}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({'source': NAME, 'jobs': matched_jobs}, f, ensure_ascii=False, indent=2)
        
        append_scanner_to_excel(json_path)
        print(f"\n=== AWS Scanner Complete ===")
        print(f"Matched: {len(matched_jobs)}")
        print(f"Results saved to: {json_path}")
    else:
        print(f"\n=== AWS Scanner Complete ===")
        print(f"No P0/P1 jobs found")
    
    return matched_jobs

if __name__ == '__main__':
    scan_aws()
