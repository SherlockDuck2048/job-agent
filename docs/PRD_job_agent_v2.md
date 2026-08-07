# Job Agent 系统产品需求文档（PRD）

> **版本：** 2.0  
> **作者：** CCO AI Job Hunter  
> **日期：** 2026-04-23  
> **状态：** Active  

---

## 1. 产品概述

### 1.1 产品定位

**Job Agent** 是一个面向个人求职者的自动化岗位扫描与智能匹配系统，专为香港地区 AI/Data/Product 相关中高端岗位设计。系统通过自动化抓取 60+ 招聘平台，结合自定义评分算法，筛选出高匹配度岗位并输出结构化报告。

### 1.2 核心价值

| 痛点 | 解决方案 | 价值 |
|------|----------|------|
| 招聘网站分散，需逐个手动搜索 | 统一扫描 60+ 平台 | 时间节省 90%+ |
| 岗位信息量大，难以筛选 | 两阶段评分算法 | 精准匹配目标岗位 |
| 重复岗位多，无法识别新增 | 跨会话去重（Plan X） | 只看今日新增 |
| JD 要点分散，难以快速判断 | JD 智能抓取 + 摘要 | 一眼看清岗位核心 |

### 1.3 目标用户

**主要用户：** CCO（产品背景，5-8 年经验，定位 BA/PM/AI Consultant）

**用户画像：**
- 寻找香港地区 AI 相关的 Business/PM/Strategy 岗位
- 不做纯技术岗位（ML Engineer、Data Scientist）
- 关注金融科技、保险、咨询行业
- 中级岗位，排除 Entry/Junior/Senior VP

### 1.4 范围与边界

**In Scope：**
- 自动化扫描招聘网站（60+ 平台）
- 基于关键词的匹配评分
- 生成 Excel 日报
- 跨会话去重

**Out of Scope：**
- 自动投递简历
- 面试安排
- 薪资估算
- 公司背景调查

---

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Job Agent System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  配置层                                                           │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐ │
│  │ scan_strategies  │ │ keywords-v2.json │ │ scanner_schedule│ │
│  │ (112 URLs)       │ │ (评分配置)        │ │ (扫描频率)      │ │
│  └────────┬─────────┘ └────────┬─────────┘ └────────┬────────┘ │
│           └────────────────────┼────────────────────┘          │
│                                ▼                                 │
│  扫描层                                                          │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  68 个扫描器 (scan_*.py)                                    ││
│  │  ├── Workday 平台 (12): AIA, Manulife, SunLife...         ││
│  │  ├── Mokahr 平台 (5): KPMG, EY, Accenture...              ││
│  │  ├── 传统 HTTP (20): Indeed, Hays, Randstad...            ││
│  │  └── 需登录 CDP (3): LinkedIn...                           ││
│  └────────────────────────────────────────────────────────────┘│
│                                │                                 │
│                                ▼                                 │
│  评分层                                                          │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  cco_scorer.py (两阶段评分)                                 ││
│  │  Stage 1: quick_filter (初筛)                              ││
│  │  Stage 2: calculate_score (详评)                           ││
│  └────────────────────────────────────────────────────────────┘│
│                                │                                 │
│                                ▼                                 │
│  数据层                                                          │
│  ┌────────────────┐ ┌─────────────────┐ ┌─────────────────────┐│
│  │ candidates/raw │ │ history/        │ │ HK_AI_Jobs_All.xlsx ││
│  │ (原始JSON)     │ │ seen_jobs.json  │ │ (合并去重结果)      ││
│  └────────────────┘ └─────────────────┘ └─────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 浏览器自动化 | Playwright 1.58 + CDP | SPA/动态页面抓取 |
| HTTP 抓取 | requests + BeautifulSoup | 静态页面抓取 |
| 评分引擎 | Python (自研) | 两阶段关键词匹配 |
| 数据存储 | JSON + Excel | 原始数据 + 报告输出 |
| 任务调度 | Cron / 手动执行 | 定时扫描 |

### 2.3 扫描策略分类

