"""
聊天室重新設定工具
------------------
當換了新 Bot 之後，用此工具一步步重新設定要發送的群組 / 私聊。

流程：
  1. 先確認新 Bot Token 有效
  2. 列出 Bot 收到過訊息的所有聊天室
  3. 讓你選擇要發到哪幾個
  4. 自動更新 config.py
  5. 推送到 GitHub
"""

import sys
import os
import re
import json
import time
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

SEP = "=" * 52

def _sep(title=""):
    print(f"\n{SEP}")
    if title:
        print(f"  {title}")
        print(SEP)

# ──────────────────────────────────────────────────────
def get_bot_info(token):
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    d = r.json()
    if d.get("ok"):
        b = d["result"]
        return True, f"@{b.get('username','?')} ({b.get('first_name','?')})"
    return False, d.get("description", "")

def get_updates(token):
    """取得 bot 收到的所有訊息（最多 100 則）"""
    r = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"limit": 100, "timeout": 0},
        timeout=15
    )
    d = r.json()
    if not d.get("ok"):
        return None, d.get("description", "")
    return d.get("result", []), ""

def parse_chats(updates):
    """從 updates 中解析出所有不重複的 chat"""
    seen = {}
    for u in updates:
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid is None:
            continue
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or str(cid)
        ctype = chat.get("type", "?")
        seen[cid] = {"id": cid, "title": title, "type": ctype}
    return list(seen.values())

def update_config_chat_ids(new_ids_str: str) -> bool:
    """更新 config.py 的 TELEGRAM_CHAT_IDS"""
    config_path = os.path.join(BASE_DIR, "config.py")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        new_content, n = re.subn(
            r'(TELEGRAM_CHAT_IDS\s*=\s*")[^"]*(")',
            rf'\g<1>{new_ids_str}\g<2>',
            content
        )
        if n == 0:
            return False
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"  [!] 更新 config.py 失敗: {e}")
        return False

def update_subscribed_chats(chat_id_list):
    """同步 subscribed_chats.json，避免舊 /start 訂閱 ID 繼續被合併進發送清單"""
    path = os.path.join(BASE_DIR, "subscribed_chats.json")
    from datetime import datetime
    data = {"chat_ids": chat_id_list, "updated": datetime.now().isoformat()}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"  [!] 更新 subscribed_chats.json 失敗: {e}")
        return False

def push_to_github() -> bool:
    import subprocess
    try:
        subprocess.run(["git", "add", "config.py", "subscribed_chats.json"], check=True, cwd=BASE_DIR)
        subprocess.run(["git", "commit", "-m", "更新發送目標 Chat IDs"], check=True, cwd=BASE_DIR)
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True, cwd=BASE_DIR)
        subprocess.run(["git", "push", "origin", "main"], check=True, cwd=BASE_DIR)
        return True
    except Exception as e:
        print(f"  [!] 推送失敗: {e}")
        return False

# ──────────────────────────────────────────────────────
def main():
    _sep("聊天室重新設定工具")

    # ── 讀取 token ──────────────────────────────────
    try:
        import config
        token = config.TELEGRAM_BOT_TOKEN
    except Exception:
        token = "8403948543:AAGB7M46NK6UQprmn_g2z8HnPWWK_jUgfX0"

    ok, info = get_bot_info(token)
    if not ok:
        print(f"\n  [FAIL] Bot Token 無效：{info}")
        print("  請先執行 set_token.bat 更換 Token")
        sys.exit(1)
    print(f"\n  Bot: {info}")

    # ── 說明 ────────────────────────────────────────
    print(f"""
步驟說明：
  1. 把新 Bot 加入你想接收通知的「每個群組」
  2. 在每個群組發任意一則訊息（例如 hi 或 /start）
  3. 若要私聊通知：直接跟 Bot 傳訊息
  4. 完成後，回到這裡按 Enter 繼續
""")
    input("  完成後按 Enter 繼續...")

    # ── 拉取 updates ─────────────────────────────────
    _sep("掃描 Bot 收到的訊息")
    print("  正在從 Telegram 取得訊息記錄...")
    updates, err = get_updates(token)
    if updates is None:
        print(f"  [FAIL] 無法取得訊息：{err}")
        sys.exit(1)

    chats = parse_chats(updates)

    if not chats:
        print("""
  [!] Bot 尚未收到任何訊息。
  請確認：
    1. Bot 已被加入群組
    2. 有人在群組裡發過訊息（或你有傳訊給 Bot）
  完成後重新執行此腳本。
""")
        sys.exit(1)

    # ── 列出可用的 Chat ──────────────────────────────
    _sep("偵測到的聊天室")
    print()
    type_label = {"supergroup": "超級群組", "group": "群組",
                  "private": "私聊", "channel": "頻道"}
    for i, c in enumerate(chats, 1):
        label = type_label.get(c["type"], c["type"])
        print(f"  {i:2d}. [{label}] {c['title']}  |  ID: {c['id']}")

    # ── 讓使用者選擇 ─────────────────────────────────
    print()
    print("  請輸入要啟用的編號（多個用空格或逗號分隔），例如：1 3")
    print("  直接 Enter 表示全部選取")
    choice = input("  選擇 > ").strip()

    if not choice:
        selected = chats
    else:
        idxs = re.findall(r'\d+', choice)
        selected = []
        for idx in idxs:
            n = int(idx)
            if 1 <= n <= len(chats):
                selected.append(chats[n - 1])
            else:
                print(f"  [!] 編號 {n} 超出範圍，已略過")

    if not selected:
        print("  [!] 未選擇任何聊天室，已取消")
        sys.exit(0)

    # ── 確認 ────────────────────────────────────────
    _sep("確認選擇")
    new_ids_str = ",".join(str(c["id"]) for c in selected)
    print()
    for c in selected:
        print(f"  • {c['title']} ({c['id']})")
    print(f"\n  將寫入 config.py：TELEGRAM_CHAT_IDS = \"{new_ids_str}\"")
    confirm = input("\n  確認？(Y/n) > ").strip().lower()
    if confirm == "n":
        print("  已取消")
        sys.exit(0)

    # ── 更新 config.py ───────────────────────────────
    _sep("更新 config.py")
    if update_config_chat_ids(new_ids_str):
        print("  [OK] config.py 已更新")
    else:
        print("  [!] 自動更新失敗，請手動修改 config.py 的 TELEGRAM_CHAT_IDS")

    # ── 同步 subscribed_chats.json（與 config 一致，避免舊 ID 殘留）──
    ids_only = [c["id"] for c in selected]
    _sep("同步 subscribed_chats.json")
    if update_subscribed_chats(ids_only):
        print("  [OK] subscribed_chats.json 已與選擇的聊天室同步")
        print("      （bot_listener /start 訂閱會再追加；此檔僅清除設定工具選定的清單）")

    # ── 推送到 GitHub ────────────────────────────────
    _sep("推送到 GitHub")
    if push_to_github():
        print("  [OK] 已推送到 GitHub")
    else:
        print("  [!] 請手動 git push")

    # ── 測試發送 ─────────────────────────────────────
    _sep("測試發送")
    ans = input("  是否立即執行 test_bot.bat 驗證？(Y/n) > ").strip().lower()
    if ans != "n":
        import subprocess
        subprocess.run(["python", "test_bot.py"], cwd=BASE_DIR)

    _sep("完成")
    print()
    print("  ✅ 聊天室設定完成！")
    print()

if __name__ == "__main__":
    main()
