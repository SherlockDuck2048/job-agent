# -*- coding: utf-8 -*-
"""
Zurich Insurance Scanner
URL: https://www.careers.zurich.com/search/?q=AI&locationsearch=hong+kong
从 scan_strategies.py 动态读取配置。
Plan C: JD 抓取 (get_jd_from_url)
Plan X: 跨会话去重 (seen_jobs)
Excel: append_scanner_to_excel
"""
import sys, os, json, time, io
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote
from playwright.sync_api import sync_playwright

# UTF-8 wrapper
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cco_scorer import score_job
from job_scanner_base import get_jd_from_url, new_page, append_scanner_to_excel
from seen_jobs import load_seen_jobs, update_job_entry, save_seen_jobs

NAME = "Zurich"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")


def load_strategies():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "scan_strategies.py")
    with open(cfg_path, "r", encoding="utf-8") as f:
        content = f.read()
    ns = {}
    exec(content, ns)
    strategies = ns.get("SCAN_STRATEGIES", {})
    return strategies.get("zurich", None)


def _extract_title_from_slug(slug):
    """从 URL slug 提取职位名。"""
    slug = slug.rstrip("/").split("/")[-1]
    slug = unquote(slug)
    parts = slug.split("-")
    title = " ".join(p for p in parts if p and not p.isdigit())
    return title


def run():
    strat = load_strategies()
    if not strat:
        print("zurich not found in scan_strategies.py")
        return []

    name = strat["name"]
    base_url = strat["url"]

    parsed = urlparse(base_url)
    params = parse_qs(parsed.query)
    base_params = {k: v[0] for k, v in params.items() if k != "pg"}
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    keyword = "AI"
    base_params["q"] = keyword

    def make_url(page_num):
        q = "&".join(f"{k}={v}" for k, v in {**base_params, "pg": str(page_num)}.items())
        return f"{base_path}?{q}"

    print(f"=== {name} Scanner ===")
    print(f"  Base URL: {base_url}")

    all_entries = []  # Stage 1 收集的所有职位
    seen_hrefs = set()
    seen_titles = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        page_number = 1
        prev_status_text = ""
        stable_count = 0
        max_pages = 20

        while page_number <= max_pages:
            url = make_url(page_number)
            print(f"\n  --- Page {page_number} ---")

            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(5)
            except Exception as e:
                print(f"  ! Load failed: {e}")
                break

            # 关闭 Cookie 弹窗
            for sel in [
                "#onetrust-accept-btn-handler",
                "[id*='cookie'] button",
                "button[class*='accept']",
            ]:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        time.sleep(1)
                        break
                except:
                    pass

            time.sleep(2)

            # 滚动触发懒加载
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(0.5)

            # 职位卡片：/job/ 链接
            raw_links = page.query_selector_all("a[href*='/job/']")
            print(f"  Links found: {len(raw_links)}")

            # 状态文字
            body_text = page.inner_text("body")
            status_text = ""
            for line in body_text.split("\n"):
                line = line.strip()
                if any(k in line.lower() for k in ["result", "page 1 of", "found"]):
                    status_text = line
                    break
            print(f"  Status: {status_text}")

            if status_text == prev_status_text and page_number > 1:
                stable_count += 1
                print(f"  Status stable x{stable_count}")
                if stable_count >= 2:
                    print("  [STOP] Status stable 2x -- last page")
                    break
            else:
                stable_count = 0
            prev_status_text = status_text

            if len(raw_links) == 0 and page_number > 1:
                print("  [STOP] No links on this page")
                break

            # 收集本页职位（仅 href 去重，不评分）
            hrefs_this_page = set()
            for link_el in raw_links:
                try:
                    href = link_el.get_attribute("href") or ""
                    if not href or "/search" in href:
                        continue
                    href = href.split("?")[0].rstrip("/")

                    if href in hrefs_this_page:
                        continue
                    hrefs_this_page.add(href)

                    title = link_el.inner_text().strip()
                    if not title or len(title) < 5:
                        title = _extract_title_from_slug(href)

                    if not title:
                        continue

                    # 跨页去重
                    if href in seen_hrefs:
                        print(f"    [DUP href] {title[:60]}")
                        continue
                    seen_hrefs.add(href)

                    title_lower = title.lower()
                    if title_lower in seen_titles:
                        print(f"    [DUP title] {title[:60]}")
                        continue
                    seen_titles.add(title_lower)

                    full_link = href if href.startswith("http") else f"https://www.careers.zurich.com{href}"

                    all_entries.append({
                        "title": title,
                        "company": name,
                        "location": "Hong Kong",
                        "link": full_link,
                        "source": name,
                        "keyword": keyword,
                    })

                except Exception as e:
                    print(f"    ! Link error: {e}")
                    continue

            print(f"  Page {page_number}: collected {len(hrefs_this_page)}, total raw={len(seen_hrefs)}")
            page_number += 1

        # ── Stage 2: Plan C (JD) + Plan X (去重) + 评分 ──
        print(f"\n=== Stage 2: {len(all_entries)} jobs → Plan C + Plan X + Scoring ===")

        # [Plan X] 加载去重索引
        seen_data = load_seen_jobs()
        all_matched = []

        jd_page = context.new_page()
        try:
            for i, job in enumerate(all_entries, 1):
                title = job["title"]
                link = job["link"]

                # quick_filter
                scored = score_job(job)
                if not scored.get("isRecommended"):
                    print(f"  [{i}/{len(all_entries)} SKIP] {title[:55]} ({scored.get('score')})")
                    continue

                # [Plan C] 获取 JD
                jd_text = ""
                try:
                    jd_text = get_jd_from_url(jd_page, link, platform="default")
                    job["description"] = jd_text
                    if jd_text:
                        print(f"  [{i}/{len(all_entries)} JD] {len(jd_text)} chars")
                except Exception as e:
                    print(f"  [{i}/{len(all_entries)} JD-ERR] {str(e)[:50]}")

                # 重新评分（含 JD）
                scored = score_job(job)
                if not scored.get("isRecommended"):
                    print(f"  [{i}/{len(all_entries)} SKIP-after-JD] {title[:55]} ({scored.get('score')})")
                    continue

                # [Plan X] 去重检查
                link_key = scored.get("link", link)
                from seen_jobs import check_job_status
                status = check_job_status(link_key, scored.get("title", title), seen_data)

                if status == "unchanged":
                    print(f"  [{i}/{len(all_entries)} UNCHANGED] {title[:55]} P{scored.get('priority')} {scored.get('score')}")
                    continue

                update_job_entry(link_key, scored.get("title", title), NAME,
                                 scored.get("description", jd_text), seen_data, status)
                all_matched.append(scored)
                print(f"  [{i}/{len(all_entries)} MATCH! {status.upper()}] {title[:55]} P{scored.get('priority')} {scored.get('score')}")
        finally:
            jd_page.close()
            browser.close()

    # [Plan X] 保存去重索引
    save_seen_jobs(seen_data)

    # 保存 JSON
    out_dir = os.path.join(os.path.dirname(__file__), "..", "candidates", "raw")
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = os.path.join(out_dir, f"zurich_{today}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "source": name,
            "url": base_url,
            "date": datetime.now().isoformat(),
            "total_raw": len(seen_hrefs),
            "total_matched": len(all_matched),
            "jobs": all_matched,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[COMPLETE] raw={len(seen_hrefs)} matched={len(all_matched)} -> {out_file}")

    # Excel 追加
    if all_matched:
        append_scanner_to_excel(out_file)

    return all_matched


if __name__ == "__main__":
    run()
