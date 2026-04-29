# Cron Job 标准模板

> 用于确保所有扫描器定时任务的格式一致性

---

## 必填字段

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `id` | UUID 唯一标识 | `c8e80a8f-e66b-44bf-9e83-ece4a2564522` |
| `name` | 任务名称 | `scan_xxx_daily` |
| `enabled` | 是否启用 | `true` |
## schedule 配置建议

| 扫描器级别 | 建议 schedule | 说明 |
|------------|-------------|------|
| S 级（每日） | `0 9 * * *` | 每天 9:00 |
| A 级（每 2 天） | `0 9 * * *` / `0 9 * * 2,4,6` | 每天或一三五行 |
| B 级（每周） | `0 9 * * 0` | 每周日 |

**注意**：优先级的定义见 `scanner_schedule.json`
| `timezone` | 时区 | `Asia/Shanghai` |
| `payload` | 执行命令 | 见下方格式 |
| `delivery` | 推送渠道 | `openclaw-weixin` |
| `accountId` | 机器人账号 | `d3b24a645266-im-bot` |

---

## payload 标准格式

```bash
cd C:\Users\ClawAdmin\.qclaw\workspace\job-agent && python -m scanners.scan_xxx --no-dry-run
```

**注意**：
- 必须使用 `cd ... &&` 方式，确保工作目录正确
- 必须加 `--no-dry-run` 参数，否则只输出测试数据
- `xxx` 为公司名小写（如 `prudential`、`macquarie`、`dbs`）

---

## 完整示例

### Prudential（每天 9:00）

```json
{
  "id": "prudential-daily-uuid",
  "name": "scan_prudential_daily",
  "enabled": true,
  "schedule": "0 9 * * *",
  "timezone": "Asia/Shanghai",
  "payload": "cd C:\\Users\\ClawAdmin\\.qclaw\\workspace\\job-agent && python -m scanners.scan_prudential --no-dry-run",
  "delivery": "openclaw-weixin",
  "accountId": "d3b24a645266-im-bot"
}
```

### Macquarie（每天 9:30）

```json
{
  "id": "macquarie-daily-uuid",
  "name": "scan_macquarie_daily",
  "enabled": true,
  "schedule": "30 9 * * *",
  "timezone": "Asia/Shanghai",
  "payload": "cd C:\\Users\\ClawAdmin\\.qclaw\\workspace\\job-agent && python -m scanners.scan_macquarie --no-dry-run",
  "delivery": "openclaw-weixin",
  "accountId": "d3b24a645266-im-bot"
}
```

### DBS（每天 10:00）

```json
{
  "id": "dbs-daily-uuid",
  "name": "scan_dbs_daily",
  "enabled": true,
  "schedule": "0 10 * * *",
  "timezone": "Asia/Shanghai",
  "payload": "cd C:\\Users\\ClawAdmin\\.qclaw\\workspace\\job-agent && python -m scanners.scan_dbs --no-dry-run",
  "delivery": "openclaw-weixin",
  "accountId": "d3b24a645266-im-bot"
}
```

---

## 新增任务检查清单

- [ ] UUID 使用 Python 生成：`python -c "import uuid; print(uuid.uuid4())"`
- [ ] name 格式：`scan_xxx_daily`
- [ ] schedule：参考现有任务的分钟数，避免撞车
- [ ] payload：替换 `xxx` 为公司名
- [ ] accountId：统一使用 `d3b24a645266-im-bot`
- [ ] delivery：统一使用 `openclaw-weixin`
- [ ] 测试运行：`python -m scanners.scan_xxx --no-dry-run`