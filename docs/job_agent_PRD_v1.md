# Job Agent System — Product Requirements Document (PRD)

> **Version:** 1.1  
> **Author:** CCO (AI Job Hunter Assistant)  
> **Generated:** 2026-04-19  
> **Last Updated:** 2026-04-20 23:30  
> **Status:** Active

---

## 1. Executive Summary

**Job Agent** 是一个基于 Playwright 的自动化招聘网站职位扫描系统，专门为 CCO（用户）设计，用于自动化抓取香港/中国区与 AI、Data、Product 相关的中高端职位。

**核心目标：**
- 覆盖 112 个招聘网站（61 个活跃扫描器）
- 累计抓取 **1400+ 个职位**（跨 133 个 JSON 文件）
- 通过关键词评分模型筛选出 P0（必投）/P1（推荐）职位
- 输出统一格式的 Excel 表格，便于 CCO 批量投递

**技术栈：**
- **浏览器自动化：** Playwright (v1.58.2) + CDP (Chrome DevTools Protocol)
- **评分引擎：** 自研 `cco_scorer.py`（两阶段过滤：quick_filter + score_job）
- **数据存储：** JSON（原始数据）+ Excel（合并去重结果）
- **跨会话去重：** `seen_jobs.json` + `merge_results.py --new-only`
- **调度：** Cron（定时任务）+ 手动执行

---

## 2. System Architecture

> 详细架构图见 `docs/data-flow.md`

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Job Agent System                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐ │
│  │   scan_strategies │    │  keywords-v2.json│    │ scanner_schedule │ │
│  │   (61 URLs)      │    │   (评分配置)     │    │   (扫描频率)    │ │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘ │
│           │                       │                       │            │
│           └───────────────────────┼───────────────────────┘            │
│                                   ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                     Scanner Execution Layer                       │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │  │
│  │  │  scan_kpmg │  │  scan_aia  │  │  scan_pwc  │  ...         │  │
│  │  │  (Mokahr)  │  │  (Workday) │  │  (SPA)    │               │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘               │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                   │                                    │
│                                   ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                     Scoring Engine (cco_scorer.py)             │  │
│  │                                                                  │  │
│  │   Stage 1: quick_filter()                                       │  │
│  │   ├── 排除 non_ai_jobs: ("assistant", "intern", "student")   │  │
│  │   ├── 排除 sales_jobs: ("sales", "account manager")            │  │
│  │   └── 排除 contract: ("contract", "临时", "短期")              │  │
│  │                                                                  │  │
│  │   Stage 2: score_job()                                          │  │
│  │   ├── high_match (100分): AI, ML, LLM, Data Scientist, etc.   │  │
│  │   ├── medium_match (80分): Data Analyst, Product Manager, etc.  │  │
│  │   └── low_match (60分): Business Analyst, Automation, etc.       │  │
│  │                                                                  │  │
│  │   输出: isRecommended + priority + score + reason               │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                   │                                    │
│                                   ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                        Output Layer                              │  │
│  │                                                                  │  │
│  │   raw/                          history/                         │  │
│  │   ├── kpmg_2026-04-20.json      ├── seen_jobs.json (Plan X)     │  │
│  │   ├── aia_2026-04-20.json       └── jd_store/                   │  │
│  │   └── ... (133 files)               └── aia/JR001.txt          │  │
│  │                                                                  │  │
│  │   HK_AI_Jobs_All.xlsx (合并去重后的推荐职位)                    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Specifications

### 3.1 Configuration Layer

#### 3.1.1 `scan_strategies.py`

**用途：** 统一管理 112 个招聘网站的 URL、选择器、扫描方法

**数据结构：**

```python
SCAN_STRATEGIES = {
    "kpmg": {
        "name": "KPMG",
        "method": "cdp_url",           # 扫描方法
        "url": "https://app.mokahr.com/...",
        "selectors": {
            "job_card": "li.job",
            "title": ".job-title"
        },
        "notes": "Mokahr SPA，URL参数翻页"
    },
    # ...
}
```

**扫描方法 (method)：**

| Method | Count | Description |
|--------|-------|-------------|
| `cdp_input` | 1 | CDP 输入框搜索（如 LinkedIn） |
| `cdp_url` | 50 | CDP + URL 参数翻页 |
| `playwright_dom` | 1 | Playwright DOM 解析（如 Deloitte） |
| `skip` | 12 | 反爬/需登录，跳过 |
| `urllist` | 1 | URL 列表直接请求 |

