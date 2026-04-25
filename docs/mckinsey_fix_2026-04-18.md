# scan_McKinsey.py 重写 - 2026-04-18

## 7 项要求完成情况

| # | 要求 | 状态 |
|---|------|------|
| 1 | 翻页翻到底（状态文字稳定） | ✅ "X Jobs Available" 文字检测 + 稳定 x2 |
| 2 | href 去重 > title 去重 | ✅ seen_hrefs[link_stem] → seen_titles[title_key] |
| 3 | URL 从 scan_strategies.py 读取 | ✅ contextlib.exec() 动态加载 _strategy['url'] |
| 4 | 清理临时调试文件 | ✅ 无调试文件遗留 |
| 5 | 评分逻辑同 scan_kpmg.py | ✅ from cco_scorer import score_job（与 kpmg 一致）|
| 6 | JSON 格式同 zurich_2026-04-13.json | ✅ source/url/date/total_raw/total_matched/jobs[] |
| 7 | 匹配结果保存 HK_AI_Jobs_All.xlsx | ✅ write_to_excel() 参考 scan_ubs.py |

## 技术细节

- **CDP**：优先连接 OpenClaw 浏览器（port 28800），有正常 Chrome 签名
- **Fallback**：无 CDP 时 launch headless（但 McKinsey 会封）
- **Cookie**：自动点击 "Accept All Cookies"
- **职位选择器**：`h2 a[href*="/jobs/"]`（实测 1 个职位）+ 备选 `a[href*="/jobs/"]`
- **地点提取**：从父级 h2 的 innerText 找 `|` 分隔的部分
- **翻页检测**：
  - `(\d+)\s+Job[s]?\s+Available` 正则匹配总职位数
  - 状态文字稳定 x2 停止
  - 无 next button 时尝试 URL 参数翻页 `?page=N`

## 运行结果

- 1 个原始职位（Business Analyst/Junior Associate - Tech & AI）
- 0 个推荐（Entry level 评分器判定不达标）
- JSON 已保存：`candidates/raw/mckinsey_2026-04-18.json`
