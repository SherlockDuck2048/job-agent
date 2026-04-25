# -*- coding: utf-8 -*-
"""
seen_jobs.py - Plan X: Cross-Session Job Deduplication

管理 seen_jobs.json，跨会话记录已处理的岗位，支持：
- 新岗位检测
- 标题变化检测（link + title hash）
- JD 文件存储路径管理
"""
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path

# 默认路径
WORKSPACE = Path(__file__).parent.parent
HISTORY_DIR = WORKSPACE / "candidates" / "history"
JD_STORE_DIR = WORKSPACE / "candidates" / "jd_store"
SEEN_JOBS_FILE = HISTORY_DIR / "seen_jobs.json"


def ensure_dirs():
    """确保目录存在"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    JD_STORE_DIR.mkdir(parents=True, exist_ok=True)


def get_title_hash(link: str, title: str) -> str:
    """
    计算 link + title 的 MD5 哈希值
    用于检测同一链接但标题变化的情况
    """
    combined = f"{link}|{title}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()


def load_seen_jobs() -> dict:
    """
    加载 seen_jobs.json
    返回结构：
    {
        "last_updated": "2026-04-20T22:53:00",
        "jobs": {
            "https://.../job/abc123": {
                "title": "IT Business Analyst",
                "company": "AIA",
                "jd_file": "aia/abc123.txt",
                "jd_chars": 4520,
                "first_seen": "2026-04-19",
                "last_seen": "2026-04-20",
                "is_new_today": false,
                "title_hash": "a1b2c3d4..."
            }
        }
    }
    """
    ensure_dirs()
    if SEEN_JOBS_FILE.exists():
        try:
            with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_updated": None, "jobs": {}}


def save_seen_jobs(data: dict):
    """保存 seen_jobs.json"""
    ensure_dirs()
    data["last_updated"] = datetime.now().isoformat()
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_job_status(link: str, title: str, seen_data: dict) -> str:
    """
    检查岗位状态
    返回值：
    - "new": 新岗位，从未见过
    - "updated": 已见过但标题有变化
    - "unchanged": 已见过且无变化
    """
    if link not in seen_data.get("jobs", {}):
        return "new"
    
    old_hash = seen_data["jobs"][link].get("title_hash", "")
    new_hash = get_title_hash(link, title)
    
    if old_hash != new_hash:
        return "updated"
    return "unchanged"


def update_job_entry(link: str, title: str, company: str, 
                     jd_text: str, seen_data: dict,
                     status: str) -> dict:
    """
    更新 seen_jobs 中的岗位条目
    同时保存 JD 文件到 jd_store/{company}/{job_id}.txt
    
    返回更新后的条目
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 提取 job_id 从 URL
    job_id = link.split("/")[-1].split("?")[0]
    if not job_id:
        job_id = hashlib.md5(link.encode()).hexdigest()[:12]
    
    # 保存 JD 文件
    jd_file = None
    jd_chars = 0
    if jd_text:
        company_dir = JD_STORE_DIR / company.lower().replace(" ", "_")
        company_dir.mkdir(parents=True, exist_ok=True)
        jd_file = f"{company.lower().replace(' ', '_')}/{job_id}.txt"
        jd_path = JD_STORE_DIR / jd_file
        with open(jd_path, "w", encoding="utf-8") as f:
            f.write(jd_text)
        jd_chars = len(jd_text)
    
    # 更新条目
    existing = seen_data.get("jobs", {}).get(link, {})
    entry = {
        "title": title,
        "company": company,
        "jd_file": jd_file,
        "jd_chars": jd_chars,
        "first_seen": existing.get("first_seen", today) if status != "new" else today,
        "last_seen": today,
        "is_new_today": (status == "new"),
        "title_hash": get_title_hash(link, title)
    }
    
    seen_data.setdefault("jobs", {})[link] = entry
    return entry


def get_new_jobs_only(seen_data: dict) -> list:
    """
    获取今天新增的岗位列表（用于 Excel 输出）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    new_jobs = []
    for link, entry in seen_data.get("jobs", {}).items():
        if entry.get("first_seen") == today:
            new_jobs.append({"link": link, **entry})
    return new_jobs


def get_updated_jobs(seen_data: dict) -> list:
    """
    获取今天有更新的岗位列表（标题变化）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    updated_jobs = []
    for link, entry in seen_data.get("jobs", {}).items():
        if entry.get("last_seen") == today and entry.get("first_seen") != today:
            updated_jobs.append({"link": link, **entry})
    return updated_jobs


# 使用示例
if __name__ == "__main__":
    # 测试
    seen = load_seen_jobs()
    print(f"已记录 {len(seen.get('jobs', {}))} 个岗位")
    
    # 模拟新岗位
    test_link = "https://aia.wd3.myworkdayjobs.com/job/abc123"
    test_title = "IT Business Analyst"
    
    status = check_job_status(test_link, test_title, seen)
    print(f"状态: {status}")
    
    if status == "new":
        update_job_entry(test_link, test_title, "AIA", "Sample JD text...", seen, status)
        save_seen_jobs(seen)
        print("已添加测试岗位")