| Method | 描述 | 数量 | 代表平台 |
|--------|------|------|----------|
| `cdp_url` | Playwright URL 参数翻页 | 35 | HSBC, AIA, Manulife |
| `cdp_input` | Playwright 搜索框输入 | 3 | LinkedIn, Hays |
| `playwright_dom` | Playwright DOM 解析 | 2 | Deloitte, PwC |
| `http` | requests 静态抓取 | 18 | Indeed, Randstad |
| `skip` | 反爬/无页面 | 12 | JobsDB, Michael Page |
| `urllist` | URL 列表直接请求 | 2 | CCB, CICC |

---

## 3. 核心功能

### 3.1 多源岗位扫描

#### 3.1.1 覆盖范围

| 类别 | 数量 | 代表公司 |
|------|------|----------|
| 综合招聘平台 | 5 | LinkedIn, Indeed, Hays, Randstad |
| 猎头网站 | 7 | Michael Page, Adecco, Persol |
| 银行/金融 | 8 | HSBC, Citi, JPMorgan, UBS, BOCHK |
| 保险公司 | 6 | AIA, Manulife, Prudential, AIG, SunLife |
| 四大咨询 | 4 | Deloitte, PwC, KPMG, EY |
| 科技公司 | 4 | IBM, Microsoft, PCCW, HKT |
| 香港机构 | 11 | Airport Authority Hong Kong, HKEX, HKJC, CLP |

#### 3.1.2 扫描器实现模式

**模式 A：Workday 平台**

```python
# 特点：URL 包含 locationCountry 过滤参数
# 分页：button[aria-label*='next'] 循环点击
# 去重：href 主干去重

def scan_workday(platform, base_url):
    # 1. CDP 连接
    browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
    
    # 2. 打开搜索页
    page.goto(base_url + "?q=AI&locationCountry=hk")
    
    # 3. 翻页抓取
    while True:
        jobs = page.query_selector_all("a[href*='/job/']")
        for job in jobs:
            title = job.inner_text()
            link = job.get_attribute('href')
            # href 去重
            if link_stem not in seen:
                all_jobs.append({'title': title, 'link': link})
        
        # 下一页
        next_btn = page.query_selector("button[aria-label*='next']")
        if next_btn.get_attribute('disabled'):
            break
        next_btn.click()
```

**模式 B：Mokahr 平台**

```python
# 特点：Hash 路由 #/jobs?keyword=AI
# 分页：page=N URL 参数
# 去重：title 去重（同一岗位 JR号不同但 title 相同）

def scan_mokahr(platform, base_url):
    for page_num in range(1, MAX_PAGES + 1):
        url = f"{base_url}#/jobs?keyword=AI&page={page_num}"
        page.goto(url)
        
        jobs = page.query_selector_all("li.job")
        for job in jobs:
            title = job.query_selector(".job-title").inner_text()
            # title 去重
            if title not in seen_titles:
                all_jobs.append({'title': title, ...})
```

---

### 3.2 智能匹配评分

#### 3.2.1 评分架构

**两阶段评分流程：**

```
岗位输入
    │
    ▼
┌─────────────────────────────────────┐
│ Stage 1: quick_filter (初筛)        │
│ 检查 title 是否包含核心领域关键词      │
│ 排除 intern/junior/entry 等岗位      │
│ → 不通过：直接返回 P3 (score=0)      │
│ → 通过：进入 Stage 2                │
└─────────────────────────────────────┘
    │
    ▼ (需要 description)
┌─────────────────────────────────────┐
│ Stage 2: calculate_score (详评)     │
│                                     │
│ 评分维度（6个因子）：                 │
│ 1. 岗位类型基础分 (100/85/60)       │
│ 2. Title 年资惩罚 (-20/-10/-5/0)   │
│ 3. 技术强度惩罚 (-35/-20/-10/0)     │
│ 4. 排除项惩罚 (-45/-35/0)           │
│ 5. 经验要求惩罚 (-15/-10/0)          │
│ 6. 加分项 (+10/+5/+3/+5)            │
│                                     │
│ 最终分数 = Σ(各因子)                │
│ 限制在 50-100 范围                   │
└─────────────────────────────────────┘
    │
    ▼
输出: {score, priority, comment, details}
```

#### 3.2.2 评分规则详解

**因子 1：岗位类型基础分**

