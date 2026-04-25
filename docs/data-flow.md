# Job Agent 数据流文档

> 生成时间: 2026-04-20
> 维护者: QClaw / CCO 第二大脑

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Job Agent 全自动招聘扫描系统                        │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────────┐
  │ scan_strategies  │────▶│  60+ 扫描器脚本  │────▶│  cco_scorer 评分引擎  │
  │   (URL配置中心)   │     │  (scan_xxx.py)  │     │  (keywords-v2.json) │
  └──────────────────┘     └────────┬────────┘     └──────────┬───────────┘
                                    │                          │
                                    ▼                          ▼
                           ┌────────────────┐        ┌─────────────────┐
                           │ candidates/raw │        │ HK_AI_Jobs_All  │
                           │  (JSON 双出口)  │        │     .xlsx       │
                           │  _raw + _matched│        │   (合并总表)     │
                           └────────────────┘        └─────────────────┘
```

---

## 2. 配置层: scan_strategies.py

**文件**: `config/scan_strategies.py`

**作用**: 61个招聘平台的 URL + 爬取策略统一配置

```python
SCAN_STRATEGIES = {
    "aia": {
        "name": "AIA",
        "method": "cdp_url",           # 爬取方式
        "url": "https://aia.wd3.myworkdayjobs.com/...",
        "selectors": {"job_card": "...", "title": "..."},
        "workday_config": {"locationCountry": "..."}  # 仅HK的Workday过滤参数
    },
    "ubs": { ... },
    ...
}
```

**method 类型**:

| method | 说明 | 数量 |
|--------|------|------|
| `cdp_url` | Playwright 打开 URL | ~40 |
| `cdp_input` | Playwright 搜索框输入 | ~5 (LinkedIn等) |
| `skip` | 跳过（反爬/无公开页） | ~10 |

---

## 3. 扫描器层: scan_xxx.py（以 AIA 为例）

**文件**: `scanners/scan_aia.py`

每个扫描器遵循 **两阶段流程**:

```
Stage 1: 收集链接 ─────────────────────────────────────────────
  ┌─────────────────────────────────────────────────────────┐
  │  Playwright/CDP 连接到 Chrome (端口 9222)                │
  │  打开目标 URL                                             │
  │  翻页到底（Workday "Next" 按钮 × N 页）                   │
  │  用 CSS Selector 提取: title + href + 摘要                │
  │  href 去重（URL主干去重，防止同标题不同JR号重复）            │
  │  输出: all_entries[]  (raw job list)                      │
  └─────────────────────────────────────────────────────────┘
                          │
                          ▼
Stage 2: JD获取 + 评分 ───────────────────────────────────────
  ┌─────────────────────────────────────────────────────────┐
  │  遍历 all_entries[]                                      │
  │  逐个打开 job detail 页面，获取完整 JD（3000字符）          │
  │  调用 cco_scorer.score_job(title, jd_text, snippet)     │
  │  按 P0/P1/P2/P3 分级，阈值: P0≥80, P1≥70, P2≥60          │
  │  过滤 exclude 关键词（intern, airline, freight等）          │
  └─────────────────────────────────────────────────────────┘
                          │
                          ▼
  ┌────────────────┐  ┌────────────────────┐
  │ candidates/raw │  │ HK_AI_Jobs_All.xlsx │
  │  _raw.json     │  │  (每次扫描追加写入)   │
  │  _matched.json │  └────────────────────┘
  └────────────────┘
```

### 平台分类详解

```
Workday 平台 (AIA, Manulife, SunLife, HSBC, OCBC, CNCB, HKEX...)
  └─ 特点: URL 包含 locationCountry 过滤参数 → 只拿 HK 职位
  └─ 分页: "Next" 按钮循环点击，翻到底停止
  └─ 标题: 从 URL slug 或页面元素提取
  └─ 坑: BASE_URL 被注释 → NameError；locationCountry 硬编码错误

SPA 平台 (Deloitte赛码, PwC, KPMG Mokahr...)
  └─ 特点: JS 动态渲染，role="grid" 等属性交互后消失
  └─ 分页: Playwright locator.click() 在 headless 下失效
  └─ 解法: JavaScript click() 直接操作 DOM
  └─ 坑: body 文本正则 [^\n]+? 零宽匹配 → 空标题

传统招聘 (LinkedIn, Indeed, Hays...)
  └─ 特点: CSS Selector 直接选职位卡片
  └─ 难点: 反爬（Cloudflare, PerimeterX, 验证码）
  └─ 解法: CDP 复用登录状态、随机 UA、独立 tab

反向链接 (LinkedIn)
  └─ 直接抓取 href，href 为主键去重
