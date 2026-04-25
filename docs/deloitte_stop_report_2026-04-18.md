# Deloitte 扫描停止报告 & 反思总结

**时间**: 2026-04-18  
**决策**: 立即停止 Deloitte 扫描，标记为 skip  
**原因**: API 返回数据异常，78 条记录全部重复同一 URL 格式，title 字段为空

---

## 问题现象

用户检查 `deloitte_2026-04-18.json` 发现：

```json
{
  "total_raw": 78,
  "total_matched": 78,
  "jobs": [
    {"title": "", "link": "https://ehjobs.deloitte.com.cn/...&jobId=69d625e1f5c9e12bf332b013"},
    {"title": "", "link": "https://ehjobs.deloitte.com.cn/...&jobId=69c20eaef5c9e12bf3328ceb"},
    ...
  ]
}
```

**核心问题**:
1. `title` 字段全部为空字符串
2. 所有记录的 URL 格式完全相同（只有 jobId 不同）
3. `total_matched` = `total_raw` = 78，说明评分逻辑被绕过或全部通过
4. 结果完全不可用

---

## 根本原因分析

### 1. API 响应结构变化

当前扫描器使用 `_fetch_page()` 函数调用 Deloitte 的 API：

```python
API_URL = "https://ehjobs.deloitte.com.cn/wecruit/positionInfo/listPosition/SU649e304a6a9f0ef690533e9a"
```

API 返回的数据结构可能已变化：
- 之前: `data["data"]["pageForm"]["pageData"]` 包含 `nameCh` 字段
- 现在: 可能字段名变化或数据为空，导致 `j.get("nameCh", "")` 返回空字符串

### 2. 评分逻辑缺陷

`score_job()` 函数接收到的 job dict 中 `title` 为空，但：
- 可能评分逻辑没有正确处理空 title 的情况
- 或者空 title 恰好通过了某些关键词匹配（unlikely）
- 更可能是评分结果被强制通过或逻辑有漏洞

### 3. 数据验证缺失

扫描器没有验证提取的数据质量：
- 没有检查 `title` 是否为空
- 没有检查 `link` 是否合理
- 没有验证 `total_matched` 与预期是否一致

---

## 为什么花费大量 Token 仍未解决

### 时间线回顾

| 日期 | 事件 |
|------|------|
| 2026-04-10 | KPMG Mokahr 扫描器成功，以为 Mokahr 平台模式已掌握 |
| 2026-04-17 | Deloitte 扫描器"完成"，标记 Code Frozen |
| 2026-04-18 | 用户检查发现数据异常，发现问题 |

### 根本问题

1. **过度自信于"模式复用"**
   - KPMG 也是 Mokahr 平台，Deloitte 也是 Mokahr 平台
   - 以为同样的方法可以复用，没有意识到 Deloitte 可能有不同的 API 结构

2. **缺乏数据验证环节**
   - Code Freeze 前没有人工抽查 JSON 输出
   - 没有自动化验证（如检查空 title 率、URL 重复率）

3. **调试迭代成本高**
   - 每次修改都需要完整运行扫描器（Playwright 启动、页面加载、API 调用）
   - 每次运行消耗大量 Token（浏览器自动化、代码分析、多次迭代）

4. **问题定位困难**
   - API 返回 200，有数据，看起来"正常"
   - 但数据内容异常（空 title），需要仔细检查才能发现
   - 没有日志记录原始 API 响应，难以诊断

---

## 已采取的措施

1. ✅ **立即停止扫描**: 在 `scan_strategies.py` 中将 Deloitte 标记为 `skip`
2. ✅ **更新 HEARTBEAT.md**: 将状态从 "Code Frozen" 改为 "STOPPED"
3. ✅ **保留历史文件**: 保留 `deloitte_2026-04-18.json` 作为问题记录

---

## 经验教训

### 对于 QClaw

1. **Code Freeze 前必须验证数据质量**
   - 不能只看"有输出"，要看"输出是否正确"
   - 必须抽查 JSON 中的具体字段（title、link、company 等）

2. **不要假设平台相同 = 实现相同**
   - 即使是同一平台（Mokahr），不同公司的配置可能不同
   - 必须针对每个站点单独验证

3. **增加数据验证层**
   - 扫描器应该自动检查：空字段率、URL 格式、重复率
   - 异常数据应该报错，而不是静默通过

4. **控制调试成本**
   - 复杂站点的调试应该设定 Token 预算上限
   - 超过预算仍未解决，应该暂停并寻求替代方案

### 对于用户

1. **Code Freeze 需要用户验证**
   - 用户应该抽查 JSON 输出，确认数据质量
   - 不要信任"Code Frozen"标签本身

2. **设定止损点**
   - 对于难以解决的站点，应该及时跳过
   - 不要追求完美覆盖，优先保证数据质量

---

## 后续建议

1. **Deloitte 处理方案**
   - 当前: 跳过，手动浏览 https://ehjobs.deloitte.com.cn/
   - 未来: 如有需要，重新设计扫描器，增加数据验证

2. **其他 Mokahr 站点检查**
   - 检查 KPMG、EY 等其他 Mokahr 站点的输出是否正常
   - 验证 title 字段是否为空

3. **增加自动化验证**
   - 在扫描器基类中增加 `validate_output()` 方法
   - 检查空字段率 > 10% 时自动报错

---

**结论**: Deloitte 扫描器因 API 数据异常已停止。这是一个典型的"看起来工作但实际异常"案例，暴露了数据验证缺失的问题。未来应该增加自动验证层，避免类似问题。