| 匹配度 | 岗位示例 | 基础分 | 优先级 |
|--------|----------|--------|--------|
| 高匹配 | AI Business Analyst, Project Manager, Product Manager, AI Evangelist, GenAI Solution Consultant | 100 | P0 |
| 中匹配 | Solution Consultant, AI Lead, Data Lead, Analytics Lead, Innovation Manager | 85 | P1 |
| 低匹配 | AI Engineer, Data Scientist, ML Engineer | 60 | P2 |

**因子 2：Title 年资惩罚**

| Title 级别 | 关键词 | 惩罚分 | 原因 |
|-----------|--------|--------|------|
| 极高 | SVP, Managing Director, Executive Director | -20 | 要求10年+高层管理经验 |
| 高 | VP, AVP, Director | -10 | 要求8-10年中高层管理经验 |
| 中高 | Senior Manager, Principal, Head of | -5 | 要求高级经验 |
| 标准 | Manager, Lead, Specialist | 0 | 符合目标级别 |

**因子 3：技术强度惩罚**

| 强度 | 关键词示例 | 惩罚分 | 原因 |
|------|-----------|--------|------|
| 高 | "strong proficiency in python", "hands-on coding", "tensorflow", "pytorch" | -35 | 需要 hands-on 开发/建模 |
| 中 | "python proficiency", "mlops", "technical design" | -20 | 需要编程/技术能力 |
| 低 | "python", "sql", "technical background" | -10 | 涉及技术背景 |

**因子 4：排除项惩罚**

| 排除类别 | 关键词 | 惩罚分 | 原因 |
|---------|--------|--------|------|
| 非AI岗位 | "traditional role", "no ai element" | -45 | 与AI无关 |
| 销售岗位 | "sales role", "business development", "account growth" | -35 | 销售性质岗位 |

**因子 5：经验要求惩罚**

| 年限要求 | 惩罚分 | 原因 |
|---------|--------|------|
| 10年+ | -15 | 要求10年以上经验 |
| 8年+ | -10 | 要求8年以上经验 |
| <8年 | 0 | 经验要求合适 |

**因子 6：加分项**

| 加分类别 | 关键词 | 加分 | 原因 |
|---------|--------|------|------|
| GenAI | genai, llm, rag, agent, prompt engineering | +10 | GenAI/LLM相关 |
| 金融科技 | fintech, banking, insurance, wealth management | +5 | 金融科技行业 |
| 香港 | hong kong, hk, 香港 | +3 | 香港本地 |
| 能力匹配 | business analysis, process optimization, digital transformation | +5 | 符合核心能力 |

#### 3.2.3 优先级阈值

| Priority | Score Range | 行动建议 |
|----------|-------------|----------|
| P0 | 90-100 | 强烈推荐，必投 |
| P1 | 75-89 | 值得关注，推荐投递 |
| P2 | 60-74 | 一般合适，可选投递 |
| P3 | <60 | 不推荐 |

---

### 3.3 跨会话去重（Plan X）

#### 3.3.1 问题背景

部分招聘网站没有"岗位更新时间"字段，每天扫描时同一岗位会重复出现。用户无法区分哪些是新岗位、哪些是"老岗位还在挂着"。

#### 3.3.2 解决方案

维护持久化的 `seen_jobs.json`，跨会话记录已处理过的岗位。

**数据结构：**

```json
{
  "last_updated": "2026-04-23T22:30:00",
  "jobs": {
    "https://aia.wd3.../Senior-AI-Architect_JR-61102": {
      "title": "AI Architect",
      "company": "AIA",
      "jd_file": "aia/JR-61102.txt",
      "first_seen": "2026-04-20",
      "last_seen": "2026-04-23",
      "is_new_today": false,
      "title_hash": "e936b30b..."
    }
  }
}
```

#### 3.3.3 使用方式

```bash
# 只输出今天新增的岗位
python merge_results.py --new-only

# 输出所有岗位（仍会更新 seen_jobs.json）
python merge_results.py
```

---

### 3.4 JD 智能抓取（Plan C）

#### 3.4.1 问题背景

评分引擎需要 JD 正文判断技术强度、排除项等，但部分扫描器只抓取 title + link，未获取详细 JD。

#### 3.4.2 解决方案

