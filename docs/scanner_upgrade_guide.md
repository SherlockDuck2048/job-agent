# 扫描器升级指南 - Plan C + Plan X 整合

## 修改要点

### 1. 导入部分
```python
# 添加这一行（在 from cco_scorer import 之后）
from job_scanner_base import get_jd_from_url, new_page
```

### 2. 删除本地 JD 函数
删除以下函数（如果存在）：
- `def get_jd(...)`
- `def get_full_jd(...)`
- `def get_jd_from_url(...)`
- `def get_full_jd_text(...)`

### 3. Stage 2 修改

**原始代码：**
```python
jd_page = ctx.new_page()  # 或类似
full_jd = get_jd(jd_page, link)
job["full_jd"] = full_jd
```

**修改后：**
```python
# [Plan C] 创建独立 jd_page
jd_page = new_page(context)
# [Plan C] 使用公共函数获取 JD
jd_text = get_jd_from_url(jd_page, link, platform='<PLATFORM>')
job["description"] = jd_text
jd_page.close()
```

### 4. 字段名统一

**原始代码：**
```python
job["full_jd"] = ...
job["jd_text"] = ...
```

**修改后：**
```python
job["description"] = ...
```

### 5. write_to_excel 修改

**原始代码：**
```python
ws.cell(row, 9, job.get("full_jd", ""))
```

**修改后：**
```python
ws.cell(row, 9, job.get("description", ""))
```

## 平台标识

| 平台 | platform 参数 | 示例扫描器 |
|------|--------------|-----------|
| Workday | `'workday'` | AIA, SunLife, Manulife, Prudential |
| Mokahr | `'mokahr'` | KPMG, EY, Accenture, PwC |
| LinkedIn | `'linkedin'` | LinkedIn |
| Hays | `'hays'` | Hays |
| Taleo | `'taleo'` | UBS |
| 默认 | `'default'` | HSBC, JPMorgan, Citi |

## 完整示例（scan_sunlife.py）

见：`C:\Users\ClawAdmin\.qclaw\workspace\job-agent\scanners\scan_sunlife.py`

## 验证命令

```bash
# 语法检查
python -m py_compile scan_xxx.py

# 试运行（不写入）
python scan_xxx.py --dry-run
```
