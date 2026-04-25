"""
Base scanner classes for different strategies
"""
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time
import json
from datetime import datetime
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

class BaseScanner(ABC):
    """Abstract base class for all scanners"""
    
    def __init__(self, keywords: List[str] = None, location: str = "Hong Kong"):
        self.keywords = keywords or ["AI", "machine learning", "data scientist"]
        self.location = location
        self.jobs = []
    
    @abstractmethod
    def scan(self) -> List[Dict]:
        """Execute scan and return job list"""
        pass
    
    def save_results(self, source: str, output_dir: str = "../candidates/raw"):
        """Save scan results to JSON"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{source}_{datetime.now().strftime('%Y-%m-%d')}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "source": source,
                "date": datetime.now().isoformat(),
                "total": len(self.jobs),
                "jobs": self.jobs
            }, f, ensure_ascii=False, indent=2)
        
        print(f"[SAVE] {len(self.jobs)} jobs saved to {filepath}")
        return filepath


class HTTPScanner(BaseScanner):
    """Scanner using HTTP requests + BeautifulSoup"""
    
    def __init__(self, base_url: str, selectors: Dict, keywords: List[str] = None, 
                 location: str = "Hong Kong", headers: Dict = None):
        super().__init__(keywords, location)
        self.base_url = base_url
        self.selectors = selectors
        self.headers = headers or {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a page"""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            print(f"[ERROR] Failed to fetch {url}: {e}")
            return None
    
    def extract_jobs(self, soup: BeautifulSoup, keyword: str) -> List[Dict]:
        """Extract jobs from parsed HTML"""
        jobs = []
        cards = soup.select(self.selectors.get('job_card', '.job-card'))
        
        for card in cards[:20]:  # Limit to 20 per page
            try:
                title_el = card.select_one(self.selectors.get('title', 'h2, h3, .title'))
                title = title_el.get_text(strip=True) if title_el else "Unknown"
                
                company_el = card.select_one(self.selectors.get('company', '.company'))
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                
                location_el = card.select_one(self.selectors.get('location', '.location'))
                loc = location_el.get_text(strip=True) if location_el else self.location
                
                link_el = card.select_one(self.selectors.get('link', 'a[href]'))
                link = link_el['href'] if link_el and link_el.has_attr('href') else ""
                if link and not link.startswith('http'):
                    link = self.base_url.rstrip('/') + '/' + link.lstrip('/')
                
                jobs.append({
                    'title': title,
                    'company': company,
                    'location': loc,
                    'link': link,
                    'keyword': keyword,
                    'source': self.__class__.__name__.replace('Scanner', ''),
                    'scraped_at': datetime.now().isoformat()
                })
            except Exception as e:
                continue
        
        return jobs
    
    def scan(self) -> List[Dict]:
        """Execute HTTP scan"""
        print(f"=== {self.__class__.__name__} (HTTP) ===")
        
        for kw in self.keywords:
            url = self.base_url.format(keyword=kw.replace(' ', '+'))
            print(f"[FETCH] {kw} -> {url[:80]}...")
            
            soup = self.fetch_page(url)
            if soup:
                jobs = self.extract_jobs(soup, kw)
                self.jobs.extend(jobs)
                print(f"  Found {len(jobs)} jobs")
            
            time.sleep(2)  # Be polite
        
        print(f"[DONE] Total: {len(self.jobs)} jobs")
        return self.jobs