**当前覆盖：** 112 站点配置，68 个活跃扫描器

---

#### 3.1.2 `keywords-v2.json`

**用途：** 关键词评分配置

**数据结构：**

```json
{
  "high_match": [
    "AI", "Artificial Intelligence", "Machine Learning", "ML",
    "LLM", "Large Language Model", "NLP", "Generative AI",
    "Data Scientist", "AI Engineer", "ML Engineer",
    "AI Product Manager", "AI Evangelist"
  ],
  "medium_match": [
    "Data Analyst", "Data Engineer", "BI",
    "Product Manager", "Product Owner",
    "Business Analyst", "BA"
  ],
  "low_match": [
    "Automation", "RPA", "Process Analyst",
    "Digital Transformation", "Innovation"
  ],
  "exclude": {
    "non_ai_jobs": ["assistant", "intern", "student", "teacher", "tutor"],
    "sales_jobs": ["sales", "account manager", "BD"],
    "contract": ["contract", "临时", "短期", "part-time"]
  }
}
```

**评分规则：**

| Category | Score | Examples |
|----------|-------|----------|
| `high_match` | 100 | AI Engineer, ML Engineer, Data Scientist |
| `medium_match` | 80 | Data Analyst, Product Manager |
| `low_match` | 60 | Business Analyst, Automation |
| 低于 60 分 | 0 | 过滤掉 |

---

#### 3.1.3 `scanner_schedule.json`

**用途：** 扫描频率调度

```json
{
  "scan_frequency": {
    "Tier S": "24h",  // LinkedIn, Indeed, JobsDB
    "Tier A": "48h",  // JPMorgan, AIA, HSBC, Hays
    "Tier B": "48h",  // Citi, Manulife, Randstad
    "Tier C": "7d"    // 其他低优先级
  },
  "active_scanners": [
    "linkedin", "indeed", "jpmorgan", "aia", "hsbc", "hays"
  ]
}
```

---

### 3.2 Scanner Execution Layer

#### 3.2.1 Scanner Base Classes

**`job_scanner_base.py`：**
- 通用基类，提供 CDP 连接、分页、Excel 输出模板
- **Plan C 实现**：公共 JD 抓取函数 `get_jd_from_url(page, url, platform)`

**`scan_workday_base.py`：**
- Workday 平台专用基类
- 统一处理 Workday SPA 的 `button[aria-label*='next']` 翻页逻辑

#### 3.2.2 Individual Scanners

**代表性扫描器实现模式：**

```python
def scan_<company>():
    # 1. 从 scan_strategies.py 读取配置
    strategy = SCAN_STRATEGIES["<company>"]
    BASE_URL = strategy["url"]
    
    # 2. CDP 连接或 launch 独立浏览器
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    
    # 3. 关键词搜索（可选）
    page.fill("input[keyword]", "AI")
    page.click("button[search]")
    
    # 4. 分页抓取
    for page_num in range(1, MAX_PAGES + 1):
        jobs = page.query_selector_all(SELECTOR)
        for job in jobs:
            # 提取 title, link, location
            # href 去重 > title 去重
            
            # Plan C: 获取完整 JD（对通过 quick_filter 的职位）
            full_jd = get_jd_from_url(jd_page, link, platform='workday')
            job['description'] = full_jd
            
            scored = score_job(job)
            if scored["isRecommended"]:
                matched_jobs.append(scored)
        
        # 状态文字稳定检测
        if is_last_page():
            break
        next_button.click()
    
    # 5. 保存 JSON + Excel
    save_json(matched_jobs)
    write_to_excel(matched_jobs)
```

---

### 3.3 Scoring Engine (`cco_scorer.py`)

#### Stage 1: Quick Filter

```python
def quick_filter(job):
    title = job.get("title", "").lower()
    
    # 排除 non_ai_jobs
    for kw in NON_AI_JOBS:
        if kw in title:
            return {"passed": False, "reason": f"non_ai: {kw}"}
    
    # 排除 sales_jobs
    for kw in SALES_JOBS:
        if kw in title:
            return {"passed": False, "reason": f"sales: {kw}"}
    
    # 排除 contract
    for kw in CONTRACT_JOBS:
        if kw in title:
            return {"passed": False, "reason": f"contract: {kw}"}
    
    return {"passed": True}
```

