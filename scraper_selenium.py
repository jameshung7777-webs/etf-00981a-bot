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
from datetime import datetime, timedelta
import re
import requests

# Selenium 啟動逾時（秒），避免卡住
SELENIUM_DRIVER_TIMEOUT = 20

# 排除明顯非股票名稱（CSS、HTML、版權等），與 scraper_requests 一致
def _is_garbage_name(name):
    if not name or len(name) > 30:
        return True
    if not isinstance(name, str):
        return True
    garbage = (
        '{', '}', ':', ';', 'px', 'rem', 'rgba', 'font', 'color', 'margin', 'padding',
        'schema', 'copyright', '©', '.title', 'data-v-', '#', 'display', 'flex',
        'justify-content', 'BreadcrumbList', 'version', 'pocket.tw', 'align-items',
        '.custom', '.fundholding', '.loading', '.text-', '.menu', '.search', '.nav-',
        '.footer', '.pageTitle', '.secondary-footer', '.default__', 'base64,'
    )
    name_lower = name.lower()
    return any(g in name_lower for g in garbage)

# 排除常見誤判代號
def _is_garbage_code(code):
    return code in ('0098', '2026')

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
    """使用 Selenium 抓取 00981A 持股明細"""
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
    
    for api_url in api_urls:
        try:
            print(f"  嘗試 API: {api_url}")
            response = requests.get(api_url, headers=headers, timeout=15)
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
                                shares = 0
                                if 'shares' in item:
                                    shares = int(item.get('shares', 0)) if item.get('shares') else 0
                                elif 'quantity' in item:
                                    shares = int(item.get('quantity', 0)) if item.get('quantity') else 0
                                elif 'amount' in item:
                                    shares = int(item.get('amount', 0)) if item.get('amount') else 0
                                
                                if len(code) == 4 and code.isdigit() and shares > 0:
                                    holdings.append({
                                        'code': code,
                                        'name': name,
                                        'shares': shares
                                    })
                        
                        if holdings:
                            print(f"[OK] 從 API 成功獲取 {len(holdings)} 筆數據: {api_url}")
                            return holdings
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
        return None
    driver = driver_result[0] if driver_result else None
    if not driver:
        if driver_error:
            print(f"[!] Selenium 啟動失敗: {driver_error[0]}")
        return None
    
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
        
        # 額外等待 JavaScript 執行
        time.sleep(3)
        print("  開始解析頁面內容...")
        
        holdings = []
        
        # 方法1: 查找持股明細表格（正確的表格結構）
        try:
            tables = driver.find_elements(By.TAG_NAME, "table")
            print(f"  找到 {len(tables)} 個表格，開始解析...")
            
            for table_idx, table in enumerate(tables):
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) < 2:
                    continue
                
                print(f"  解析表格 #{table_idx+1}，有 {len(rows)} 行")
                
                # 檢查表頭，確認是持股明細表格
                header_row = rows[0]
                header_text = header_row.text.lower()
                if '代號' not in header_text and '名稱' not in header_text:
                    # 可能不是持股明細表格，跳過
                    continue
                
                print(f"  確認是持股明細表格，開始解析數據行...")
                
                for row_idx, row in enumerate(rows[1:], 1):
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) < 4:  # 至少需要：代號、名稱、權重、持有數
                            continue
                        
                        # 解析表格結構：代號 | 名稱 | 權重 | 持有數 | 單位
                        code_text = cells[0].text.strip()
                        name_text = cells[1].text.strip() if len(cells) > 1 else ""
                        holding_text = cells[3].text.strip() if len(cells) > 3 else ""  # 持有數在第4列（索引3）
                        unit_text = cells[4].text.strip() if len(cells) > 4 else ""  # 單位在第5列（索引4）
                        
                        # 提取股票代號（4位數字）
                        code_match = re.search(r'^(\d{4})', code_text)
                        if not code_match:
                            # 跳過非股票項目（如 CASH, MARGIN 等）
                            continue
                        
                        code = code_match.group(1)
                        
                        # 過濾掉現金、保證金等非股票項目
                        if code_text.upper() in ['CASH', 'MARGIN', 'PFUR', 'RDI'] or '現金' in name_text or '保證金' in name_text:
                            continue
                        
                        # 提取持有數（股數）
                        # 移除千分位逗號
                        holding_clean = holding_text.replace(',', '').replace('，', '')
                        shares_match = re.search(r'([\d]+)', holding_clean)
                        
                        if not shares_match:
                            continue
                        
                        shares_raw = int(shares_match.group(1))
                        
                        # 根據單位轉換：如果是"股"，需要轉換為張數（1張=1000股）
                        # 如果是"元"，跳過（現金項目）
                        if '元' in unit_text or 'NTD' in unit_text.upper():
                            continue
                        
                        # 轉換為張數（1張 = 1000股）
                        shares = shares_raw // 1000
                        
                        if shares > 0 and len(code) == 4 and code.isdigit():
                            holdings.append({
                                'code': code,
                                'name': name_text,
                                'shares': shares
                            })
                            if len(holdings) <= 5:  # 只顯示前5筆的調試信息
                                print(f"    解析到: {name_text} ({code}) - {shares_raw} 股 = {shares} 張")
                    
                    except Exception as e:
                        continue
                
                if holdings:
                    print(f"  從表格 #{table_idx+1} 成功解析 {len(holdings)} 筆股票數據")
                    break
        except Exception as e:
            print(f"解析表格時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        # 方法2: 查找 div 或其他元素結構
        if not holdings:
            try:
                # 查找包含股票代號的元素
                stock_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='stock'], [class*='holding'], [data-code]")
                for elem in stock_elements:
                    try:
                        text = elem.text.strip()
                        code_match = re.search(r'(\d{4})', text)
                        if code_match:
                            code = code_match.group(1)
                            # 查找同一行或父元素中的數量
                            parent = elem.find_element(By.XPATH, "./..")
                            shares_text = parent.text
                            shares_match = re.search(r'([\d,]+)', shares_text.replace(',', ''))
                            if shares_match:
                                shares = int(shares_match.group(1).replace(',', ''))
                                name = re.sub(r'\d{4}', '', text).strip()
                                holdings.append({
                                    'code': code,
                                    'name': name,
                                    'shares': shares
                                })
                    except:
                        continue
            except:
                pass
        
        # 方法3: 從 script 標籤中提取 JSON
        if not holdings:
            print("嘗試從 JavaScript 中提取數據...")
            script_tags = driver.find_elements(By.TAG_NAME, "script")
            print(f"  找到 {len(script_tags)} 個 script 標籤")
            
            for i, script in enumerate(script_tags):
                try:
                    script_text = script.get_attribute('innerHTML') or script.text
                    if not script_text or len(script_text) < 50:
                        continue
                    
                    # 檢查是否包含相關關鍵字
                    if not any(keyword in script_text.lower() for keyword in ['holding', '00981', 'stock', 'fund']):
                        continue
                    
                    print(f"  檢查 script #{i+1} (長度: {len(script_text)})")
                    
                    # 查找 JSON 對象（更寬鬆的模式）
                    json_patterns = [
                        r'holdings["\']?\s*[:=]\s*(\[.*?\])',
                        r'"holdings"\s*:\s*(\[.*?\])',
                        r'data["\']?\s*[:=]\s*(\{.*?"holdings".*?\})',
                        r'(\[.*?"code".*?\])',
                        r'(\{.*?"code".*?\})',
                    ]
                    
                    for pattern in json_patterns:
                        try:
                            matches = re.findall(pattern, script_text, re.IGNORECASE | re.DOTALL)
                            for match in matches[:5]:  # 只處理前5個匹配
                                try:
                                    # 嘗試修復常見的 JSON 問題
                                    match_clean = match.strip()
                                    if not match_clean.startswith(('{', '[')):
                                        continue
                                    
                                    data = json.loads(match_clean)
                                    if isinstance(data, list) and len(data) > 0:
                                        holdings = data
                                        print(f"  從 script #{i+1} 成功提取列表數據")
                                        break
                                    elif isinstance(data, dict):
                                        if 'holdings' in data:
                                            holdings = data['holdings']
                                            print(f"  從 script #{i+1} 成功提取字典數據")
                                            break
                                        elif 'data' in data:
                                            holdings = data['data']
                                            print(f"  從 script #{i+1} 成功提取 data 數據")
                                            break
                                except json.JSONDecodeError:
                                    continue
                                except Exception as e:
                                    continue
                            
                            if holdings:
                                break
                        except Exception:
                            continue
                    
                    if holdings:
                        break
                except Exception as e:
                    continue
        
        if holdings:
            # 標準化並過濾垃圾（只保留乾淨持股）
            result = []
            for item in holdings:
                if not isinstance(item, dict):
                    continue
                code = str(item.get('code', item.get('stockCode', item.get('symbol', '')))).strip()
                name = str(item.get('name', item.get('stockName', item.get('stock_name', '')))).strip()
                try:
                    shares = int(item.get('shares', item.get('quantity', item.get('amount', 0))) or 0)
                except (ValueError, TypeError):
                    continue
                if len(code) != 4 or not code.isdigit() or shares <= 0:
                    continue
                if _is_garbage_code(code) or _is_garbage_name(name):
                    continue
                result.append({'code': code, 'name': name, 'shares': shares})
            
            if result:
                print(f"[OK] 成功解析 {len(result)} 檔股票")
                return result
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
        
        return None
        
    except Exception as e:
        print(f"抓取數據時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        driver.quit()

def load_previous_holdings(data_file=None):
    """載入「昨天」的持股數據做比較；優先讀取昨天日期的檔名，沒有再讀 holdings_data.json。會過濾垃圾項目。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    yesterday = (datetime.now() - timedelta(days=1))
    yesterday_prefix = f"holdings_data_{yesterday:%Y-%m-%d}_"
    # 優先：昨天日期的檔案（取時間最新的一筆）
    if data_file is None:
        try:
            import glob
            pattern = os.path.join(base_dir, yesterday_prefix + "*.json")
            files = glob.glob(pattern)
            if files:
                files.sort(reverse=True)
                data_file = files[0]
            else:
                data_file = os.path.join(base_dir, "holdings_data.json")
        except Exception:
            data_file = os.path.join(base_dir, "holdings_data.json")
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data and 'holdings' in data:
                clean = [h for h in data['holdings']
                         if isinstance(h, dict) and h.get('code') and h.get('name')
                         and not _is_garbage_code(str(h.get('code', '')))
                         and not _is_garbage_name(str(h.get('name', '')))]
                data = {'date': data['date'], 'holdings': clean}
            return data
        except Exception as e:
            print(f"載入歷史數據時發生錯誤: {e}")
            return None
    return None

def save_holdings(holdings, date_str, data_file=None):
    """保存當前持股數據。會寫入：帶日期時間的檔案 + holdings_data.json（供下次比較用）"""
    from datetime import datetime
    now = datetime.now()
    data = {
        'date': date_str,
        'holdings': holdings
    }
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # 帶日期與時間的檔名，例如 holdings_data_2025-02-04_1430.json
    dated_file = os.path.join(base_dir, f"holdings_data_{now:%Y-%m-%d}_{now:%H%M}.json")
    latest_file = os.path.join(base_dir, "holdings_data.json")
    try:
        with open(dated_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(latest_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已保存 {date_str} 的持股數據 -> {os.path.basename(dated_file)}")
    except Exception as e:
        print(f"保存數據時發生錯誤: {e}")

def compare_holdings(current, previous):
    """比較持股變化"""
    if not previous or 'holdings' not in previous:
        return None
    
    prev_holdings = {h['code']: h for h in previous['holdings']}
    curr_holdings = {h['code']: h for h in current}
    
    # 找出新增和刪除
    added = []
    removed = []
    increased = []
    decreased = []
    
    current_codes = set(curr_holdings.keys())
    previous_codes = set(prev_holdings.keys())
    
    # 新增的股票
    for code in current_codes - previous_codes:
        added.append(curr_holdings[code])
    
    # 刪除的股票
    for code in previous_codes - current_codes:
        removed.append(prev_holdings[code])
    
    # 持股變化
    for code in current_codes & previous_codes:
        curr_shares = curr_holdings[code]['shares']
        prev_shares = prev_holdings[code]['shares']
        
        if curr_shares > prev_shares:
            increased.append({
                'code': code,
                'name': curr_holdings[code]['name'],
                'prev': prev_shares,
                'curr': curr_shares,
                'diff': curr_shares - prev_shares
            })
        elif curr_shares < prev_shares:
            decreased.append({
                'code': code,
                'name': curr_holdings[code]['name'],
                'prev': prev_shares,
                'curr': curr_shares,
                'diff': prev_shares - curr_shares
            })
    
    # 按變化量排序
    increased.sort(key=lambda x: x['diff'], reverse=True)
    decreased.sort(key=lambda x: x['diff'], reverse=True)
    
    return {
        'added': added,
        'removed': removed,
        'increased': increased,
        'decreased': decreased
    }

def format_today_holdings(holdings, date_str):
    """格式化「今日持股」訊息（供 Telegram 第一則）；僅含乾淨項目，避免 CSS/HTML 混入"""
    clean = [h for h in holdings
             if isinstance(h, dict) and h.get('name') and h.get('code')
             and not _is_garbage_code(str(h.get('code', '')))
             and not _is_garbage_name(str(h.get('name', '')))]
    lines = [f"00981A 今日持股明細（{date_str}）", ""]
    for h in sorted(clean, key=lambda x: (x.get('name') or '')):
        lines.append(f"・{h['name']}（{h['code']}）：{h['shares']:,} 張")
    lines.append("")
    lines.append("＊以上為「張數」整理（1 張＝1,000 股），僅供參考，未涉及投資建議。")
    return "\n".join(lines)

def format_report(changes, prev_date, curr_date):
    """格式化「與前日比較」報告（供 Telegram 第二則）"""
    report = f"00981A 持股更新（{prev_date} → {curr_date}）\n\n"
    
    # 新增/刪除（只顯示乾淨項目，過濾 CSS/版權等）
    def _ok(h):
        n = (h.get('name') or '')
        return n and not _is_garbage_name(n) and not _is_garbage_code(str(h.get('code', '')))
    added_clean = [h for h in changes['added'] if _ok(h)]
    removed_clean = [h for h in changes['removed'] if _ok(h)]
    
    report += "🆕 新增／刪除\n"
    if added_clean:
        added_list = [f"・{h['name']}（{h['code']}）：{h['shares']:,} 張" for h in added_clean]
        report += "・新增：\n" + "\n".join(added_list) + "。\n"
    else:
        report += "・新增：無。\n"
    
    if removed_clean:
        removed_list = [f"・{h['name']}（{h['code']}）：{h['shares']:,} 張" for h in removed_clean]
        report += "・刪除：\n" + "\n".join(removed_list) + "。\n"
    else:
        report += "・刪除：無。\n"
    
    # 加碼/減碼（只顯示乾淨名稱）
    increased_clean = [x for x in changes['increased'] if _ok(x)]
    decreased_clean = [x for x in changes['decreased'] if _ok(x)]
    report += "\n📈 主要加碼一覽（張數增加）\n"
    if increased_clean:
        for item in increased_clean:
            report += f"・{item['name']}（{item['code']}）：＋{item['diff']:,} 張（{item['prev']:,} → {item['curr']:,} 張）。\n"
    else:
        report += "・無。\n"
    
    report += "\n📉 主要減碼一覽（張數減少）\n"
    if decreased_clean:
        for item in decreased_clean:
            report += f"・{item['name']}（{item['code']}）：－{item['diff']:,} 張（{item['prev']:,} → {item['curr']:,} 張）。\n"
    else:
        report += "・無。\n"
    
    report += "\n＊以上為「張數」變動整理（1 張＝1,000 股），僅為持股結構異動說明，未涉及股價或投資建議。"
    
    return report

# Telegram 單則訊息上限 4096 字元，分段時用 4000 保留餘裕
TELEGRAM_MAX_MESSAGE_LENGTH = 4000

def _split_message(text, max_len=TELEGRAM_MAX_MESSAGE_LENGTH):
    """將過長訊息依換行分段，每段不超過 max_len"""
    if len(text) <= max_len:
        return [text]
    chunks = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            chunks.append(rest)
            break
        part = rest[:max_len]
        last_nl = part.rfind("\n")
        if last_nl > max_len // 2:
            chunks.append(rest[: last_nl + 1])
            rest = rest[last_nl + 1 :]
        else:
            chunks.append(rest[:max_len])
            rest = rest[max_len:]
    return chunks

def send_to_telegram(message, bot_token, chat_id=None):
    """發送消息到 Telegram（若超過長度限制會自動分段發送）"""
    if not chat_id:
        updates_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        try:
            response = requests.get(updates_url, timeout=10)
            updates = response.json()
            if updates.get('result') and len(updates['result']) > 0:
                chat_id = updates['result'][-1]['message']['chat']['id']
                print(f"自動獲取到 chat_id: {chat_id}")
            else:
                print("無法自動獲取 chat_id，請手動提供")
                print("您可以發送任意消息給 bot，然後重新運行腳本")
                return False
        except Exception as e:
            print(f"獲取 chat_id 時發生錯誤: {e}")
            return False
    
    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = _split_message(message)
    if len(chunks) > 5:
        chunks = chunks[:5]
        chunks[-1] = chunks[-1] + "\n\n…（訊息過長已截斷）"
    all_ok = True
    
    for i, chunk in enumerate(chunks):
        data = {"chat_id": chat_id, "text": chunk}
        try:
            response = requests.post(send_url, json=data, timeout=10)
            body = response.json() if response.text else {}
            if response.status_code == 200 and body.get("ok"):
                if len(chunks) > 1:
                    print(f"[OK] 訊息第 {i + 1}/{len(chunks)} 段已發送")
                else:
                    print("[OK] 消息已成功發送到 Telegram")
            else:
                all_ok = False
                err = body.get("description", response.text or f"HTTP {response.status_code}")
                print(f"發送失敗: {err}")
        except Exception as e:
            all_ok = False
            print(f"發送消息時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
    return all_ok

def main():
    """主函數"""
    # 獲取當前日期
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    today_str = f"{today.month}/{today.day}"
    yesterday_str = f"{yesterday.month}/{yesterday.day}"
    
    print(f"正在抓取 {today_str} 的持股數據...")
    print(f"比較日期: {yesterday_str} → {today_str}")
    
    # 抓取當前持股
    current_holdings = fetch_holdings_selenium()
    
    if not current_holdings:
        print("[FAIL] 無法抓取持股數據")
        print("提示: 請確保已安裝 Chrome 瀏覽器和 ChromeDriver")
        return
    
    print(f"[OK] 成功抓取 {len(current_holdings)} 檔股票的持股數據")
    
    # 載入前一天的數據
    previous_data = load_previous_holdings()
    
    if previous_data:
        print(f"[OK] 載入 {previous_data['date']} 的歷史數據")
        # 比較變化
        changes = compare_holdings(current_holdings, previous_data)
        if changes:
            report = format_report(changes, previous_data['date'], today_str)
            print("\n" + "="*50)
            print(report)
            print("="*50 + "\n")
            
            # 發送到 Telegram
            bot_token = "8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo"
            send_to_telegram(report, bot_token)
    else:
        print("ℹ 沒有前一天的數據，僅保存當前數據")
        print("明天運行時將進行比較")
    
    # 保存當前數據
    save_holdings(current_holdings, today_str)

if __name__ == "__main__":
    main()
