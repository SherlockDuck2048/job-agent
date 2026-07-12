#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JobsDB Scanner — 详细代码注释版

【扫描器整体架构】
本扫描器采用两阶段（Two-Stage）设计：
  Stage 1: 遍历搜索结果所有分页，收集职位卡片的 href 链接（不去重、不抓 JD、不评分）
  Stage 2: 对 Stage 1 收集到的原始职位，逐个抓 JD → 评分 → 去重 → 输出

【核心设计模式】
  - Plan C: JD 动态抓取（通过 get_jd_from_url 从详情页抓取完整 JD 文本）
  - Plan X: 跨会话去重（通过 seen_jobs.json 记录已见过的职位，避免重复推送）
  - CDP 模式: 复用本地已登录的 Chrome（localhost:9222），可绕过反爬登录墙

【依赖关系】
  - config/scan_strategies.py   → 读取扫描策略（URL、选择器、平台配置）
  - cco_scorer.py              → CCOSCORER 类，quick_filter() + score_job()
  - job_scanner_base.py        → get_jd_from_url(), new_page(), append_scanner_to_excel()
  - seen_jobs.py               → load_seen_jobs(), check_job_status(), update_job_entry(), save_seen_jobs()

【输入/输出】
  - 输入: scan_strategies["jobsdb"]["url"]（搜索 URL）
  - 输出 JSON: candidates/raw/jobsdb_YYYY-MM-DD.json       （matched 职位）
               candidates/raw/jobsdb_raw_YYYY-MM-DD.json  （全部 raw 职位）
  - 输出 Excel: config/HK_AI_Jobs_All.xlsx（通过 append_scanner_to_excel 追加）