#### Stage 2: Score Job

```python
def score_job(job):
    title = job.get("title", "").lower()
    jd_text = job.get("description", "")
    score = 0
    reason = ""
    
    # high_match (100分)
    for kw in HIGH_MATCH:
        if kw.lower() in title:
            score = 100
            reason = f"high: {kw}"
            break
    
    # medium_match (80分)
    if score == 0:
        for kw in MEDIUM_MATCH:
            if kw.lower() in title:
                score = 80
                reason = f"medium: {kw}"
                break
    
    # low_match (60分)
    if score == 0:
        for kw in LOW_MATCH:
            if kw.lower() in title:
                score = 60
                reason = f"low: {kw}"
                break
    
    return {
        "isRecommended": score >= 60,
        "priority": "P0" if score >= 90 else ("P1" if score >= 70 else "P2"),
        "score": score,
        "reason": reason,
        **job
    }
```

---

### 3.4 Data Pipeline

```
Raw JSON (scan_*.py)
       │
       ▼
┌──────────────────────────────────────────┐
│  merge_results.py --new-only (Plan X)    │
│  ├── 读取所有 raw/*.json                  │
│  ├── 加载 seen_jobs.json                  │
│  ├── 过滤 is_new_today=True               │
│  ├── 按 link 去重                         │
│  ├── 更新 seen_jobs.json                  │
│  └── 合并为 HK_AI_Jobs_All.xlsx         │
└──────────────────────────────────────────┘
       │
       ▼
   HK_AI_Jobs_All.xlsx
       │
       ├── 列: Company, Title, Location, Score, Priority, Match_Reason, Link, Description
       └── 用途: CCO 批量投递（只看新岗位）
```

---

## 4. Data Statistics

### 4.1 Scanner Coverage (截至 2026-04-20)

| Category | Count | Examples |
|----------|-------|----------|
| **配置站点总数** | 112 | scan_strategies.py |
| **活跃扫描器** | 68 | scan_*.py |
| **Code Frozen** | 31 | JPMorgan, UBS, AIA, HSBC, Deloitte, PwC, Manulife... |
| **Skip (反爬)** | 12 | JobsDB, Michael Page, Robert Walters |
| **Plan C/X 已实现** | 31 | 全部 Code Frozen 扫描器 |

### 4.2 Job Data Volume

| Metric | Value |
|--------|-------|
| JSON 文件总数 | 133 |
| 累计职位数 | ~1400 |
| 去重后职位数 | ~900 |
| 推荐职位 (P0+P1) | ~250+ |

### 4.3 Top Sources by Matched Jobs

| Source | Raw | Matched | Notes |
|--------|-----|--------|-------|
| AIA | 131 | 3 | P1×3 |
| Manulife | 100 | 7 | P0×4, P1×3 |
| SunLife | 52 | 3 | P0×2, P1×1 |
| UBS | 51 | 2 | P1×2 |
| Accenture | 12 | 4 | P0×2, P1×2 |
| PwC | 72 | 9 | P0×5, P1×4 |
| Deloitte | 78 | 9 | P0×5, P1×4 |

---

## 5. Key Implementation Patterns

### 5.1 Pagination Detection

**通用模式（UBS, Hays, etc.）：**

```python
# 1. 状态文字匹配
status_match = re.search(r'Showing\s+(\d+)\s*[-–]\s*(\d+)\s*of\s+(\d+)', body)

# 2. 稳定检测
if current_status == prev_status and page_new == 0:
    stable_count += 1
else:
    stable_count = 0
if stable_count >= 2:
    break  # 停止翻页
```

**Workday 专用模式：**

```python
# button[aria-label*='next'] 点击
next_btn = page.query_selector("button[aria-label*='next']")
if next_btn.get_attribute("disabled"):
    break
next_btn.click()
```

### 5.2 Deduplication

**优先级：href > title**

```python
# href 去重（优先）
link_stem = link.split("?")[0]  # 或保留完整 URL
if link_stem in seen_hrefs:
    continue
seen_hrefs[link_stem] = True

# title 去重（兜底）
title_key = title.lower()
if title_key in seen_titles:
    continue
seen_titles[title_key] = True
```

### 5.3 Browser Launch Patterns

**模式 A：CDP 连接（推荐，有登录态）**

```python
browser = p.chromium.connect_over_cdp("http://localhost:9222")
```

**模式 B：独立 launch（无登录态）**

