"""
使用 requests + BeautifulSoup 的版本（不需要 Selenium）
如果 Selenium 版本無法使用，可以使用這個版本
"""

import os
import time
import warnings
import requests
from bs4 import BeautifulSoup
import re

if os.getenv("ETF_REQUESTS_VERIFY_SSL", "1").strip().lower() in ("0", "false", "no"):
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

from holdings_common import (
    _is_garbage_name,
    _parse_percent,
    dedupe_holdings_by_code,
    extract_holdings_list_from_embedded_json,
    holding_cell_looks_like_weight,
    normalize_equity_lots_raw,
    parse_disclosure_date_from_html,
    refine_quantity_kind,
    shares_column_header_kind,
    standardize_holdings_rows,
    table_column_indices,
    validate_fetched_holdings,
    load_previous_holdings,
    save_holdings,
    compare_holdings,
    format_report,
    format_today_holdings,
    send_to_telegram,
)


def fetch_holdings_requests():
    """使用 requests 抓取 00981A 持股明細。

    回傳 (持股 list 或 None, 網頁「資料日期／更新時間」字串或 None)。
    第二個值若存在，應寫入 JSON 的 date，避免與本機日曆與公告日不一致。
    """
    url = "https://www.pocket.tw/etf/tw/00981A/fundholding"
    fetch_url = f"{url}?_={int(time.time())}"
    verify_ssl = os.getenv("ETF_REQUESTS_VERIFY_SSL", "1").strip().lower() not in ("0", "false", "no")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.pocket.tw/',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    
    try:
        print("正在請求網頁...")
        try:
            response = requests.get(fetch_url, headers=headers, timeout=30, verify=verify_ssl)
        except requests.exceptions.SSLError as ssl_err:
            if verify_ssl:
                print(f"  SSL 驗證失敗，改以 verify=False 重試一次（可設 ETF_REQUESTS_VERIFY_SSL=0 略過）: {ssl_err}")
                response = requests.get(fetch_url, headers=headers, timeout=30, verify=False)
            else:
                raise
        response.raise_for_status()
        print(f"  網頁回應狀態碼: {response.status_code}")
        html = response.text
        print(f"  網頁內容長度: {len(html)} 字元")

        page_date = parse_disclosure_date_from_html(html)
        if page_date:
            print(f"  網頁「資料日期／更新時間」: {page_date}")

        soup = BeautifulSoup(html, "html.parser")

        holdings = []
        embedded = extract_holdings_list_from_embedded_json(html)
        if embedded:
            print(f"  從內嵌 JSON（\"holdings\" 陣列）擷取 {len(embedded)} 列（已避開正則誤匹配小段）")
            holdings = list(embedded)
        else:
            embedded_loose = extract_holdings_list_from_embedded_json(html, min_score=5)
            if embedded_loose:
                print(f"  從內嵌 JSON（寬鬆門檻）擷取 {len(embedded_loose)} 列")
                holdings = list(embedded_loose)

        # 方法2: 解析持股明細表格（依表頭對應欄位，適用欄序調整）
        if not holdings:
            print("嘗試解析 HTML 表格...")
            tables = soup.find_all("table")
            print(f"  找到 {len(tables)} 個表格")

            for table_idx, table in enumerate(tables):
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue

                header_row = rows[0]
                header_cells_raw = [c.get_text(strip=True) for c in header_row.find_all(["td", "th"])]
                header_joined = " ".join(header_cells_raw)

                if "代號" not in header_joined and "名稱" not in header_joined:
                    continue

                print(f"  解析表格 #{table_idx + 1}，有 {len(rows)} 行（確認是持股明細表格）")
                ic, ina, iw, ish, iu = table_column_indices(header_cells_raw)
                hdr_kind = shares_column_header_kind(
                    header_cells_raw[ish] if ish < len(header_cells_raw) else ""
                )

                for row_idx, row in enumerate(rows[1:], 1):
                    cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
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

                    if holding_cell_looks_like_weight(holding_text):
                        continue

                    digits = re.sub(r"[^\d]", "", holding_text or "")
                    if not digits:
                        continue
                    shares_raw = int(digits)

                    if "元" in unit_text or "NTD" in unit_text.upper():
                        continue

                    qk = refine_quantity_kind(hdr_kind, holding_text, unit_text)
                    shares = normalize_equity_lots_raw(shares_raw, qk)

                    if shares > 0 and len(code) == 4 and code.isdigit() and not _is_garbage_name(name_text):
                        item = {
                            "code": code,
                            "name": name_text,
                            "shares": shares,
                            "unit": "張",
                            "_quantity_kind": qk,
                        }
                        w = _parse_percent(weight_text)
                        if w is not None:
                            item["weight_pct"] = w
                        holdings.append(item)
                        if len(holdings) <= 5:
                            print(f"    解析到: {name_text} ({code}) - {shares_raw} 股 = {shares} 張")

                if holdings:
                    print(f"  從表格 #{table_idx + 1} 成功解析 {len(holdings)} 筆股票數據")
                    break

        # 方法3: 僅從「非 script/style」的純文字中抓「・名稱（1234）：數字 張」一行一行
        if not holdings:
            print("嘗試從頁面文字匹配持股行...")
            bad_tags = {"script", "style", "svg", "noscript"}
            for tag in soup.find_all(["p", "div", "td", "li", "span"]):
                if tag.name in bad_tags or tag.find_parent(bad_tags):
                    continue
                text = tag.get_text(strip=True)
                if len(text) > 200:
                    continue
                for m in re.finditer(r"[・·]?\s*([^（(]+)[（(](\d{4})[）)]\s*[：:]\s*([\d,]+)\s*張", text):
                    name_, code_, num_ = m.group(1).strip(), m.group(2), m.group(3).replace(",", "")
                    if _is_garbage_name(name_) or not num_.isdigit():
                        continue
                    shares_ = int(num_)
                    if 0 < shares_ < 10000000:
                        holdings.append({"code": code_, "name": name_, "shares": shares_})
            if holdings:
                holdings = dedupe_holdings_by_code(holdings)

        if holdings:
            result = standardize_holdings_rows(holdings)
            if result:
                ok, vmsg = validate_fetched_holdings(result)
                print(f"[i] 抓取合理性: {vmsg}")
                if not ok:
                    print("[FAIL] 解析結果未通過合理性檢查，視為抓取失敗")
                    return (None, page_date)
                print(f"[OK] 成功解析 {len(result)} 檔股票")
                return (result, page_date)

        print("[FAIL] 無法從網頁中提取持股數據")
        return (None, page_date)

    except requests.exceptions.RequestException as e:
        print(f"網絡請求失敗: {e}")
        return (None, None)
    except Exception as e:
        print(f"抓取數據時發生錯誤: {e}")
        import traceback

        traceback.print_exc()
        return (None, None)

