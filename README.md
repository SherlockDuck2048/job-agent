# Personal Job Assistant - AI Job Auto-Tracking System

> Using technology to solve information overload in job searching

## 🎯 Why I Built This Project

When job searching, manually browsing dozens of job sites daily and filtering positions is time-consuming and opportunities are easily missed.

**My Pain Points:**
- Each job search takes 2-3 hours browsing LinkedIn, Indeed, and company career pages
- Different job sites have different structures, making systematic tracking difficult
- Good positions disappear quickly; by the time I discover them, they're already filled

**Solution:** Developed an automated scanning system that automatically runs through all target companies daily, notifying me immediately when new positions are available.

---

## 📊 Project Results

| Metric | Result |
|--------|--------|
| Companies Covered | 70+ (Banks, Insurance, Consulting, Tech) |
| Daily Automated Scans | 9 AM to 10 PM, executed in time slots |
| Matched Positions Found | 200+ (filtered by intelligent scoring) |
| Time Saved | ~2 hours/day → 10 hours/week |

---

## 🛠 Technical Implementation (Simplified)

```
1. Write web scraping scripts -> Automatically crawl company career pages
2. Intelligent scoring -> Score matching degree based on my background (Finance IT + AI)
3. Deduplication mechanism -> Avoid pushing the same position repeatedly
4. Automatic aggregation -> Output results to Excel for quick browsing
5. JD Analysis -> Analyze job descriptions to quickly understand job responsibilities and requirements
```

**Key Technologies:**
- Python (primary language)
- Playwright/Selenium (browser automation)
- LLM (automatically generate job summaries, extract core requirements)
- Cron scheduled tasks (daily automated execution)

**Challenges Encountered:**
- Some companies have anti-scraping measures → Solved by reusing logged-in browser sessions
- Different website structures → Designed universal adapter compatible with multiple patterns

---

## 💡 What I Learned from This Project

1. **My New Role in the AI Era**: Work focus shifted from writing code to directing AI — clearly communicating ideas, architecture, and specifications to AI, helping it break down tasks, set standards, and judge outputs

2. **Systems Thinking**: Break down complex problems into executable modules, build a complete system from scratch (collection → analysis → scoring → deduplication → aggregation), anticipate edge cases (anti-scraping), design universal adapters to be compatible with different recruitment platforms, ensure single points of failure don't affect the whole system

3. **Give Precise Instructions, but Know When to Leave Space**: Give AI enough room for innovation, rather than rigid commands. Lead, rather than supervise

4. **Continuous Iteration**: Let AI continuously improve based on usage feedback (scoring, deduplication, summarization)

---

## 📂 Project Structure

```
job-agent/
├── scanners/          # 70+ company scanners
├── config/           # Configuration files
├── candidates/       # Job data
└── docs/            # Technical documentation
```

---

## 🚀 How to Use

```bash
# Run scan
python3 scanners/scan_aia.py

# Merge results to Excel
python3 merge_results.py --new-only
```

---

**If you're interested in this project, feel free to connect!**

- GitHub: https://github.com/Jemma2046/job-agent

---

*Project is still under continuous iteration, welcome to Star and Fork 📌*




# 个人求职助手 - AI职位自动追踪系统

> 用技术解决求职过程中的信息过载问题

## 🎯 为什么做这个项目

求职时每天手动刷几十个招聘网站、筛选职位，既耗时又容易漏机会。

**我的痛点**：
- 每次求职搜索要花2-3小时刷LinkedIn、Indeed、招聘官网
- 不同的招聘站点结构不同，很难系统性追踪
- 好的职位稍纵即逝，等发现时已经招满了

**解决方案**：开发自动化扫描系统，每天自动跑一遍所有目标公司，有新职位第一时间知道。

---

## 📊 项目成果

| 指标 | 结果 |
|------|------|
| 覆盖公司数 | 70+ （银行、保险、咨询、科技） |
| 每日自动扫描 | 早上9点到晚上10点，分时段执行 |
| 已发现匹配职位 | 200+ 个（通过智能评分筛选） |
| 节省时间 | 每天约2小时 → 每周10小时 |

---

## 🛠 技术实现（简化版）

```
1. 编写爬虫脚本 -> 自动抓取各公司招聘页面
2. 智能评分 -> 根据我的背景（金融IT + AI）匹配度打分
3. 去重机制 -> 避免重复推送同一职位
4. 自动汇总 -> 结果输出到Excel，便于快速浏览
5. JD分析 -> 对JD的道法术器进行分析，快速了解岗位职责
```

**关键技术**：
- Python（主力语言）
- Playwright/Selenium（浏览器自动化）
- LLM（自动生成职位摘要，提炼核心要求）
- Cron定时任务（每日自动执行）

**遇到的挑战**：
- 部分公司有反爬虫 → 通过复用登录态浏览器解决
- 不同网站结构不同 → 设计通用适配器兼容多种模式

---

## 💡 从这个项目学到了什么

1. **AI时代的新角色CCO**：:工作重心从写代码变成驾驭AI,把想法、架构、规格清晰传达给AI,帮AI拆解任务、设定标准、判断产出，让AI执行

2. **系统思维**：把复杂问题拆解成可执行的模块,从0到1搭建完整系统（采集→分析→评分→去重→聚合），预判边界情况（反爬），设计通用适配器兼容不同的招聘平台，确保单点故障不影响全局

3. **精准下指令，但懂得留白**：给AI足够的创新空间，而不是死命令。领导，而非监工

4. **持续迭代**：让AI根据使用反馈不断完善（评分、去重、摘要）

---

## 📂 项目结构

```
job-agent/
├── scanners/          # 70+公司扫描器
├── config/           # 配置文件
├── candidates/       # 职位数据
└── docs/            # 技术文档
```

---

## 🚀 如何使用

```bash
# 运行扫描
python3 scanners/scan_aia.py

# 合并结果到Excel
python3 merge_results.py --new-only
```

---

**如果你对我这个项目感兴趣，欢迎交流！**

- GitHub: https://github.com/Jemma2046/job-agent

---

*项目仍在持续迭代中，欢迎Star和Fork 📌*