```python
browser = p.chromium.launch(
    headless=True,
    args=[
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--user-agent=Mozilla/5.0..."
    ]
)
```

---

## 6. Known Issues & Solutions

| Issue | Root Cause | Solution | Status |
|-------|-------------|----------|--------|
| **Deloitte: 78 条重复 URL** | API title 字段为空 | 改用 Playwright DOM 解析 + 正则 `+`→`*` | ✅ 已修复 |
| **McKinsey: CDP 翻页失效** | 复用 tab 导致 SPA 状态冲突 | Launch 独立浏览器 | ✅ 已修复 |
| **PwC: locator.click() 无效** | Playwright 对 SPA 无效 | 改用 JS `.click()` | ✅ 已修复 |
| **Manulife: cp1252 编码崩溃** | Windows 默认编码 | UTF-8 TextIOWrapper | ✅ 已修复 |
| **AIA: BASE_URL=None** | 行被注释 | 取消注释 | ✅ 已修复 |
| **Plan C: JD 字段未使用** | 字段名不匹配 `full_jd` vs `description` | 统一为 `description` | ✅ 已实现 |
| **Plan X: 重复推送老岗位** | 无跨会话去重 | `seen_jobs.json` + `--new-only` | ✅ 已实现 |

---

## 7. Plan C: Hybrid JD Fetching Strategy (已实现)

> **实施日期：** 2026-04-20  
> **状态：** ✅ 已完成

### 7.1 问题背景

当前评分引擎存在两个问题：
1. **字段名不匹配**：部分扫描器将 JD 存到 `job['full_jd']`，但 `score_job()` 读取 `job.get('description', '')`
2. **大部分扫描器不抓 JD**：只传 title 给评分引擎，完全依赖标题关键词

### 7.2 解决方案

对通过 `quick_filter` 初筛的职位，访问 JD 详情页获取完整 JD 文本。

### 7.3 实现细节

**公共函数：** `job_scanner_base.get_jd_from_url()`

```python
def get_jd_from_url(jd_page, url, platform='workday'):
    """
    统一 JD 抓取函数，支持平台适配器 + fallback
    """
    adapters = {
        'workday': [
            "[data-automation-id='jobDescription']",
            "[class*='description']",
            "[class*='detail']"
        ],
        'linkedin': [
            '.jobs-description-content',
            "[class*='job-description']"
        ],
        'mokahr': [
            '.job-detail-content',
            "[class*='description']"
        ],
        'hays': [
            '.job-description',
            "[data-testid='job-description']"
        ],
        'default': ['body']
    }
    
    # 依次尝试选择器
    for sel in adapters.get(platform, adapters['default']):
        try:
            jd_page.goto(url, wait_until='domcontentloaded', timeout=25000)
            time.sleep(3)
            el = jd_page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    return text[:3000]
        except Exception:
            continue
    
    # fallback
    try:
        jd_page.goto(url, wait_until='domcontentloaded', timeout=25000)
        time.sleep(3)
        return jd_page.evaluate('document.body.innerText')[:3000]
    except Exception:
        return ''
```

### 7.4 已接入扫描器

| Scanner | 平台 | JD 获取方式 | 状态 |
|---------|------|------------|------|
| scan_manulife.py | Workday | `get_jd_from_url(jd_page, link, platform='workday')` | ✅ |
| scan_aia.py | Workday | 公共函数 + 字段名修正 `description` | ✅ |
| scan_sunlife.py | Workday | 公共函数 | ✅ |
| scan_prudential.py | Workday | 公共函数 | ✅ |
| scan_aig.py | Workday | 公共函数 | ✅ |

---

## 8. Plan X: Cross-Session Deduplication (已实现)

> **实施日期：** 2026-04-20  
> **状态：** ✅ 已完成

### 8.1 问题背景

部分招聘网站没有"岗位更新时间"字段，每天扫描时同一个岗位会重复出现。用户不知道哪些是新岗位、哪些是"老岗位还在挂着"。

### 8.2 解决方案

维护持久化的 `seen_jobs.json`，跨会话记录已处理过的岗位。

### 8.3 数据结构

```
candidates/
├── raw/                   # 扫描结果
├── history/
│   └── seen_jobs.json     # 跨会话去重索引
└── jd_store/              # JD 正文存储（预留）
```

**`seen_jobs.json` 结构：**

