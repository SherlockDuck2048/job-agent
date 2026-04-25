# PRD 更新与迁移记录

> 时间: 2026-04-20 23:35 GMT+8

---

## 任务背景

用户发现 `C:\Users\clawAdmin\.qclaw\workspace\docs\job_agent_PRD_v1.md` 内容已过时，需要：
1. 根据 job-agent 项目当前状态更新内容
2. 将文件移动到正确位置（job-agent/docs/）

---

## 完成的工作

### 1. PRD 内容更新

| 章节 | 变更 |
|------|------|
| **Executive Summary** | 更新统计数据：133 JSON, 1400+ 职位 |
| **System Architecture** | 新增 Plan C/X 到输出层 |
| **Data Statistics** | 更新覆盖范围和职位数量 |
| **Known Issues** | 添加已修复的问题（编码、字段名等） |
| **Plan C** | 从"Enhancement Plans"移到独立章节，标记"已实现" |
| **Plan X** | 从"Enhancement Plans"移到独立章节，标记"已实现" |
| **Future Enhancements** | 移除已实现的 Plan C/X |

### 2. 文件迁移

| 操作 | 路径 |
|------|------|
| ✅ 新建 | `job-agent/docs/job_agent_PRD_v1.md` (18,443 bytes) |
| ✅ 删除 | `.qclaw/workspace/docs/job_agent_PRD_v1.md` (旧位置) |

### 3. 与现有文档的协调

- `job-agent/docs/data-flow.md` — 保留，包含架构图
- `job-agent/docs/job_agent_PRD_v1.md` — PRD 需求文档，互补而非重复

---

## 关键更新点

### Plan C: 已实现 (2026-04-20)

- 公共 JD 抓取函数 `get_jd_from_url(page, url, platform)`
- 支持 Workday/LinkedIn/Mokahr/Hays 等平台选择器链
- 已接入：Manulife, AIA, SunLife, Prudential, AIG

### Plan X: 已实现 (2026-04-20)

- `scanners/seen_jobs.py` — 跨会话去重模块
- `merge_results.py --new-only` — 只输出新岗位
- `candidates/history/seen_jobs.json` — 持久化索引

### 统计数据更新

| 指标 | 旧值 | 新值 |
|------|------|------|
| JSON 文件数 | 102 | 133 |
| 累计职位数 | 1017 | ~1400 |
| Code Frozen 扫描器 | 15 | 31 |
| Plan C/X 实现 | 规划中 | ✅ 已完成 |

---

## 文件位置变更原因

用户提问："这个文件属于 job agent 项目下的文件，是不是放 job agent 下的路径更加合适？"

**回答：是。**

PRD 属于项目级文档，应该放在项目目录下：
- ✅ 正确：`job-agent/docs/job_agent_PRD_v1.md`
- ❌ 错误：`.qclaw/workspace/docs/job_agent_PRD_v1.md`（workspace 是通用工作区，不是项目目录）

---

## 后续建议

1. 定期更新 PRD 统计数据（每月一次）
2. 当 Code Frozen 扫描器增加时，更新第 4 节
3. 新功能实现后，从"Future Enhancements"移到对应章节

---

*记录完成*
