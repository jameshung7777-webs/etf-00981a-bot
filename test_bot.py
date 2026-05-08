"""
Bot 發送診斷工具
執行後會顯示：
  1. Bot 身份是否有效（getMe）
  2. 目前設定的 Chat ID 和 Topic ID
  3. 嘗試發送一則測試訊息並顯示 API 錯誤原因
"""
import sys
import os
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

SEP = "=" * 52

def check(label, ok, info=""):
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {label}{': ' + info if info else ''}")

print()
print(SEP)
print("  Bot 發送診斷工具")
print(SEP)

# ── 讀取 config ───────────────────────────────────────
try:
    import config
    token     = config.TELEGRAM_BOT_TOKEN
    chat_ids  = config.get_chat_ids()
    thread_id = config.get_message_thread_id()
    print(f"\n  Token     : {token[:10]}...{token[-6:]}")
    print(f"  Chat IDs  : {chat_ids}")
    print(f"  Thread ID : {thread_id}")
except Exception as e:
    print(f"  [FAIL] 讀取 config 失敗: {e}")
    sys.exit(1)

# ── 驗證 Bot Token（getMe）────────────────────────────
print(f"\n{SEP}")
print("  1. 驗證 Bot Token")
print(SEP)
try:
    resp = requests.get(
        f"https://api.telegram.org/bot{token}/getMe",
        timeout=10
    )
    data = resp.json()
    if data.get("ok"):
        bot = data["result"]
        check("Token 有效", True,
              f"@{bot.get('username','?')} | ID: {bot.get('id')}")
    else:
        check("Token 有效", False, data.get("description", str(resp.status_code)))
        print("\n  ⛔ Token 無效，請先執行 set_token.bat 更換 Token")
        sys.exit(1)
except Exception as e:
    check("Token 有效", False, str(e))
    sys.exit(1)

# ── 嘗試發送測試訊息到每個 Chat ───────────────────────
print(f"\n{SEP}")
print("  2. 嘗試發送測試訊息")
print(SEP)

if not chat_ids:
    print("  [!] chat_ids 為空，無法測試發送")
    print("      請確認 config.py 的 TELEGRAM_CHAT_IDS 已設定")
    sys.exit(1)

all_ok = True
url = f"https://api.telegram.org/bot{token}/sendMessage"

for cid in chat_ids:
    payload = {
        "chat_id": cid,
        "text": "🔧 [診斷] Bot 連線測試訊息，請忽略。"
    }
    if thread_id:
        payload["message_thread_id"] = thread_id

    try:
        r = requests.post(url, json=payload, timeout=10)
        body = r.json() if r.text else {}
        if r.status_code == 200 and body.get("ok"):
            check(f"發送到 {cid}", True, f"message_id={body['result']['message_id']}")
        else:
            err = body.get("description", f"HTTP {r.status_code}")
            check(f"發送到 {cid}", False, err)
            all_ok = False

            # 常見錯誤解說
            if "bot was kicked" in err or "not a member" in err:
                print(f"    ➜ Bot 不在群組中！請在 Telegram 把 Bot 加進群組後再試")
            elif "chat not found" in err:
                print(f"    ➜ 找不到 Chat ID：{cid}")
                print(f"       請確認 Chat ID 正確，或 Bot 尚未和此 Chat 互動過")
            elif "TOPIC_CLOSED" in err or "thread" in err.lower():
                print(f"    ➜ Topic ID {thread_id} 可能已關閉或不存在")
            elif "Forbidden" in err:
                print(f"    ➜ Bot 被封鎖或已被踢出群組")
    except Exception as e:
        check(f"發送到 {cid}", False, str(e))
        all_ok = False

# ── 結果總結 ──────────────────────────────────────────
print(f"\n{SEP}")
if all_ok:
    print("  ✅ 所有測試通過！Bot 可正常發送訊息")
else:
    print("  ❌ 有發送失敗，請依上方提示排除問題")
    print()
    print("  常見解決方式：")
    print("  1. 在 Telegram 把 Bot 加進群組（需給予發送訊息權限）")
    print("  2. 在目標 Topic 隨便發一則訊息，讓 Bot 取得權限")
    print("  3. 若 Token 已更換，執行 set_token.bat 重新設定")
print(SEP)
print()
