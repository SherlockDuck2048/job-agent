#!/usr/bin/env python3
"""
cron_job_generator.py - 生成扫描器 cron job 配置

用法:
    python cron_job_generator.py <company> [schedule]
    
示例:
    python cron_job_generator.py add prudential "0 9 * * *"
    python cron_job_generator.py add macquarie "0 10 * * 1,3,5"
    python cron_job_generator.py add hsbc  # 使用默认 schedule "0 9 * * *"
"""

import json
import uuid
import sys
import os
from datetime import datetime

# 默认配置
DEFAULT_SCHEDULE = "0 9 * * *"
DEFAULT_TIMEZONE = "Asia/Shanghai"
WORKDIR = r"C:\Users\ClawAdmin\.qclaw\workspace\job-agent"
ACCOUNT_ID = "d3b24a645266-im-bot"
DELIVERY_CHANNEL = "openclaw-weixin"
USER_WECHAT_ID = "o9cq802ouk_i3bGq7zV56Vsm0p3I@im.wechat"

# 已知扫描器列表
KNOWN_SCANNERS = [
    "prudential", "macquarie", "dbs", "manulife", "hsbc", "aia", "sunlife",
    "linkedin", "indeed", "jpmorgan", "citi", "ubs", "goldman", "bochk",
    "hays", "kpmg", "ey", "deloitte", "pwc", "accenture", "ibm", "microsoft",
    "fwd", "hkjc", "hkex", "cicc", "bea", "ccb", "ubs", "citi"
]


def generate_cron_job(company: str, schedule: str = None, enabled: bool = True) -> dict:
    """生成单个 cron job 配置（OpenClaw 正确格式）"""
    
    company_upper = company.strip().upper()  # e.g., "prudential" -> "Prudential"
    company_lower = company.lower().strip()
    now_ms = int(datetime.now().timestamp() * 1000)
    
    # 验证扫描器名称
    if company_lower not in KNOWN_SCANNERS:
        print(f"警告: '{company}' 不在已知扫描器列表中")
        print(f"已知扫描器: {', '.join(KNOWN_SCANNERS)}")
    
    # 生成 payload 消息
    scan_cmd = f"cd {WORKDIR} && python -m scanners.scan_{company_lower} --no-dry-run"
    message = f"运行 {company_upper} 职位扫描：执行 {scan_cmd}，完成后汇报扫描结果（raw数量、matched数量）。要求：(1) 不要回复 HEARTBEAT_OK (2) 不要调用 message 工具 (3) 直接输出扫描结果 (4) 控制在 2-3 句话以内"
    
    # 构建任务配置（OpenClaw cron 正确格式）
    job = {
        "id": f"{company_lower}-daily-scan",
        "agentId": "main",
        "name": f"scan_{company_lower}_daily",
        "enabled": enabled,
        "createdAtMs": now_ms,
        "updatedAtMs": now_ms,
        "schedule": {
            "kind": "cron",
            "expr": schedule or DEFAULT_SCHEDULE
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": message
        },
        "delivery": {
            "mode": "announce",
            "channel": DELIVERY_CHANNEL,
            "to": USER_WECHAT_ID,
            "accountId": ACCOUNT_ID
        },
        "state": {}
    }
    
    return job

def list_cron_jobs(jobs_file: str = None) -> None:
    """列出当前所有 cron 任务"""
    if jobs_file is None:
        jobs_file = r"C:\Users\ClawAdmin\.qclaw\cron\jobs.json"
    
    jobs_file = os.path.normpath(jobs_file)
    
    if not os.path.exists(jobs_file):
        print(f"文件不存在: {jobs_file}")
        return
    
    with open(jobs_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    
    print(f"\n当前 cron 任务数: {len(jobs.get('jobs', []))}\n")
    print(f"{'名称':<30} {'schedule':<18} {'enabled':<8}")
    print("-" * 60)
    
    for job in jobs.get("jobs", []):
        schedule = job.get('schedule')
        if isinstance(schedule, dict):
            schedule_str = schedule.get('expr', '')
        else:
            schedule_str = str(schedule)
        print(f"{job.get('name', ''):<30} {schedule_str:<18} {str(job.get('enabled', '')):<8}")

def add_cron_job(company: str, schedule: str = None, jobs_file: str = None, replace: bool = False) -> None:
    """添加新的 cron 任务到 jobs.json"""
    
    if jobs_file is None:
        jobs_file = r"C:\Users\ClawAdmin\.qclaw\cron\jobs.json"
    
    jobs_file = os.path.normpath(jobs_file)
    
    # 读取现有任务
    if os.path.exists(jobs_file):
        with open(jobs_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    else:
        jobs = {"jobs": []}
    
    # 检查是否已存在
    job_name = f"scan_{company.lower()}_daily"
    existing_job = None
    for job in jobs.get("jobs", []):
        if job.get("name") == job_name:
            existing_job = job
            break
    
    if existing_job:
        if replace:
            # 替换现有任务
            jobs["jobs"] = [j for j in jobs.get("jobs", []) if j.get("name") != job_name]
            print(f"替换现有任务: {job_name}")
        else:
            print(f"任务已存在: {job_name}")
            print(f"  schedule: {existing_job.get('schedule', {}).get('expr') if isinstance(existing_job.get('schedule'), dict) else existing_job.get('schedule')}")
            print(f"  enabled: {existing_job.get('enabled')}")
            print("\n使用 --replace 替换现有任务")
            return
    
    # 生成新任务
    new_job = generate_cron_job(company, schedule)
    jobs["jobs"].append(new_job)
    
    # 写入文件
    os.makedirs(os.path.dirname(jobs_file), exist_ok=True)
    with open(jobs_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    
    print(f"已添加任务: {new_job['name']}")
    print(f"  schedule: {new_job['schedule']['expr']}")
    print(f"  enabled: {new_job['enabled']}")
    print(f"\n文件: {jobs_file}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n当前 cron 任务:")
        list_cron_jobs()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_cron_jobs()
    elif command == "add":
        if len(sys.argv) < 3:
            print("用法: python cron_job_generator.py add <company> [schedule] [--replace]")
            sys.exit(1)
        company = sys.argv[2]
        # 解析参数
        replace = "--replace" in sys.argv
        schedule = None
        for arg in sys.argv[3:]:
            if not arg.startswith("--"):
                schedule = arg
        add_cron_job(company, schedule, replace=replace)
    else:
        # 默认为生成模式
        company = sys.argv[1]
        schedule = sys.argv[2] if len(sys.argv) > 2 else None
        
        job = generate_cron_job(company, schedule)
        print(json.dumps(job, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()