对通过 `quick_filter` 初筛的岗位，访问详情页获取完整 JD 文本（最多 3000 字符）。

**平台适配器：**

```python
JD_SELECTORS = {
    'workday': [
        "[data-automation-id='jobPostingDescription']",
        "[class*='job-posting-description']",
        ...
    ],
    'linkedin': ['.jobs-description-content', ...],
    'mokahr': ['.job-detail-content', ...],
    'default': ['body']
}
```

#### 3.4.3 清洗逻辑

- 移除导航栏、按钮文本
- 压缩多余空白
- 截取前 3000 字符

---

## 4. 数据流程

### 4.1 数据流图

```
                    扫描执行
                        │
                        ▼
         ┌──────────────────────────┐
         │  scan_xxx.py             │
         │  ├── 抓取岗位列表          │
         │  ├── href/title 去重      │
         │  ├── quick_filter 初筛   │
         │  ├── get_jd_from_url      │
         │  └── score_job 评分       │
         └──────────────────────────┘
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
     ┌────────────┐ ┌────────────┐ ┌─────────────┐
     │ raw/*.json │ │ matched/   │ │ Excel追加   │
     │ (全量)     │ │ (推荐)      │ │ (实时更新)  │
     └────────────┘ └────────────┘ └─────────────┘
            │
            ▼
     ┌────────────────────────────────────┐
     │  merge_results.py                  │
     │  ├── 扫描 raw/ 目录                 │
     │  ├── 加载 seen_jobs.json           │
     │  ├── 过滤 is_new_today=True        │
     │  ├── 按 link 去重                  │
     │  ├── 更新 seen_jobs.json           │
     │  └── 合并为 HK_AI_Jobs_All.xlsx    │
     └────────────────────────────────────┘
                        │
                        ▼
               最终输出 Excel
```

### 4.2 数据存储结构

```
job-agent/
├── SKILL.md                      # Job Hunter Pro Skill 定义
├── scanner_status.md             # 扫描器状态追踪表
├── merge_results.py              # 合并去重脚本（含 --new-only）
├── scanners/
│   ├── seen_jobs.py              # Plan X: 跨会话JD去重模块
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
│   │   └── seen_jobs.json        # Plan X 跨会话索引
│   └── jd_store/                 # JD 正文存储（预留）
├── docs/
│   ├── job_agent_PRD_v2.md       # 本文件
│   ├── data-flow.md              # 数据流文档
│   └── JD_PDFs/                  # JD PDF 归档
├── logs/
│   └── scan_log.md               # 扫描日志
└── reports/
    └── *.md                      # 修复报告
```

### 4.3 Excel 输出格式

| 列名 | 说明 | 示例 |
|------|------|------|
| 编号 | 唯一ID | 1, 2, 3... |
| 来源平台 | 扫描来源 | AIA, HSBC, LinkedIn |
| 公司 | 公司名称 | AIA Group, HSBC |
| 职位 | 岗位标题 | AI Business Analyst |
| 链接 | JD 详情页 URL | https://... |
| 地点 | 工作地点 | Hong Kong |
| 优先级 | P0/P1/P2 | P0 |
| 评分 | 匹配分数 | 95 |
| 匹配原因 | 评分说明 | 高匹配岗位 + GenAI加分 |
| 发布日期 | 岗位发布时间 | 2026-04-20 |
| 抓取时间 | 扫描时间 | 2026-04-23 22:30 |
| JD Summary | JD 摘要（200字） | Translate business requirements... |
| 完整JD文件路径 | JD 文本存储路径 | jd_store/aia/JR-61102.txt |

---

## 5. 运行指南

### 5.1 环境要求

```bash
# Python 版本
Python 3.10+

# 依赖安装
pip install playwright requests beautifulsoup4 openpyxl

# Playwright 浏览器
playwright install chromium

# Chrome CDP（用于需登录的网站）
chrome.exe --remote-debugging-port=9222
```

### 5.2 运行命令

