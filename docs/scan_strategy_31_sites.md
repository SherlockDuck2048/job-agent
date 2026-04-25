# 31个网站扫描策略总表

> 生成时间: 2026-04-07
> 负责人: CCO 第二大脑
> 扫描引擎: Playwright (CDP: http://127.0.0.1:9222)

---

## 扫描方法速查

| 方法 | 说明 | 技术要求 | 网站数量 |
|------|------|---------|---------|
| **M1: Playwright CDP + 登录态** | 使用已有Chrome登录态 | CDP运行中 | 1 |
| **M2: Playwright CDP + 模拟输入** | 动态搜索，需填表/点按钮 | CDP运行中 | 6 |
| **M3: Playwright CDP + URL翻页** | URL参数翻页，无需交互 | CDP运行中 | 6 |
| **M4: HTTP直接请求** | 最快，无需JS渲染 | requests | 0 (暂不推荐) |
| **M5: LinkedIn手动搜索** | 反爬太严，建议手动 | 无 | 2 |
| **M6: 手动查找** | 无公开招聘页 | 无 | 3 |

---

## 🌍 综合招聘平台（2个）

| # | 平台 | 方法 | 脚本 | 状态 | 说明 |
|---|------|------|------|------|------|
| 1 | LinkedIn | **M1** | scan_linkedin.py | ⚠️ 需登录 | 手动登录Chrome后扫描 |
| 2 | Indeed | **M3** | 待创建 | ⚠️ 未测试 | URL参数: `?q=AI&l=Hong+Kong` |

### LinkedIn (M1: Playwright CDP + 登录态)
```python
# 前提: Chrome已登录LinkedIn，CDP端口9222运行
browser = p.chromium.connect_over_cdp(CDP_URL)
context = browser.contexts[0]  # 复用登录态
page = context.new_page()
page.goto("https://www.linkedin.com/jobs/search/?keywords=AI&location=Hong+Kong")
```

### Indeed (M3: Playwright CDP + URL翻页)
```python
# Indeed使用URL参数翻页，但可能被反爬
page.goto("https://hk.indeed.com/jobs?q=AI&l=Hong+Kong&start=0")
page.goto("https://hk.indeed.com/jobs?q=AI&l=Hong+Kong&start=10")
# 注意: 建议用M3先测试，成功后再优化
```

---

## 🕵️ 猎头网站（9个）

| # | 平台 | 方法 | 脚本 | 状态 | 说明 |
|---|------|------|------|------|------|
| 3 | Hays | **M2** | scan_hays_v2.py | ✅ 已验证 | 需模拟输入"AI"搜索 |
| 4 | Michael Page | **M2** | scan_michaelpage_v6.py | ⚠️ 偶尔失败 | 多关键词搜索，需滚动加载 |
| 5 | Seamatch | **M3** | 待创建 | ⚠️ 未测试 | 香港本地猎头，结构简单 |
| 6 | Ambition | **M3** | 待创建 | ⚠️ 未测试 | 香港本地猎头 |
| 7 | Randstad | **M3** | 待创建 | ⚠️ 未测试 | 全球猎头 |
| 8 | Adecco | **M2** | 待创建 | ⚠️ 未测试 | 页面有噪音，需严格过滤 |
| 9 | Robert Walters | **M5** | - | ❌ 反爬严 | PerimeterX，需手动 |
| 10 | PageUp | **M3** | 待创建 | ⚠️ 未测试 | 香港猎头 |
| 11 | Classy Wheeler | **M3** | 待创建 | ⚠️ 未测试 | 香港猎头 |

### 方法详解

#### Hays (M2: Playwright CDP + 模拟输入)
- **URL**: `https://www.hays.com.hk/find-jobs`
- **难度**: ⭐⭐ (中等)
- **关键操作**: 
  1. 找搜索框 `input[placeholder*=Keyword]`
  2. 填入 "AI"
  3. 按Enter
  4. 等待 `networkidle`
  5. 抓 `a[href*='job-detail']` 链接
- **已知问题**: 无

#### Michael Page (M2: Playwright CDP + 模拟输入)
- **URL**: `https://www.michaelpage.com.hk/jobs/{keyword}`
- **难度**: ⭐⭐⭐ (较高)
- **关键操作**:
  1. 遍历关键词: AI, machine-learning, product-manager, data-scientist
  2. `wait_until="networkidle"`
  3. 滚动3次加载更多
  4. 找 `View Job` 按钮的祖先a标签
- **已知问题**: 偶尔 "Target page closed"，需加重试

#### Robert Walters (M5: 手动/LinkedIn)
- **原因**: PerimeterX反爬，自动化极难
- **替代方案**: LinkedIn搜索 `site:linkedin.com/jobs Robert Walters AI Hong Kong`

---

## 🏢 企业官网直招（20家）

### 金融 / 保险（11家）

| # | 公司 | 系统 | 方法 | 脚本 | 状态 |
|---|------|------|------|------|------|
| 12 | HSBC | Workday | **M3** | scan_hsbc_v3.py | ✅ 已验证 |
| 13 | AIA | Workday | **M3** | scan_aia_v2.py | ✅ 已验证 |
| 14 | Manulife | Workday | **M3** | 待创建 | ⚠️ 推测 |
| 15 | Prudential | Taleo | **M3** | 待创建 | ⚠️ 推测 |
| 16 | FWD Insurance | Greenhouse | **M3** | 待创建 | ⚠️ 推测 |
| 17 | Bowtie | Lever | **M3** | 待创建 | ⚠️ 未测试 |
| 18 | AIG | Workday | **M3** | 待创建 | ⚠️ 推测 |
| 19 | HKEX | 自研 | **M3** | 待创建 | ⚠️ 未测试 |
| 20 | OCBC | Workday | **M3** | 待创建 | ⚠️ 推测 |
| 21 | CNCBI | 自研 | **M3** | 待创建 | ⚠️ 未测试 |
| 22 | Macquarie | Workday | **M3** | 待创建 | ⚠️ 推测 |

#### HSBC (M3: Playwright CDP + URL翻页) ✅ 已验证
```python
url = "https://mycareer.hsbc.com/en_GB/external/SearchJobs/?keywords=AI&location=Hong+Kong"
page.goto(url, wait_until="networkidle", timeout=30000)
time.sleep(4)
for _ in range(5):
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
# 找 View Job 按钮的祖先元素
job_data = page.evaluate("""...""")  # 见scan_hsbc_v3.py
```

#### AIA (M3: Playwright CDP + URL翻页) ✅ 已验证
```python
base_url = "https://aia.wd3.myworkdayjobs.com/zh-TW/External"
url = f"{base_url}?keyword=AI"
page.goto(url, wait_until="networkidle", timeout=30000)
time.sleep(4)
```

#### Prudential (M3: Playwright CDP + URL翻页)
```python
url = "https://careers.prudential.com.hk/search/?q=AI"
# Taleo系统，选择器: .job-title, .jobLocation, .jobDate
```

#### Manulife (M3: Playwright CDP + URL翻页)
```python
url = "https://careers.manulife.com/global/en/search-results?keywords=AI&location=Hong+Kong"
```

#### FWD Insurance (M3: Playwright CDP + URL翻页)
```python
url = "https://careers.fwd.com/search/?q=AI&locationsearch=Hong+Kong"
# Greenhouse系统，结构标准
```

#### Bowtie (M3: Playwright CDP + URL翻页)
```python
url = "https://www.bowtie.com.hk/en/careers"
# 可能需要点击 "View Open Positions"
```

#### AIG (M3: Workday)
```python
url = "https://aig.wd1.myworkdayjobs.com/aig/jobs?q=AI&locations=Hong+Kong"
```

#### HKEX (M3)
```python
url = "https://careers.hkex.com/search/?q=AI"
```

#### OCBC (M3: Workday)
```python
url = "https://careers.ocbc.com/search/?q=AI&location=Hong+Kong"
```

#### Macquarie (M3: Workday)
```python
url = "https://careers.macquarie.com/en/search/?q=AI&location=Hong+Kong"
```

---

### 航空 / 交通（3家）

| # | 公司 | 系统 | 方法 | 脚本 | 状态 |
|---|------|------|------|------|------|
| 23 | Cathay Pacific | Taleo | **M3** | 待创建 | ⚠️ 推测 |
| 24 | HKJC | 自研 | **M2** | 待创建 | ⚠️ 未测试 |
| 25 | GoGoX | 自研 | **M3** | 待创建 | ⚠️ 未测试 |

#### HKJC (M2: 需点击)
```python
url = "https://careers.hkjc.com/careers/employment/en/search.aspx?q=AI"
# 可能有表单需交互
```

---

### 科技 / 商业服务（5家）

| # | 公司 | 系统 | 方法 | 脚本 | 状态 |
|---|------|------|------|------|------|
| 26 | Microsoft | Microsoft Careers | **M2** | 待创建 | ⚠️ 需测试 |
| 27 | PCCW / HKT | Jobylon | **M3** | 待创建 | ⚠️ 推测 |
| 28 | SMARTCare | ? | **M6** | - | ❌ 无公开页 |
| 29 | Bowtie Life | Lever | **M3** | 待创建 | 同#17 |
| 30 | Prus 科技 | ? | **M5** | - | ⚠️ 未知 |

#### Microsoft (M2: 需交互)
```python
url = "https://jobs.careers.microsoft.com/global/en/search?q=AI&lc=Hong+Kong"
# Microsoft Careers 自研系统
# 找搜索框，填AI，点击搜索
# 滚动加载
```

#### PCCW/HKT (M3: Jobylon)
```python
url = "https://careers.pccw.com/search/?q=AI"
# Jobylon SaaS，结构标准
```

#### SMARTCare (M6: 手动)
- 无公开招聘页面
- 建议: LinkedIn搜索 `site:linkedin.com/jobs SMARTCare Hong Kong`

#### Prus 科技 (M5: 手动)
- 公司名不确定（可能是Prudential缩写或另一家公司）
- 建议: 确认公司全名后手动查找

---

### 地产 / 其他（6家）

| # | 公司 | 系统 | 方法 | 脚本 | 状态 |
|---|------|------|------|------|------|
| 31 | Swire Properties | SAP SF | **M3** | 待创建 | ⚠️ 未测试 |
| 32 | Aedas | ? | **M5** | - | ❌ 无公开页 |
| 33 | Caritas | ? | **M6** | - | ❌ 无公开页 |
| 34 | City University | 自研 | **M3** | 待创建 | ⚠️ 未测试 |
| 35 | Lingnan | ? | **M6** | - | ❌ 无公开页 |
| 36 | HKUST | HROnline | **M3** | 待创建 | ⚠️ 未测试 |

#### Swire Properties (M3: SAP SuccessFactors)
```python
url = "https://careers.swireproperties.com/en-hk/search/?q=ai"
# SAP SuccessFactors，结构标准
```

#### City University (M3: 自研)
```python
url = "https://www.cityu.edu.hk/hro/en/job/vacancy.htm"
# 自研系统，需探索DOM结构
```

#### HKUST (M3: HROnline)
```python
url = "https://career.hkust.edu.hk/search/?q=AI"
# HROnline系统
```

---

## 📊 方法分类汇总

### M1: Playwright CDP + 登录态 (1个)
- LinkedIn

### M2: Playwright CDP + 模拟输入 (5个)
- Hays ✅
- Michael Page ⚠️
- Microsoft ⚠️
- HKJC ⚠️
- Adecco ⚠️

### M3: Playwright CDP + URL翻页 (18个)
- HSBC ✅
- AIA ✅
- Indeed ⚠️
- Seamatch ⚠️
- Ambition ⚠️
- Randstad ⚠️
- PageUp ⚠️
- Classy Wheeler ⚠️
- Manulife ⚠️
- Prudential ⚠️
- FWD ⚠️
- Bowtie ⚠️
- AIG ⚠️
- HKEX ⚠️
- OCBC ⚠️
- CNCBI ⚠️
- Macquarie ⚠️
- Cathay Pacific ⚠️
- GoGoX ⚠️
- PCCW ⚠️
- Swire Properties ⚠️
- City University ⚠️
- HKUST ⚠️

### M5: 手动/LinkedIn (3个)
- Robert Walters ❌
- Aedas ❌
- Prus 科技 ⚠️

### M6: 手动查找 (4个)
- SMARTCare ❌
- Caritas ❌
- Lingnan ❌

---

## ⚠️ 高风险网站（需特殊处理）

| 网站 | 风险 | 建议 |
|------|------|------|
| Robert Walters | PerimeterX反爬 | 放弃自动化，用LinkedIn替代 |
| SMARTCare | 无公开招聘页 | 手动查找 |
| Aedas | 无公开招聘页 | LinkedIn替代 |
| Caritas | 无公开招聘页 | 手动查找 |
| Lingnan | 无公开招聘页 | 手动查找 |

---

## 🔧 扫描脚本命名规范

```
scan_hsbc_v3.py       # 汇丰
scan_aia_v2.py        # 友邦
scan_hays_v2.py       # 猎头
scan_michaelpage_v6.py # 猎头
scan_indeed.py        # 待创建
scan_seamatch.py      # 待创建
scan_ambition.py      # 待创建
scan_randstad.py      # 待创建
scan_adecco.py        # 待创建
scan_pageup.py        # 待创建
scan_classy.py        # 待创建
scan_manulife.py      # 待创建
scan_prudential.py    # 待创建
scan_fwd.py           # 待创建
scan_bowtie.py        # 待创建
scan_aig.py           # 待创建
scan_hkex.py          # 待创建
scan_ocbc.py          # 待创建
scan_cncb.py          # 待创建
scan_macquarie.py     # 待创建
scan_cathay.py        # 待创建
scan_hkjc.py          # 待创建
scan_gogox.py         # 待创建
scan_microsoft.py     # 待创建
scan_pccw.py          # 待创建
scan_swire.py         # 待创建
scan_cityu.py         # 待创建
scan_hkust.py         # 待创建
scan_linkedin.py      # 已有，需登录态
```

---

## 📝 run_all_scanners.py 更新建议

```python
SCANNER_MAP = {
    # 已验证
    "hays":         ("Hays",              "scan_hays_v2.py",         "AI"),
    "michaelpage":  ("Michael Page",      "scan_michaelpage_v6.py",  "AI"),
    "hsbc":         ("HSBC",              "scan_hsbc_v3.py",          "AI"),
    "aia":          ("AIA",               "scan_aia_v2.py",           "AI"),
    "linkedin":     ("LinkedIn",           "scan_linkedin.py",        "AI"),
    # 待创建
    "indeed":       ("Indeed",            "scan_indeed.py",           "AI"),
    "seamatch":     ("Seamatch",          "scan_seamatch.py",         "AI"),
    "ambition":     ("Ambition",          "scan_ambition.py",         "AI"),
    "randstad":     ("Randstad",          "scan_randstad.py",         "AI"),
    "manulife":     ("Manulife",          "scan_manulife.py",         "AI"),
    "prudential":   ("Prudential",        "scan_prudential.py",       "AI"),
    "fwd":          ("FWD",               "scan_fwd.py",              "AI"),
    "bowtie":       ("Bowtie",            "scan_bowtie.py",           "AI"),
    "microsoft":    ("Microsoft HK",       "scan_microsoft.py",       "AI"),
    "pccw":         ("PCCW/HKT",          "scan_pccw.py",             "AI"),
    "swire":        ("Swire Properties",   "scan_swire.py",           "AI"),
    "hkust":        ("HKUST",             "scan_hkust.py",           "AI"),
    "cityu":        ("City University",   "scan_cityu.py",           "AI"),
}
```

---

## ✅ 下一步行动计划

### Phase 1: 优先创建脚本 (8个)
1. scan_indeed.py - URL翻页
2. scan_prudential.py - Taleo
3. scan_manulife.py - Workday
4. scan_fwd.py - Greenhouse
5. scan_microsoft.py - 模拟输入
6. scan_swire.py - SAP
7. scan_hkust.py - HROnline
8. scan_bowtie.py - Lever

### Phase 2: 第二批 (8个)
9. scan_seamatch.py
10. scan_ambition.py
11. scan_randstad.py
12. scan_aig.py
13. scan_hkex.py
14. scan_ocbc.py
15. scan_cathay.py
16. scan_pccw.py

### Phase 3: 第三批 (6个)
17. scan_adecco.py
18. scan_pageup.py
19. scan_classy.py
20. scan_cncb.py
21. scan_macquarie.py
22. scan_hkjc.py

### Phase 4: 手动处理 (4个)
- SMARTCare - 确认公司
- Aedas - LinkedIn
- Caritas - 手动
- Lingnan - 手动

---

*最后更新: 2026-04-07*