"""

# =====================================================================
# 标准库导入
# =====================================================================
import sys      # 系统相关：命令行参数、标准输入输出控制
import os       # 操作系统接口：文件路径、目录操作
import json     # JSON 编解码：读写扫描结果 JSON 文件
import time     # 时间相关：sleep 延时、时间戳
import io       # I/O 操作：用于重定向 stdout/stderr 编码

# 第三方库导入
from datetime import datetime           # 日期时间：生成时间戳、日期字符串
from playwright.sync_api import sync_playwright  # 浏览器自动化：控制 Chrome 渲染页面

# =====================================================================
# Windows 控制台 UTF-8 编码修复
# =====================================================================
# 问题：Windows PowerShell/CMD 默认 GBK 编码，直接 print 中文会乱码或报编码错误
# 解决：将 sys.stdout / sys.stderr 替换为 UTF-8 编码的 TextIOWrapper
# errors='replace'：遇到无法编码的字符时用 � 替代，避免程序崩溃
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# =====================================================================
# 模块搜索路径设置
# =====================================================================
# 将 job-agent/ 根目录加入 sys.path，使 Python 能 import config/ 等上级目录模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# 将 scanners/ 目录加入 sys.path，使 Python 能 import 同级目录下的模块（必须放在后面，确保 scanners/ 优先搜索）
sys.path.insert(0, os.path.dirname(__file__))

# =====================================================================
# 业务模块导入
# =====================================================================
from config.scan_strategies import SCAN_STRATEGIES       # 扫描策略配置（各平台 URL、参数）
from cco_scorer import CCOSCORER, score_job             # 评分器：quick_filter() 标题过滤 + score_job() 完整评分
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel  # 基础工具：JD抓取、新建页面、Excel追加
from seen_jobs import load_seen_jobs, check_job_status, update_job_entry, save_seen_jobs  # 跨会话去重

print("SCRIPT LOADED - imports done", flush=True)

# =====================================================================
# ===== 配置区 =====
# =====================================================================

# 搜索关键词列表（当前只用 ["AI"]，保持与 scan_strategies.py 一致）
KEYWORDS = ["AI"]

# 最大翻页数（防止 cron 执行超时；10页约对应250-300个raw职位，抓JD+评分约需15-20分钟）
MAX_PAGE = 5

# 目标地点（注意：原文拼写为 LOCATION，但变量名拼错了，实际不影响运行）
LOCATION = "Hong Kong"

# 从扫描策略配置中读取 JobsDB 的平台配置（url、method 等）
JOBS_DB_CFG = SCAN_STRATEGIES["jobsdb"]

# 搜索 URL（来自配置，例如 https://hk.jobsdb.com/AI-jobs/in-Hong-Kong-SAR?sortmode=ListedDate）
SEARCH_URL = JOBS_DB_CFG["url"]

# 输出文件路径（matched 职位，即评分通过的建议职位）
# 路径：job-agent/candidates/raw/jobsdb_YYYY-MM-DD.json
OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__),   # scanners/ 目录
    "..",                        # 上一级（job-agent/）
    "candidates", "raw",
    f"jobsdb_{datetime.now().strftime('%Y-%m-%d')}.json"
)

# 输出文件路径（raw 职位，即 Stage 1 收集的所有职位卡片）
# 注意：只有通过了 quick_filter 的职位才会在 description 字段填充 JD 文本
RAW_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "candidates", "raw",
    f"jobsdb_raw_{datetime.now().strftime('%Y-%m-%d')}.json"
)


# =====================================================================
# ===== 工具函数 =====
# =====================================================================

def _safe_close(page):
    """
    【安全关闭 Playwright Page 对象】

    功能：
        尝试关闭 Playwright 的 page 对象，如果页面已关闭则忽略异常。
        避免因重复关闭或操作已关闭的页面导致异常中断扫描流程。

    参数：
        page: Playwright Page 对象，或 None

    逻辑：
        1. 先检查 page 是否为 None（未初始化时直接跳过）
        2. 再检查 page.is_closed()（页面可能已被其他逻辑关闭）
        3. 两个条件都满足时才调用 page.close()
        4. 任何异常均静默忽略（pass）
    """
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def _build_page_url(base_url, page_num):
    """
    【构造 JobsDB 分页 URL】

    功能：
        根据当前页码，在基础搜索 URL 后追加 page=N 参数。
        JobsDB 的分页格式为：?page=2（第一页无需追加参数）

    参数：
        base_url (str): 基础搜索 URL（如 https://hk.jobsdb.com/AI-jobs/in-Hong-Kong-SAR?sortmode=ListedDate）
        page_num (int): 目标页码（从 1 开始）

    返回：
        str: 完整的分页 URL

    逻辑：
        - 第 1 页：直接返回 base_url（JobsDB 第一页无 page 参数）
        - 第 2 页及以上：
            - 如果 base_url 已有 ? 参数，用 & 连接：base_url & page=N
            - 如果 base_url 无 ? 参数，用 ? 连接：base_url ? page=N
    """
    if page_num == 1:
        return base_url
    # 判断 base_url 是否已包含查询参数，决定连接符
    sep = '&' if '?' in base_url else '?'
    return f"{base_url}{sep}page={page_num}"


def _wait_for_page_stable(page, timeout=15):
    """
    【等待 JobsDB 页面渲染稳定】

    功能：
        JobsDB 使用 JavaScript 动态渲染职位卡片，页面加载完成后卡片可能还在异步渲染。
        本函数通过「连续检测卡片数量是否稳定」来判断页面渲染完成。

    参数：
        page: Playwright Page 对象
        timeout (int): 最大等待秒数（默认 15 秒）

    逻辑：
        1. 每秒查询一次当前页面中的职位卡片数量
        2. 记录上一次的卡片数 prev_count
        3. 如果本次卡片数 == 上一次卡片数 且 > 0：
           → 说明卡片数量已稳定（连续两次检测不变），认为渲染完成，退出
        4. 如果超时（timeout 秒）仍未稳定：
           → 循环结束，返回（不报错，继续执行后续逻辑）
        5. 选择器说明：
           '[data-testid="job-card"]'        → JobsDB 新版 data-testid 属性
           'article[data-automation="jobCard"]' → JobsDB 旧版 automation 属性
           '.job-card'                        → 通用 CSS 类名兜底

    注意：
        这个函数的退出条件是「连续两次检测到相同数量且 > 0」，
        但代码实际判断是 count == prev_count（不要求 prev_count > 0），
        首次 prev_count=0 时若 count=0 也会退出，这是预期行为（页面为空）。
    """
    prev_count = 0
    for _ in range(timeout):
        time.sleep(1)
        cards = page.query_selector_all(
            '[data-testid="job-card"], article[data-automation="jobCard"], .job-card'
        )
        count = len(cards)
        # 连续两次数量相同（且均 > 0）说明渲染稳定
        if count == prev_count and count > 0:
            break
        prev_count = count
    return


def scan_jobsdb():
    """
    【主扫描函数 — JobsDB 两阶段扫描器】

    【执行流程概览】
    Stage 0: 初始化（打印信息、加载 seen_jobs、初始化评分器）
    Stage 1: 循环翻页，收集所有职位卡片的 href/标题/公司（不去重、不抓 JD）
    Stage 2: 对 raw_jobs 逐个：标题过滤 → 抓 JD → 评分 → 去重 → 收集结果
    Stage 3: 后处理（seen_jobs 持久化、href 最终去重、输出 JSON + Excel）

    【返回值】
        list: 所有 matched 职位（即 isRecommended=True 的职位列表）

    【异常处理】
        - CDP 连接失败 → 打印错误并返回空列表（不崩溃）
        - 单张卡片解析失败 → 捕获异常，打印警告，继续处理下一张
        - 单个职位 Stage 2 处理失败 → 捕获异常，打印错误，继续处理下一个
    """
    print("  [Plan C] JD fetch enabled (platform=jobsdb)", flush=True)
    print("  [Plan X] Cross-session dedup enabled", flush=True)
    print("  [DEBUG] Initializing scorer...", flush=True)

    # 初始化评分器（CCOSCORER 类，内部维护关键词配置和评分规则）
    scorer = CCOSCORER()
    print("  [DEBUG] Scorer initialized", flush=True)

    # all_jobs: 存放所有通过评分的职位（含重复，后续会去重）
    all_jobs = []
    # raw_jobs: 存放 Stage 1 收集到的所有原始职位卡片（未评分、未去重）
    raw_jobs = []

    print("  [DEBUG] Loading seen_jobs...", flush=True)

    # [Plan X] 从 seen_jobs.json 加载已见过的职位记录
    # 返回 dict，结构：{ link_key: { "title": ..., "last_seen": ..., "status": "new"/"seen" } }
    seen_data = load_seen_jobs()

    print("  [DEBUG] Seen_jobs loaded", flush=True)

    # new_matched: 存放本次新发现的推荐职位（用于最后统一写入 seen_jobs.json）
    new_matched = []

    # =====================================================================
    # Playwright CDP 连接（复用本地 Chrome，端口 9222）
    # =====================================================================
    with sync_playwright() as p:
        # 通过 CDP (Chrome DevTools Protocol) 连接到本地已启动的 Chrome 调试端口
        # 使用环境变量 CDP_PORT，或默认 9222（兼容旧版）
        # 优势：复用已登录的 Chrome 会话，绕过登录墙和反爬
        cdp_port = "56114"  # 硬编码测试端口（OpenClaw browser CDP port）
        try:
            print(f"  [INFO] Connecting to CDP... (port {cdp_port})", flush=True)
            # 注意：test_cdp.py 无 timeout 参数，连接成功；添加 timeout 反而超时
            browser = p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
            print("  [INFO] CDP connected successfully!", flush=True)
        except Exception as e:
            print(f"CDP 连接失败: {e}")
            print(f"  请确保 Chrome 已通过 --remote-debugging-port={cdp_port} 启动")
            return []

        # 创建新的浏览器上下文（独立 session，不共享 cookie/缓存）
        # viewport 设置窗口大小，避免页面因窗口过小而隐藏元素
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        # =====================================================================
        # ===== Stage 1: 遍历所有分页，收集职位卡片 href =====
        # =====================================================================
        # 策略：先不抓 JD、不评分，只收集链接和基本信息
        # 原因：JobsDB 翻页较快，先批量收集再批量处理更高效
        #
        # 去重策略：seen_hrefs（内存级去重，防止同一会话内重复收集）
        # 翻页终止条件：本页新增卡片数 < 5 → 判定为尾页
        # =====================================================================

        # 新建页面对象（用于 Stage 1 翻页浏览）
        page = context.new_page()
        page_num = 1                   # 当前页码（从 1 开始）
        seen_hrefs = set()              # href 主干去重集合（全局，跨分页去重）

        while True:
            # 构造当前页的 URL
            url = _build_page_url(SEARCH_URL, page_num)
            print(f"\n--- Page {page_num}: {url} ---")

            # 导航到当前页（wait_until="domcontentloaded"：DOM 加载完成即可，不必等所有资源）
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                break  # 页面加载失败 → 终止翻页

            # 等待页面动态渲染稳定（JobsDB 用 JS 渲染卡片）
            _wait_for_page_stable(page)

            # 用多种选择器获取当前页所有职位卡片元素
            cards = page.query_selector_all(
                '[data-testid="job-card"], article[data-automation="jobCard"], .job-card'
            )
            print(f"  Cards: {len(cards)}")

            # 如果本页没有任何卡片 → 说明已超出有效页数，终止翻页
            if not cards:
                print("  No cards — stopping pagination.")
                break

            # 统计本页「新卡片」数量（用于判断是否为尾页）
            new_cards_count = 0

            # 遍历本页每张职位卡片
            for card in cards:
                try:
                    # --- 提取职位详情页链接 ---
                    # 查找卡片内的 <a href="..."> 元素，href 需包含 "/job/" 特征
                    link_el = card.query_selector('a[href*="/job/"]')
                    if not link_el:
                        continue  # 这张卡片没有链接，跳过

                    href = link_el.get_attribute("href") or ""
                    if not href:
                        continue  # href 为空，跳过

                    # --- 标准化链接为完整 URL ---
                    # JobsDB 的 href 可能是三种格式：
                    #   1. 相对路径: /job/xxx → 补全称 https://hk.jobsdb.com/job/xxx
                    #   2. 无协议路径: hk.jobsdb.com/job/xxx → 补 https://
                    #   3. 完整 URL: https://hk.jobsdb.com/job/xxx → 直接使用
                    if href.startswith("/"):
                        full_link = f"https://hk.jobsdb.com{href}"
                    elif not href.startswith("http"):
                        full_link = f"https://hk.jobsdb.com/{href}"
                    else:
                        full_link = href

                    # link_key: 去除 query 参数后的 URL 主干（用于去重）
                    # 例如：https://.../job/123?src=search → https://.../job/123
                    link_key = full_link.split("?")[0]

                    # --- href 主干去重（跨分页去重）---
                    # 如果这根 link 已经收集过 → 跳过，避免重复
                    if link_key in seen_hrefs:
                        continue
                    seen_hrefs.add(link_key)

                    # --- 提取职位标题 ---
                    # 尝试多种选择器：h1/h2/h3 标签，或 data-testid / class 属性
                    title_el = card.query_selector(
                        'h1, h2, h3, [data-testid="job-title"], .job-title'
                    )
                    title = title_el.inner_text().strip() if title_el else ""
                    if not title:
                        continue  # 标题为空，跳过这张卡片

                    # --- 提取公司名称 ---
                    company_el = card.query_selector(
                        '.company, [data-testid="company-name"], .job-company'
                    )
                    company = company_el.inner_text().strip() if company_el else "JobsDB"

                    # --- 组装 raw job dict ---
                    # description 先留空，Stage 2 中通过 Plan C 填充
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
                    # 单张卡片解析失败不中断整体流程，只打印警告
                    print(f"  [WARN] card parse error: {e}")

            print(f"  New cards: {new_cards_count} (total raw: {len(raw_jobs)})")

            # --- 翻页终止条件 ---
            # 条件1：本页新增卡片数 < 5 → 判定为尾页
            # 条件2：已达到最大翻页数（防止超时，默认限制 10 页）
            if new_cards_count < 5:
                print(f"  Low count ({new_cards_count}) — assuming last page.")
                break
            if page_num >= MAX_PAGE:
                print(f"  Reached max pages ({MAX_PAGE}) — stopping pagination.")
                break

            # 准备翻下一页
            page_num += 1
            time.sleep(2)  # 礼貌性延时，避免触发反爬

        # Stage 1 结束，关闭翻页用的 page 对象
        _safe_close(page)

        # =====================================================================
        # ===== Stage 2: Plan C (JD抓取) + 评分 + Plan X (去重) =====
        # =====================================================================
        # 对 Stage 1 收集到的每个 raw job：
        #   1. quick_filter: 标题关键词过滤（快速淘汰明显不匹配的职位）
        #   2. get_jd_from_url: 抓取 JD 详情页文本（Plan C）
        #   3. score_job: 完整评分（CCO 评分算法）
        #   4. check_job_status: 检查是否为新职位（Plan X 跨会话去重）
        #   5. 如果是新职位 → 写入 seen_jobs.json
        # =====================================================================
        print(f"\n=== Stage2: Processing {len(raw_jobs)} raw jobs ===")

        # 为 JD 抓取新建一个 page 对象（与 Stage 1 的 page 独立，避免冲突）
        jd_page = new_page(context)

        # 遍历所有 raw jobs
        processed_count = 0  # 用于定期持久化计数
        for job in raw_jobs:
            title = job["title"]
            link = job["link"]
            link_key = link.split("?")[0]  # URL 主干，用于去重和 seen_jobs 查询
            status = None  # 每轮初始化，防止异常时 status 泄漏

            try:
                # --- Step 1: quick_filter 标题过滤 ---
                # 只根据职位标题判断是否与 AI/数据/业务分析相关
                # 不相关的直接淘汰，避免不必要的 JD 抓取（节省时间）
                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [FILTER] {title[:40]} - {fr['reason']}", flush=True)
                    continue  # 淘汰，处理下一个职位
                print(f"  [PASS] {title[:40]}", flush=True)

                # --- Step 2: [Plan C] 抓取 JD 详情页文本 ---
                # get_jd_from_url 会根据 platform='jobsdb' 选择正确的选择器和抓取策略
                # 返回值：JD 纯文本字符串（成功）或 空字符串/None（失败）
                jd_text = get_jd_from_url(jd_page, link_key, platform='jobsdb')
                job["description"] = jd_text  # 回填到 job dict（用于评分和输出）
                if jd_text:
                    print(f"    [JD] {len(jd_text)} chars", flush=True)
                else:
                    print(f"    [JD] empty/failed", flush=True)

                # --- Step 2.5: 立即写入 JD 文件（防止被 SIGKILL 丢失）---
                # 只要成功抓到 JD，不管是否 isRecommended，都立即持久化
                # 这样即使进程被 kill，已抓取的 JD 不会丢失
                # ⚠️ 注意：必须在 update_job_entry 之前拿 status，否则 seen_data 已被修改
                # status 已在循环开头初始化为 None，此处仅在有 JD 时赋值
                if jd_text and len(jd_text) > 50:
                    status = check_job_status(link_key, title, seen_data)  # 先查状态（此时 seen_data 还未更新）
                    update_job_entry(link_key, title, "JobsDB", jd_text, seen_data, status)  # 再写入（会修改 seen_data）

                # --- Step 3: 完整评分 ---
                # score_job() 会综合 title + description 进行评分
                # 返回 dict，包含：score, priority (P0/P1/P2), isRecommended, 各维度分项
                scored = score_job(job)

                # --- Step 4: 如果评分通过（isRecommended=True）---
                if scored.get("isRecommended"):
                    # status 已在 Step 2.5 中获取（在 update_job_entry 修改 seen_data 之前）
                    # 此处直接复用，无需再调 check_job_status()
                    if status is None:
                        status = check_job_status(link_key, title, seen_data)  # fallback（理论上不会走到这里）

                    # 无论新旧，都加入 all_jobs（用于本次输出）
                    all_jobs.append(scored)

                    # 新职位才记录到 new_matched（用于日志和 Excel）
                    if status == "new":
                        new_matched.append(scored)

                    print(f"  [MATCH] {title[:55]} "
                          f"(P{scored.get('priority')}, {scored.get('score')}) [{status.upper()}]", flush=True)

                else:
                    # 评分未通过（score < 阈值）
                    print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})", flush=True)

                # --- Step 5: 定期持久化（每 10 个 job）---
                processed_count += 1
                if processed_count % 10 == 0:
                    save_seen_jobs(seen_data)
                    print(f"  [SAVE] checkpoint: processed {processed_count} jobs", flush=True)

            except Exception as e:
                # 单个职位处理失败不中断，打印错误后继续
                print(f"  [ERR] {title[:40]}: {e}", flush=True)

        # Stage 2 结束，关闭 JD 抓取用的 page 和 browser
        _safe_close(jd_page)
        browser.close()

    # =====================================================================
    # ===== Stage 3: 后处理 =====
    # =====================================================================

    # [Plan X] 将本次新发现的职位持久化到 seen_jobs.json
    # 只在有新增职位时才写文件（避免无意义的 I/O）
    if new_matched:
        save_seen_jobs(seen_data)
        print(f"\n  [Plan X] Saved {len(new_matched)} new jobs to seen_jobs.json", flush=True)

    # --- href 最终去重（安全保障）---
    # 虽然 Stage 1 已做 seen_hrefs 去重，但经过评分、Plan X 等流程后
    # all_jobs 仍可能因某些边界情况出现重复，这里再做一次最终保障
    seen_final = set()
    unique = []
    for j in all_jobs:
        lk = j.get("link", "").split("?")[0]
        if lk not in seen_final:
            seen_final.add(lk)
            unique.append(j)
    all_jobs = unique

    # =====================================================================
    # ===== 输出 JSON 文件 =====
    # 格式与 zurich_2026-04-28.json 保持一致，便于 merge_results.py 合并
    # =====================================================================

    # 确保输出目录存在（如果不存在则创建）
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)

    # 输出 raw 职位 JSON（所有 Stage 1 收集到的职位，含未通过评分的）
    # 注意：只有通过 quick_filter 的职位 description 字段才有 JD 文本
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

    # 输出 matched 职位 JSON（通过评分的推荐职位）
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

    # ===== 追加到 Excel（HK_AI_Jobs_All.xlsx）=====
    # append_scanner_to_excel 会：
    #   1. 读取 OUTPUT_FILE (JSON)
    #   2. 解析其中的 matched jobs
    #   3. 追加到 config/HK_AI_Jobs_All.xlsx（按 link 去重）
    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)

    print(f"\n=== Done ===")
    print(f"  [RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}", flush=True)

    return all_jobs


# =====================================================================
# ===== 主程序入口 =====
# =====================================================================
if __name__ == "__main__":
    # 当直接运行 `python scan_jobsdb.py` 时执行
    # cron 任务也是通过调用这个入口脚本来触发扫描
    print("MAIN BLOCK REACHED", flush=True)
    scan_jobsdb()
