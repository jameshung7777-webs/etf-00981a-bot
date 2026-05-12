"""
Telegram Bot Token 快速復原工具
---------------------------------
當 Bot 被刪除或 Token 被撤銷時，執行此腳本即可：
  1. 輸入新 Token
  2. 自動驗證 Token 是否有效
  3. 更新 config.py
  4. 嘗試更新 GitHub Secret（需安裝 gh CLI）
  5. 推送到 GitHub
  6. 發送測試訊息確認恢復

用法：
  python set_token.py                         # 互動式輸入
  python set_token.py 123456:ABCDEFG...       # 直接帶入 Token
"""

import sys
import os
import re
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.py")

# ──────────────────────────────────────────────
# 工具函式
# ──────────────────────────────────────────────

def _print_sep(title=""):
    line = "=" * 52
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)

def validate_token_format(token: str) -> bool:
    """Bot Token 格式：數字:35 位以上英數字"""
    return bool(re.match(r'^\d{5,}:[A-Za-z0-9_-]{35,}$', token.strip()))

def test_token_api(token: str):
    """呼叫 Telegram getMe，回傳 (ok: bool, info: str)"""
    try:
        import requests
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10
        )
        data = resp.json()
        if data.get("ok"):
            bot = data["result"]
            return True, f"@{bot.get('username','?')} ({bot.get('first_name','?')})"
        return False, data.get("description", f"HTTP {resp.status_code}")
    except Exception as e:
        return False, str(e)

