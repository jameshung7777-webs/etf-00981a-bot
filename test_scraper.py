"""
測試腳本 - 用於調試和驗證爬蟲功能
"""

from scraper_selenium import fetch_holdings_selenium, save_holdings
from datetime import datetime

def test_fetch():
    """測試抓取功能"""
    print("開始測試抓取功能...")
    print("="*60)
    
    holdings = fetch_holdings_selenium()
    
    if holdings:
        print(f"\n[OK] 成功抓取 {len(holdings)} 檔股票")
        print("\n前 10 檔股票:")
        for i, h in enumerate(holdings[:10], 1):
            print(f"{i}. {h['name']} ({h['code']}): {h['shares']:,} 張")
        
        # 保存測試數據
        today = datetime.now()
        today_str = f"{today.month}/{today.day}"
        save_holdings(holdings, today_str)
        print(f"\n[OK] 測試數據已保存")
    else:
        print("\n[FAIL] 抓取失敗")
        print("\n請檢查:")
        print("1. 網絡連接")
        print("2. Chrome 和 ChromeDriver 是否正確安裝")
        print("3. 網站是否可訪問")

if __name__ == "__main__":
    test_fetch()
