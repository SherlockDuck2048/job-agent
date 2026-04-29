#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JobsDB Scanner
URL: https://hk.jobsdb.com/AI-jobs/in-Hong-Kong-SAR (from scan_strategies.py)
方法: CDP (localhost:9222 Chrome debug port)

[Plan C] Integrated: JD fetch via get_jd_from_url(platform='jobsdb')
[Plan X] Integrated: Cross-session dedup via seen_jobs
[Two-stage] Stage1=collect hrefs, Stage2=JD+score+dedup
JSON格式: 与zurich_2026-04-28.json一致
"""
import sys, os, json, time, io
from datetime import datetime
from playwright.sync_api import sync_playwright

# Windows 控制台 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, check_job_status, update_job_entry, save_seen_jobs

# ===== 配置 =====
KEYWORDS = ["AI"]
LOCATION = "Hong Kong"
JOBS_DB_CFG = SCAN_STRATEGIES["jobsdb"]
SEARCH_URL = JOBS_DB_CFG["url"]  # e.g. https://hk.jobsdb.com/AI-jobs/in-Hong-Kong-SAR?sortmode=ListedDate

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw",
                           f"jobsdb_{datetime.now().strftime('%Y-%m-%d')}.json")
RAW_FILE = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw",
                        f"jobsdb_raw_{datetime.now().strftime('%Y-%m-%d')}.json")

# ===== 工具函数 =====
def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _build_page_url(base_url, page_num):
    """为JobsDB构造分页URL"""
    if page_num == 1:
        return base_url
    # base_url = https://hk.jobsdb.com/AI-jobs/in-Hong-Kong-SAR?sortmode=ListedDate
    sep = '&' if '?' in base_url else '?'
    return f"{base_url}{sep}page={page_num}"


def scan_jobsdb():
    print("=== JobsDB Scanner ===")
    print("  [Plan C] JD fetch enabled (platform=jobsdb)")
    print("  [Plan X] Cross-session dedup enabled")
    scorer = CCOSCORER()
    all_jobs = []
    raw_jobs = []

    # [Plan X] Load seen jobs
    seen_data = load_seen_jobs()
    new_matched = []

    with sync_playwright() as p:
        # CDP 复用本地 Chrome（需已启动调试模式）
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"CDP 连接失败: {e}")
            return []

        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        # ===== Stage 1: 遍历所有页面，收集 href 去重 =====
        page = context.new_page()
        page_num = 1
        seen_hrefs = set()  # href 主干去重（全局）

        while True:
            url = _build_page_url(SEARCH_URL, page_num)
            print(f"\n--- Page {page_num}: {url} ---")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                break

            # 等待职位卡片稳定（JobsDB 动态渲染）
            _wait_for_page_stable(page)

            cards = page.query_selector_all(
                '[data-testid="job-card"], article[data-automation="jobCard"], .job-card'
            )
            print(f"  Cards: {len(cards)}")

            if not cards:
                print("  No cards — stopping pagination.")
                break

            new_cards_count = 0
            for card in cards:
                try:
                    link_el = card.query_selector('a[href*="/job/"]')
                    if not link_el:
                        continue
                    href = link_el.get_attribute("href") or ""
                    if not href:
                        continue

                    # 标准化为完整 URL 并去除 query param
                    if href.startswith("/"):
                        full_link = f"https://hk.jobsdb.com{href}"
                    elif not href.startswith("http"):
                        full_link = f"https://hk.jobsdb.com/{href}"
                    else:
                        full_link = href
                    link_key = full_link.split("?")[0]

                    # href 主干去重
                    if link_key in seen_hrefs:
                        continue
                    seen_hrefs.add(link_key)

                    # 提取标题和公司
                    title_el = card.query_selector(
                        'h1, h2, h3, [data-testid="job-title"], .job-title'
                    )
                    title = title_el.inner_text().strip() if title_el else ""
                    if not title:
                        continue

                    company_el = card.query_selector(
                        '.company, [data-testid="company-name"], .job-company'
                    )
                    company = company_el.inner_text().strip() if company_el else "JobsDB"

                    job = {
                        "title": title,
                        "company": company,
                        "location": LOCATION,
                        "link": full_link,
                        "keyword": "AI",
                        "source": "JobsDB",
                        "description": "",  # Plan C: 将在 Stage 2 填充
                        "scraped_at": datetime.now().isoformat()
                    }
                    raw_jobs.append(job)
                    new_cards_count += 1

                except Exception as e:
                    print(f"  [WARN] card parse error: {e}")

            print(f"  New cards: {new_cards_count} (total raw: {len(raw_jobs)})")

            # 如果本页新卡片 < 5 张，大概率已到尾页
            if new_cards_count < 5:
                print(f"  Low count ({new_cards_count}) — assuming last page.")
                break

            page_num += 1
            time.sleep(2)

        _safe_close(page)

        # ===== Stage 2: Plan C + Plan X + 评分 =====
        print(f"\n=== Stage 2: Processing {len(raw_jobs)} raw jobs ===")

        jd_page = new_page(context)

        for job in raw_jobs:
            title = job["title"]
            link = job["link"]
            link_key = link.split("?")[0]

            try:
                # quick_filter 过滤
                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [FILTER] {title[:40]} - {fr['reason']}", flush=True)
                    continue
                print(f"  [PASS] {title[:40]}", flush=True)

                # [Plan C] JD 抓取
                jd_text = get_jd_from_url(jd_page, link_key, platform='jobsdb')
                job["description"] = jd_text
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars", flush=True)
                else:
                    print(f"    [JD] empty/failed", flush=True)

                # 评分
                scored = score_job(job)

                if scored.get("isRecommended"):
                    # [Plan X] 检查是否新职位
                    status = check_job_status(link_key, title, seen_data)
                    if status == "new":
                        update_job_entry(link_key, title, "JobsDB", jd_text, seen_data, status)
                        new_matched.append(scored)
                    all_jobs.append(scored)
                    print(f"  [MATCH] {title[:55]} "
                          f"(P{scored.get('priority')}, {scored.get('score')}) [{status.upper()}]", flush=True)
                else:
                    print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})", flush=True)

            except Exception as e:
                print(f"  [ERR] {title[:40]}: {e}", flush=True)

        _safe_close(jd_page)
        browser.close()

    # [Plan X] 保存 seen_jobs
    if new_matched:
        save_seen_jobs(seen_data)
        print(f"\n  [Plan X] Saved {len(new_matched)} new jobs to seen_jobs.json", flush=True)

    # href 去重（最终保障）
    seen_final = set()
    unique = []
    for j in all_jobs:
        lk = j.get("link", "").split("?")[0]
        if lk not in seen_final:
            seen_final.add(lk)
            unique.append(j)
    all_jobs = unique

    # ===== 输出 JSON（与 zurich_2026-04-28.json 格式一致）=====
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)

    raw_output = {
        "source": "JobsDB",
        "url": SEARCH_URL,
        "date": datetime.now().isoformat(),
        "total_raw": len(raw_jobs),
        "total_matched": len(all_jobs),
        "jobs": raw_jobs
    }
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(raw_output, f, ensure_ascii=False, indent=2)

    matched_output = {
        "source": "JobsDB",
        "url": SEARCH_URL,
        "date": datetime.now().isoformat(),
        "total_raw": len(raw_jobs),
        "total_matched": len(all_jobs),
        "jobs": all_jobs
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(matched_output, f, ensure_ascii=False, indent=2)

    # Excel 追加
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)

    print(f"\n=== Done ===")
    print(f"  [RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}", flush=True)

    return all_jobs


def _wait_for_page_stable(page, timeout=15):
    """
    等待页面渲染稳定：连续2次查询到的卡片数不变，且等待至少3秒
    """
    prev_count = 0
    for _ in range(timeout):
        time.sleep(1)
        cards = page.query_selector_all(
            '[data-testid="job-card"], article[data-automation="jobCard"], .job-card'
        )
        count = len(cards)
        if count == prev_count and count > 0:
            # 连续相同，可以继续
            break
        prev_count = count
    return


if __name__ == "__main__":
    scan_jobsdb()