def update_config_file(new_token: str) -> bool:
    """替換 config.py 中的 hardcode token"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 匹配目前格式：TELEGRAM_BOT_TOKEN = (_t or "").strip() or "舊token"
        new_content, n = re.subn(
            r'(TELEGRAM_BOT_TOKEN\s*=\s*\(_t\s*or\s*""\)\.strip\(\)\s*or\s*")[^"]*(")',
            rf'\g<1>{new_token}\g<2>',
            content
        )
        if n == 0:
            print("  [!] 找不到 Token 樣板，嘗試備用替換...")
            # 備用：直接搜尋舊 Token 字串
            new_content = re.sub(
                r'(?<=or ")[\d]+:[A-Za-z0-9_-]+(?=")',
                new_token,
                content
            )
            if new_content == content:
                return False

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"  [!] 更新 config.py 失敗: {e}")
        return False

def update_github_secret(new_token: str):
    """
    用 gh CLI 更新 GitHub Secret TELEGRAM_BOT_TOKEN
    回傳：True=成功, False=失敗, None=未安裝 gh CLI
    """
    try:
        result = subprocess.run(
            ["gh", "secret", "set", "TELEGRAM_BOT_TOKEN", "--body", new_token],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except FileNotFoundError:
        return None
    except Exception:
        return False

def push_to_github() -> bool:
    """git add config.py → commit → pull --rebase → push"""
    try:
        subprocess.run(["git", "add", "config.py"], check=True, cwd=BASE_DIR)
        subprocess.run(
            ["git", "commit", "-m", "緊急復原：更換 Bot Token"],
            check=True, cwd=BASE_DIR
        )
        subprocess.run(
            ["git", "pull", "origin", "main", "--rebase"],
            check=True, cwd=BASE_DIR
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            check=True, cwd=BASE_DIR
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [!] git 指令失敗: {e}")
        return False

def send_test_message(new_token: str):
    """讀取 config 取得目標群組，發送一則「已恢復」測試訊息"""
    try:
        import requests, importlib, sys as _sys

        # 強制重新載入 config（因為已修改 config.py）
        for mod in list(_sys.modules.keys()):
            if mod in ("config",):
                del _sys.modules[mod]

        _sys.path.insert(0, BASE_DIR)
        import config

        chat_ids    = config.get_chat_ids()
        url         = f"https://api.telegram.org/bot{new_token}/sendMessage"
        text        = "✅ Bot Token 已成功更換，系統已恢復正常運作！"

        if not chat_ids:
            print("  [!] 找不到 chat_id，跳過測試發送")
            return

        for cid in chat_ids:
            payload = {"chat_id": cid, "text": text}
            tid = config.get_message_thread_id_for_chat(cid)
            if tid is not None:
                payload["message_thread_id"] = tid
            resp = requests.post(url, json=payload, timeout=10)
            body = resp.json() if resp.text else {}
            if resp.status_code == 200 and body.get("ok"):
                print(f"  [OK] 測試訊息已送達 chat {cid}")
            else:
                print(f"  [!] 發送到 {cid} 失敗：{body.get('description', resp.status_code)}")
    except Exception as e:
        print(f"  [!] 測試發送發生錯誤: {e}")

# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def main():
    _print_sep("Telegram Bot Token 快速復原工具")
    print()
    print("步驟：")
    print("  1. 到 BotFather 取得新 Token")
    print("  2. 在下方貼上新 Token")
    print("  3. 工具會自動驗證、更新並推送到 GitHub")
    print()

    # ── 輸入 Token ──
    if len(sys.argv) > 1:
        new_token = sys.argv[1].strip()
        print(f"使用命令列傳入的 Token")
    else:
        print("請貼上新的 Bot Token（格式：123456789:AABBCC...）：")
        new_token = input("Token > ").strip()

    if not new_token:
        print("[!] Token 不能為空，已中止")
        sys.exit(1)

    # ── 格式驗證 ──
    print()
    if not validate_token_format(new_token):
        print("[!] Token 格式不正確（應為 數字:35位以上英數字）")
        cont = input("仍要繼續？(y/N) > ").strip().lower()
        if cont != "y":
            sys.exit(1)

    # ── 呼叫 Telegram API 驗證 ──
    print("正在向 Telegram 驗證 Token...")
    ok, info = test_token_api(new_token)
    if ok:
        print(f"[OK] Token 有效 → Bot: {info}")
    else:
        print(f"[!] Token 驗證失敗：{info}")
        cont = input("仍要繼續更新？(y/N) > ").strip().lower()
        if cont != "y":
            sys.exit(1)

    # ── 更新 config.py ──
    _print_sep("步驟 1：更新 config.py")
    if update_config_file(new_token):
        print("[OK] config.py 已更新")
    else:
        print("[!] 自動更新失敗，請手動將 config.py 第 12 行的 Token 改為新值後再繼續")
        input("按 Enter 繼續...")

    # ── 更新 GitHub Secret ──
    _print_sep("步驟 2：更新 GitHub Secret")
    result = update_github_secret(new_token)
    if result is True:
        print("[OK] GitHub Secret TELEGRAM_BOT_TOKEN 已更新")
    elif result is None:
        print("[i] 未偵測到 gh CLI，略過此步驟")
        print("    ➜ 請手動到 GitHub > Settings > Secrets > Actions")
        print("      更新 TELEGRAM_BOT_TOKEN 為新 Token")
    else:
        print("[!] GitHub Secret 更新失敗，請手動更新")

    # ── Git push ──
    _print_sep("步驟 3：推送 config.py 到 GitHub")
    if push_to_github():
        print("[OK] 已推送到 GitHub main 分支")
    else:
        print("[!] 推送失敗，請手動執行：")
        print("    git add config.py")
        print("    git commit -m '緊急復原：更換 Bot Token'")
        print("    git push origin main")

    # ── 測試發送 ──
    _print_sep("步驟 4：發送測試訊息")
    ans = input("是否發送測試訊息到 Telegram 群組確認恢復？(Y/n) > ").strip().lower()
    if ans != "n":
        send_test_message(new_token)
    else:
        print("[i] 跳過測試發送")

    # ── 完成 ──
    _print_sep("復原完成")
    print()
    print("✅ Bot Token 已更換完畢！")
    print()
    print("提醒事項：")
    print("  • 如果是建立全新 Bot（非重新取得 Token）：")
    print("    請確認新 Bot 已被加入所有目標群組和 topic")
    print("  • GitHub Actions 下一次執行會自動使用新 Token")
    print("  • 如需立即發送，可執行 run_once.bat")
    print()

if __name__ == "__main__":
    main()
