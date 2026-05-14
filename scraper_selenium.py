from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import json
import os
import time
import threading
from datetime import datetime, timedelta, timezone
import re
import requests

# Selenium 啟動逾時（秒），避免卡住（GitHub Actions 下載 ChromeDriver 較慢）
SELENIUM_DRIVER_TIMEOUT = 60


from holdings_common import (
    _is_garbage_code,
    _is_garbage_name,
    _parse_percent,
    _resolve_weight_pct,
    dedupe_holdings_by_code,
    extract_holdings_list_from_embedded_json,
    json_row_quantity_kind,
    normalize_equity_lots_raw,
    parse_disclosure_date_from_html,
    refine_quantity_kind,
    shares_column_header_kind,
    load_previous_holdings,
    save_holdings,
    compare_holdings,
    format_report,
    format_today_holdings,
    send_to_telegram,
)
from scraper_requests import _table_column_indices

def setup_driver():
    """設置 Chrome WebDriver（支援 GitHub Actions 環境）"""
    import os
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 無頭模式
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    # GitHub Actions 環境：使用 Chromium
    chrome_bin = os.getenv('CHROME_BIN', None)
    if chrome_bin and os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin
        print(f"[OK] 使用 GitHub Actions 環境的 Chrome: {chrome_bin}")
    
    chromedriver_path = os.getenv('CHROMEDRIVER_PATH', None)
    
    # 方法1: 嘗試直接使用系統 PATH 中的 chromedriver（最快）
    try:
        if chromedriver_path and os.path.exists(chromedriver_path):
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"[OK] 使用指定的 ChromeDriver: {chromedriver_path}")
            return driver
        else:
            driver = webdriver.Chrome(options=chrome_options)
            print("[OK] 使用系統 ChromeDriver 啟動 Chrome")
            return driver
    except Exception as e1:
        print(f"系統 ChromeDriver 不可用: {e1}")
        
        # 方法2: 嘗試使用 webdriver-manager（如果已安裝）
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            print("正在下載 ChromeDriver（這可能需要一些時間，請耐心等待）...")
            print("提示：如果下載失敗，可以手動下載 ChromeDriver")
            try:
                driver_path = ChromeDriverManager().install()
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                print("[OK] 使用 webdriver-manager 啟動 Chrome")
                return driver
            except KeyboardInterrupt:
                print("\n下載被中斷")
                print("建議：手動下載 ChromeDriver 或使用 requests 版本")
                return None
            except Exception as e:
                print(f"webdriver-manager 下載失敗: {e}")
                print("建議：手動下載 ChromeDriver")
        except ImportError:
            print("webdriver-manager 未安裝")
        except Exception as e2:
            print(f"webdriver-manager 失敗: {e2}")
    
    # 方法3: 嘗試使用本地 chromedriver.exe（如果存在）
    import os
    local_driver = os.path.join(os.path.dirname(__file__), 'chromedriver.exe')
    if os.path.exists(local_driver):
        try:
            service = Service(local_driver)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("[OK] 使用本地 ChromeDriver 啟動 Chrome")
            return driver
        except Exception as e3:
            print(f"本地 ChromeDriver 失敗: {e3}")
    
    print("\n[FAIL] 無法啟動 Chrome WebDriver")
    print("\n解決方案:")
    print("1. 手動下載 ChromeDriver:")
    print("   - 訪問: https://chromedriver.chromium.org/downloads")
    print("   - 下載與您的 Chrome 版本匹配的 ChromeDriver")
    print("   - 將 chromedriver.exe 放在項目目錄或系統 PATH 中")
    print("2. 或安裝 webdriver-manager: pip install webdriver-manager")
    print("3. 或使用 requests + BeautifulSoup 版本（不需要 Selenium）")
    return None

