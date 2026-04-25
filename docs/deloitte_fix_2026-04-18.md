# Deloitte 扫描器修复 - 2026-04-18

## 问题

用户发现 deloitte_2026-04-18.json 中 total_raw=78 但 total_matched=78，且所有 78 条记录的 title 都为空字符串，URL 全部相同格式（只有 jobId 不同）。

原因：旧的 API 扫描器使用的 API 端点返回的 JSON 中 title 字段为空（可能是 wecruit 平台 API 结构变化）。

## 分析与修复

### 发现的关键信息

1. **翻页参数**：`currentPage=1, currentPage=2, ...`（用户提供）
2. **职位数据**：直接在页面 body 文本中渲染，格式为：
   ```
   Senior - Assurance & Advisory - Emerging Services - Hong Kong(315778)
   审计及鉴证
   香港
   更新日期：2026-04-15
   ```
3. **78 个职位分 7 页**，每页约 12 个

### 根本 bug

正则表达式中的 `[^\n]+?`（非贪婪匹配）在每个换行符后贪婪到下一个 `(` 字符，导致：
- `title` 组匹配到空字符串（因为 `+?` 非贪婪，最小化到零字符）
- 后续 group 也错位

**修复**：改为 `[^\n]*`（零或多个字符）：
```python
# OLD (broken):  r'(?P<title>[^\n]+?)\s*\(\d{6}\)\s*\n'
# NEW (fixed):   r'(?P<title>[^\n]*)\((\d{6})\)\n'
```

### 最终结果

| 指标 | 结果 |
|------|------|
| 总 raw | 78 |
| matched | 9 |
| 评分 P0 | 2 个 |
| 评分 P1 | 7 个 |

## 技术总结

- **平台**：ehjobs（赛码招聘平台），非 Mokahr
- **解析方式**：Playwright DOM → `page.inner_text('body')` → 正则解析
- **正则**：`r'(?P<title>[^\n]*)\((\d{6})\)\n(?P<category>[^\n]+)\n(?P<location>[^\n]+)\n...'`
