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

from datetime import datetime, timedelta, timezone
import threading

# 台灣時區 UTC+8，讓 GitHub Actions（UTC）執行時顯示台灣日期
TAIWAN_TZ = timezone(timedelta(hours=8))

def _now_taiwan():
    """取得目前台灣時間（用於日期與顯示，避免 workflow 顯示「昨天」）"""
    return datetime.now(TAIWAN_TZ)
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
    """發送訊息到所有聊天室和群組（含隨機傳送順序、間隔延遲，降低被 Telegram 偵測風險）。"""
    import random, time as _time
    try:
        from config import get_message_thread_id
        thread_id = get_message_thread_id()
    except ImportError:
        thread_id = None

    if not chat_ids:
        for cid in [None]:
            ok1 = send_to_telegram_fn(msg_today, bot_token, cid, thread_id)
            ok2 = send_to_telegram_fn(report_compare, bot_token, cid, thread_id)
            if ok1 or ok2:
                return True
        print("[!] 無法取得 chat_id，請在 config.py 設定 TELEGRAM_CHAT_IDS 或 TELEGRAM_CHAT_ID")
        return False

    # 多個目標時打亂傳送順序，避免每次以固定順序傳送
    shuffled_ids = list(chat_ids)
    if len(shuffled_ids) > 1:
        random.shuffle(shuffled_ids)
        print(f"[i] 傳送順序隨機排列，共 {len(shuffled_ids)} 個目標")

    all_ok = True
    for idx, cid in enumerate(shuffled_ids):
        # 切換不同目標之間加入隨機停頓（4～12 秒）
        if idx > 0:
            inter_wait = random.uniform(4.0, 12.0)
            print(f"[i] 切換下一個目標，隨機等待 {inter_wait:.1f} 秒...")
            _time.sleep(inter_wait)

        ok1 = send_to_telegram_fn(msg_today, bot_token, cid, thread_id)
        # 同一目標兩則訊息之間隨機停頓（3～8 秒），模擬人工停頓
        msg_wait = random.uniform(3.0, 8.0)
        _time.sleep(msg_wait)
        ok2 = send_to_telegram_fn(report_compare, bot_token, cid, thread_id)
        if not (ok1 and ok2):
            all_ok = False
    return all_ok

def _date_str(dt):
    """統一日期格式：YYYY/M/D"""
    return f"{dt.year}/{dt.month}/{dt.day}"

def _is_weekend_taiwan(dt=None):
    """台灣時間是否為週六、週日（datetime.weekday：週一 0 … 週日 6）。"""
    t = dt if dt is not None else _now_taiwan()
    return t.weekday() >= 5


