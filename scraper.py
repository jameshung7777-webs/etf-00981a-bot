import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import re

def fetch_holdings():
    """抓取 00981A 持股明細"""
    url = "https://www.pocket.tw/etf/tw/00981A/fundholding"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 嘗試解析 JSON 數據（如果網站使用 API）
        # 或者解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找持股數據（需要根據實際網頁結構調整）
        # 通常這類網站會使用 JavaScript 動態載入數據
        # 可能需要查找 script 標籤中的 JSON 數據
        
        # 嘗試從 script 標籤中提取 JSON
        scripts = soup.find_all('script')
        holdings_data = None
        
        for script in scripts:
            if script.string and 'holdings' in script.string.lower():
                # 嘗試提取 JSON 數據
                text = script.string
                # 查找 JSON 對象
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        if 'holdings' in str(data).lower() or 'fund' in str(data).lower():
                            holdings_data = data
                            break
                    except:
                        pass
        
        # 如果找不到 JSON，嘗試解析 HTML 表格
        if not holdings_data:
            # 查找表格
            tables = soup.find_all('table')
            holdings = []
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # 跳過標題行
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        # 假設格式：股票代號/名稱, 持股數量
                        stock_code = cols[0].get_text(strip=True)
                        shares = cols[1].get_text(strip=True)
                        
                        # 提取股票代號和名稱
                        code_match = re.search(r'(\d{4})', stock_code)
                        name_match = re.search(r'[^\d]+', stock_code)
                        
                        if code_match:
                            code = code_match.group(1)
                            name = name_match.group(0) if name_match else ''
                            # 提取張數（假設格式為 "X,XXX 張"）
                            shares_match = re.search(r'([\d,]+)', shares.replace(',', ''))
                            if shares_match:
                                shares_num = int(shares_match.group(1).replace(',', ''))
                                holdings.append({
                                    'code': code,
                                    'name': name.strip(),
                                    'shares': shares_num
                                })
            
            return holdings if holdings else None
        
        return holdings_data
        
    except Exception as e:
        print(f"抓取數據時發生錯誤: {e}")
        return None

def load_previous_holdings():
    """載入前一天的持股數據"""
    data_file = "holdings_data.json"
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    return None

def save_holdings(holdings, date_str):
    """保存當前持股數據"""
    data_file = "holdings_data.json"
    data = {
        'date': date_str,
        'holdings': holdings
    }
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

def format_report(changes, prev_date, curr_date):
    """格式化報告"""
    report = f"00981A 持股更新（{prev_date} → {curr_date}）\n\n"
    
    # 新增/刪除
    report += "🆕 新增／刪除\n"
    if changes['added']:
        added_list = [f"・{h['name']}（{h['code']}）：{h['shares']:,} 張" for h in changes['added']]
        report += "・新增：\n" + "\n".join(added_list) + "。\n"
    else:
        report += "・新增：無。\n"
    
    if changes['removed']:
        removed_list = [f"・{h['name']}（{h['code']}）：{h['shares']:,} 張" for h in changes['removed']]
        report += "・刪除：\n" + "\n".join(removed_list) + "。\n"
    else:
        report += "・刪除：無。\n"
    
    # 加碼
    report += "\n📈 主要加碼一覽（張數增加）\n"
    if changes['increased']:
        for item in changes['increased']:
            report += f"・{item['name']}（{item['code']}）：＋{item['diff']:,} 張（{item['prev']:,} → {item['curr']:,} 張）。\n"
    else:
        report += "・無。\n"
    
    # 減碼
    report += "\n📉 主要減碼一覽（張數減少）\n"
    if changes['decreased']:
        for item in changes['decreased']:
            report += f"・{item['name']}（{item['code']}）：－{item['diff']:,} 張（{item['prev']:,} → {item['curr']:,} 張）。\n"
    else:
        report += "・無。\n"
    
    report += "\n＊以上為「張數」變動整理（1 張＝1,000 股），僅為持股結構異動說明，未涉及股價或投資建議。"
    
    return report

def send_to_telegram(message, bot_token, chat_id=None):
    """發送消息到 Telegram"""
    # 如果沒有提供 chat_id，使用 getUpdates 獲取最新的聊天 ID
    if not chat_id:
        # 先獲取更新以找到 chat_id
        updates_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        try:
            response = requests.get(updates_url)
            updates = response.json()
            if updates.get('result'):
                chat_id = updates['result'][-1]['message']['chat']['id']
            else:
                print("無法獲取 chat_id，請手動提供")
                return False
        except Exception as e:
            print(f"獲取 chat_id 時發生錯誤: {e}")
            return False
    
    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(send_url, json=data)
        response.raise_for_status()
        print("消息已成功發送到 Telegram")
        return True
    except Exception as e:
        print(f"發送消息時發生錯誤: {e}")
        return False

if __name__ == "__main__":
    # 獲取當前日期
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    today_str = f"{today.month}/{today.day}"
    yesterday_str = f"{yesterday.month}/{yesterday.day}"
    
    print(f"正在抓取 {today_str} 的持股數據...")
    
    # 抓取當前持股
    current_holdings = fetch_holdings()
    
    if not current_holdings:
        print("無法抓取持股數據，可能需要使用 Selenium 處理動態內容")
        exit(1)
    
    # 載入前一天的數據
    previous_data = load_previous_holdings()
    
    if previous_data:
        # 比較變化
        changes = compare_holdings(current_holdings, previous_data)
        if changes:
            report = format_report(changes, previous_data['date'], today_str)
            print("\n" + report)
            
            # 發送到 Telegram
            bot_token = "8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo"
            send_to_telegram(report, bot_token)
    else:
        print("沒有前一天的數據，僅保存當前數據")
    
    # 保存當前數據
    save_holdings(current_holdings, today_str)
    print(f"\n已保存 {today_str} 的持股數據")
