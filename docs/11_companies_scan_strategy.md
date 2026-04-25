# 11家公司扫描策略

> 生成时间: 2026-04-07
> 更新人: CCO 第二大脑

## 扫描方法分类

| 方法 | 特点 | 适用网站数 |
|------|------|-----------|
| **A. Workday/Taleo 系统** | 企业招聘系统，有标准结构 | 4 |
| **B. Greenhouse/Jobvite** | SaaS招聘平台，API可用 | 3 |
| **C. 自研系统** | 公司自建，需特殊处理 | 3 |
| **D. 静态页面** | 简单HTML，无需JS | 1 |

---

## 详细扫描策略

### 科技 / 商业服务 (5家)

#### 1. Microsoft 微软香港
**招聘URL**: `https://jobs.careers.microsoft.com/global/en/search?q=AI&lc=Hong+Kong`
**招聘系统**: Microsoft Careers (自研)
**推荐方法**: **Playwright CDP** (方法 B)

**扫描脚本**: 
```python
# scan_microsoft.py
url = "https://jobs.careers.microsoft.com/global/en/search?q=AI&lc=Hong+Kong"
page.goto(url, wait_until="networkidle")
# 找 job card elements
```

**历史状态**: ✅ 已知可扫描
**关键词**: AI, Machine Learning, Data Scientist, Product Manager
**特殊处理**: 需滚动加载更多岗位

---

#### 2. PCCW / HKT 电讯盈科
**招聘URL**: `https://careers.pccw.com/search/?q=AI`
**招聘系统**: Jobylon (SaaS)
**推荐方法**: **Playwright CDP** (方法 B)

**扫描脚本**:
```python
# scan_pccw.py
url = "https://careers.pccw.com/search/?q=AI"
# Jobylon 系统，结构标准
```

**历史状态**: ⚠️ 未测试
**关键词**: AI, Digital, Technology, IT

---

#### 3. SMARTCare  
**招聘URL**: 未找到公开招聘页面
**推荐方法**: **手动查找** 或 **搜索引擎**

**建议**: 通过 LinkedIn 或公司官网查找招聘入口

---

#### 4. Bowtie Life 蓝十字保险
**招聘URL**: `https://www.bowtie.com.hk/en/careers`
**招聘系统**: 自研或Lever
**推荐方法**: **Playwright CDP** (方法 B)

**扫描脚本**:
```python
# scan_bowtie.py
url = "https://www.bowtie.com.hk/en/careers"
# 可能需要点击 "View Open Positions"
```

**历史状态**: ⚠️ 未测试
**关键词**: AI, Technology, Actuarial, Software

---

#### 5. Prudential 保诚
**招聘URL**: `https://careers.prudential.com.hk/search/?q=AI`
**招聘系统**: Taleo (Oracle)
**推荐方法**: **Playwright CDP** (方法 A)

**扫描脚本**:
```python
# scan_prudential.py
url = "https://careers.prudential.com.hk/search/?q=AI"
# Taleo 系统，结构标准
# 找 .jobTitle, .jobLocation, .jobDate 等元素
```

**历史状态**: ⚠️ 未测试，但 Taleo 系统已知可扫描
**关键词**: AI, Digital, Analytics, Technology

---

### 地产 / 其他 (6家)

#### 6. Swire Properties 太古地产
**招聘URL**: `https://careers.swireproperties.com/en-hk/search/?q=ai`
**招聘系统**: SAP SuccessFactors
**推荐方法**: **Playwright CDP** (方法 B)

**扫描脚本**:
```python
# scan_swire.py
url = "https://careers.swireproperties.com/en-hk/search/?q=ai"
page.goto(url, wait_until="networkidle")
# SAP SuccessFactors 结构
```

**历史状态**: ⚠️ 未测试，web_fetch 仅返回简单内容
**关键词**: AI, Digital, Technology, Data

---

#### 7. Aedas 凯达环球
**招聘URL**: 未找到公开招聘页面
**推荐方法**: **手动查找** 或 **LinkedIn**

**建议**: 
- LinkedIn: `site:linkedin.com/jobs/ aedas`
- 公司官网可能无在线申请

