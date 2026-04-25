#!/usr/bin/env python3
"""
Daily scan and push script
Runs all active scanners, merges results, and pushes to GitHub
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Project paths
PROJECT_ROOT = Path(__file__).parent.resolve()
SCANNERS_DIR = PROJECT_ROOT / "scanners"

# Active scanners (those with 3/3 Done in scanner_tasks_status.xlsx)
ACTIVE_SCANNERS = [
    "aia", "manulife", "prudential", "sunlife", "hkex", "aig", "ocbc",
    "cncb", "kpmg", "ey", "citi", "jpmorgan", "clp", "fwd", "dbs",
    "hkjc", "macquarie"
]

def run_scanner(name: str) -> bool:
    """Run a single scanner, return True if successful"""
    scanner_path = SCANNERS_DIR / f"scan_{name}.py"
    if not scanner_path.exists():
        print(f"[SKIP] {name} - scanner not found")
        return False
    
    print(f"\n[RUN] {name}")
    result = subprocess.run(
        [sys.executable, str(scanner_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"[OK] {name}")
        return True
    else:
        print(f"[ERR] {name}")
        print(result.stderr[:500])
        return False

def merge_results() -> bool:
    """Merge all JSON results to Excel"""
    print("\n[STEP] Merging results...")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "merge_results.py"), "--new-only"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("[OK] Results merged")
        return True
    else:
        print("[ERR] Merge failed")
        print(result.stderr[:500])
        return False

def git_commit_and_push() -> bool:
    """Commit and push changes to GitHub"""
    print("\n[STEP] Git commit and push...")
    
    # Check if there are changes
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    
    if not result.stdout.strip():
        print("[OK] No changes to commit")
        return True
    
    # Add changes
    subprocess.run(["git", "add", "."], cwd=PROJECT_ROOT)
    
    # Commit
    today = datetime.now().strftime("%Y-%m-%d")
    commit_msg = f"Daily scan results - {today}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=PROJECT_ROOT)
    
    # Push
    result = subprocess.run(
        ["git", "push", "origin", "master"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"[OK] Pushed: {commit_msg}")
        return True
    else:
        print("[ERR] Push failed")
        print(result.stderr[:500])
        return False

def main():
    """Main entry point"""
    print(f"=== Daily Scan - {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    
    # Run scanners
    success_count = 0
    for name in ACTIVE_SCANNERS:
        if run_scanner(name):
            success_count += 1
    
    print(f"\n[SUMMARY] {success_count}/{len(ACTIVE_SCANNERS)} scanners succeeded")
    
    # Merge results
    if success_count > 0:
        merge_results()
    
    # Git push
    git_commit_and_push()
    
    print("\n=== Done ===")

if __name__ == "__main__":
    main()
