"""
取得 Telegram Chat ID
使用方式：
1. 在 Telegram 搜尋你的 Bot（用 Bot 的用戶名）
2. 對 Bot 發送任意一則訊息（例如：hi）
3. 執行：python get_chat_id.py
4. 把畫面上顯示的 Chat ID 填進 config.py 的 TELEGRAM_CHAT_ID
"""

import os
import requests

try:
    from config import get_telegram_bot_token
except ImportError:
    get_telegram_bot_token = None

def _token():
    if get_telegram_bot_token:
        t = get_telegram_bot_token()
        if t:
            return t
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip() or None

def main():
    token = _token()
    if not token:
        print("未設定 TELEGRAM_BOT_TOKEN。請在環境變數或 config.py 設定（勿將含真 token 的 config 提交至公開 repo）。")
        return
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    print("正在取得最近與 Bot 的對話...")
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"請求失敗: {e}")
        return
    if not data.get("ok"):
        print("API 錯誤:", data.get("description", "未知"))
        return
    results = data.get("result") or []
    if not results:
        print("目前沒有收到任何訊息。")
        print("請先在 Telegram 對你的 Bot 發送一則訊息（例如：hi），再重新執行本腳本。")
        return
    # 取最後一則訊息的 chat id
    last = results[-1]
    chat = last.get("message", {}).get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        print("無法解析 Chat ID。")
        return
    # 收集所有不同的 chat_id
    all_chats = {}
    for r in results:
        msg = r.get("message", {})
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid is not None:
            title = chat.get("title") or chat.get("first_name") or str(cid)
            all_chats[cid] = title
    
    print("")
    print("=" * 50)
    print("發送對象列表（填入 config.py 的 TELEGRAM_CHAT_IDS）")
    print("=" * 50)
    print("")
    if len(all_chats) == 1:
        print("TELEGRAM_CHAT_ID =", chat_id)
        print("")
    else:
        ids_str = ",".join(str(c) for c in all_chats.keys())
        print("TELEGRAM_CHAT_IDS = \"" + ids_str + "\"")
        print("")
        for cid, title in all_chats.items():
            print(f"  {cid} - {title}")
        print("")
    print("（若要發到多個聊天室/群組，用逗號分隔 Chat ID）")
    print("=" * 50)

if __name__ == "__main__":
    main()