def fetch_holdings_selenium():
    """使用 Selenium（或 API）抓取 00981A 持股明細。

    回傳 (持股 list 或 None, 網頁公告日字串或 None)。
    """
    url = "https://www.pocket.tw/etf/tw/00981A/fundholding"
    
    # 首先嘗試直接 API 請求（多個可能的端點）
    print("嘗試從 API 獲取數據...")
    api_urls = [
        "https://www.pocket.tw/api/etf/tw/00981A/holdings",
        "https://www.pocket.tw/api/v1/etf/tw/00981A/holdings",
        "https://api.pocket.tw/etf/tw/00981A/holdings",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Referer': url,
        'Origin': 'https://www.pocket.tw'
    }
    verify_ssl = os.getenv("ETF_REQUESTS_VERIFY_SSL", "1").strip().lower() not in ("0", "false", "no")

    for api_url in api_urls:
        try:
            print(f"  嘗試 API: {api_url}")
            response = requests.get(api_url, headers=headers, timeout=15, verify=verify_ssl)
            print(f"  API 回應狀態碼: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  API 回應類型: {type(data)}")
                    
                    # 嘗試不同的數據結構
                    holdings_list = None
                    if isinstance(data, dict):
                        if 'holdings' in data:
                            holdings_list = data['holdings']
                        elif 'data' in data and isinstance(data['data'], list):
                            holdings_list = data['data']
                        elif 'result' in data and isinstance(data['result'], list):
                            holdings_list = data['result']
                    elif isinstance(data, list):
                        holdings_list = data
                    
                    if holdings_list and len(holdings_list) > 0:
                        holdings = []
                        for item in holdings_list:
                            if isinstance(item, dict):
                                code = str(item.get('code', item.get('stockCode', item.get('symbol', '')))).strip()
                                name = str(item.get('name', item.get('stockName', item.get('stock_name', '')))).strip()
                                try:
                                    raw_s = int(
                                        item.get("shares", item.get("quantity", item.get("amount", 0))) or 0
                                    )
                                except (ValueError, TypeError):
                                    continue
                                shares = normalize_equity_lots_raw(raw_s, json_row_quantity_kind(item))

                                if len(code) == 4 and code.isdigit() and shares > 0:
                                    row = {"code": code, "name": name, "shares": shares}
                                    w = _resolve_weight_pct(item)
                                    if w is not None:
                                        row["weight_pct"] = w
                                    holdings.append(row)
                        
                        if holdings:
                            holdings = dedupe_holdings_by_code(holdings)
                            print(f"[OK] 從 API 成功獲取 {len(holdings)} 筆數據: {api_url}")
                            return (holdings, None)
                except json.JSONDecodeError as e:
                    print(f"  JSON 解析失敗: {e}")
                    print(f"  回應內容前 200 字元: {response.text[:200]}")
            else:
                print(f"  API 回應非 200: {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"  API 請求逾時: {api_url}")
        except requests.exceptions.RequestException as e:
            print(f"  API 請求錯誤: {type(e).__name__}: {e}")
        except Exception as e:
            print(f"  API 處理錯誤: {type(e).__name__}: {e}")
    
    print("所有 API 端點都失敗，改用 Selenium 載入網頁...")
    
    # 如果 API 失敗，使用 Selenium（帶逾時，避免卡住）
    driver = None
    driver_result = []
    driver_error = []

    def _run_driver():
        try:
            d = setup_driver()
            if d is not None:
                driver_result.append(d)
        except Exception as e:
            error_msg = f"Selenium 啟動異常: {type(e).__name__}: {e}"
            print(error_msg)
            driver_error.append(error_msg)

    th = threading.Thread(target=_run_driver, daemon=True)
    th.start()
    th.join(timeout=SELENIUM_DRIVER_TIMEOUT)
    if th.is_alive():
        print(f"[!] Selenium 啟動逾時（{SELENIUM_DRIVER_TIMEOUT} 秒），跳過")
        return (None, None)
    driver = driver_result[0] if driver_result else None
    if not driver:
        if driver_error:
            print(f"[!] Selenium 啟動失敗: {driver_error[0]}")
        return (None, None)
    
    page_date = None
    try:
        print("使用 Selenium 載入網頁...")
        driver.set_page_load_timeout(40)  # 設定頁面載入超時（增加到 40 秒）
        try:
            driver.get(url)
            print("  網頁已載入，等待內容...")
        except Exception as e:
            print(f"  頁面載入逾時或錯誤: {type(e).__name__}: {e}")
            print("  嘗試繼續解析當前頁面內容...")
        
        # 等待頁面載入完成（多種選擇器）
        wait_selectors = [
            (By.CSS_SELECTOR, "table"),
            (By.CSS_SELECTOR, "[class*='holding']"),
            (By.CSS_SELECTOR, "[class*='stock']"),
            (By.CSS_SELECTOR, "[data-code]"),
            (By.TAG_NAME, "tbody"),
        ]
        
        element_found = False
        for selector_type, selector_value in wait_selectors:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                print(f"  找到元素: {selector_value}")
                element_found = True
                break
            except Exception:
                continue
        
        if not element_found:
            print("  警告: 未找到預期的元素，繼續嘗試解析...")
        
        # 額外等待 JavaScript 執行，並等表格列變多（SPA 載入後才有持股）
        time.sleep(2)
        try:
            WebDriverWait(driver, 25).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr")) >= 15
            )
            print("  表格列已載入（>=15 tr）")
        except Exception:
            print("  警告: 等待表格列逾時，仍嘗試解析…")
        time.sleep(1)

        print("  開始解析頁面內容…")
        page_source = driver.page_source
        page_date = parse_disclosure_date_from_html(page_source)
        if page_date:
            print(f"  網頁「資料日期／更新時間」: {page_date}")

        def _parse_holdings_from_dom_tables():
            rows_out = []
            tables = driver.find_elements(By.TAG_NAME, "table")
            print(f"  找到 {len(tables)} 個表格（DOM）")

            for table_idx, table in enumerate(tables):
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) < 2:
                    continue

                header_row = rows[0]
                header_cells_raw = [c.text.strip() for c in header_row.find_elements(By.XPATH, "./*")]
                header_joined = " ".join(header_cells_raw)
                if "代號" not in header_joined and "名稱" not in header_joined:
                    continue

                print(f"  解析表格 #{table_idx + 1}，有 {len(rows)} 行（持股明細）")
                ic, ina, iw, ish, iu = _table_column_indices(header_cells_raw)
                hdr_kind = shares_column_header_kind(
                    header_cells_raw[ish] if ish < len(header_cells_raw) else ""
                )
                local = []

                for row in rows[1:]:
                    try:
                        cells = [c.text.strip() for c in row.find_elements(By.XPATH, "./*")]
                        max_idx = max(ic, ina, iw, ish)
                        if len(cells) <= max_idx:
                            continue

                        code_text = cells[ic].strip()
                        name_text = cells[ina].strip() if ina < len(cells) else ""
                        weight_text = cells[iw].strip() if iw < len(cells) else ""
                        holding_text = cells[ish].strip() if ish < len(cells) else ""
                        unit_text = cells[iu].strip() if iu is not None and iu < len(cells) else ""

                        code_match = re.search(r"^(\d{4})", code_text)
                        if not code_match:
                            continue

                        code = code_match.group(1)

                        if code_text.upper() in ["CASH", "MARGIN", "PFUR", "RDI"] or "現金" in name_text or "保證金" in name_text:
                            continue

                        digits = re.sub(r"[^\d]", "", holding_text or "")
                        if not digits:
                            continue
                        shares_raw = int(digits)

                        if "元" in unit_text or "NTD" in unit_text.upper():
                            continue

                        qk = refine_quantity_kind(hdr_kind, holding_text, unit_text)
                        shares = normalize_equity_lots_raw(shares_raw, qk)

                        if shares > 0 and len(code) == 4 and code.isdigit():
                            # 已依表頭／單位轉成「張」，最後一輪 normalize 須視為張，勿再當股除 1000
                            item = {"code": code, "name": name_text, "shares": shares, "unit": "張"}
                            w = _parse_percent(weight_text)
                            if w is not None:
                                item["weight_pct"] = w
                            local.append(item)
                            if len(local) <= 3:
                                print(f"    解析到: {name_text} ({code}) raw={shares_raw} → {shares} 張")
                    except Exception:
                        continue

                if len(local) > len(rows_out):
                    rows_out = local
                    print(f"  目前最佳 DOM 表格筆數: {len(rows_out)}")

            return rows_out

        holdings_dom = _parse_holdings_from_dom_tables()
        emb = extract_holdings_list_from_embedded_json(page_source)
        if emb:
            print(f"  從頁面內嵌 JSON（\"holdings\"）擷取 {len(emb)} 列")

        def _pick_dom_or_embedded(dom_h, emb_h):
            dc = len(dom_h) if dom_h else 0
            ec = len(emb_h) if emb_h else 0
            if dc >= 15:
                print(f"  [i] 採用 DOM 表格（{dc} 筆），優先於內嵌 JSON（避免快取較舊 JSON）")
                return list(dom_h)
            if ec >= 15:
                print(f"  [i] 採用內嵌 JSON（{ec} 筆）")
                return list(emb_h)
            if dc >= ec and dc > 0:
                print(f"  [i] 採用 DOM 表格（{dc} 筆）")
                return list(dom_h)
            if ec > 0:
                print(f"  [i] 採用內嵌 JSON（{ec} 筆）")
                return list(emb_h)
            return []

        holdings = _pick_dom_or_embedded(holdings_dom, emb)

        # 方法2: 查找 div 或其他元素結構
        if not holdings:
            try:
                stock_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='stock'], [class*='holding'], [data-code]")
                for elem in stock_elements:
                    try:
                        text = elem.text.strip()
                        code_match = re.search(r"(\d{4})", text)
                        if code_match:
                            code = code_match.group(1)
                            parent = elem.find_element(By.XPATH, "./..")
                            shares_text = parent.text
                            shares_match = re.search(r"([\d,]+)", shares_text.replace(",", ""))
                            if shares_match:
                                raw_s = int(shares_match.group(1).replace(",", ""))
                                shares = normalize_equity_lots_raw(raw_s, "auto")
                                name = re.sub(r"\d{4}", "", text).strip()
                                holdings.append({"code": code, "name": name, "shares": shares})
                    except Exception:
                        continue
            except Exception:
                pass

        if holdings:
            # 標準化並過濾垃圾（只保留乾淨持股）
            result = []
            for item_src in holdings:
                if not isinstance(item_src, dict):
                    continue
                code = str(item_src.get('code', item_src.get('stockCode', item_src.get('symbol', '')))).strip()
                name = str(item_src.get('name', item_src.get('stockName', item_src.get('stock_name', '')))).strip()
                try:
                    raw_s = int(item_src.get("shares", item_src.get("quantity", item_src.get("amount", 0))) or 0)
                except (ValueError, TypeError):
                    continue
                kind = json_row_quantity_kind(item_src)
                shares = normalize_equity_lots_raw(raw_s, kind)
                if len(code) != 4 or not code.isdigit() or shares <= 0:
                    continue
                if _is_garbage_code(code) or _is_garbage_name(name):
                    continue
                item = {'code': code, 'name': name, 'shares': shares}
                w = _resolve_weight_pct(item_src)
                if w is not None:
                    item['weight_pct'] = w
                result.append(item)

            if result:
                result = dedupe_holdings_by_code(result)
                print(f"[OK] 成功解析 {len(result)} 檔股票")
                return (result, page_date)
            else:
                print(f"[!] 解析到 {len(holdings)} 筆原始數據，但過濾後為空")
        
        # 如果所有方法都失敗，輸出頁面資訊用於調試
        print("[!] 所有解析方法都失敗")
        try:
            page_title = driver.title
            page_source_length = len(driver.page_source)
            print(f"  頁面標題: {page_title}")
            print(f"  頁面源碼長度: {page_source_length} 字元")
            print(f"  頁面 URL: {driver.current_url}")
        except:
            pass
        
        return (None, page_date)
        
    except Exception as e:
        print(f"抓取數據時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return (None, None)
    finally:
        driver.quit()

def main():
    """主函數（本機直接執行 scraper_selenium 時）。"""
    tw = timezone(timedelta(hours=8))
    today = datetime.now(tw)
    yesterday = today - timedelta(days=1)
    today_str = f"{today.year}/{today.month}/{today.day}"
    yesterday_str = f"{yesterday.year}/{yesterday.month}/{yesterday.day}"
    print(f"正在抓取 {today_str} 的持股數據...")
    print(f"比較日期: {yesterday_str} → {today_str}")
    current_holdings, _page_disclosure = fetch_holdings_selenium()
    if not current_holdings:
        print("[FAIL] 無法抓取持股數據")
        print("提示: 請確保已安裝 Chrome 瀏覽器和 ChromeDriver")
        return
    print(f"[OK] 成功抓取 {len(current_holdings)} 檔股票的持股數據")
    previous_data = load_previous_holdings(current_date_str=today_str)
    if previous_data:
        print(f"[OK] 載入 {previous_data['date']} 的歷史數據")
        changes = compare_holdings(current_holdings, previous_data)
        if changes:
            report = format_report(changes, previous_data['date'], today_str)
            print("\n" + "=" * 50)
            print(report)
            print("=" * 50 + "\n")
            import os
            try:
                from config import get_telegram_bot_token
                bot_token = get_telegram_bot_token()
            except ImportError:
                bot_token = None
            if not bot_token:
                for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "BOT_TOKEN"):
                    bot_token = (os.getenv(k) or "").strip() or None
                    if bot_token:
                        break
            if not bot_token:
                print("[!] 未設定 Bot Token（TELEGRAM_BOT_TOKEN 等），略過發送")
            else:
                send_to_telegram(report, bot_token)
    else:
        print("ℹ 沒有前一天的數據，僅保存當前數據")
        print("明天運行時將進行比較")
    save_holdings(current_holdings, today_str)


if __name__ == "__main__":
    main()