class CDPScanner(BaseScanner):
    """Scanner using Playwright CDP"""
    
    def __init__(self, cdp_url: str = "http://localhost:9222", 
                 keywords: List[str] = None, location: str = "Hong Kong"):
        super().__init__(keywords, location)
        self.cdp_url = cdp_url
        self.browser = None
        self.context = None
    
    def init_browser(self):
        """Initialize browser connection"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
        self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
        print(f"[CDP] Connected to {self.cdp_url}")
    
    def close_browser(self):
        """Close browser connection (idempotent, error-safe)"""
        try:
            if self.context:
                try:
                    self.context.close()
                except Exception:
                    pass
                self.context = None
        except Exception:
            pass
        
        try:
            if self.browser:
                try:
                    self.browser.close()
                except Exception:
                    pass
                self.browser = None
        except Exception:
            pass
        
        try:
            if hasattr(self, 'playwright') and self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        
        print("[CDP] Browser closed")
    
    def _safe_close_page(self, page):
        """Safely close a page without raising on already-closed errors"""
        try:
            if page and not page.is_closed():
                page.close()
        except Exception:
            pass
    
    def scroll_page(self, page, times: int = 3):
        """Scroll page to load more content"""
        for _ in range(times):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)
    
    def scan(self) -> List[Dict]:
        """Override in subclass"""
        raise NotImplementedError("Use CDPURLScanner or CDPInputScanner")


class CDPURLScanner(CDPScanner):
    """CDP scanner for URL-based navigation"""
    
    def __init__(self, url_template: str, selectors: Dict, 
                 cdp_url: str = "http://localhost:9222",
                 keywords: List[str] = None, location: str = "Hong Kong",
                 wait_time: int = 3000, scroll_times: int = 3):
        super().__init__(cdp_url, keywords, location)
        self.url_template = url_template
        self.selectors = selectors
        self.wait_time = wait_time
        self.scroll_times = scroll_times
    
    def scan(self) -> List[Dict]:
        """Execute CDP URL scan"""
        print(f"=== {self.__class__.__name__} (CDP URL) ===")
        self.init_browser()
        
        try:
            for kw in self.keywords:
                url = self.url_template.format(keyword=kw.replace(' ', '%20'))
                print(f"[NAVIGATE] {kw}")
                
                page = self.context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(self.wait_time / 1000)
                
                self.scroll_page(page, self.scroll_times)
                
                # Extract jobs
                cards = page.query_selector_all(self.selectors.get('job_card', '[class*="job"]'))
                print(f"  Found {len(cards)} job cards")
                
                for card in cards[:15]:
                    try:
                        job = self.extract_job(card, kw)
                        if job:
                            self.jobs.append(job)
                    except Exception as e:
                        continue
                
                self._safe_close_page(page)
                time.sleep(2)
        
        finally:
            self.close_browser()
        
        print(f"[DONE] Total: {len(self.jobs)} jobs")
        return self.jobs
    
    def extract_job(self, card, keyword: str) -> Optional[Dict]:
        """Extract single job from card element"""
        title_el = card.query_selector(self.selectors.get('title', 'h2, h3, a'))
        if not title_el:
            return None
        
        title = title_el.inner_text().strip()
        
        company_el = card.query_selector(self.selectors.get('company', '.company, [class*="company"]'))
        company = company_el.inner_text().strip() if company_el else "Unknown"
        
        location_el = card.query_selector(self.selectors.get('location', '.location'))
        loc = location_el.inner_text().strip() if location_el else self.location
        
        link_el = card.query_selector(self.selectors.get('link', 'a[href]'))
        link = link_el.get_attribute("href") if link_el else ""
        
        return {
            'title': title,
            'company': company,
            'location': loc,
            'link': link,
            'keyword': keyword,
            'source': self.__class__.__name__.replace('Scanner', ''),
            'scraped_at': datetime.now().isoformat()
        }


class CDPInputScanner(CDPScanner):
    """CDP scanner requiring form input simulation"""
    
    def __init__(self, url: str, actions: List[Dict], selectors: Dict,
                 cdp_url: str = "http://localhost:9222",
                 keywords: List[str] = None, location: str = "Hong Kong"):
        super().__init__(cdp_url, keywords, location)
        self.url = url
        self.actions = actions
        self.selectors = selectors
    
    def scan(self) -> List[Dict]:
        """Execute CDP input scan"""
        print(f"=== {self.__class__.__name__} (CDP Input) ===")
        self.init_browser()
        
        try:
            for kw in self.keywords:
                print(f"[SEARCH] {kw}")
                
                page = self.context.new_page()
                page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                
                # Execute actions
                for action in self.actions:
                    action_type = action.get('type')
                    
                    if action_type == 'fill':
                        selector = action['selector']
                        value = action['value'].format(keyword=kw)
                        page.fill(selector, value)
                    
                    elif action_type == 'press':
                        page.press(action.get('selector', 'body'), action['key'])
                    
                    elif action_type == 'click':
                        page.click(action['selector'])
                    
                    elif action_type == 'wait':
                        time.sleep(action.get('ms', 1000) / 1000)
                
                # Extract jobs
                cards = page.query_selector_all(self.selectors.get('job_card', '[class*="job"]'))
                print(f"  Found {len(cards)} job cards")
                
                for card in cards[:15]:
                    try:
                        title_el = card.query_selector(self.selectors.get('title', 'h2, h3, a'))
                        if title_el:
                            title = title_el.inner_text().strip()
                            self.jobs.append({
                                'title': title,
                                'company': 'Unknown',
                                'location': self.location,
                                'link': '',
                                'keyword': kw,
                                'source': self.__class__.__name__.replace('Scanner', ''),
                                'scraped_at': datetime.now().isoformat()
                            })
                    except:
                        continue
                
                self._safe_close_page(page)
                time.sleep(2)
        
        finally:
            self.close_browser()
        
        print(f"[DONE] Total: {len(self.jobs)} jobs")
        return self.jobs
