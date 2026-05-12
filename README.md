# Job Agent - AI猎头职位扫描系统

香港AI相关职位自动追踪系统，扫描70+招聘网站，智能评分筛选匹配职位。
一句话定位： 个人求职自动化工具——把"人肉找职位"变成"机器跑、人决策".

## 功能特点

- **68+ 公司扫描器**：覆盖银行、保险、科技、咨询等行业
- **两阶段评分**：`quick_filter` 快速过滤 → `cco_scorer` 精准评分
- **三级输出**：P0 (≥90分)、P1 (75-89分)、P2 (70-74分)
- **跨会话去重**：`seen_jobs.json` 索引，避免重复推送
- **道法术器摘要**：LLM自动生成职位解读，提炼核心要求
- **定时任务**：每日自动扫描，通过 OpenClaw cron 驱动

## 项目结构

```
job-agent/
├── scanners/               # 扫描器模块
│   ├── scan_*.py          # 各公司扫描器（68个）
│   ├── job_scanner_base.py # 基类（Plan C/X函数）
│   ├── cco_scorer.py      # 评分引擎
│   └── seen_jobs.py       # 去重索引管理
├── config/
│   ├── scan_strategies.py # URL配置
│   └── HK_AI_Jobs_All.xlsx # 汇总Excel
├── candidates/
│   ├── raw/               # 扫描原始JSON
│   ├── jd_store/          # JD文本存储
│   ├── history/           # seen_jobs索引
│   └── HK_AI_Jobs_All.xlsx # 聚合职位库
├── docs/                  # 文档
│   ├── scanner_matrix.xlsx
│   └── scanner_architecture.md
└── merge_results.py       # JSON→Excel合并
```

## 快速开始

```bash
# 运行单个扫描器
python3 scanners/scan_aia.py

# 合并今日结果到Excel
python3 merge_results.py --new-only

# 查看扫描器状态
python3 scanners/_check_tasks.py
```


## 评分体系

| 等级 | 分数范围 | 说明 |
|------|----------|------|
| P0 | ≥90 | 强匹配，优先投递 |
| P1 | 75-89 | 中等匹配，值得尝试 |
| P2 | 70-74 | 弱匹配，观望 |
| P3 | <70 | 过滤 |

## 扫描器状态

### Code Frozen（21个）✅

AIA, AIG, BEA, BOCHK, CCB, CICC, CRC, DBS, Deloitte, FWD, HSBC, JPMorgan, KPMG, Manulife, PCCW, PwC, SunLife, UBS, Zurich, Accenture, HKAirport, HKPC

### 平台分布

| 平台类型 | 扫描器数量 |
|----------|-----------|
| Workday | SunLife, FWD, Manulife, AIA, AIG, Prudential, AXA, OCBC, CNCB, etc. |
| Mokahr | KPMG, EY, Accenture, PwC |
| Oracle HCM | JPMorgan, CLP |
| Taleo | UBS, PCCW, HKPC |
| PeopleSoft | BEA |
| 自建 | IBM, Microsoft, HKAirport, HKEX |

### 技术方案

- **CDP 模式**：复用本地 Chrome 调试端口（9222），适合需登录态站点
- **Headless 模式**：无头浏览器，适合公开页面
- **urllib 模式**：轻量抓取，适合简单页面


## Cron 任务

通过 OpenClaw cron 定时执行：

| 时间 | 任务 | 包含扫描器 |
|------|------|-----------|
| 17:00 | scan_public_sector_daily_1 | HKEX, HKPC, HKAirport |
| 18:00 | scan_bank_daily_2 | Goldman Sachs, BEA, UBS, SC |
| 19:00 | scan_bank_daily_1 | DBS, CNCB, CCBAsia, OCBC |
| 19:00 | scan_bank_daily_3 | BOCHK, Citi, JPMorgan |
| 21:00 | scan_insurance_daily_2 | FWD, Zurich, AXA, AIA |
| 21:25 | scan_consultant_daily_1 | KPMG, Accenture, EY, PwC |
| 22:00 | scan-clp-daily | CLP |


### 数据飞轮评估
- 潜在飞轮：jd_store 积累 → 可以训练一个"根据 JD 生成 岗位角色画像"的模型；seen_jobs 趋势分析 → 可以预测"哪类职位最近变多了,从而提前布局"


## 许可证

私有项目，仅供个人使用。

---

**作者**: CCO (Jemma2046)  
**创建日期**: 2026-04-25  
**仓库**: https://github.com/Jemma2046/job-agent  
**最后更新**: 2026-05-12
