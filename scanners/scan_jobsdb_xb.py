#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JobsDB Scanner — xbrowser 重构版

【架构变化】
  - 旧版：Playwright CDP（connect_over_cdp），端口易冲突、进程易堆积
  - 新版：xb CLI（Node.js 子进程），每条命令独立 JSON 调用，无长连接问题

【Stage 设计（与旧版一致）】
  Stage 1: xb batch 翻页，收集所有职位卡片（href / title / company）
  Stage 2: 复用 cco_scorer / seen_jobs / job_scanner_base（不变）
  Stage 3: 输出 JSON + Excel（不变）

【依赖】
  - xb CLI（通过 subprocess 调用）
  - config.scan_strategies / cco_scorer / job_scanner_base / seen_jobs（复用现有模块）
"""

# =====================================================================
# 标准库
# =====================================================================
import sys
import os
import json
import time
import io
import subprocess
import re
import shlex
from datetime import datetime

# =====================================================================
# Windows UTF-8 编码修复
# =====================================================================
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# =====================================================================
# sys.path（与原版一致）
# =====================================================================
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

# =====================================================================
# 业务模块（复用）
# =====================================================================
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, check_job_status, update_job_entry, save_seen_jobs

print("SCRIPT LOADED - xbrowser version", flush=True)

# =====================================================================
# 配置区
# =====================================================================
KEYWORDS     = ["AI"]
MAX_PAGE     = 1  # 每小时运行只扫第1页（避免超时）
LOCATION     = "Hong Kong"
JOBS_DB_CFG  = SCAN_STRATEGIES["jobsdb"]
SEARCH_URL   = JOBS_DB_CFG["url"]

# xb CLI 路径
XB_NODE      = os.environ.get("QCLAW_CLI_NODE_BINARY", "node")
XB_CJS       = r"C:\Users\clawAdmin\.qclaw\skills\xbrowser\scripts\xb.cjs"

# 输出路径（与原版一致）
OUTPUT_FILE  = os.path.join(
    os.path.dirname(__file__), "..", "candidates", "raw",
    f"jobsdb_xb_{datetime.now().strftime('%Y-%m-%d')}.json"
)
RAW_FILE     = os.path.join(
    os.path.dirname(__file__), "..", "candidates", "raw",
    f"jobsdb_xb_raw_{datetime.now().strftime('%Y-%m-%d')}.json"
)


# =====================================================================
# xb CLI 封装
# =====================================================================

def xb_run(cmd, timeout=60):
    """
    执行 xb CLI 命令，返回解析后的 JSON dict。

    cmd: str 或 list[str]，如 "init" 或 ["run", "--browser", "default", "get", "html", "@e114"]
    timeout: int，秒
    """
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = list(cmd)
    full_cmd = [XB_NODE, XB_CJS] + cmd_list
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout
        )
        output = result.stdout.strip()
        if not output:
            return {"ok": False, "error": "empty output"}
        return json.loads(output)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout ({timeout}s)"}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON decode error: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def xb_batch(cmds, timeout=90):
    """
    执行 xb batch 命令（多条命令打包发送，首条失败则停止）。

    cmds: list[str]，如 ["snapshot -i", "click @e3", "wait --load networkidle"]
    timeout: int，秒

    注意：batch --bail 后面每个 cmd 作为一个参数传入，不加额外引号。
    """
    # 构建：xb run --browser default batch --bail "cmd1" "cmd2" "cmd3"
    args = ["run", "--browser", "default"]
    args.append("batch")
    args.append("--bail")
    for cmd in cmds:
        args.append(cmd)  # 不加引号，split() 会正确拆分
    return xb_run(args, timeout=timeout)


def extract_refs(r):
    """
    从 xb snapshot JSON 中提取 refs dict。

    支持两种格式：
      - batch 模式：r['data']['result'][0]['result']['refs']  ← search 列表页
      - run 模式：r['data']['result']['data']['refs']          ← JD 详情页

    r: xb run/batch 返回的 dict（ok=True 的情况）
    返回: dict {ref_id: {"name": ..., "role": ...}} 或 {}
    """
    try:
        data = r.get("data", {})
        result = data.get("result", {})
        # batch 模式：result 是 list [ {'result': {'refs': {...}}}, ... ]
        if isinstance(result, list):
            result = result[0] if result else {}
        # batch 列表页：refs 在 result['result']['refs']
        inner = result.get("result", {})
        refs = inner.get("refs")
        if refs:
            return refs
        # run 模式 / JD 详情页：refs 在 result['data']['refs']
        return result.get("data", {}).get("refs", {})
    except Exception:
        return {}


def find_ref_by_role(refs, role, name_contains=None):
    """
    在 refs dict 中查找指定 role 的元素。

    refs: dict，从 snapshot 提取的 refs
    role: str，如 "link", "button", "textbox"
    name_contains: str，可选，过滤 name 必须包含的字符串

    返回: ref_id (str) 或 None
    """
    for ref_id, info in refs.items():
        if info.get("role") == role:
            name = info.get("name", "")
            if name_contains is None or name_contains in name:
                return ref_id
    return None


# =====================================================================
# JobsDB 解析函数
# =====================================================================

def parse_job_cards(refs):
    """
    从 xb snapshot refs 中解析出所有 JobsDB 职位卡片。

    JobsDB 卡片在 xb snapshot 中的特征（已验证）：
      - role="heading" → 职位标题（如 "Application Project Managers (CRM...)"）
      - 每个职位一个 heading ref
      - heading 的 name 就是完整职位标题
      - 链接需要通过 get href @ref 获取

    排除规则：
      - e1: 页面总计数 heading（如 "2,705 ai jobs in Hong Kong SAR"）
      - 短标题（<10字符）：可能是其他 UI 元素

    返回: list[dict] [{"title": ..., "company": ..., "_ref_id": ...}]
    """
    jobs = []
    skip_ids = {"e1"}  # 页面级 heading（总数统计等）

    for ref_id, info in refs.items():
        name = info.get("name", "")
        role = info.get("role", "")

        # JobsDB 职位卡片 = heading 类型 + 标题足够长
        if role == "heading" and len(name) > 10 and ref_id not in skip_ids:
            jobs.append({
                "title": name.strip(),
                "company": "JobsDB",
                "link": "",
                "_ref_id": ref_id
            })

    return jobs


def get_heading_link(ref_id):
    """
    通过 xb get html @ref 获取 heading 内部的 <a href="/job/..."> 链接。

    JobsDB 的 heading (h2) 内部包含一个 <a> 标签，href 格式为：
      /job/92625409?type=standard&ref=search-standalone&origin=cardTitle#sol=...

    xb get html 返回路径：r['data']['result']['data']['html']

    返回: str（完整 URL）或 None
    """
    r = xb_run(["run", "--browser", "default", "get", "html", ref_id], timeout=15)
    if not r.get("ok"):
        return None
    # 路径：r['data']['result']['data']['html']
    html = r.get("data", {}).get("result", {}).get("data", {}).get("html", "")
    if not html:
        return None
    # 正则提取 href（JobsDB URL 格式：/job/ID?query#hash）
    # 用贪婪匹配到下一个双引号，避免 ?type= 之后的 &amp; 影响
    m = re.search(r'href="(/job/[^"]+)"', html)
    if m:
        raw = m.group(1)
        # HTML 实体还原：&amp; -> &
        raw = raw.replace("&amp;", "&")
        return f"https://hk.jobsdb.com{raw}"
    return None


# =====================================================================
# Stage 1: xb 翻页收集
# =====================================================================

def stage1_collect(xb_init_ok=True):
    """
    使用 xbrowser 翻页，收集所有 JobsDB 职位卡片。

    返回: list[dict]，每项含 title/company/link/keyword/source/description/scraped_at
    """
    print("\n=== Stage 1: xb pagination ===", flush=True)

    # Step 1: init（确保 xb 环境就绪）
    if not xb_init_ok:
        r = xb_run("init")
        if not r.get("ok"):
            print(f"  [ERR] xb init failed: {r.get('error')}", flush=True)
            return []
        print(f"  [INFO] xb init: browser={r['data']['env']['browser']}", flush=True)

    # Step 2: open JobsDB
    print(f"  [OPEN] {SEARCH_URL}", flush=True)
    r = xb_run(f'run --browser default open "{SEARCH_URL}"', timeout=90)
    if not r.get("ok"):
        print(f"  [ERR] open failed: {r.get('error')}", flush=True)
        return []
    print(f"  [OK] title={r['data']['result']['data'].get('title', 'N/A')}", flush=True)

    # Step 3: wait load
    r = xb_run("run --browser default wait --load networkidle", timeout=30)
    print(f"  [WAIT] networkidle: {r.get('ok')}", flush=True)

    # 收集结果
    all_jobs = []
    seen_links = set()
    page_num = 1

    while page_num <= MAX_PAGE:
        print(f"\n--- Page {page_num} ---", flush=True)

        # 获取当前页快照
        r = xb_batch(["snapshot -i"], timeout=30)
        if not r.get("ok"):
            print(f"  [ERR] snapshot failed: {r.get('error')}", flush=True)
            break

        # 解析结果
        refs = extract_refs(r)
        if not refs:
            # 调试：打印 batch result 结构
            batch_result = r.get('data', {}).get('result', {})
            if isinstance(batch_result, list):
                first = batch_result[0] if batch_result else {}
                warn_keys = list(first.get('result', {}).keys())
            else:
                warn_keys = list(batch_result.keys())
            print(f"  [WARN] No refs extracted, keys: {warn_keys}", flush=True)

        # 解析职位卡片
        raw_jobs = parse_job_cards(refs)
        print(f"  Cards found: {len(raw_jobs)}", flush=True)

        if not raw_jobs:
            # 可能到尾页了，或者需要滚动
            print("  No cards — checking for next button...", flush=True)
            next_ref = find_ref_by_role(refs, "link", "下一页")
            if not next_ref:
                next_ref = find_ref_by_role(refs, "link", "next")
            if not next_ref:
                next_ref = find_ref_by_role(refs, "button", "下一页")
            if not next_ref:
                print("  No next button — stopping.", flush=True)
                break

        # 提取链接和基本信息
        new_count = 0
        for job in raw_jobs:
            ref_id = job.get("_ref_id")

            # 通过 get html @ref 提取 heading 内部的 <a href="/job/...">
            link = get_heading_link(ref_id) if ref_id else ""
            link_key = link.split("?")[0] if link else ""

            # 去重
            if not link_key or link_key in seen_links:
                continue
            seen_links.add(link_key)

            # 获取标题（从 snapshot refs 的 name）
            title = job["title"]

            # 公司名（尝试从相邻 ref 获取，或在 Stage 2 JD 页面补充）
            company = "JobsDB"

            all_jobs.append({
                "title": title,
                "company": company,
                "location": LOCATION,
                "link": link,
                "keyword": "AI",
                "source": "JobsDB",
                "description": "",
                "scraped_at": datetime.now().isoformat()
            })
            new_count += 1

        print(f"  New jobs: {new_count} (total: {len(all_jobs)})", flush=True)

        # 判断是否继续翻页
        if new_count == 0:
            print("  Zero new jobs — assuming last page.", flush=True)
            break

        if page_num >= MAX_PAGE:
            print(f"  Reached MAX_PAGE ({MAX_PAGE}).", flush=True)
            break

        # 翻页：找下一页按钮
        next_ref = None
        for ref_id, info in refs.items():
            name = info.get("name", "")
            role = info.get("role", "")
            # 匹配 JobsDB 下一页的各种可能名称
            if role in ("link", "button") and ("下一页" in name or "next" in name.lower() or ">" in name):
                next_ref = ref_id
                break

        if not next_ref:
            print("  No next page button found — stopping.", flush=True)
            break

        # 点击下一页
        print(f"  [CLICK] next page button @{next_ref}", flush=True)
        r = xb_batch([f"click @{next_ref}", "wait --load networkidle"], timeout=30)
        if not r.get("ok"):
            print(f"  [ERR] click next failed: {r.get('error')}", flush=True)
            break

        page_num += 1
        time.sleep(2)  # 礼貌性延时

    print(f"\n  Stage 1 done: {len(all_jobs)} raw jobs collected", flush=True)
    return all_jobs


# =====================================================================
# Stage 2: JD 抓取 + 评分 + 去重
# =====================================================================

def stage2_process(raw_jobs):
    """
    对 raw_jobs 逐个：JD 抓取（通过 xb） + 评分 + 去重。

    注意：这里不用 Playwright，而是通过 xb snapshot 获取 JD 文本。
    JobsDB JD 页面选择器（Plan C）：
      - window.__NEXT_DATA__ 或 window.__INITIAL_PROPS__（JSON 内嵌数据）
      - [data-automation="jobDetailDescription"] > div
      - .job-details .content
    """
    print(f"\n=== Stage 2: Processing {len(raw_jobs)} jobs ===", flush=True)

    if not raw_jobs:
        return [], []

    scorer = CCOSCORER()
    seen_data = load_seen_jobs()
    all_jobs = []
    new_matched = []

    for i, job in enumerate(raw_jobs):
        title = job.get("title", "")
        link = job.get("link", "")
        link_key = link.split("?")[0]

        if i % 5 == 0:
            print(f"  Progress: {i}/{len(raw_jobs)}", flush=True)

        try:
            # Step 1: quick_filter
            fr = scorer.quick_filter(job)
            if not fr["passed"]:
                print(f"  [FILTER] {title[:40]} - {fr['reason']}", flush=True)
                continue
            print(f"  [PASS] {title[:40]}", flush=True)

            # Step 2: 抓 JD（通过 xb snapshot）
            jd_text = get_jd_via_xb(link)
            job["description"] = jd_text
            if jd_text:
                print(f"    [JD] {len(jd_text)} chars", flush=True)
            else:
                print(f"    [JD] empty/failed", flush=True)

            # Step 2.5: seen_jobs 更新
            status = None
            if jd_text and len(jd_text) > 50:
                status = check_job_status(link_key, title, seen_data)
                update_job_entry(link_key, title, "JobsDB", jd_text, seen_data, status)

            # Step 3: 评分
            scored = score_job(job)
            if scored.get("isRecommended"):
                if status is None:
                    status = check_job_status(link_key, title, seen_data)
                all_jobs.append(scored)
                if status == "new":
                    new_matched.append(scored)
                print(f"  [MATCH] {title[:55]} (P{scored.get('priority')}, {scored.get('score')}) [{status}]", flush=True)
            else:
                print(f"  [SKIP] {title[:55]} (score: {scored.get('score', 'N/A')})", flush=True)

        except Exception as e:
            print(f"  [ERR] {title[:40]}: {e}", flush=True)

        # 每5个保存一次，避免 OOM 丢失
        if (i + 1) % 5 == 0:
            save_seen_jobs(seen_data)

    save_seen_jobs(seen_data)
    if new_matched:
        print(f"  [Plan X] Saved {len(new_matched)} new jobs", flush=True)

    print(f"  Stage 2 done: {len(all_jobs)} matched", flush=True)
    return all_jobs, raw_jobs


def get_jd_via_xb(jd_url):
    """
    在当前浏览器标签内 navigate 到 JD 页面，抓取后 back 回搜索页。
    全程同一标签，避免标签堆积导致 OOM。
    """
    if not jd_url:
        return ""

    # navigate 到 JD 页面（复用当前标签，不新建）
    r = xb_run(["run", "--browser", "default", "open", jd_url], timeout=30)
    if not r.get("ok"):
        return ""

    # 等待页面加载
    xb_run(["run", "--browser", "default", "wait", "--load", "networkidle"], timeout=20)

    text = ""

    # 策略1：get html 通过 CSS 选择器获取 JD 内容
    for sel in [
        "[data-automation='jobAdDetails']",
        "main",
        "[class*='description']"
    ]:
        r = xb_run(["run", "--browser", "default", "get", "html", sel], timeout=15)
        if not r.get("ok"):
            continue
        result_data = r.get("data", {}).get("result", {})
        if isinstance(result_data, list):
            result_data = result_data[0] if result_data else {}
        html = ""
        if isinstance(result_data, dict):
            html = result_data.get("data", {}).get("html", "")
        if html and len(html) > 100:
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            break

    if not text:
        # 策略2：snapshot refs 拼凑（无结构化 HTML 时的兜底）
        r = xb_batch(["snapshot -i"], timeout=30)
        if r.get("ok"):
            results = r.get("data", {}).get("result", [])
            if results:
                snap_data = results[0]
                refs = snap_data.get("result", {}).get("refs", {})
                jd_parts = []
                for ref_id, info in refs.items():
                    name = info.get("name", "")
                    role = info.get("role", "")
                    if role in ("link", "button", "heading") or len(name) < 50:
                        continue
                    jd_parts.append(name)
                text = " ".join(jd_parts)

    # back 回搜索页（保持当前标签，不新建）
    xb_run(["run", "--browser", "default", "press", "back"], timeout=15)
    xb_run(["run", "--browser", "default", "wait", "--load", "networkidle"], timeout=20)

    return text


# =====================================================================
# Stage 3: 输出
# =====================================================================

def stage3_output(all_jobs, raw_jobs):
    """输出 JSON + Excel（与原版一致）"""
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

    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)

    print(f"\n=== Done ===", flush=True)
    print(f"  [RAW] {len(raw_jobs)} | [MATCHED] {len(all_jobs)}", flush=True)
    return all_jobs


# =====================================================================
# 主程序
# =====================================================================

def scan_jobsdb_xb():
    """JobsDB xbrowser 重构版主入口"""
    print("MAIN BLOCK REACHED - xbrowser version", flush=True)

    # xb init
    r = xb_run("init")
    if not r.get("ok"):
        print(f"[ERR] xb init: {r.get('error')}", flush=True)
        return []
    print(f"[INFO] xb ready: {r['data']['env']}", flush=True)

    # Stage 1
    raw_jobs = stage1_collect(xb_init_ok=True)
    if not raw_jobs:
        print("[WARN] Stage 1: no jobs collected", flush=True)
        return []

    # Stage 2
    all_jobs, raw_jobs = stage2_process(raw_jobs)

    # Stage 3
    return stage3_output(all_jobs, raw_jobs)


if __name__ == "__main__":
    scan_jobsdb_xb()