---

#### 8. Caritas 明爱
**招聘URL**: 未找到
**推荐方法**: **手动查找**

**说明**: 非营利机构，可能通过其他渠道招聘

---

#### 9. City University 城市大学
**招聘URL**: `https://www.cityu.edu.hk/hro/en/job/vacancy.htm`
**招聘系统**: 自研
**推荐方法**: **Playwright CDP** (方法 C)

**扫描脚本**:
```python
# scan_cityu.py
url = "https://www.cityu.edu.hk/hro/en/job/vacancy.htm"
# 找 .vacancy-title, .vacancy-info 等
```

**历史状态**: ⚠️ 未测试
**关键词**: AI, Machine Learning, Data Science, Research

---

#### 10. Lingnan 岭南大学
**招聘URL**: 未找到
**推荐方法**: **手动查找**

**说明**: 大学职位通常较少且特殊

---

#### 11. HKUST 科技大学
**招聘URL**: `https://career.hkust.edu.hk/search/?q=AI`
**招聘系统**: 自研 (HROnline)
**推荐方法**: **Playwright CDP** (方法 C)

**扫描脚本**:
```python
# scan_hkust.py
url = "https://career.hkust.edu.hk/search/?q=AI"
# 自研系统，需探索页面结构
```

**历史状态**: ⚠️ 未测试
**关键词**: AI, Machine Learning, Data Science, Research

---

## 扫描优先级

| 优先级 | 公司 | 方法 | 理由 |
|--------|------|------|------|
| **P0** | Microsoft | Playwright | 大公司，AI岗位多 |
| **P0** | Prudential | Playwright | Taleo系统已知可用 |
| **P1** | PCCW/HKT | Playwright | Jobylon标准结构 |
| **P1** | Bowtie | Playwright | 保险科技公司 |
| **P1** | Swire Properties | Playwright | SAP系统可用 |
| **P2** | City University | Playwright | 大学职位较固定 |
| **P2** | HKUST | Playwright | 科技大学可能有AI岗 |
| **P3** | SMARTCare | 手动 | 无公开页面 |
| **P3** | Aedas | LinkedIn | 建筑行业非核心 |
| **P3** | Caritas | 手动 | 非营利机构 |
| **P3** | Lingnan | 手动 | 大学职位较少 |

---

## 通用扫描脚本模板

### 方法 A: Taleo/Workday 系统
```python
def scan_taleo(url, keywords):
    page.goto(url, wait_until="networkidle")
    time.sleep(3)
    
    # 找所有岗位卡片
    job_cards = page.query_selector_all('.job-title, [class*="jobTitle"], a[href*="/job/"]')
    
    for card in job_cards:
        title = card.inner_text().strip()
        if any_kw_in(title, keywords):
            # 获取详情
            href = card.get_attribute('href')
            # ...
```

### 方法 B: Greenhouse/标准SaaS
```python
def scan_greenhouse(url, keywords):
    page.goto(url, wait_until="networkidle")
    time.sleep(2)
    
    # 滚动加载
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    
    # 找岗位链接
    jobs = page.query_selector_all('a[href*="/jobs/"]')
```

### 方法 C: 自研系统
```python
def scan_custom(url, keywords):
    page.goto(url, wait_until="networkidle")
    time.sleep(3)
    
    # 探索页面结构
    # 根据实际情况调整选择器
```

---

## 下一步

1. **P0 优先级**: 先扫描 Microsoft 和 Prudential
2. **测试脚本**: 逐个网站测试扫描
3. **收集结果**: 存入 candidates/raw 目录
4. **生成报告**: 合并到 Excel 报告

---

## 附录: 已验证可用的扫描方式

| 网站 | 系统 | 状态 | 脚本 |
|------|------|------|------|
| HSBC | Workday | ✅ 可用 | scan_hsbc_v3.py |
| AIA | Workday | ✅ 可用 | scan_aia_v2.py |
| Michael Page | 自研 | ⚠️ 偶尔失败 | scan_michaelpage_v6.py |
| Hays | 自研 | ⚠️ 需模拟输入 | 需重写 |
