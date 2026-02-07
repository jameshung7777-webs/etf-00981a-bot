"""
00981A 訂閱機器人
監聽 /start 指令，自動將使用者的 Chat ID 加入訂閱名單
每天 18:30 會自動發送持股報告到所有已訂閱的聊天室/群組
"""

import sys
import io
import json
import os
import time
import requests

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from config import TELEGRAM_BOT_TOKEN
except ImportError:
    TELEGRAM_BOT_TOKEN = "8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo"

SUBSCRIBED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscribed_chats.json")

def load_subscribed():
    """載入已訂閱的 Chat ID 列表"""
    if os.path.exists(SUBSCRIBED_FILE):
        try:
            with open(SUBSCRIBED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("chat_ids", [])
        except Exception:
            pass
    return []

def save_subscribed(chat_ids):
    """儲存已訂閱的 Chat ID 列表"""
    from datetime import datetime
    data = {"chat_ids": list(set(chat_ids)), "updated": datetime.now().isoformat()}
    with open(SUBSCRIBED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_message(bot_token, chat_id, text):
    """發送訊息"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def run_listener():
    """監聽 /start 指令並自動加入訂閱"""
    offset = 0
    print("="*50, flush=True)
    print("00981A 訂閱機器人已啟動", flush=True)
    print("="*50, flush=True)
    print("請在 Telegram 對機器人發送 /start，Chat ID 會顯示在此", flush=True)
    print("按 Ctrl+C 停止", flush=True)
    print("="*50, flush=True)

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=35)
            data = r.json()

            if not data.get("ok"):
                time.sleep(5)
                continue

            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue

                text = (msg.get("text") or "").strip()
                chat = msg.get("chat", {})
                chat_id = chat.get("id")

                if text.startswith("/start") and chat_id is not None:
                    ids = load_subscribed()
                    name = chat.get("title") or chat.get("first_name") or "(未知)"
                    if chat_id not in ids:
                        ids.append(chat_id)
                        save_subscribed(ids)
                        send_message(TELEGRAM_BOT_TOKEN, chat_id,
                            "✅ 已加入 00981A 持股報告訂閱！\n\n"
                            "您將在每天 18:30 收到持股明細與變化報告。")
                    else:
                        send_message(TELEGRAM_BOT_TOKEN, chat_id,
                            "您已在訂閱名單中，每天 18:30 會收到 00981A 持股報告。")
                    # 終端顯示 Chat ID，方便手動加入 config
                    print("", flush=True)
                    print("=" * 50, flush=True)
                    print("收到 /start，請將以下 Chat ID 加入 config.py 或 TELEGRAM_CHAT_IDS：", flush=True)
                    print(f"  Chat ID: {chat_id}", flush=True)
                    print(f"  來源: {name}", flush=True)
                    print("=" * 50, flush=True)
                    sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n機器人已停止")
            break
        except Exception as e:
            print(f"錯誤: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_listener()
