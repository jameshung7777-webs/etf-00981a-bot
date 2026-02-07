"""
00981A ETF 持股變化追蹤腳本 - 整合版
自動抓取持股明細，比較變化，並發送到 Telegram
支援每天自動執行（排程功能）
"""

# Windows 主控台 UTF-8，避免 cp950 無法輸出符號
import sys
import io
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from datetime import datetime, timedelta
import threading
import schedule
import time

# Selenium 整體逾時（秒），留足夠時間給頁面載入與表格解析
SELENIUM_TIMEOUT = 60  # 增加到 60 秒

def _get_scraper_modules():
    """取得 scraper 模組（requests 優先，selenium 備用）"""
    try:
        from scraper_requests import (
            fetch_holdings_requests, load_previous_holdings, save_holdings,
            compare_holdings, format_report, format_today_holdings, send_to_telegram
        )
        return fetch_holdings_requests, load_previous_holdings, save_holdings, compare_holdings, format_report, format_today_holdings, send_to_telegram
    except ImportError:
        from scraper_selenium import (
            fetch_holdings_selenium, load_previous_holdings, save_holdings,
            compare_holdings, format_report, format_today_holdings, send_to_telegram
        )
        return fetch_holdings_selenium, load_previous_holdings, save_holdings, compare_holdings, format_report, format_today_holdings, send_to_telegram

def send_to_all_chats(msg_today, report_compare, bot_token, chat_ids, send_to_telegram_fn):
    """發送訊息到所有聊天室和群組"""
    if not chat_ids:
        # 若沒設定，嘗試自動取得最後一個對話的 chat_id
        for cid in [None]:
            ok1 = send_to_telegram_fn(msg_today, bot_token, cid)
            ok2 = send_to_telegram_fn(report_compare, bot_token, cid)
            if ok1 or ok2:
                return True
        print("[!] 無法取得 chat_id，請在 config.py 設定 TELEGRAM_CHAT_IDS 或 TELEGRAM_CHAT_ID")
        return False
    all_ok = True
    for cid in chat_ids:
        ok1 = send_to_telegram_fn(msg_today, bot_token, cid)
        ok2 = send_to_telegram_fn(report_compare, bot_token, cid)
        if not (ok1 and ok2):
            all_ok = False
    return all_ok

def fetch_data_only():
    """18:00 執行：只抓取數據並儲存，不發送訊息"""
    today = datetime.now()
    today_str = f"{today.month}/{today.day}"
    print("="*60)
    print("[18:00] 00981A 抓取持股數據")
    print("="*60)
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    fetch_fn, load_prev, save_fn = None, None, None
    current_holdings = None
    
    try:
        fetch_fn, load_prev, save_fn, _, _, _, _ = _get_scraper_modules()
        if fetch_fn.__name__ == "fetch_holdings_requests":
            print(f"正在抓取 {today_str} 的持股數據（使用 requests）...")
            current_holdings = fetch_fn()
        else:
            print(f"正在抓取 {today_str} 的持股數據（使用 Selenium）...")
            _r = [None]
            def _run():
                try:
                    _r[0] = fetch_fn()
                except Exception as e:
                    print(f"Selenium 執行錯誤: {e}")
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=SELENIUM_TIMEOUT)
            current_holdings = _r[0]
    except Exception as e:
        print(f"抓取失敗: {e}")
    
    if not current_holdings:
        print("[FAIL] 無法抓取持股數據")
        print("\n提示:")
        print("1. 請確保已安裝 Chrome 瀏覽器")
        print("2. 請確保已安裝 ChromeDriver")
        print("   - 方法1: pip install webdriver-manager（自動下載）")
        print("   - 方法2: 手動下載 ChromeDriver 並添加到 PATH")
        print("   - 方法3: 將 chromedriver.exe 放在項目目錄中")
        print("3. 檢查網絡連接")
        print("4. 如果 Selenium 無法使用，腳本會自動嘗試使用 requests 版本")
        
        return
    
    save_fn(current_holdings, today_str)
    print(f"[OK] 已保存 {today_str} 的持股數據（共 {len(current_holdings)} 檔）")
    print("="*60 + "\n")

def send_messages_only():
    """18:30 執行：載入已儲存數據，比較變化，發送到所有聊天室和群組"""
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    today_str = f"{today.month}/{today.day}"
    yesterday_str = f"{yesterday.month}/{yesterday.day}"
    
    print("="*60)
    print("[18:30] 00981A 發送持股報告")
    print("="*60)
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    try:
        from config import TELEGRAM_BOT_TOKEN, get_chat_ids
        bot_token = TELEGRAM_BOT_TOKEN
        chat_ids = get_chat_ids()
    except ImportError:
        bot_token = "8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo"
        chat_ids = []
    
    _, load_prev, _, compare_fn, format_report, format_today, send_fn = _get_scraper_modules()
    
    # 載入今日數據（剛剛 18:00 抓的）
    import json
    import os
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings_data.json")
    if not os.path.exists(data_file):
        print("[FAIL] 找不到 holdings_data.json，請先執行 18:00 的抓取")
        return
    
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    current_holdings = data.get("holdings", [])
    today_str = data.get("date", today_str)
    
    previous_data = load_prev()
    msg_today = format_today(current_holdings, today_str)
    
    if previous_data and previous_data.get("date") != today_str:
        changes = compare_fn(current_holdings, previous_data)
        report_compare = format_report(changes, previous_data["date"], today_str)
    else:
        report_compare = f"00981A 持股更新（{yesterday_str} → {today_str}）\n\n（無前日資料可比較）\n\n" + msg_today
    
    if bot_token:
        print(f"正在發送到 {len(chat_ids) or 1} 個聊天室/群組...")
        send_to_all_chats(msg_today, report_compare, bot_token, chat_ids, send_fn)
        print("[OK] 訊息已發送到所有設定對象\n")
    else:
        print("[!] 未設定 Telegram Bot Token\n")
    print("="*60 + "\n")

def fetch_and_send():
    """一次執行：抓取 + 儲存 + 發送（用於 --now 或手動測試）"""
    fetch_data_only()
    send_messages_only()

def run_scheduler():
    """執行排程器：18:00 抓資料，18:30 發訊息到所有聊天室和群組"""
    schedule.every().day.at("18:00").do(fetch_data_only)
    schedule.every().day.at("18:30").do(send_messages_only)
    
    print("="*60)
    print("00981A ETF 自動追蹤系統已啟動")
    print("="*60)
    print(f"啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("排程設定:")
    print("  18:00 - 抓取持股數據並儲存")
    print("  18:30 - 發送持股明細與變化報告到所有聊天室/群組")
    print("="*60)
    print("\n提示: 按 Ctrl+C 可停止程式\n")
    
    # 持續運行排程
    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分鐘檢查一次

def main():
    """主函數：可選擇立即執行或啟動排程器"""
    import argparse
    
    parser = argparse.ArgumentParser(description='00981A ETF 持股變化追蹤')
    parser.add_argument('--now', action='store_true', help='立即執行一次（不啟動排程器）')
    parser.add_argument('--schedule', action='store_true', default=True, help='啟動排程器（每天6點執行）')
    
    args = parser.parse_args()
    
    if args.now:
        # 立即執行一次
        fetch_and_send()
    else:
        # 啟動排程器
        try:
            run_scheduler()
        except KeyboardInterrupt:
            print("\n\n程式已停止")
        except Exception as e:
            print(f"\n發生錯誤: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
