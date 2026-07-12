# -*- coding: utf-8 -*-
r"""
Tencent Careers Scanner - Hong Kong positions
URL: https://careers.tencent.com/en-us/search.html?query=co_1,ci_37
API: GET https://careers.tencent.com/tencentcareer/api/post/Query?cityId=37&countryId=5&pageIndex=1&pageSize=50&language=en-us

架构: 单阶段（纯HTTP，无需浏览器）
  Stage 1: 调用API获取所有职位JSON → 解析 → 评分 → 写入Excel
  API返回已含完整JD (Responsibility字段)，无需Stage 2
"""
import sys, os, json, time, re, io
from datetime import datetime
import urllib.request
import urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
from job_scanner_base import append_scanner_to_excel
from seen_jobs import load_seen_jobs, update_job_entry, save_seen_jobs
from cco_scorer import score_job

NAME = "Tencent"
API_URL = (
    "https://careers.tencent.com/tencentcareer/api/post/Query"
    "?cityId=37&countryId=5&pageIndex=1&pageSize=50&language=en-us"
)
RAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'candidates', 'raw')
os.makedirs(RAW_DIR, exist_ok=True)


def fetch_json(url, max_retries=3):
    """
    HTTP GET请求获取JSON响应
    重试机制（指数退避）
    """
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/125.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Referer': 'https://careers.tencent.com/en-us/search.html',
    }

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('Code') == 200:
                    return data
                else:
                    print(f"  [API] Unexpected response code: {data.get('Code')}")
                    return None
        except Exception as e:
            print(f"  [API] Attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
    return None


def scan_tencent():
    print(f"=== {NAME} Scanner ===")
    print(f"  [Stage 1] Fetching jobs from API...")
    print(f"  [Stage 1] URL: {API_URL}")

    data = fetch_json(API_URL)
    if not data:
        print(f"  [Stage 1] Failed to fetch API data")
        return []

    posts = data.get('Data', {}).get('Posts', [])
    total_count = data.get('Data', {}).get('Count', 0)
    print(f"  [Stage 1] API returned {total_count} jobs total, {len(posts)} in current page")

    # 只保留香港职位
    hk_posts = [p for p in posts if p.get('LocationName', '').lower() == 'hong kong']
    print(f"  [Stage 1] Hong Kong jobs: {len(hk_posts)}/{len(posts)}")

    if not hk_posts:
        print(f"  [Stage 1] No Hong Kong jobs found")
        return []

    # Stage 2: 评分
    print(f"\n  [Stage 2] Scoring jobs...")
    seen_data = load_seen_jobs()
    matched_jobs = []

    for idx, post in enumerate(hk_posts, 1):
        title = post.get('RecruitPostName', '').strip()
        post_id = post.get('PostId', '')
        post_url = post.get('PostURL', '')
        bg_name = post.get('BGName', '')
        category = post.get('CategoryName', '')
        location = post.get('LocationName', '')
        responsibility = post.get('Responsibility', '')

        print(f"  [{idx}/{len(hk_posts)}] {title[:60]}")

        # 构建link_key (去重用)
        link_key = post_url or f"tencent_{post_id}"

        # 跳过已见过的
        if seen_data.get('jobs', {}).get(link_key):
            print(f"    [Stage 2] Skipping (seen)")
            continue

        if not responsibility:
            print(f"    [Stage 2] No JD content, skipping")
            continue

        # 构建job dict用于评分
        job = {
            'title': title,
            'link': link_key,
            'company': 'Tencent 腾讯',
            'location': location,
            'description': responsibility,
            'category': category,
            'bg_name': bg_name,
        }

        result = score_job(job)
        score = result.get('score', 0)
        priority = result.get('priority', '')
        match_reason = result.get('match_reason', '')

        print(f"    [Stage 2] Score: {score}, Priority: {priority}")

        if priority in ('P0', 'P1'):
            matched_jobs.append({
                'Company': job['company'],
                'Title': title,
                'Location': location,
                'Score': score,
                'Priority': priority,
                'Match Reason': match_reason,
                'Link': link_key,
                'Keyword': 'AI',
                'Scraped At': datetime.now().isoformat(),
            })

            # 更新seen_jobs (含完整JD)
            update_job_entry(
                link=link_key,
                title=title,
                company=job['company'],
                jd_text=responsibility,
                seen_data=seen_data,
                status='matched'
            )
        elif score > 0:
            # 非匹配但也算看过
            update_job_entry(
                link=link_key,
                title=title,
                company=job['company'],
                jd_text=responsibility,
                seen_data=seen_data,
                status='skipped'
            )

    # 保存seen_data
    save_seen_jobs(seen_data)

    # 写入Excel
    if matched_jobs:
        date_str = datetime.now().strftime("%Y-%m-%d")
        json_path = os.path.join(RAW_DIR, f'tencent_{date_str}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({'source': NAME, 'jobs': matched_jobs}, f, ensure_ascii=False, indent=2)

        append_scanner_to_excel(json_path)
        print(f"\n=== {NAME} Scanner Complete ===")
        print(f"Matched: {len(matched_jobs)}")
        print(f"Results saved to: {json_path}")
    else:
        print(f"\n=== {NAME} Scanner Complete ===")
        print(f"No P0/P1 jobs found")

    return matched_jobs


if __name__ == '__main__':
    scan_tencent()