```json
{
  "last_updated": "2026-04-20T23:29:12",
  "jobs": {
    "https://aia.../Senior-AI-Architect_JR-61102": {
      "title": "AI Architect",
      "company": "AIA",
      "jd_file": "aia/Senior-AI-Architect_JR-61102.txt",
      "jd_chars": 3000,
      "first_seen": "2026-04-20",
      "last_seen": "2026-04-20",
      "is_new_today": true,
      "title_hash": "e936b30b..."
    }
  }
}
```

### 8.4 使用方式

```bash
# 只输出今天新增的岗位
python merge_results.py --new-only

# 输出所有岗位（仍会更新 seen_jobs.json）
python merge_results.py
```

### 8.5 变化检测

- **新岗位**：`link` 不在 seen_jobs.json 中
- **有更新**：`title_hash` 变化（同链接但标题改了）
- **无变化**：`link` + `title_hash` 都一致

---

## 9. Migration Checklist

See: `docs/migration_report_2026-04-19.md`

---

## 10. Future Enhancements

1. **评分模型升级**
   - 引入 LLM 自动读取 JD 提取关键技能
   - 基于公司历史投递反馈调整权重

2. **自动化调度**
   - 完善 Cron 定时任务（当前全部 OFF）
   - 微信/Telegram 推送新职位提醒

3. **数据可视化**
   - Dashboard 显示每日新增职位趋势
   - 公司投递进度追踪

4. **扩展覆盖**
   - 新增 20+ 待测试扫描器
   - 自动化测试框架验证扫描器稳定性

---

## 11. Scanner Implementation Patterns

### 11.1 Pattern Categories

根据实现方式，68个扫描器可分为以下几类：

| Pattern | Count | Examples | Key Technique |
|---------|-------|----------|---------------|
| **CDP + URL参数翻页** | 35 | HSBC, UBS, AIA, Manulife | URL中带 `?page=N` 或 `?q=AI` |
| **Workday SPA** | 12 | AIA, SunLife, Prudential, OCBC | `button[aria-label*='next']` 翻页 |
| **Mokahr SPA** | 5 | KPMG, EY, Accenture | Hash路由 `#/jobs?keyword=AI` |
| **CDP输入搜索** | 2 | LinkedIn, Hays | 填搜索框 + Enter |
| **Playwright DOM** | 1 | Deloitte | 正则解析HTML文本 |
| **Skip (反爬)** | 12 | JobsDB, Michael Page | - |

### 11.2 详细实现模式

> 详见原 PRD 第 10 节，此处不再重复

---

## 12. Appendix

### A. File Structure

```
job-agent/
├── SKILL.md                      # Job Hunter Pro Skill 定义
├── scanner_status.md             # 扫描器状态追踪表
├── merge_results.py              # 合并去重脚本（含 --new-only）
├── scanners/
│   ├── seen_jobs.py              # Plan X: 跨会话去重模块
│   ├── job_scanner_base.py       # Plan C: 公共 JD 抓取函数
│   ├── cco_scorer.py             # 评分引擎
│   └── scan_*.py                 # 68 个扫描器
├── config/
│   ├── scan_strategies.py        # 112 个站点 URL 配置
│   ├── keywords-v2.json          # 关键词评分配置
│   ├── scanner_schedule.json     # 扫描频率配置
│   └── HK_AI_Jobs_All.xlsx       # 合并去重结果
├── candidates/
│   ├── raw/                      # 原始 JSON (133 files)
│   ├── history/
│   │   └── seen_jobs.json        # Plan X 索引
│   └── jd_store/                 # JD 正文存储（预留）
├── docs/
│   ├── job_agent_PRD_v1.md       # 本文件
│   ├── data-flow.md              # 数据流文档
│   └── JD_PDFs/                  # JD PDF 归档
├── logs/
│   └── scan_log.md               # 扫描日志
└── reports/
    └── *.md                      # 修复报告
```

### B. Scoring Thresholds

| Priority | Score Range | Action |
|----------|-------------|--------|
| P0 | 90-100 | 必投 |
| P1 | 70-89 | 推荐投 |
| P2 | 60-69 | 可选 |
| - | <60 | 过滤 |

### C. Contact & Logs

- **腾讯文档:** docs.qq.com (AI Knowledge Base)
- **最近扫描:** 2026-04-20 (Manulife, AIA, AIG)
- **总 Token 消耗:** ~3500万

---

*End of Document*
