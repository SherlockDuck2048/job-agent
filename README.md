# Job Agent - AI猎头职位扫描系统

香港AI相关职位自动追踪系统，扫描70+招聘网站，智能评分筛选匹配职位。

## 功能特点

- **70+ 公司扫描器**：覆盖银行、保险、科技、咨询等行业
- **两阶段评分**：`quick_filter` 快速过滤 → `cco_scorer` 精准评分
- **三级输出**：P0 (100分)、P1 (75-99分)、P2 (70-74分)
- **跨会话去重**：`seen_jobs.json` 索引，避免重复推送
- **道法术器摘要**：LLM自动生成职位解读，提炼核心要求

## 项目结构

```
job-agent/
├── scanners/               # 扫描器模块
│   ├── scan_*.py          # 各公司扫描器
│   ├── job_scanner_base.py # 基类（Plan C/X函数）
│   ├── cco_scorer.py      # 评分引擎
│   └── seen_jobs.py       # 去重索引管理
├── config/
│   ├── scan_strategies.py # URL配置
│   └── HK_AI_Jobs_All.xlsx # 汇总Excel
├── candidates/
│   ├── raw/               # 扫描原始JSON
│   ├── jd_store/          # JD文本存储
│   └── history/           # seen_jobs索引
├── docs/                  # 文档
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

## 扫描器开发

每个扫描器需完成三个任务：

1. **Plan C** - 调用 `get_jd_from_url()` 抓取完整JD
2. **Plan X** - 调用 `seen_jobs` 模块去重
3. **Excel追加** - 调用 `append_scanner_to_excel()`

参考 `scan_aia.py` / `scan_sunlife.py` 作为模板。

## 评分体系

| 等级 | 分数范围 | 说明 |
|------|----------|------|
| P0 | ≥100 | 强匹配，优先投递 |
| P1 | 75-99 | 中等匹配，值得尝试 |
| P2 | 70-74 | 弱匹配，观望 |
| P3 | <70 | 过滤 |

## 已完成扫描器（31个）

JPMorgan, HSBC, Hays, Citi, IBM, Randstad, KPMG, SunLife, HKEX, AIA, OCBC, CNCB, Prudential, EY, Manulife, AIG, UBS, Accenture, Zurich, PCCW, BOCHK, FWD, LinkedIn, CRC, BEA, CICC, DBS, SC, CCB, Deloitte, PwC

## 许可证

私有项目，仅供个人使用。

---

**作者**: CCO (Jemma2046)  
**创建日期**: 2026-04-25  
**仓库**: https://github.com/Jemma2046/job-agent
