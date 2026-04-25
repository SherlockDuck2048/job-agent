"""
McKinsey Scanner - Playwright DOM parsing
URL: https://www.mckinsey.com/careers/search-jobs?q=AI&cities=Hong+Kong+SAR&query=ai
来源: scan_strategies.py 配置
关键行为:
  - SPA (React): 翻页通过点击按钮或 URL 参数
  - 职位列表通过 JS 渲染在 DOM 中
  - 分页状态文字稳定检测翻页停止
"""
import sys, os, json, io, time, re, contextlib
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from job_scanner_base import append_scanner_to_excel
from cco_scorer import score_job

KEYWORDS = ["AI"]
LOCATION = "Hong Kong"

# ── 从 scan_strategies.py 动态读取配置 ──────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_strategies_src = open(os.path.join(SCRIPT_DIR, '..', 'config', 'scan_strategies.py'), encoding='utf-8').read()
_globals = {}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_strategies_src, 'scan_strategies.py', 'exec'), _globals)
_strategy = _globals.get('SCAN_STRATEGIES', {}).get('mckinsey', {})
BASE_URL = _strategy.get(
    'url',
    'https://www.mckinsey.com/careers/search-jobs?q=AI&cities=Hong+Kong+SAR&query=ai'
)
COMPANY = _strategy.get('name', 'McKinsey')

OUTPUT_FILE = os.path.join(SCRIPT_DIR, '..', 'candidates', 'raw',
                            f'mckinsey_{datetime.now().strftime("%Y-%m-%d")}.json')
EXCEL_FILE = os.path.join(SCRIPT_DIR, '..', 'candidates', 'HK_AI_Jobs_All.xlsx')


