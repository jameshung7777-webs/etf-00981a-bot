"""
配置文件
支援環境變數（GitHub Actions / 本機）。
Telegram Bot Token 請勿寫死在程式碼，請用環境變數或本機 config（勿提交含真 token 的檔案至公開 repo）。
"""

import os
import json


def get_telegram_bot_token():
    """從環境變數讀取 Bot Token（每次呼叫重新讀取；發送前請用此函式，勿依賴過期的 import 快照）。"""
    t = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    return t or None


# Telegram Bot Token（模組載入時快照，相容舊程式 `from config import TELEGRAM_BOT_TOKEN`）
TELEGRAM_BOT_TOKEN = get_telegram_bot_token()

# Telegram Chat ID（單一，相容舊版）
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", None)

# Telegram 發送對象列表（支援多個聊天室和群組，機器人會發到所有設定對象）
# 格式：用逗號分隔，例如 "123456789,-1001234567890"
# 取得 Chat ID：1) 私聊：對 Bot 發訊息後執行 get_chat_id.py
#              2) 群組：將 Bot 加入群組後，在群組發一則訊息，執行 get_chat_id.py
# 這裡預設加入固定群組 ID（可被 setup_chats 等工具覆寫此行）
# 超級群組／頻道在 Bot API 多為 -100xxxxxxxxxx；若漏寫「100」會出現 chat not found
TELEGRAM_CHAT_IDS = "-1006644792281,-1002890383818"


def _parse_chat_ids_csv(s):
    if not s:
        return []
    return [x.strip() for x in str(s).replace(" ", "").split(",") if x.strip()]


# GitHub Actions 會注入環境變數 TELEGRAM_CHAT_IDS（Secrets）。
# 「檔案預設 + 環境變數」合併去重。
_ids_env = os.getenv("TELEGRAM_CHAT_IDS")
_base_ids = _parse_chat_ids_csv(TELEGRAM_CHAT_IDS)
_env_ids = _parse_chat_ids_csv(_ids_env) if _ids_env else []
TELEGRAM_CHAT_IDS_STR = ",".join(dict.fromkeys(_base_ids + _env_ids))

# ── Topic（討論串）：依「群組 chat_id」對應，未列出的群組不帶 message_thread_id ──
# 環境變數 TELEGRAM_CHAT_TOPIC_IDS_JSON 可覆寫／擴充，例如：
#   {"-1002890383818": 50627}
# 舊版單一 TELEGRAM_MESSAGE_THREAD_ID 已不再套用到所有群組（避免錯群）。
_DEFAULT_CHAT_TOPIC_MAP = {-1002890383818: 50627}


def _effective_topic_map():
    m = dict(_DEFAULT_CHAT_TOPIC_MAP)
    raw = (os.getenv("TELEGRAM_CHAT_TOPIC_IDS_JSON") or "").strip()
    if raw:
        try:
            for k, v in json.loads(raw).items():
                m[int(k)] = int(v)
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    return m


def get_message_thread_id_for_chat(chat_id):
    """若該 chat 有設定 Topic，回傳 int；否則 None（不寫入 Telegram 的 message_thread_id）。"""
    if chat_id is None:
        return None
    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return None
    if cid >= 0:
        return None
    return _effective_topic_map().get(cid)


def get_message_thread_id():
    """相容舊診斷腳本：回傳 map 中任一 thread id（僅供顯示）；發送時實際依 get_message_thread_id_for_chat。"""
    m = _effective_topic_map()
    if not m:
        return None
    return next(iter(m.values()))


# 訂閱名單（/start 指令自動加入的 Chat ID）
SUBSCRIBED_CHATS_FILE = "subscribed_chats.json"


def _resolve_telegram_chat_ids(ids):
    """合併 Secret 時常出現「超級群組少抄 -100」的 id；若清單內已有正確 -100… 形則略過短形。"""
    sset = set(ids)
    res = []
    for n in ids:
        if n < 0 and not str(n).startswith("-100"):
            body = str(n)[1:]
            if body.isdigit() and len(body) == 10:
                alt = int("-100" + body)
                if alt in sset:
                    continue
                n = alt
        res.append(n)
    return list(dict.fromkeys(res))


def get_chat_ids():
    """取得所有要發送的 Chat ID 列表（config + 訂閱名單）"""
    ids = []
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
    return _resolve_telegram_chat_ids(ids)


# ETF 代號
ETF_CODE = "00981A"

# 數據文件路徑
DATA_FILE = "holdings_data.json"

# Selenium 設置
HEADLESS_MODE = True
WAIT_TIME = 5