```bash
# 1. 单个扫描器
python scanners/scan_aia.py --no-dry-run

# 2. 批量扫描（调度器）
python scanners/run_dispatcher.py

# 仅运行 HTTP 类型（快速）
python run_dispatcher.py --http-only

# 运行指定扫描器
python run_dispatcher.py -s aia -s hsbc -s manulife

# 3. 合并结果
python merge_results.py

# 只看今天新增
python merge_results.py --new-only

# 4. 查看 Excel
explorer config\HK_AI_Jobs_All.xlsx
```

### 5.3 定时任务示例

```bash
# 每天早上 8 点运行
crontab -e
0 8 * * * cd /path/to/job-agent && python scanners/run_dispatcher.py
```

---

## 6. 配置管理

### 6.1 新增扫描网站

**步骤 1：在 `scan_strategies.py` 添加配置**

```python
SCAN_STRATEGIES["newcompany"] = {
    "name": "New Company",
    "method": "cdp_url",  # 或 http/cdp_input
    "url": "https://careers.newcompany.com/jobs?q=AI",
    "selectors": {
        "job_card": ".job-item",
        "title": ".job-title",
        "company": ".company-name"
    },
    "notes": "平台特点说明"
}
```

**步骤 2：实现扫描器脚本**

继承 `job_scanner_base.py`：

```python
from job_scanner_base import *

def scan_newcompany():
    strategy = SCAN_STRATEGIES["newcompany"]
    p, browser, context = connect_browser()
    page = new_page(context)
    
    # 实现抓取逻辑
    ...
    
    # 评分
    for job in all_jobs:
        scored = score_job(job)
        if scored['isRecommended']:
            matched.append(scored)
    
    # 保存
    save_results("newcompany", matched, "success")
    browser.close()
    p.stop()
```

### 6.2 修改评分规则

编辑 `config/keywords-v2.json`，修改后即时生效，无需重启。

---

## 7. 已知问题与解决方案

| 问题 | 根因 | 解决方案 | 状态 |
|------|------|----------|------|
| Deloitte: 78 条重复 URL | API title 字段为空 | Playwright DOM 解析 + 正则修复 | ✅ 已修复 |
| McKinsey: CDP 翻页失效 | 复用 tab 导致 SPA 状态冲突 | Launch 独立浏览器 | ✅ 已修复 |
| PwC: locator.click() 无效 | Playwright 对 SPA 无效 | 改用 JS `.click()` | ✅ 已修复 |
| Manulife: cp1252 编码崩溃 | Windows 默认编码 | UTF-8 TextIOWrapper | ✅ 已修复 |
| AIA: BASE_URL=None | 行被注释 | 取消注释 | ✅ 已修复 |
| Plan C: JD 字段未使用 | 字段名不匹配 | 统一为 `description` | ✅ 已实现 |
| Plan X: 重复推送老岗位 | 无跨会话去重 | `seen_jobs.json` + `--new-only` | ✅ 已实现 |

---

## 8. 未来规划

### 8.1 短期优化（Q2 2026）

- [ ] 完善定时任务调度（当前全部手动执行）
- [ ] 新增 20+ 待测试扫描器
- [ ] 微信/Telegram 推送新职位提醒

### 8.2 中期扩展（Q3 2026）

- [ ] 引入 LLM 自动读取 JD 提取关键技能
- [ ] 基于历史投递反馈调整评分权重
- [ ] Dashboard 可视化每日新增趋势

### 8.3 长期愿景

- [ ] 自动投递简历
- [ ] 面试安排集成
- [ ] 多用户支持

---

## 9. 附录

### 9.1 扫描器状态统计（截至 2026-04-23）

| 状态 | 数量 | 说明 |
|------|------|------|
| ✅ Code Frozen | 31 | 已验证通过 |
| 🔧 Active | 15 | 正在调试 |
| ⚠️ Re-validate | 10 | URL 更新后需重测 |
| ❓ Unknown | 12 | 尚未测试 |
| ⏭️ Skip | 12 | 反爬/无页面 |

### 9.2 数据统计

| 指标 | 数值 |
|------|------|
| JSON 文件总数 | 133+ |
| 累计职位数 | ~1400 |
| 去重后职位数 | ~900 |
| 推荐职位 (P0+P1) | ~250 |

### 9.3 联系方式

- **GitHub:** github.com/cco/job-agent
- **文档:** docs.qq.com (AI Knowledge Base)

---

*End of Document*