def _safe_close(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass



def scan_mckinsey():
    print('=== McKinsey Scanner ===')
    print(f'  URL: {BASE_URL}')

    all_jobs = []    # matched jobs
    raw_jobs = []   # all jobs found

    # href / title 去重集合（href 优先）
    seen_hrefs = {}
    seen_titles = {}

    with sync_playwright() as p:
        # 优先使用 OpenClaw 已有的浏览器（端口 28800），有正常 Chrome 签名
        try:
            browser = p.chromium.connect_over_cdp('http://localhost:28800')
            print('  [CDP] Connected to OpenClaw browser (port 28800)')
        except Exception:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-http2',
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36',
                ]
            )
            print('  [CDP] Fallback: launched fresh browser')
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=45000)
        time.sleep(6)

        # 滚动触发懒加载
        for _ in range(6):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(2)

        # ── 分页：状态文字稳定检测翻页停止 ──────────────────────────
        stable_count = 0
        prev_body = ''
        max_pages = 50

        for page_num in range(1, max_pages + 1):
            print(f'\n  Page {page_num}...', end='', flush=True)

            body_text = page.inner_text('body')

            # ── 处理 Cookie 弹窗 ──────────────────────────────────
            try:
                cookie_btn = page.query_selector('button:has-text("Accept All Cookies")')
                if cookie_btn:
                    cookie_btn.click()
                    time.sleep(1)
                    print(' [cookie accepted]', end='', flush=True)
            except Exception:
                pass

            # 收集当前页所有 job 链接
            # McKinsey 真实结构：<h2><link>Job Title</link></h2>
            job_links = page.query_selector_all('h2 a[href*="/jobs/"]')
            if not job_links:
                # 备选：所有包含 /jobs/ 的链接
                job_links = page.query_selector_all('a[href*="/jobs/"]')

            print(f' {len(job_links)} job links', end='', flush=True)

            page_new = 0
            for title_a in job_links:
                try:
                    title = title_a.inner_text().strip()
                    raw_href = title_a.get_attribute('href') or ''

                    if not title or len(title) < 5:
                        continue
                    if 'mailto:' in raw_href[:30]:
                        continue

                    # 完整 URL
                    if raw_href.startswith('/'):
                        link = 'https://www.mckinsey.com' + raw_href
                    elif raw_href.startswith('http'):
                        link = raw_href
                    else:
                        continue

                    # ── href 去重（优先）─────────────────────────────
                    link_stem = link.split('?')[0]
                    if link_stem in seen_hrefs:
                        continue
                    seen_hrefs[link_stem] = True

                    # ── title 去重兜底 ─────────────────────────────
                    title_key = title.lower()
                    if title_key in seen_titles:
                        continue
                    seen_titles[title_key] = True

                    page_new += 1

                    # 从父级 h2 附近找地点信息
                    location = LOCATION
                    try:
                        h2 = title_a.evaluate('el => el.closest("h2")')
                        if h2:
                            h2_text = page.evaluate(
                                '(el) => el.innerText',
                                h2
                            )
                            # 地点通常在 | 分隔的最后部分
                            if '|' in h2_text:
                                loc_parts = h2_text.split('|')
                                for part in reversed(loc_parts):
                                    part = part.strip()
                                    if part and part.lower() not in ['ai', 'ai focus', 'hong kong sar', 'beijing']:
                                        location = part
                                        break
                    except Exception:
                        pass

                    job = {
                        'title': title,
                        'company': COMPANY,
                        'location': location or LOCATION,
                        'link': link,
                        'keyword': KEYWORDS[0],
                        'source': COMPANY,
                        'scraped_at': datetime.now().isoformat(),
                    }
                    raw_jobs.append(job)

                    # ── 评分 ──────────────────────────────────────
                    scored = score_job(job)
                    if scored.get('isRecommended'):
                        all_jobs.append(scored)
                        pri = scored.get('priority', '?')
                        sc = scored.get('score', '?')
                        print(f'\n    [MATCH {len(all_jobs)}] P{pri}/{sc} {title[:60]}')

                except Exception as e:
                    continue

            print(f' | new={page_new} total_href={len(seen_hrefs)}')

            # ── 状态文字稳定检测 ───────────────────────────────────
            if page_new == 0 and body_text == prev_body:
                stable_count += 1
            else:
                stable_count = 0
            prev_body = body_text

            if stable_count >= 2:
                print('  [Stop] Status stable x2 - no more pages')
                break

            # 检测总职位数文字（如 "1 Jobs Available" / "12 Jobs Available"）
            m_total = re.search(r'(\d+)\s+Job[s]?\s+Available', body_text, re.IGNORECASE)
            if m_total:
                total_available = int(m_total.group(1))
                print(f' [{total_available} jobs available total]', end='', flush=True)
                if page_num >= 1 and total_available <= len(seen_hrefs):
                    print('  [Stop] All jobs collected')
                    break

            if page_num >= max_pages:
                print('  [Stop] Max pages reached')
                break

            # ── 翻页 ────────────────────────────────────────────
            # 找下一页按钮
            next_btn = None
            for sel in [
                'button[aria-label*="next"]', 'button[aria-label*="Next"]',
                'a[aria-label*="next"]', 'a[aria-label*="Next"]',
                '[class*="pagination"] button', '[class*="pagination"] a',
                'button[class*="next"]', 'a[class*="next"]',
                '[data-testid*="next"]',
            ]:
                candidates = page.query_selector_all(sel)
                for b in candidates:
                    t = b.inner_text().strip().lower()
                    if any(x in t for x in ['next', '>']):
                        next_btn = b
                        break
                if next_btn:
                    break

            if not next_btn:
                # 尝试 URL 翻页（Hash/Query 参数）
                current_url = page.url
                next_url = None
                # 尝试 ?page=N
                m_page = re.search(r'([?&]page[=:]?)(\d+)', current_url)
                if m_page:
                    next_num = int(m_page.group(2)) + 1
                    next_url = re.sub(r'([?&]page[=:]?)\d+', rf'\g<1>{next_num}', current_url)
                # 尝试 ?p=N
                if not next_url:
                    m_p = re.search(r'([?&]p[=:]?)(\d+)', current_url)
                    if m_p:
                        next_num = int(m_p.group(2)) + 1
                        next_url = re.sub(r'([?&]p[=:]?)\d+', rf'\g<1>{next_num}', current_url)

                if next_url and next_url != current_url:
                    print('  [Next] via URL param', end='', flush=True)
                    _safe_close(page)
                    page = context.new_page()
                    page.goto(next_url, wait_until='domcontentloaded', timeout=45000)
                    time.sleep(6)
                    for _ in range(6):
                        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        time.sleep(1.5)
                    continue
                else:
                    print('  [Stop] No next button / URL')
                    break

            # 检查按钮是否禁用
            disabled = next_btn.get_attribute('disabled')
            ng_disabled = next_btn.get_attribute('ng-disabled')
            aria_disabled = next_btn.get_attribute('aria-disabled')
            if disabled is not None or (ng_disabled and 'true' in ng_disabled.lower()) \
                    or (aria_disabled and 'true' in aria_disabled.lower()):
                print('  [Stop] Next button disabled')
                break

            # 点击翻页
            try:
                next_btn.scroll_into_view_if_needed()
                next_btn.click()
                time.sleep(4)
                for _ in range(4):
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    time.sleep(1.5)
            except Exception as e:
                print(f'  [Stop] Click failed: {str(e)[:50]}')
                break

        _safe_close(page)
        browser.close()

    # ── 保存 JSON ─────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'source': COMPANY,
            'url': BASE_URL,
            'date': datetime.now().isoformat(),
            'total_raw': len(raw_jobs),
            'total_matched': len(all_jobs),
            'jobs': all_jobs,
        }, f, ensure_ascii=False, indent=2)

    print(f'\n[Complete] {len(raw_jobs)} raw / {len(all_jobs)} matched -> {OUTPUT_FILE}')

    if all_jobs:
        append_scanner_to_excel(OUTPUT_FILE)

    return all_jobs


if __name__ == '__main__':
    scan_mckinsey()

