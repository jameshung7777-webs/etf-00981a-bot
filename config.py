"""
配置文件
支援環境變數（優先使用環境變數，適合 GitHub Actions）
"""

import os
import json

# Telegram Bot Token
# 優先使用環境變數（GitHub Actions），否則使用預設值
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo")

# Telegram Chat ID（單一，相容舊版）
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", None)

# Telegram 發送對象列表（支援多個聊天室和群組，機器人會發到所有設定對象）
# 格式：用逗號分隔，例如 "123456789,-1001234567890"
# 取得 Chat ID：1) 私聊：對 Bot 發訊息後執行 get_chat_id.py
#              2) 群組：將 Bot 加入群組後，在群組發一則訊息，執行 get_chat_id.py
TELEGRAM_CHAT_IDS = ""  # 本地設定，例如 "123456789,-1001234567890"
TELEGRAM_CHAT_IDS_STR = os.getenv("TELEGRAM_CHAT_IDS", TELEGRAM_CHAT_IDS)

# 訂閱名單（/start 指令自動加入的 Chat ID）
SUBSCRIBED_CHATS_FILE = "subscribed_chats.json"

def get_chat_ids():
    """取得所有要發送的 Chat ID 列表（config + 訂閱名單）"""
    ids = []
    # 1. config 設定的 Chat IDs
    if TELEGRAM_CHAT_IDS_STR:
        for s in TELEGRAM_CHAT_IDS_STR.replace(" ", "").split(","):
            s = s.strip()
            if s:
                try:
                    ids.append(int(s))
                except ValueError:
                    pass
    cid = TELEGRAM_CHAT_ID
    if cid is not None and str(cid).lower() != "none":
        try:
            c = int(cid) if isinstance(cid, str) else cid
            if c not in ids:
                ids.append(c)
        except (ValueError, TypeError):
            pass
    # 2. 透過 /start 訂閱的 Chat IDs
    sub_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), SUBSCRIBED_CHATS_FILE)
    if os.path.exists(sub_file):
        try:
            with open(sub_file, "r", encoding="utf-8") as f:
                sub = json.load(f)
                for c in sub.get("chat_ids", []):
                    if c not in ids:
                        ids.append(c)
        except Exception:
            pass
    return ids

# ETF 代號
ETF_CODE = "00981A"

# 數據文件路徑
DATA_FILE = "holdings_data.json"

# Selenium 設置
HEADLESS_MODE = True  # 是否使用無頭模式
WAIT_TIME = 5  # 頁面載入等待時間（秒）
