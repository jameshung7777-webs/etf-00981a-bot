"""
使用 requests + BeautifulSoup 的版本（不需要 Selenium）
如果 Selenium 版本無法使用，可以使用這個版本
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re

from holdings_common import (
    _is_garbage_code,
    _is_garbage_name,
    _parse_percent,
    _resolve_weight_pct,
    load_previous_holdings,
    save_holdings,
    compare_holdings,
    format_report,
    format_today_holdings,
    send_to_telegram,
)

def fetch_holdings_requests():
    """使用 requests 抓取 00981A 持股明細（僅從表格或 JSON 取數，不掃整頁避免抓到 CSS/HTML）"""
    url = "https://www.pocket.tw/etf/tw/00981A/fundholding"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.pocket.tw/'
    }
    
    try:
        print("正在請求網頁...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"  網頁回應狀態碼: {response.status_code}")
        print(f"  網頁內容長度: {len(response.text)} 字元")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 方法1: 從 script 中提取 JSON（僅限明確的 holdings 結構）
        holdings = []
        script_count = 0
        for script in soup.find_all('script'):
            script_text = script.string or script.get_text()
            if not script_text or len(script_text) < 50:
                continue
            
            script_count += 1
            # 檢查是否包含相關關鍵字
            if not any(keyword in script_text.lower() for keyword in ['holding', '00981', 'stock', 'fund', 'etf']):
                continue
            
            print(f"  檢查 script #{script_count} (長度: {len(script_text)})")
            
            json_patterns = [
                r'holdings["\']?\s*[:=]\s*(\[.*?\])',
                r'"holdings"\s*:\s*(\[.*?\])',
                r'data["\']?\s*[:=]\s*(\{.*?"holdings".*?\})',
                r'(\[.*?"code".*?\])',
            ]
            for pattern in json_patterns:
                matches = re.findall(pattern, script_text, re.IGNORECASE | re.DOTALL)
                for match in matches[:3]:  # 只處理前3個匹配
                    try:
                        match_clean = match.strip()
                        if not match_clean.startswith(('{', '[')):
                            continue
                        data = json.loads(match_clean)
                        if isinstance(data, list) and len(data) > 0:
                            holdings = data
                            print(f"  從 script #{script_count} 成功提取列表數據")
                            break
                        elif isinstance(data, dict) and 'holdings' in data:
                            holdings = data['holdings']
                            print(f"  從 script #{script_count} 成功提取字典數據")
                            break
                    except json.JSONDecodeError as e:
                        continue
                    except Exception:
                        continue
                if holdings:
                    break
            if holdings:
                break
        
        # 方法2: 解析持股明細表格（正確的表格結構：代號 | 名稱 | 權重 | 持有數 | 單位）
        if not holdings:
            print("嘗試解析 HTML 表格...")
            tables = soup.find_all('table')
            print(f"  找到 {len(tables)} 個表格")
            
            for table_idx, table in enumerate(tables):
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue
                
                # 檢查表頭，確認是持股明細表格
                header_row = rows[0]
                header_cells = [c.get_text(strip=True).lower() for c in header_row.find_all(['td', 'th'])]
                header_text = ' '.join(header_cells)
                
                if '代號' not in header_text and '名稱' not in header_text:
                    # 可能不是持股明細表格，跳過
                    continue
                
                print(f"  解析表格 #{table_idx+1}，有 {len(rows)} 行（確認是持股明細表格）")
                
                for row_idx, row in enumerate(rows[1:], 1):
                    cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                    if len(cells) < 4:  # 至少需要：代號、名稱、權重、持有數
                        continue
                    
                    # 解析表格結構：代號 | 名稱 | 權重 | 持有數 | 單位
                    code_text = cells[0].strip()
                    name_text = cells[1].strip() if len(cells) > 1 else ""
                    weight_text = cells[2].strip() if len(cells) > 2 else ""  # 權重在第3列（索引2）
                    holding_text = cells[3].strip() if len(cells) > 3 else ""  # 持有數在第4列（索引3）
                    unit_text = cells[4].strip() if len(cells) > 4 else ""  # 單位在第5列（索引4）
                    
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
                    
                    if shares > 0 and len(code) == 4 and code.isdigit() and not _is_garbage_name(name_text):
                        item = {'code': code, 'name': name_text, 'shares': shares}
                        w = _parse_percent(weight_text)
                        if w is not None:
                            item['weight_pct'] = w
                        holdings.append(item)
                        if len(holdings) <= 5:  # 只顯示前5筆的調試信息
                            print(f"    解析到: {name_text} ({code}) - {shares_raw} 股 = {shares} 張")
                
                if holdings:
                    print(f"  從表格 #{table_idx+1} 成功解析 {len(holdings)} 筆股票數據")
                    break
        
        # 方法3: 僅從「非 script/style」的純文字中抓「・名稱（1234）：數字 張」一行一行
        if not holdings:
            print("嘗試從頁面文字匹配持股行...")
            bad_tags = {'script', 'style', 'svg', 'noscript'}
            for tag in soup.find_all(['p', 'div', 'td', 'li', 'span']):
                if tag.name in bad_tags or tag.find_parent(bad_tags):
                    continue
                text = tag.get_text(strip=True)
                if len(text) > 200:  # 跳過整塊 CSS 等
                    continue
                for m in re.finditer(r'[・·]?\s*([^（(]+)[（(](\d{4})[）)]\s*[：:]\s*([\d,]+)\s*張', text):
                    name_, code_, num_ = m.group(1).strip(), m.group(2), m.group(3).replace(',', '')
                    if _is_garbage_name(name_) or not num_.isdigit():
                        continue
                    shares_ = int(num_)
                    if 0 < shares_ < 10000000:
                        holdings.append({'code': code_, 'name': name_, 'shares': shares_})
            if holdings:
                holdings = list({(h['code']): h for h in holdings}.values())  # 去重
        
        # 標準化並過濾垃圾
        if holdings:
            result = []
            for item_src in holdings:
                if not isinstance(item_src, dict):
                    continue
                code = str(item_src.get('code', item_src.get('stockCode', ''))).strip()
                name = str(item_src.get('name', item_src.get('stockName', ''))).strip()
                try:
                    shares = int(item_src.get('shares', item_src.get('quantity', 0)) or 0)
                except (ValueError, TypeError):
                    continue
                if len(code) != 4 or not code.isdigit() or shares <= 0:
                    continue
                if code in ('0098', '2026'):  # 常見誤判（00981A 縮寫、年份）
                    continue
                if _is_garbage_name(name):
                    continue
                item = {'code': code, 'name': name, 'shares': shares}
                w = _resolve_weight_pct(item_src)
                if w is not None:
                    item['weight_pct'] = w
                result.append(item)
            if result:
                print(f"[OK] 成功解析 {len(result)} 檔股票")
                return result
        
        print("[FAIL] 無法從網頁中提取持股數據")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"網絡請求失敗: {e}")
        return None
    except Exception as e:
        print(f"抓取數據時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return None