def _skip_send_on_weekend():
    """是否略過週末發送。環境變數 SKIP_WEEKEND_SEND：未設或 1/true 則略過；設 0/false/no 則週末仍發。"""
    import os
    v = (os.getenv("SKIP_WEEKEND_SEND") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")

def fetch_data_only():
    """18:00 執行：只抓取數據並儲存，不發送訊息。成功回傳 True，失敗回傳 False。"""
    today = _now_taiwan()
    today_str = _date_str(today)
    print("="*60)
    print("[18:00] 00981A 抓取持股數據")
    print("="*60)
    print(f"執行時間（台灣）: {today.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    current_holdings = None
    
    # 先試 requests，失敗再試 Selenium
    try:
        from scraper_requests import fetch_holdings_requests
        print(f"正在抓取 {today_str} 的持股數據（使用 requests）...")
        current_holdings = fetch_holdings_requests()
    except Exception as e:
        print(f"requests 失敗: {e}")
    
    if not current_holdings:
        try:
            from scraper_selenium import fetch_holdings_selenium
            print(f"正在抓取 {today_str} 的持股數據（使用 Selenium）...")
            _r = [None]
            def _run():
                try:
                    _r[0] = fetch_holdings_selenium()
                except Exception as ex:
                    print(f"Selenium 執行錯誤: {ex}")
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=SELENIUM_TIMEOUT)
            current_holdings = _r[0]
        except Exception as e:
            print(f"Selenium 失敗: {e}")
    
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
        
        return False
    
    _, _, save_fn, _, _, _, _ = _get_scraper_modules()
    save_fn(current_holdings, today_str)
    print(f"[OK] 已保存 {today_str} 的持股數據（共 {len(current_holdings)} 檔）")
    print("="*60 + "\n")
    return True

def send_messages_only():
    """18:30 執行：載入已儲存數據，比較變化，發送到所有聊天室和群組"""
    today = _now_taiwan()
    yesterday = today - timedelta(days=1)
    today_str = _date_str(today)
    yesterday_str = _date_str(yesterday)
    
    print("="*60)
    print("[18:30] 00981A 發送持股報告")
    print("="*60)
    print(f"執行時間（台灣）: {today.strftime('%Y-%m-%d %H:%M:%S')}\n")

    if _skip_send_on_weekend() and _is_weekend_taiwan(today):
        wname = ("週一", "週二", "週三", "週四", "週五", "週六", "週日")[today.weekday()]
        print(f"[i] 今日為 {wname}（台灣 {today.strftime('%Y-%m-%d')}），依設定不發送 Telegram；略過。")
        print("[i] 若要在週末也發送：設定環境變數 SKIP_WEEKEND_SEND=0（GitHub Actions 可在 workflow env 加入）\n")
        print("="*60 + "\n")
        return
    
    try:
        from config import TELEGRAM_BOT_TOKEN, get_chat_ids
        bot_token = TELEGRAM_BOT_TOKEN
        chat_ids = get_chat_ids()
    except ImportError:
        bot_token = "8403948543:AAGB7M46NK6UQprmn_g2z8HnPWWK_jUgfX0"
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
    
    previous_data = load_prev(current_date_str=today_str)
    msg_today = format_today(current_holdings, today_str)
    
    if previous_data and previous_data.get("date") != today_str:
        changes = compare_fn(current_holdings, previous_data)
        report_compare = format_report(changes, previous_data["date"], today_str)
    else:
        report_compare = f"00981A 持股更新（{yesterday_str} → {today_str}）\n\n（無前日資料可比較）\n\n" + msg_today
    
    if not bot_token:
        print("[FAIL] 未設定 Telegram Bot Token\n")
        print("="*60 + "\n")
        import sys; sys.exit(1)

    print(f"正在發送到 {len(chat_ids) or 1} 個聊天室/群組...")
    print(f"[i] Chat IDs: {chat_ids}")
    ok = send_to_all_chats(msg_today, report_compare, bot_token, chat_ids, send_fn)
    if ok:
        print("[OK] 訊息已成功發送到所有設定對象\n")
    else:
        print("[FAIL] 部分或全部訊息發送失敗！\n")
        print("="*60 + "\n")
        import sys; sys.exit(1)
    print("="*60 + "\n")

def fetch_and_send():
    """一次執行：抓取 + 儲存 + 發送（用於 --now 或手動測試）"""
    ok = fetch_data_only()
    if ok:
        send_messages_only()
    else:
        print("[i] 抓取失敗，跳過發送")

def run_scheduler():
    """執行排程器：16:30 抓資料，17:00 發訊息到所有聊天室和群組"""
    schedule.every().day.at("16:30").do(fetch_data_only)
    schedule.every().day.at("17:00").do(send_messages_only)

    print("="*60)
    print("00981A ETF 自動追蹤系統已啟動")
    print("="*60)
    print(f"啟動時間（台灣）: {_now_taiwan().strftime('%Y-%m-%d %H:%M:%S')}")
    print("排程設定:")
    print("  16:30 - 抓取持股數據並儲存")
    print("  17:00 - 發送持股明細與變化報告到所有聊天室/群組")
    print("="*60)
    print("\n提示: 按 Ctrl+C 可停止程式\n")

    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    """主函數：可選擇立即執行、僅抓取、僅發送或啟動排程器"""
    import argparse

    parser = argparse.ArgumentParser(description='00981A ETF 持股變化追蹤')
    parser.add_argument('--now', action='store_true', help='立即抓取並發送（本機測試用）')
    parser.add_argument('--fetch-only', action='store_true', help='僅抓取並儲存持股數據（16:30 使用）')
    parser.add_argument('--send-only', action='store_true', help='僅讀取已儲存數據並發送報告（17:00 使用）')

    args = parser.parse_args()

    if args.fetch_only:
        fetch_data_only()
    elif args.send_only:
        send_messages_only()
    elif args.now:
        fetch_and_send()
    else:
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
