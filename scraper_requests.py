"""
使用 requests + BeautifulSoup 的版本（不需要 Selenium）
如果 Selenium 版本無法使用，可以使用這個版本
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timedelta

# 排除明顯非股票名稱的內容（CSS、HTML、版權等）
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

def _is_garbage_code(code):
    return code in ('0098', '2026')


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
                        holdings.append({'code': code, 'name': name_text, 'shares': shares})
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
            for item in holdings:
                if not isinstance(item, dict):
                    continue
                code = str(item.get('code', item.get('stockCode', ''))).strip()
                name = str(item.get('name', item.get('stockName', ''))).strip()
                try:
                    shares = int(item.get('shares', item.get('quantity', 0)) or 0)
                except (ValueError, TypeError):
                    continue
                if len(code) != 4 or not code.isdigit() or shares <= 0:
                    continue
                if code in ('0098', '2026'):  # 常見誤判（00981A 縮寫、年份）
                    continue
                if _is_garbage_name(name):
                    continue
                result.append({'code': code, 'name': name, 'shares': shares})
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

# 導入其他必要的函數（這些函數在兩個文件中都相同）
import json
import os
import requests

def load_previous_holdings(data_file=None):
    """載入「昨天」的持股數據做比較；優先讀取昨天日期的檔名，沒有再讀 holdings_data.json。會過濾垃圾項目。"""
    from datetime import datetime, timedelta
    base_dir = os.path.dirname(os.path.abspath(__file__))
    yesterday = (datetime.now() - timedelta(days=1))
    yesterday_prefix = f"holdings_data_{yesterday:%Y-%m-%d}_"
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
    parts = str(date_str or "").split("/")
    if not parts or len(parts[0]) != 4:
        date_str = f"{now.year}/{now.month}/{now.day}"
    data = {
        'date': date_str,
        'holdings': holdings
    }
    base_dir = os.path.dirname(os.path.abspath(__file__))
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
    
    added = []
    removed = []
    increased = []
    decreased = []
    
    current_codes = set(curr_holdings.keys())
    previous_codes = set(prev_holdings.keys())
    
    for code in current_codes - previous_codes:
        added.append(curr_holdings[code])
    
    for code in previous_codes - current_codes:
        removed.append(prev_holdings[code])
    
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
    """格式化「與前日比較」報告（供 Telegram 第二則）；只顯示乾淨項目"""
    def _ok(h):
        n = (h.get('name') or '')
        return n and not _is_garbage_name(n) and not _is_garbage_code(str(h.get('code', '')))
    added_clean = [h for h in changes['added'] if _ok(h)]
    removed_clean = [h for h in changes['removed'] if _ok(h)]
    
    report = f"00981A 持股更新（{prev_date} → {curr_date}）\n\n"
    
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

def send_to_telegram(message, bot_token, chat_id=None, message_thread_id=None):
    """發送消息到 Telegram（若超過長度限制會自動分段發送）。
    message_thread_id: 群組內 Topic/討論串 ID，不設則發到一般聊天。"""
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
    # 單次最多發 5 段，避免異常長文導致狂發
    if len(chunks) > 5:
        chunks = chunks[:5]
        chunks[-1] = chunks[-1] + "\n\n…（訊息過長已截斷）"
    all_ok = True
    
    for i, chunk in enumerate(chunks):
        data = {"chat_id": chat_id, "text": chunk}
        if message_thread_id is not None:
            data["message_thread_id"] = int(message_thread_id)
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
