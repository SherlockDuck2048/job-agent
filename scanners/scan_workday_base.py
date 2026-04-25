r"""
Workday Scanner Base Class
统一处理 Workday 站点的分页逻辑
关键: button[aria-label*='next'] 点击 → 等待新职位加载
"""
import sys, os, time
from playwright.sync_api import sync_playwright

class WorkdayScanner:
    """Workday 平台扫描器基类"""

    # 每个子类覆盖这些属性
    NAME = "GenericWorkday"
    BASE_URL = ""
    KEYWORDS = ["AI"]
    LOCATION = "Hong Kong"
    SCROLL_COUNT = 3          # 每次翻页前的滚动次数
    WAIT_MS = 6000            # 首次加载等待 ms
    PAGE_WAIT_S = 2.5         # 每次翻页后等待秒数
    MAX_PAGES = 10            # 最多翻页次数（安全上限）
    NEXT_BTN_SELECTOR = "button[aria-label*='next']"

    def __init__(self):
        self.scored_jobs = []
        self.raw_jobs = []

    # ─── 子类实现 ───────────────────────────────────────────────
    def build_url(self, kw):
        """构建搜索 URL（子类覆盖）"""
        raise NotImplementedError

    def extract_jobs_from_page(self, page):
        """
        从当前页面提取所有职位。
        子类可覆盖自定义选择器。
        返回: [{"title": str, "link": str}, ...]
        """
        seen = set()
        entries = []
        for a in page.query_selector_all("a[href*='/job/']"):
            try:
                href = a.get_attribute("href") or ""
                text = " ".join(a.inner_text().split()).strip()
                if not text or len(text) < 5 or text in seen:
                    continue
                seen.add(text)
                link = href if href.startswith("http") else self.BASE_URL + href
                entries.append({"title": text[:100], "link": link})
            except Exception:
                pass
        return entries

    def get_full_jd(self, page, url):
        """获取完整 JD（子类可覆盖）"""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(3)
            for sel in ["[class*='description']", "[class*='detail']", ".job-detail"]:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if len(text) > 100:
                        return text[:3000]
            return page.inner_text("body")[:3000]
        except Exception:
            return ""

    # ─── 核心分页逻辑 ───────────────────────────────────────────
    def scrape_all_pages(self):
        """
        分页抓取全部职位。
        流程: 加载首页 → 提取 → 翻页 → 提取 → ... → Next禁用或达上限
        返回: [{"title": str, "link": str, "page_num": int}, ...]
        """
        all_entries = []
        first_url = self.build_url(self.KEYWORDS[0])
        print(f"  [WorkdayBase] Entry URL: {first_url}")

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = ctx.new_page()

            try:
                page.goto(first_url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(self.WAIT_MS / 1000)
            except Exception as e:
                print(f"  [!] Load failed: {e}")
                self._safe(page)
                browser.close()
                return []

            for page_num in range(1, self.MAX_PAGES + 1):
                # 滚动加载（首页需要，后续页 Workday 通常已全量）
                for _ in range(self.SCROLL_COUNT):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.0)

                entries = self.extract_jobs_from_page(page)
                new_count = sum(1 for e in entries if e["title"] not in {x["title"] for x in all_entries})
                print(f"  [Page {page_num}] {len(entries)} visible / +{new_count} new → total: {len(all_entries) + new_count}")

                for e in entries:
                    e["page_num"] = page_num
                    if e["title"] not in {x["title"] for x in all_entries}:
                        all_entries.append(e)

                # 检查 Next 按钮状态
                btn = page.query_selector(self.NEXT_BTN_SELECTOR)
                if not btn:
                    print(f"  [Done] No Next button found")
                    break

                disabled = btn.get_attribute("disabled")
                if disabled is not None:
                    print(f"  [Done] Next button disabled (page {page_num})")
                    break

                # 点击下一页
                print(f"  [→] Clicking Next...")
                try:
                    btn.scroll_into_view_if_needed()
                    time.sleep(0.8)
                    btn.click()
                    time.sleep(self.PAGE_WAIT_S)
                except Exception as e:
                    print(f"  [!] Next click failed: {e}")
                    break

                # 防止死循环（URL不变+内容不变）
                prev_titles = {e["title"] for e in all_entries}

            self._safe(page)
            browser.close()

        print(f"  [Total] {len(all_entries)} unique job entries across pages")
        return all_entries

    # ─── 工具 ───────────────────────────────────────────────────
    @staticmethod
    def _safe(page):
        try:
            if page and not page.is_closed():
                page.close()
        except Exception:
            pass

    def save_raw(self, path, jobs):
        import json
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "source": self.NAME,
                "date": self._now(),
                "total_raw": len(jobs),
                "jobs": [{"title": j.get("title"), "link": j.get("link"), "company": self.NAME,
                          "location": self.LOCATION, "keyword": j.get("keyword", ""),
                          "scraped_at": self._now()} for j in jobs]
            }, f, ensure_ascii=False, indent=2)
        print(f"  [RAW] saved {len(jobs)} → {path}")

    @staticmethod
    def _now():
        from datetime import datetime
        return datetime.now().isoformat()
