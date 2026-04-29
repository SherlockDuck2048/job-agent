# Scanner Status Tracker

> Last updated: 2026-04-13 18:50

## ⚠️ 重要更新 (2026-04-10)
**所有扫描器 URL 已全面更新！**
旧版 `scan_strategies.py` 中的部分 URL 是 AI 通过搜索+推理自行生成的，**与用户提供的一致 URL 不符**。
已替换为用户提供的 **67 个验证过的真实 URL**，详见 `config/scan_strategies.py`。

**重点修复：**
- HSBC: `portal.careers.hsbc.com` (旧: `mycareer.hsbc.com`)
- Citi: `search-jobs/AI/Hong+Kong+SAR/287/...` (旧: `search-jobs?k=AI&l=Hong+Kong`)
- AIA/Manulife/Prudential/AIG/Sunlife/OCBC/CNCBI: 添加了 `locationCountry` 参数

---

## Status Legend
| Symbol | Meaning |
|--------|---------|
| ✅ | Code Frozen — 已跑通、数据验证通过 |
| 🔧 | Active — 正在调试 |
| ⚠️ | Re-validate — 需重新测试（新URL替换后） |
| ❓ | Unknown — 尚未测试 |
| ⏭️ | Skip — 反爬/无页面/手动处理 |
| 🔲 | Pending — 等待测试 |

---

## Tier S — Daily (24h)
| Scanner | Status | Last Run | Notes |
|---------|--------|----------|-------|
| linkedin | ✅ | 2026-04-14 | 70职位，6匹配(P0×1/P1×2/P2×3)；href去重翻页；URL动态读取；安全编码打印 ✅ |
| indeed | ⚠️ | 2026-04-08 | 用户URL含cf-turnstile参数，需手动处理Cookie |
| jobsdb | ⏭️ | — | Cloudflare反爬，Skip |

## Tier A — Every 2 Days (48h)
| Scanner | Status | Last Run | Notes |
|---------|--------|----------|-------|
| jpmorgan | ✅ | 2026-04-08 | Code Frozen |
| aia | ✅ | 2026-04-11 | 7页=113职位，3匹配(P1×3)，分页✅ |
| hsbc | ⚠️ | 2026-04-09 | ✅ 新URL已更新，需重新测试 |
| hays | ✅ | 2026-04-09 | Code Frozen |
| michaelpage | ⏭️ | — | 需登录，Skip |
| manulife | ⚠️ | 2026-04-08 | ✅ 新URL已更新，需重新测试 |
| randstad | ✅ | 2026-04-09 | Code Frozen |

## Tier B — Every 2 Days (48h)
| Scanner | Status | Last Run | Notes |
|---------|--------|----------|-------|
| citi | ⚠️ | 2026-04-08 | ✅ 新URL已更新（Hong Kong SAR路径），需重新测试 |
| sc (Standard Chartered) | ⚠️ | 2026-04-08 | 用户URL已更新，需重新测试 |
| ubs | ✅ | 2026-04-13 | Code Frozen -- 51 raw / 2 matched (P1×2: Global Banking IB Analyst HK 75, IB Analyst Canada 75)，keyword通过JS hash设置，li.job选择器，location=first .position3，单页无需分页 |
| accenture | ✅ | 2026-04-27 | Code Frozen + Plan C + Plan X + Excel ✅ — 12 raw / 4 matched (P0×2: BA Lead/BA Assoc., P1×2: Data Analyst/Consultant, Consulting Manager)；cron `scan_accenture_daily` 每天 14:45 |
| deloitte | ❓ | — | 用户URL已提供，待测试 |
| ey | ❓ | — | Mokahr平台，待测试 |
| kpmg | ❓ | — | Mokahr平台，待测试 |
| pwc | ⏭️ | — | 无公开搜索页，用户手动 |
| mckinsey | ❓ | — | 用户URL已提供，待测试 |
| goldman | ❓ | — | 用户URL已提供，待测试 |
| macquarie | ❓ | — | 用户URL已提供，待测试 |

