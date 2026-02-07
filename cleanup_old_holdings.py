"""
清理 7 天前的 holdings_data 檔案
保留 holdings_data.json（最新比對用），刪除 holdings_data_YYYY-MM-DD_HHMM.json 中超過 7 天的
可在 GitHub Actions 運行
"""

import os
import re
import glob
from datetime import datetime, timedelta

def cleanup_old_holdings(days=7, dry_run=False):
    """刪除超過 N 天的 holdings_data_*.json（不含 holdings_data.json）"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cutoff = datetime.now() - timedelta(days=days)
    pattern = os.path.join(base_dir, "holdings_data_*.json")
    files = glob.glob(pattern)
    deleted = []
    
    for path in files:
        name = os.path.basename(path)
        if name == "holdings_data.json":
            continue
        m = re.match(r"holdings_data_(\d{4})-(\d{2})-(\d{2})_(\d{4})\.json", name)
        if m:
            try:
                file_time = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if file_time < cutoff:
                    if not dry_run:
                        os.remove(path)
                    deleted.append(name)
            except (ValueError, OSError):
                pass
        else:
            # 依檔案修改時間判斷
            try:
                mtime = os.path.getmtime(path)
                file_time = datetime.fromtimestamp(mtime)
                if file_time < cutoff:
                    if not dry_run:
                        os.remove(path)
                    deleted.append(name)
            except OSError:
                pass
    
    return deleted

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="清理舊的 holdings 檔案")
    parser.add_argument("--days", type=int, default=7, help="保留最近 N 天，預設 7")
    parser.add_argument("--dry-run", action="store_true", help="只顯示不刪除")
    args = parser.parse_args()
    
    deleted = cleanup_old_holdings(days=args.days, dry_run=args.dry_run)
    
    if deleted:
        action = "將刪除" if args.dry_run else "已刪除"
        print(f"[OK] {action} {len(deleted)} 個檔案：")
        for f in deleted:
            print(f"  - {f}")
    else:
        print("[i] 無需清理的檔案")
