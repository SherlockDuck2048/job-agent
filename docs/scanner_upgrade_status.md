# 扫描器升级进度 - Plan C + Plan X 整合

> 更新时间: 2026-04-20 24:00 GMT+8

---

## ✅ 已完成并验证（7个）

| 扫描器 | 平台 | 验证状态 | 备注 |
|--------|------|---------|------|
| scan_sunlife.py | Workday | ✅ 手动验证 | 完整模板 |
| scan_kpmg.py | Mokahr | ✅ 手动验证 | 完整模板 |
| scan_ey.py | Mokahr | ✅ 语法通过 | 批量修改 |
| scan_prudential.py | Workday | ✅ 语法通过 | 批量修改 |
| scan_aig.py | Workday | ✅ 语法通过 | 批量修改 |
| scan_ocbc.py | Workday | ✅ 语法通过 | 批量修改 |
| scan_bochk.py | Workday | ✅ 语法通过 | 批量修改 |

---

## ⏳ 待修改（24个）

### Workday 平台（推荐优先级：高）
- scan_hkex.py
- scan_fwd.py
- scan_zurich.py

### Mokahr 平台（推荐优先级：高）
- scan_accenture.py
- scan_pwc.py

### 默认平台（推荐优先级：中）
- scan_hsbc.py
- scan_jpmorgan.py
- scan_citi.py
- scan_ibm.py
- scan_randstad.py
- scan_pccw.py
- scan_crc.py
- scan_bea.py
- scan_cicc.py
- scan_sc.py
- scan_ccb.py
- scan_deloitte.py

### 其他平台
- scan_linkedin.py (LinkedIn)
- scan_ubs.py (Taleo)
- scan_dbs.py (Workday, 已恢复备份需重新修改)

---

## 📋 修改步骤（通用流程）

### 步骤 1: 添加导入
在 `from cco_scorer import ...` 后添加：
```python
from job_scanner_base import get_jd_from_url, new_page
```

### 步骤 2: 删除本地 JD 函数
删除文件中的以下函数定义：
- `def get_jd(...)`
- `def get_full_jd(...)`
- `def get_jd_from_url(...)`
- `def get_full_jd_text(...)`

### 步骤 3: 修改 Stage 2
找到 `quick_filter` 通过后的代码块，替换为：
```python
# [Plan C] 创建独立 jd_page
jd_page = new_page(context)

# [Plan C] 使用公共函数获取 JD
jd_text = get_jd_from_url(jd_page, link, platform='<PLATFORM>')
job["description"] = jd_text
jd_page.close()
```

### 步骤 4: 统一字段名
全局替换：
- `job["full_jd"]` → `job["description"]`
- `job["jd_text"]` → `job["description"]`
- `job.get("full_jd"` → `job.get("description"`

### 步骤 5: 更新 Excel 写入
修改 `write_to_excel` 中的字段引用：
```python
ws.cell(row, 9, job.get("description", ""))
```

### 步骤 6: 验证
```bash
python -m py_compile scan_xxx.py
```

---

## 🔧 平台标识速查表

| 平台 | platform 参数 | 特征 |
|------|--------------|------|
| Workday | `'workday'` | URL 含 wd3.myworkdayjobs.com |
| Mokahr | `'mokahr'` | URL 含 app.mokahr.com |
| LinkedIn | `'linkedin'` | linkedin.com/jobs |
| Hays | `'hays'` | hays.com.hk |
| Taleo | `'taleo'` | URL 含 TGnewUI |
| 默认 | `'default'` | 其他平台 |

---

## ⚠️ 常见问题

### 问题 1: IndentationError
**原因**: 正则替换时缩进错误
**解决**: 手动调整缩进，确保 `jd_page` 创建和关闭在同一缩进层级

### 问题 2: 多个 JD 调用
**原因**: 部分扫描器有多个 JD 抓取点
**解决**: 识别所有调用点，逐一替换

### 问题 3: 字段名不一致
**原因**: 不同扫描器使用不同的字段名
**解决**: 全局搜索 `full_jd`, `jd_text`, `full_description` 等变体

---

## 📂 备份位置

所有原始文件已备份至：
```
C:\Users\ClawAdmin\.qclaw\workspace\job-agent\scanners\backups_2026-04-20\
```

---

## 🎯 推荐执行顺序

1. **手动修改关键扫描器**（已验证模板）
   - 参考 scan_sunlife.py 或 scan_kpmg.py

2. **批量修改相同平台**
   - Workday: hkex, fwd, zurich
   - Mokahr: accenture, pwc

3. **逐个验证语法**
   - 使用 `python -m py_compile scan_xxx.py`

4. **测试运行**
   - 选择 1-2 个扫描器进行真实测试

---

*进度更新完成*