## Tier C — Weekly / Optional
| Scanner | Status | Notes |
|---------|--------|-------|
| aig | ❓ | ✅ 新URL已更新（locationCountry），待测试 |
| prudential | ❓ | ✅ 新URL已更新，待测试 |
| axa | ✅ | 2026-04-13 | Code Frozen -- 11 raw / 0 matched (9 jobs score 70 P2: Chief AI Officer/AI Learning/AI Portfolio Mgr; threshold P1>=80, AXA jobs rated P2 by scorer, correct) |
| fwd | ❓ | 用户URL已提供，待测试 |
| sunlife | ✅ | 2026-04-11 | 3页=38职位，3匹配(P0×1/P1×2)，分页✅ |
| zurich | DONE | 2026-04-13 | Code Frozen -- 4 raw / 1 matched (P1: Manager/Asst Manager Distribution Management & Transformation 75) |
| bochk | ✅ | 2026-04-13 | Code Frozen — 15 raw / 3 matched (P0: Sr Wealth Mgmt Product Manager 100 / P1×2: Tech Risk Mgr AI 80, Credit Risk Mgr LLM 80)，单页无需翻页，href去重✅ |
| microsoft | ❓ | ✅ 新URL已更新（apply.careers.microsoft.com），待测试 |
| ibm | ✅ | 2026-04-10 Code Frozen |
| pccw | ✅ | 2026-04-13 | Code Frozen -- 19 raw / 3 matched (P0: Project Manager 100 / P1: Senior Data Analytics Manager 85, Data Analyst 85)，无需翻页，href去重✅ |
| hkt | ✅ | 2026-04-13 | 与 pccw 同系统（同一 Taleo CMS），已合并 |
| hkex | ✅ | 2026-04-11 | 2页=20职位，0匹配(纯IT/工程岗非目标)，分页✅ |
| hkjc | ❓ | 用户URL已提供，待测试 |
| hkairport | ❓ | 用户URL已提供，待测试 |
| clp | ❓ | 用户URL已提供（Oracle HCM），待测试 |
| cathay | ❓ | 用户URL已提供，待测试 |
| swire | ❓ | ✅ 新URL已更新，待测试 |
| ocbc | ❓ | ✅ 新URL已更新（Workday），待测试 |
| cncbi | ❓ | ✅ 新URL已更新（Workday），待测试 |
| bea | ❓ | 用户URL已提供，待测试 |
| bnp | ❓ | 用户URL已提供，待测试 |
| classywheeler | ❓ | 用户URL已提供，待测试 |
| ambition | ❓ | 用户URL已提供，待测试 |
| seamatch | ❓ | 用户URL已提供，待测试 |
| ConnectedGroup | ❓ | 用户URL已提供，待测试 |
| Captar Partners | ❓ | 用户URL已提供，待测试 |
| persol | ❓ | 用户URL已提供，待测试 |
| dahsing | ❓ | Taleo系统，待测试 |

## Skipped (Manual / Anti-Bot)
| Scanner | Reason |
|---------|--------|
| jobsdb | Cloudflare反爬，无法绕过 |
| michaelpage | 需登录注册才能查看职位列表 |
| robertwalters | PerimeterX反爬，Skip |
| dbs | Job Application Portal升级中 |
| hkelectric | 无公开搜索页，需手动 |
| shkp | 无公开搜索页，需手动 |
| zabank | 无公开搜索页，需手动 |
| fubonbank | 无公开搜索页，需手动 |
| icbcasia | 无公开搜索页，需手动 |
| ccbasia | 无公开搜索页，需手动 |
| cmbi | 无公开搜索页，需手动 |
| haitong | 无公开搜索页，需手动 |
| cicc | 无公开搜索页，需手动 |
| crcapital | 无公开搜索页，需手动 |
| smartcare | 无公开招聘页面 |
| aedas | 无公开招聘页面 |

---

## Code Freeze Checklist
- [x] jpmorgan (2026-04-08)
- [x] hays (2026-04-09)
- [x] randstad (2026-04-09)
- [x] ibm (2026-04-10)
- [ ] linkedin
- [ ] indeed
- [ ] jobsdb
- [ ] aia (⚠️ 新URL待重测)
- [ ] hsbc (⚠️ 新URL待重测)
- [ ] michaelpage
- [ ] manulife (⚠️ 新URL待重测)
- [ ] citi (⚠️ 新URL待重测)
- [ ] sc
- [x] ubs (2026-04-13)
- [x] accenture (2026-04-13)
- [ ] deloitte
- [ ] ey
- [ ] kpmg
- [ ] pwc
- [ ] mckinsey
- [ ] gs
- [ ] macquarie
- [ ] aig
- [ ] prudential
- [x] axa (2026-04-13)
- [ ] fwd
- [ ] sunlife
- [x] bochk (2026-04-13)
- [x] zurich (2026-04-13)
- [ ] microsoft
- [x] pccw
- [x] hkt
- [ ] hkex
- [ ] hkjc
- [ ] hkairport
- [ ] clp
- [ ] cathay
- [ ] swire
- [ ] ocbc
- [ ] cncbi
- [ ] bea
- [ ] bnp
- [ ] ambition
- [ ] seamatch
- [ ] ConnectedGroup
- [ ] Captar Partners
- [ ] persol
- [ ] dahsing
- [ ] classywheeler

---

## JSON Data Summary (as of 2026-04-10)
| Platform | Best JSON | Notes |
|---------|-----------|-------|
| jpmorgan | jpmorgan_raw_2026-04-08.json | ✅ Code Frozen |
| aia | aia_raw_2026-04-09.json | ⚠️ 旧URL数据，新URL需重测 |
| hsbc | hsbc_raw_2026-04-09.json | ⚠️ 旧URL数据，新URL需重测 |
| hays | hays_2026-04-09.json | ✅ Code Frozen |
| randstad | randstad_2026-04-09.json | ✅ Code Frozen |
| ibm | ibm_2026-04-09.json | ✅ Code Frozen |
| citi | citi_2026-04-08.json | ⚠️ 旧URL数据，新URL需重测 |
| manulife | manulife_2026-04-08.json | ⚠️ 旧URL数据，新URL需重测 |
| sc | sc_2026-04-16.json | ✅ Code Frozen — 0 matched（2 raw，低于阈值70）|
| ccb | ccb_2026-04-16.json | ✅ Code Frozen — 1 matched PP1 (75) |

---

## Next Actions
1. [ ] 重测 hsbc（portal.careers.hsbc.com）
2. [ ] 重测 aia（新Workday URL + locationCountry）
3. [ ] 重测 citi（Hong Kong SAR /287 路径）
4. [ ] 测试 UBS, Manulife（新URL）
5. [ ] 批量测试其余 30+ 扫描器（按优先级）
6. [ ] 合并所有新JSON到 HK_AI_Jobs_All.xlsx