```

---

## 4. 评分层: cco_scorer.py + keywords-v2.json

**文件**: `scanners/cco_scorer.py` + `config/keywords-v2.json`

```
cco_scorer.score_job(title, jd_text, snippet)
    │
    ├── Step 1: title 快速初筛
    │   ├── 高优匹配 (high_match): BA, PM, AI Consultant, GenAI, RAG...
    │   ├── 中优匹配 (medium_match): Digital, Automation, Data...
    │   └── 低优匹配 (low_match): 基础支撑类
    │
    ├── Step 2: exclude 关键词过滤
    │   └── intern, airline, freight, 实习, 實習 → 直接排除
    │
    ├── Step 3: JD 正文关键词命中
    │   ├── 技术关键词: LLM(×3), GenAI(×3), RAG(×3), Agent(×2), ML...
    │   └── 软技能: Agile, Stakeholder, Roadmap, Business Case...
    │
    ├── Step 4: 优先级分层
    │   ├── P0 (≥80分): high_match + 强AI关键词 + HK
    │   ├── P1 (≥70分): medium_match + AI关键词
    │   ├── P2 (≥60分): 基础达标
    │   └── P3 (<60分): 不入库
    │
    └── 输出: {"score": 85, "priority": "P1", "reason": "强AI关键词命中..."}
```

---

## 5. 合并层: merge_results.py

**文件**: `merge_results.py`

```
每次运行 scan_xxx.py 时:
  ↓
  写入 candidates/raw/{platform}_{date}_raw.json      (全量条目)
  写入 candidates/raw/{platform}_{date}.json           (仅 matched)
  追加到 config/HK_AI_Jobs_All.xlsx                     (一键合并)
  
merge_results.py (手动/定期执行):
  ↓
  扫描 candidates/raw/ 目录
  读取所有 *_raw.json + *{date}.json
  按 URL 主干去重（去除 ?wdjobreqid=xxx 等查询参数）
  合并到 HK_AI_Jobs_All.xlsx
  按 priority(P0>P1>P2) + score(高>低) 排序
```

---

## 6. 数据存储结构

```
job-agent/
├── config/
│   ├── scan_strategies.py      # 61平台 URL 配置 ⭐
│   ├── keywords-v2.json         # 评分规则配置 ⭐
│   ├── scanner_schedule.json    # 扫描频率配置
│   └── HK_AI_Jobs_All.xlsx     # 合并总表（每次追加）
│
├── scanners/
│   ├── cco_scorer.py           # 评分引擎 ⭐
│   ├── job_scanner_base.py     # 通用工具库
│   ├── scan_workday_base.py    # Workday 分页基础
│   ├── scan_xxx.py             # 60+ 平台扫描器 ⭐
│   └── _archive/               # 旧版扫描器归档
│
├── candidates/raw/              # ⭐ 原始数据湖
│   ├── aia_2026-04-20.json          # matched (推荐职位)
│   ├── aia_2026-04-20_raw.json     # raw (全部条目)
│   ├── manulife_2026-04-20.json
│   ├── manulife_2026-04-20_raw.json
│   └── ... (按平台+日期命名)
│
├── reports/                    # 历史报告
├── docs/
│   └── JD_PDFs/               # JD 人工下载归档
├── logs/
│   └── scan_log.md            # 扫描日志
└── merge_results.py           # 合并脚本 ⭐
```

---

## 7. 已知坑与修复记录

| 坑 | 根因 | 修复 |
|----|------|------|
| cp1252 UnicodeEncodeError | Windows PowerShell 默认编码非 UTF-8 | `sys.stdout.reconfigure(encoding='utf-8')` |
| BASE_URL NameError | 变量被注释但代码中仍引用 | 用 `href` 直接作为 link，或正确拼接 |
| href 重复路径 | BASE_URL 含 `/zh-TW/External`，href 也有 | `page.url.split('/zh-TW/External')[0]` 取域名 |
| SPA 分页点击失败 | Playwright locator.click() 在 headless 无效 | 改用 `page.evaluate('el.click()')` |
| SPA 正则零匹配 | `[^\n]+?` 非贪婪导致无匹配 | 改为 `[^\n]*` |
| role="grid" 消失 | SPA 交互后动态属性被移除 | 用稳定 class 选择器代替 |
| 扫描中崩溃丢数据 | finally 在 crash 时未执行 | 每10条增量保存一次 |
| locationCountry 硬编码 | 旧服务器值迁移到新服务器 | 从 scan_strategies.py 动态读取 |

---

## 8. 执行命令速查

```bash
# 单个扫描器
python scanners/scan_aia.py --no-dry-run

# 合并结果
python merge_results.py

# 查看 Excel（当日合并）
explorer config\HK_AI_Jobs_All.xlsx
```
