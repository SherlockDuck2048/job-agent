# -*- coding: utf-8 -*-
"""
AIG Scanner - Workday 单页（20职位）
URL: https://aig.wd1.myworkdayjobs.com/zh-CN/aig?q=AI (从 scan_strategies 读取)
结构: 两阶段 - Stage 1 收集链接 / Stage 2 批量获取 JD 并评分
遵循: (1) href 去重  (2) URL slug + 标题合并过滤  (3) dry-run 对比总数
"""
import sys, os, json, time, re, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.scan_strategies import SCAN_STRATEGIES
from cco_scorer import CCOSCORER, score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, update_job_entry, save_seen_jobs

NAME = "AIG"
AIG_URL = SCAN_STRATEGIES["aig"]["base_url"]
LOCATION = "Hong Kong"
KEYWORDS = ["AI"]
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "config",
                         f"HK_AI_Jobs_{datetime.now().strftime('%Y-%m-%d')}.xlsx")


def _safe(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass



def get_jd(jd_page, url):
    try:
        jd_page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(3)
        for sel in ["[data-automation-id='jobDescription']",
                    "[class*='description']", "[class*='detail']"]:
            try:
                el = jd_page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if len(text) > 100:
                        return text[:3000]
            except Exception:
                pass
        body = jd_page.evaluate("document.body.innerText")
        return body[:3000] if body else ""
    except Exception:
        return ""


def _title_for_filter(href: str, title: str) -> str:
    """合并标题 + URL slug，作为 quick_filter 的输入"""
    slug = href.split("/job/")[-1].split("?")[0] if "/job/" in href else ""
    slug_clean = slug.replace("-", " ").replace("_", " ")
    return f"{title} {slug_clean}".strip()[:200]


def scan_aig():
    print("=== AIG Scanner (Workday) ===")
    scorer = CCOSCORER()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        print(f"  [Stage 1] URL: {AIG_URL}")

        try:
            page.goto(AIG_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(7)
        except Exception as e:
            print(f"  [!] Load failed: {e}")
            _safe(page); browser.close(); return []

        # 等待 Workday 动态渲染
        try:
            page.wait_for_selector("a[href*='/job/']", timeout=15000)
        except Exception:
            print("  [!] No job links found on page")
            _safe(page); browser.close(); return []

        # 密集滚动触发懒加载
        for _ in range(4):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.0)

        # -- Stage 1: 收集所有唯一链接（JR 号去重）--
        seen_jrs = set()
        all_entries = []

        for a in page.query_selector_all("a[href*='/job/']"):
            try:
                href = a.get_attribute("href") or ""
                if not href:
                    continue

                # JR 号去重（key）
                m = re.search(r'JR\d+', href)
                jr = m.group(0) if m else href.split('/')[-1].split('?')[0]
                if jr in seen_jrs:
                    continue
                seen_jrs.add(jr)

                text = " ".join(a.inner_text().split()).strip()
                slug = href.split("/job/")[-1].split("?")[0] if "/job/" in href else ""
                slug_clean = slug.replace("-", " ").replace("_", " ")
                title_for_filter = f"{text} {slug_clean}".strip()[:200]

                if not text or len(text) < 3:
                    continue

                link = href if href.startswith("http") else \
                    "https://aig.wd1.myworkdayjobs.com" + href

                all_entries.append({
                    "jr": jr,
                    "title": text[:100],
                    "title_for_filter": title_for_filter,
                    "link": link,
                })
            except Exception:
                pass

        print(f"\n  [Stage 1 Done] {len(all_entries)} unique jobs")
        print(f"  [DRY-RUN] 网站显示总数应为 20，当前收集 {len(all_entries)}")
        _safe(page)

        # -- Stage 2: 批量获取 JD + 评分 --
        all_matched = []
        raw_jobs = []

        # [Plan X] 加载去重索引
        seen_data = load_seen_jobs()
        new_matched = []

        try:
            for i, job_data in enumerate(all_entries, 1):
                title = job_data["title"]
                link = job_data["link"]
                title_for_filter = job_data["title_for_filter"]

                # 从 URL slug 提取地点（如 Hong-Kong, Shanghai, Guangzhou）
                slug = link.split("/job/")[-1].split("?")[0]
                slug_parts = [p for p in slug.split("/") if p]
                location = slug_parts[0].replace("-", " ") if slug_parts else LOCATION

                job = {
                    "title": title,
                    "company": NAME,
                    "location": location,
                    "link": link,
                    "keyword": "AI",
                    "source": NAME,
                    "scraped_at": datetime.now().isoformat(),
                    "_title_for_filter": title_for_filter,
                }
                raw_jobs.append(job)

                fr = scorer.quick_filter(job)
                if not fr["passed"]:
                    print(f"  [{i}/{len(all_entries)} FILTER] {title_for_filter[:50]} - {fr['reason']}")
                    continue
                print(f"  [{i}/{len(all_entries)} PASS] {title_for_filter[:55]}")

                # [Plan C] Using common JD fetch function
                jd_pg = ctx.new_page()
                try:
                    jd_text = get_jd_from_url(jd_pg, link, platform="workday")
                    job["description"] = jd_text
                    if jd_text:
                        print(f"    [JD] {len(jd_text)} chars")
                finally:
                    jd_pg.close()

                scored = score_job(job)
                if scored.get("isRecommended"):
                    # [Plan X] 去重检查
                    link_key = scored.get("link", "")
                    title_hash = hash(scored.get("title", "").lower().strip())
                    is_new = True
                    status = "new"
                    if link_key in seen_data.get("jobs", {}):
                        prev = seen_data["jobs"][link_key]
                        if prev.get("title_hash") == title_hash:
                            is_new = False
                            status = "unchanged"
                        else:
                            status = "updated"
                    if is_new:
                        update_job_entry(link_key, scored.get("title", ""), NAME, scored.get("description", ""), seen_data, status)
                        new_matched.append(scored)
                        print(f"  [MATCH! {status.upper()}] {title[:55]} -> P{scored.get('priority')} {scored.get('score')}")
                    else:
                        print(f"  [MATCH! UNCHANGED] {title[:55]} -> P{scored.get('priority')} {scored.get('score')}")
                else:
                    print(f"  [SKIP ] {title[:55]} (P{scored.get('priority')} {scored.get('score')})")
        finally:
            browser.close()

    # [Plan X] 保存去重索引
    save_seen_jobs(seen_data)
    all_matched = new_matched

    # 最终去重（按 link）
    seen_links = set()
    unique = [j for j in all_matched
              if j.get("link") not in seen_links and not seen_links.add(j.get("link"))]
    all_matched = unique

    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = os.path.join(RAW_DIR, f"aig_raw_{today}.json")
    out_file = os.path.join(RAW_DIR, f"aig_{today}.json")
    os.makedirs(RAW_DIR, exist_ok=True)

    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump({"source": NAME, "date": datetime.now().isoformat(),
                   "total_raw": len(raw_jobs), "jobs": raw_jobs},
                  f, ensure_ascii=False, indent=2)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"source": NAME, "date": datetime.now().isoformat(),
                   "total_found": len(all_matched), "jobs": all_matched},
                  f, ensure_ascii=False, indent=2)

    print(f"\n[RAW] {len(raw_jobs)} | [MATCHED] {len(all_matched)}")
    if all_matched:
        append_scanner_to_excel(out_file)
    return all_matched


if __name__ == "__main__":
    scan_aig()


