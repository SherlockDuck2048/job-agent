# job-agent Skill

AI求职助手 - 智能岗位扫描、匹配评分与报告生成系统。

## 功能概述

本skill提供完整的AI求职工作流：
1. **多源岗位扫描** - 支持60+招聘网站自动化抓取
2. **智能匹配评分** - 基于CCO求职画像的精准岗位匹配算法
3. **报告生成** - 自动输出Excel格式的求职日报

## 目录结构

```
job-agent/
├── config/
│   ├── keywords-v2.json      # 岗位匹配关键词配置
│   ├── scan_schedule.json    # 扫描调度配置
│   └── scan_strategies.py    # 扫描策略定义
├── scanners/
│   ├── scanner_base.py       # 扫描器基类
│   ├── cco_scorer.py         # CCO岗位评分器
│   ├── run_dispatcher.py     # 统一调度器
│   └── scan_*.py             # 各网站扫描脚本
├── candidates/
│   └── raw/                  # 原始抓取数据
├── reports/                  # 生成的Excel报告
├── logs/                     # 扫描日志
└── docs/                     # 扫描策略文档
```

## 快速开始

### 1. 运行单个扫描器

```bash
cd scanners
python scan_indeed_v2.py
```

### 2. 使用调度器批量扫描

```bash
# 运行所有扫描器
cd scanners
python run_dispatcher.py

# 仅运行HTTP类型（快速）
python run_dispatcher.py --http-only

# 运行指定扫描器
python run_dispatcher.py -s indeed -s hays

# 列出所有可用扫描器
python run_dispatcher.py --list
```

### 3. 生成Excel报告

```bash
cd ..
python gen_final_excel.py
```

## 扫描策略分类

| 策略 | 方法 | 代表网站 | 速度 |
|------|------|----------|------|
| HTTP | requests + BeautifulSoup | Indeed, JobsDB, Randstad | 快 |
| CDP_URL | Playwright URL翻页 | HSBC, AIA, Manulife, Citi | 中 |
| CDP_INPUT | Playwright 模拟输入 | Hays, Microsoft | 中 |
| CDP_LOGIN | Playwright 需登录 | LinkedIn | 慢 |

## CCO评分算法

### 岗位类型匹配

| 匹配度 | 岗位示例 | 基础分 | 优先级 |
|--------|----------|--------|--------|
| 高匹配 | AI Business Analyst, Project Manager, Product Manager | 100 | P0 |
| 中匹配 | GenAI Solution Consultant, Data Analyst, AI Product Manager | 85 | P1 |
| 低匹配 | AI Engineer, Data Scientist, ML Engineer | 60 | P2 |

### 评分维度

1. **岗位类型基础分** - 基于职位标题匹配
2. **技术强度惩罚** - 检测hands-on技术需求（高35/中20/低10分）
3. **排除项惩罚** - 非AI岗位(45)/销售岗位(35)
4. **经验要求惩罚** - 10年+(15)/8年+(10)
5. **加分项** - GenAI(10)/金融科技(5)/香港(3)
6. **能力匹配** - 核心能力关键词匹配（最多+5）

### 优先级阈值

- **P0**: 90-100分（强烈推荐）
- **P1**: 75-89分（值得关注）
- **P2**: 60-74分（一般合适）
- **P3**: <60分（不推荐）

## 配置文件说明

### keywords-v2.json

```json
{
  "job_type_scores": {
    "high_match": {
      "titles": ["AI Business Analyst", "Project Manager"],
      "base_score": 100,
      "priority": "P0"
    }
  },
  "tech_penalty_keywords": {
    "high_penalty": {
      "keywords": ["hands-on coding", "tensorflow"],
      "penalty": 35
    }
  },
  "bonus_keywords": {
    "genai": {
      "keywords": ["genai", "llm", "rag"],
      "bonus": 10
    }
  }
}
```

### 修改评分规则

编辑 `config/keywords-v2.json` 后即时生效，无需重启。

## 开发新扫描器

继承基类实现新网站扫描：

```python
from scanner_base import HTTPScanner

class MyScanner(HTTPScanner):
    def __init__(self):
        super().__init__(
            base_url="https://example.com/jobs",
            selectors={
                "job_card": ".job-item",
                "title": "h2.title",
                "company": ".company-name"
            }
        )
    
    def scan(self):
        # 实现扫描逻辑
        soup = self.fetch_page(self.base_url)
        jobs = self.extract_jobs(soup, "AI")
        return jobs

if __name__ == "__main__":
    scanner = MyScanner()
    jobs = scanner.scan()
    scanner.save_results("my_site")
```

## 依赖要求

- Python 3.10+
- requests + beautifulsoup4
- playwright (用于CDP扫描)
- openpyxl (用于Excel生成)

## 注意事项

1. **反爬虫**: 部分网站有反爬机制，使用CDP策略并控制请求频率
2. **编码问题**: Windows环境下设置 `PYTHONIOENCODING=utf-8`
3. **Chrome CDP**: 确保Chrome已启动远程调试端口9222

## Keywords

求职, 招聘, job search, AI岗位, 扫描器, 岗位匹配, 简历投递
