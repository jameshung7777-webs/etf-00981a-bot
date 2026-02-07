"""
Debug 與測試腳本：在給出修改前先跑此腳本驗證。
- 測試 requests 抓取頁面與解析
- 測試 main 流程不會卡住（先 requests 再 Selenium 逾時）
"""

import sys
import os
import io

# Windows 主控台 UTF-8
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def test_requests_fetch():
    """測試 requests 版本能否抓取並解析"""
    print("=" * 50)
    print("1. 測試 requests 抓取...")
    print("=" * 50)
    try:
        from scraper_requests import fetch_holdings_requests
        holdings = fetch_holdings_requests()
        if holdings and len(holdings) > 0:
            print(f"   OK: 取得 {len(holdings)} 檔持股，前 3 筆: {holdings[:3]}")
            return True
        print("   結果: 無法解析出持股（可能是網頁結構變動）")
        return False
    except Exception as e:
        print(f"   錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_main_no_hang():
    """測試 main 流程不會卡住（限時內跑完）"""
    print("\n" + "=" * 50)
    print("2. 測試 main 流程（限時 45 秒）...")
    print("=" * 50)
    import threading
    result = {"done": False, "error": None}

    def run_main():
        try:
            from main import main
            main()
            result["done"] = True
        except Exception as e:
            result["error"] = e
            result["done"] = True

    th = threading.Thread(target=run_main, daemon=True)
    th.start()
    th.join(timeout=45)
    if th.is_alive():
        print("   逾時: main 在 45 秒內未結束（可能卡在 Selenium）")
        return False
    if result.get("error"):
        print(f"   錯誤: {result['error']}")
        import traceback
        traceback.print_exc()
        return False
    print("   OK: main 正常結束")
    return True


if __name__ == "__main__":
    r1 = test_requests_fetch()
    r2 = test_main_no_hang()
    print("\n" + "=" * 50)
    print("結果: requests 抓取=%s, main 不卡住=%s" % (r1, r2))
    print("=" * 50)
    sys.exit(0 if (r1 or r2) else 1)
