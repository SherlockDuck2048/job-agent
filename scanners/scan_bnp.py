# -*- coding: utf-8 -*-
"""
BNP Paribas Job Scanner
- 目标站点: https://group.bnpparibas/en/careers/all-job-offers/hong-kong?page=1
- 方法: connect_over_cdp (需要登录态/Cookies绕过403)
- 输出: JSON + 自动追加到 Excel
"""
import sys, os, time, re, json
from datetime import datetime
from playwright.sync_api import sync_playwright

# 添加父目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cco_scorer import score_job, get_priority
from job_scanner_base import append_scanner_to_excel

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

CDP_URL = "http://localhost:9222"
LISTING_URL = "https://group.bnpparibas/en/careers/all-job-offers/hong-kong"
MAX_PAGES = 7  # 66 jobs, ~10 per page = 7 pages


def _wait_for_job_links(page, timeout=15000):
    """等待职位链接出现（SPA 路由稳定后再查询，避免 execution context destroyed）"""
    try:
        page.wait_for_selector('a[href*="/job-offer/"]', timeout=timeout, state='attached')
    except Exception:
        pass  # 兜底：get_job_links 内部会重试


def _safe_query_all(page, selector, retries=3):
    """带重试的 query_selector_all，吸收瞬时 context 销毁错误"""
    last = None
    for i in range(retries):
        try:
            return page.query_selector_all(selector)
        except Exception as e:
            last = e
            if i < retries - 1:
                print(f'  [retry] query context destroyed, retrying ({i+1}/{retries})...', flush=True)
                time.sleep(1)
    print(f'  [WARN] query_selector_all failed after {retries} retries: {last}', flush=True)
    return []


def get_job_links_from_listing(page):
    """
    Stage 1: 从列表页提取所有职位链接
    返回: [{'title': ..., 'link': ...}, ...]
    """
    # 等待列表稳定（替代原有的固定 sleep，避免 SPA 导航 race）
    _wait_for_job_links(page)

    # 获取所有职位链接
    links = _safe_query_all(page, 'a[href*="/job-offer/"]')

    jobs = []
    for link in links:
        href = link.get_attribute('href')
        # 转为绝对 URL
        if href.startswith('/'):
            href = f'https://group.bnpparibas{href}'

        text = link.inner_text().strip()
        # 文本格式: PERMANENT\nTitle\nHONG KONG, HONG KONG
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        if len(lines) >= 2:
            title = lines[1]  # 第二行是标题
            jobs.append({'title': title, 'link': href})

    # 去重
    seen_links = set()
    unique_jobs = []
    for job in jobs:
        if job['link'] not in seen_links:
            seen_links.add(job['link'])
            unique_jobs.append(job)

    return unique_jobs

def get_jd_from_url(page, url):
    """
    Stage 2: 从职位详情页提取 JD
    返回: jd_text 或 None
    """
    try:
        page.goto(url, timeout=30000, wait_until='networkidle')
        time.sleep(1)

        # 获取页面文本
        body_text = page.inner_text('body')

        # 截取 JD 部分 (从职位描述开始到 "LAST UPDATE" 之前)
        # 简化: 直接返回前 5000 字符
        return body_text[:5000] if body_text else None

    except Exception as e:
        print(f'[WARN] get_jd_from_url failed: {url} -> {e}', flush=True)
        return None

def scan_bnp():
    """
    主函数:扫描 BNP Paribas 职位
    """
    timestamp = datetime.now().strftime('%Y-%m-%d')
    output_file = os.path.join(OUTPUT_DIR, f'bnp_{timestamp}.json')

    jobs_raw = []
    jobs_scored = []

    with sync_playwright() as p:
        print('[Stage 1] Connecting to CDP...', flush=True)
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.new_context()
        page = context.new_page()

        page_num = 1
        has_more = True

        # 进入第 1 页
        page.goto(LISTING_URL + '?page=1', timeout=30000, wait_until='networkidle')

        while page_num <= MAX_PAGES and has_more:
            print(f'\n[Stage 1] Scanning page {page_num}', flush=True)

            # 等待列表加载稳定后再提取（避免 SPA 路由导致的 execution context destroyed）
            _wait_for_job_links(page)
            job_links = get_job_links_from_listing(page)
            print(f'[Stage 1] Found {len(job_links)} jobs on page {page_num}', flush=True)

            for job in job_links:
                jobs_raw.append({
                    'title': job['title'],
                    'company': 'BNP Paribas',
                    'link': job['link'],
                    'source': 'bnp',
                    'date': timestamp,
                    'location': 'Hong Kong',
                })

            # 尝试翻到下一页：直接导航并检测是否还有职位链接（每页仅导航一次）
            next_url = LISTING_URL + f'?page={page_num + 1}'
            page.goto(next_url, timeout=30000, wait_until='networkidle')
            _wait_for_job_links(page)
            next_page_links = _safe_query_all(page, 'a[href*="/job-offer/"]')
            if next_page_links:
                page_num += 1
            else:
                print('[Stage 1] No more pages', flush=True)
                has_more = False

        print(f'\n[Stage 1] Total raw jobs: {len(jobs_raw)}', flush=True)

        # Stage 2: 获取 JD 并评分（每个 job 直接导航详情页，无需回到列表）
        print('\n[Stage 2] Fetching JD and scoring...', flush=True)
        for i, job in enumerate(jobs_raw, 1):
            print(f'[Stage 2] ({i}/{len(jobs_raw)}) {job["title"][:50]}', flush=True)

            jd_text = get_jd_from_url(page, job['link'])
            if not jd_text:
                print(f'  [WARN] No JD found, skipping', flush=True)
                continue

            # 评分
            job_data = {
                'title': job['title'],
                'description': jd_text
            }
            scored = score_job(job_data)

            job_scored = {
                **job,
                'jd': jd_text,
                'description': jd_text,        # for Excel JD summary
                'match_reason': scored['comment'],  # for Excel Match Reason
                'scraped_at': timestamp,
                'score': scored['score'],
                'priority': scored['priority'],
                'recommend': scored['isRecommended'],
                'comment': scored['comment']
            }

            jobs_scored.append(job_scored)
            print(f'  Score: {scored["priority"]} ({scored["score"]})', flush=True)

            time.sleep(1)

        browser.close()

    # 保存 JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'source': 'bnp',
            'scan_date': timestamp,
            'jobs': jobs_scored,
        }, f, ensure_ascii=False, indent=2)

    # 追加到 Excel
    print('\n[Stage 3] Appending to Excel...', flush=True)
    # 追加到 Excel -- 与所有其他扫描器一致,写入 config/HK_AI_Jobs_All.xlsx
    # (该文件 schema 与 append_scanner_to_excel 的预期一致;candidates/ 为旧 9 列 schema 已损坏)
    excel_path = os.path.join(WORKSPACE_ROOT, 'config', 'HK_AI_Jobs_All.xlsx')
    try:
        append_scanner_to_excel(output_file, excel_path)
    except Exception as e:
        print(f'[WARN] Excel append failed: {e}', flush=True)

    print(f'\n[Done] Saved {len(jobs_scored)} scored jobs to {output_file}', flush=True)
    print(f'[Done] P0: {sum(1 for j in jobs_scored if j["priority"] == "P0")}, '
          f'P1: {sum(1 for j in jobs_scored if j["priority"] == "P1")}', flush=True)

    return output_file, jobs_scored

if __name__ == '__main__':
    scan_bnp()
