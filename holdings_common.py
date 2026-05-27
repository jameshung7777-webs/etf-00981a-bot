"""
持股 JSON 讀寫、持股比較與 Telegram 發送（requests 版）。
供 scraper_requests / scraper_selenium 共用，避免兩份邏輯分岔。
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

_AGENT_DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-97ec5f.log")


def _agent_log(hypothesis_id, location, message, data, run_id="pre-fix"):
    # #region agent log
    try:
        from time import time

        payload = {
            "sessionId": "97ec5f",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time() * 1000),
            "runId": run_id,
        }
        with open(_AGENT_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


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

def normalize_equity_lots_from_api_value(shares_val):
    """向下相容：未帶單位資訊時用啟發式（舊程式名稱保留）。"""
    return normalize_equity_lots_raw(shares_val, "auto")


def shares_column_header_kind(header_label):
    """依持股數量欄表頭判斷數字是「股」還是「張」：'share' | 'lot' | 'auto'。"""
    s = (header_label or "").replace(" ", "").strip()
    if not s:
        return "auto"
    if "張數" in s or "千張" in s or "持有張" in s:
        return "lot"
    if "股數" in s or "持有股數" in s or s == "股數":
        return "share"
    if "張" in s and "股數" not in s:
        return "lot"
    if "股" in s and "張" not in s and "權" not in s:
        return "share"
    return "auto"


def refine_quantity_kind(header_kind, holding_cell, unit_cell):
    """用儲存格／單位欄覆寫表頭判斷（股、張優先看明寫的單位）。"""
    t = f"{holding_cell or ''} {unit_cell or ''}"
    if re.search(r"[\d,，]+\s*[張张]", t):
        return "lot"
    if re.search(r"[\d,，]+\s*股", t):
        return "share"
    uc = unit_cell or ""
    if uc and ("張" in uc or "张" in uc) and "股" not in uc:
        return "lot"
    if uc and "股" in uc and "張" not in uc and "张" not in uc:
        return "share"
    return header_kind if header_kind in ("share", "lot") else "auto"


def json_row_quantity_kind(item):
    """從 JSON 物件的 unit 等欄位推斷持股數單位。"""
    if not isinstance(item, dict):
        return "auto"
    qk = item.get("_quantity_kind") or item.get("quantity_kind")
    if qk in ("share", "lot", "auto"):
        return qk
    u = str(item.get("unit") or item.get("shareUnit") or item.get("qtyUnit") or item.get("quantityUnit") or "")
    if any(x in u for x in ("張", "张", "lot", "LOT")):
        return "lot"
    if any(x in u for x in ("股", "Share", "share", "SHARE")):
        return "share"
    return "auto"


def _normalize_header_cell(s):
    return (s or "").strip().lower().replace(" ", "")


def table_column_indices(header_cells):
    """依表頭對應欄位索引。張數欄優先明確關鍵字，避免「持有」誤配；權重勿單用 % 匹配。"""
    hs = [_normalize_header_cell(c) for c in header_cells]

    def find_idx(keywords):
        for i, h in enumerate(hs):
            if any(kw in h for kw in keywords):
                return i
        return None

    idx_code = find_idx(("代號", "股票代號", "code"))
    idx_name = find_idx(("名稱", "股名", "股票名稱", "name"))
    idx_weight = find_idx(("權重", "比重", "占比", "比例", "weight"))
    idx_shares = find_idx(("持有張數", "張數", "千張", "持有股數", "股數", "持有", "數量"))
    idx_unit = find_idx(("單位", "unit"))
    if idx_code is None:
        idx_code = 0
    if idx_name is None:
        idx_name = 1
    if idx_weight is None:
        idx_weight = 2
    if idx_shares is None:
        idx_shares = 3
    if idx_unit is None:
        idx_unit = 4 if len(hs) > 4 else None
    if len({idx_code, idx_name, idx_weight, idx_shares}) < 4:
        idx_code, idx_name, idx_weight, idx_shares = 0, 1, 2, 3
        idx_unit = 4 if len(hs) > 4 else None
    return idx_code, idx_name, idx_weight, idx_shares, idx_unit


def holding_cell_looks_like_weight(text):
    """持股數欄若像權重百分比（5.28、9.86%），不可當張數/股數解析。"""
    s = (text or "").strip()
    if not s or "%" in s:
        return True
    if re.match(r"^\d{1,2}\.\d{1,4}$", s.replace(",", "")):
        return True
    return False


def standardize_holdings_rows(rows):
    """統一清洗、股張換算、去重；DOM/API/內嵌 JSON 最後都應走此函式。"""
    if not rows:
        return []
    result = []
    for item_src in rows:
        if not isinstance(item_src, dict):
            continue
        code = str(item_src.get("code", item_src.get("stockCode", item_src.get("symbol", "")))).strip()
        name = str(item_src.get("name", item_src.get("stockName", item_src.get("stock_name", "")))).strip()
        try:
            raw_s = int(
                item_src.get("_raw_digits")
                or item_src.get("shares_raw")
                or item_src.get("shares", item_src.get("quantity", item_src.get("amount", 0)))
                or 0
            )
        except (ValueError, TypeError):
            continue
        kind = json_row_quantity_kind(item_src)
        shares = normalize_equity_lots_raw(raw_s, kind)
        w = _resolve_weight_pct(item_src)
        shares_before_adj = shares
        shares = _adjust_lots_by_weight_hint(shares, w, raw_s, kind)
        if code in ("2330", "2303"):
            # #region agent log
            _agent_log(
                "H1",
                "holdings_common.py:standardize_holdings_rows",
                "normalize pipeline",
                {
                    "code": code,
                    "raw_s": raw_s,
                    "stored_shares_field": item_src.get("shares"),
                    "has_raw_digits": "_raw_digits" in item_src,
                    "kind": kind,
                    "weight_pct": w,
                    "shares_after_norm": shares_before_adj,
                    "shares_after_adj": shares,
                },
            )
            # #endregion
        if len(code) != 4 or not code.isdigit() or shares <= 0:
            continue
        if _is_garbage_code(code) or _is_garbage_name(name):
            continue
        item = {"code": code, "name": name, "shares": shares, "unit": "張"}
        if w is not None:
            item["weight_pct"] = w
        result.append(item)
    return dedupe_holdings_by_code(result)


def validate_fetched_holdings(holdings):
    """抓取後合理性檢查；失敗應視為抓取無效、勿寫入 JSON。

    回傳 (ok: bool, message: str)
    """
    if not holdings:
        return False, "無持股資料"
    n = len(holdings)
    if n < 35:
        return False, f"筆數過少（{n}，00981A 正常約 50 檔上下）"

    by = {str(h.get("code")): h for h in holdings if h.get("code")}
    ts = by.get("2330")
    if not ts:
        return False, "缺少台積電 2330"

    sh2330 = int(ts.get("shares") or 0)
    wt2330 = _resolve_weight_pct(ts) or 0.0
    if not (3000 <= sh2330 <= 25000):
        return False, f"2330 張數異常: {sh2330}（常見股/張混用或欄位抓錯）"
    if wt2330 and not (4.5 <= wt2330 <= 14.5):
        return False, f"2330 權重異常: {wt2330}%"

    for h in holdings:
        code = str(h.get("code", ""))
        s = int(h.get("shares") or 0)
        w = _resolve_weight_pct(h) or 0.0
        if s > 35000 and 0 < w < 4.0:
            err = f"{code} 張數 {s} 與權重 {w:.2f}% 矛盾（疑為股數未換算或抓錯欄）"
            # #region agent log
            _agent_log("H4", "holdings_common.py:validate_fetched_holdings", "validation failed", {"code": code, "shares": s, "weight": w})
            # #endregion
            return False, err

    suspicious = []
    for h in holdings:
        code = str(h.get("code", ""))
        s = int(h.get("shares") or 0)
        w = _resolve_weight_pct(h) or 0.0
        if w >= 2.0 and s <= 10:
            suspicious.append(f"{code}(wt{w:.1f}%→{s}張)")
        if s >= 50000 and 0 < w < 4.0:
            suspicious.append(f"{code}(wt{w:.1f}%→{s}張)")
    if len(suspicious) >= 4:
        return False, "異常列過多: " + "、".join(suspicious[:8])

    ones = sum(1 for h in holdings if int(h.get("shares") or 0) == 1)
    if ones >= 6:
        return False, f"疑似股/張混用：{ones} 檔張數=1"

    msg = f"OK {n} 檔；2330 {sh2330} 張 / {wt2330:.2f}%"
    # #region agent log
    _agent_log("H4", "holdings_common.py:validate_fetched_holdings", "validation passed", {"n": n, "msg": msg})
    # #endregion
    return True, msg


def normalize_equity_lots_raw(raw_val, quantity_kind="auto"):
    """依明確單位把數字轉成「張」。

    quantity_kind:
      - 'share': 輸入為股，整數除 1000（台股 1 張 = 1000 股）向下取整。
      - 'lot': 輸入已是張，不除。
      - 'auto': 無表頭／單位時的保守推測（大數多為股）。

    pocket 表頭常寫「持有股數」，但儲存格可能是已換算成「張」的 11,657（非 11,657,000 股）；
    若一律 //1000 會變成 11 張（2330 誤判）。大於 10 萬股才視為股數。
    """
    if raw_val is None:
        return 0
    try:
        v = int(float(raw_val))
    except (TypeError, ValueError):
        return 0
    if v <= 0:
        return 0
    if quantity_kind == "lot":
        return v
    if quantity_kind == "share":
        if v >= 100_000:
            return v // 1000
        if v >= 10_000:
            if v % 1000 == 0:
                return v // 1000
            return v
        if v >= 1_000:
            if v % 1000 == 0:
                return v // 1000
            return v
        return max(1, v // 1000) if v >= 100 else v
    # --- auto ---
    if v >= 100_000:
        return v // 1000
    if v >= 10_000 and v % 1000 == 0:
        return v // 1000
    return v


def _adjust_lots_by_weight_hint(shares, weight_pct, raw_val, quantity_kind):
    """權重很低但張數異常大時，嘗試修正多一位數的千分位誤讀（如 71,190,000→71190 應為 7119）。"""
    w = weight_pct or 0
    if w <= 0 or w >= 5 or shares <= 25_000:
        return shares
    if quantity_kind not in ("share", "auto"):
        return shares
    alt = None
    if raw_val >= 10_000_000 and shares > 30_000:
        alt = shares // 10
    elif shares > 35_000 and 0 < w < 4.0:
        alt = shares // 10
    if alt is not None and 800 <= alt <= 20_000:
        # #region agent log
        _agent_log(
            "H1",
            "holdings_common.py:_adjust_lots_by_weight_hint",
            "applied weight hint correction",
            {"raw_val": raw_val, "shares_in": shares, "shares_out": alt, "weight_pct": w, "kind": quantity_kind},
        )
        # #endregion
        return alt
    return shares


def _parse_percent(text):
    """把百分比字串轉成 float，例如 '3.21%' -> 3.21"""
    if text is None:
        return None
    s = str(text).strip().replace("%", "").replace("％", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None

def _resolve_weight_pct(item):
    """從不同欄位名稱解析單檔市值占比（百分比）。"""
    if not isinstance(item, dict):
        return None
    for key in ("weight_pct", "weight", "ratio", "proportion", "holdingRatio", "percent"):
        v = _parse_percent(item.get(key))
        if v is not None and v >= 0:
            return v
    return None


def _positive_weight_for_dedupe(item):
    """去重時僅把「>0」的權重當有效；0.0% 多為表尾占位，不應覆蓋未帶權重的大張數列。"""
    w = _resolve_weight_pct(item)
    if w is None or w <= 0:
        return None
    return w


def dedupe_holdings_by_code(rows):
    """同股票代碼若出現多列（表尾誤列、重複列），保留權重較高者；皆無有效權重則取張數較大者。"""
    if not rows:
        return rows
    best = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = str(r.get("code") or "").strip()
        if len(code) != 4 or not code.isdigit():
            continue
        w = _positive_weight_for_dedupe(r)
        sh = int(r.get("shares") or 0) or 0
        prev = best.get(code)
        if prev is None:
            best[code] = r
            continue
        pw = _positive_weight_for_dedupe(prev)
        psh = int(prev.get("shares") or 0) or 0
        if w is not None and pw is None:
            best[code] = r
        elif pw is not None and w is None:
            pass
        elif w is not None and pw is not None:
            if w > pw or (w == pw and sh > psh):
                best[code] = r
        else:
            if sh > psh:
                best[code] = r
    return list(best.values())


def parse_disclosure_date_from_html(text):
    """從口袋證券持股頁等 HTML 擷取「資料日期」「更新時間」或內嵌 JSON 的 date，取日曆上**最新**一筆（YYYY/M/D）。

    頁面上常有多處「資料日期：」模板（含舊的靜態字），若只用 re.search 第一個命中會永遠卡在某天（例如一直 5/12）。
    """
    if not text:
        return None
    patterns = (
        r"資料日期\s*[：:]\s*(\d{4})\s*[./年\-]\s*(\d{1,2})\s*[./月\-]\s*(\d{1,2})",
        r"更新時間\s*[：:]\s*(\d{4})\s*[./年\-]\s*(\d{1,2})\s*[./月\-]\s*(\d{1,2})",
        r'"date"\s*:\s*"(\d{4})[/-](\d{1,2})[/-](\d{1,2})"',
        r"asOf[Dd]ate\s*[:=]\s*[\"']?(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
        # 頁面常見「2026/05/13」或「2026-05-13」單獨出現在 script / JSON
        r"(?<![0-9])(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?![0-9])",
    )
    best = None
    for pat in patterns:
        for m in re.finditer(pat, text):
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if not (2020 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31):
                    continue
                cand = datetime(y, mo, d).date()
            except (ValueError, IndexError):
                continue
            if best is None or cand > best:
                best = cand
    if best is None:
        return None
    return f"{best.year}/{best.month}/{best.day}"


def coerce_snapshot_date_for_save(disclosure_str, taiwan_today_str):
    """決定寫入 holdings JSON 的 date：優先網頁擷取；若明顯過舊（相對台灣日）則改採台灣當日，避免卡死舊日。"""
    parts = str(taiwan_today_str or "").strip().replace("-", "/").split("/")
    tw_d = None
    if len(parts) >= 3:
        try:
            tw_d = datetime(int(parts[0]), int(parts[1]), int(parts[2])).date()
        except (ValueError, TypeError):
            pass
    if not tw_d:
        tw = datetime.now(timezone(timedelta(hours=8)))
        tw_d = tw.date()
        taiwan_today_str = f"{tw_d.year}/{tw_d.month}/{tw_d.day}"

    if not disclosure_str or not str(disclosure_str).strip():
        return taiwan_today_str

    ps = str(disclosure_str).strip().replace("-", "/").split("/")
    if len(ps) < 3:
        return taiwan_today_str
    try:
        d_dis = datetime(int(ps[0]), int(ps[1]), int(ps[2])).date()
    except (ValueError, TypeError):
        return taiwan_today_str

    if d_dis > tw_d:
        print(f"[i] 網頁擷取日 {disclosure_str} 晚於台灣今日 {taiwan_today_str}，改用台灣日寫入。")
        return taiwan_today_str

    # 資料日僅落後台灣曆 1 天時，常為頁面模板仍顯示「昨日」但實務已換日；寫入台灣曆可避免
    # send 階段 load_previous 用舊 JSON date 當錨點，誤拿上上業務日（例：5/13 檔卻去對 5/12 基準）。
    gap_days = (tw_d - d_dis).days
    if gap_days == 1:
        if os.getenv("HOLDINGS_DATE_LAG_AUTO_BUMP", "1").strip().lower() not in ("0", "false", "no"):
            print(
                f"[i] 網頁資料日 {disclosure_str} 為台灣日前一日（差 1 天），"
                f"持股 JSON 改寫入 {taiwan_today_str} 以利與前一日快照對齊。"
            )
            return taiwan_today_str

    if (tw_d - d_dis).days > 10:
        print(
            f"[i] 網頁擷取日 {disclosure_str} 早於台灣今日 {taiwan_today_str} 超過 10 天，"
            f"疑似誤判靜態字，改用台灣日寫入。"
        )
        return taiwan_today_str

    return f"{d_dis.year}/{d_dis.month}/{d_dis.day}"


def _score_holdings_raw_list(lst):
    """粗分：有效持股列數（4 位代號、有張數／股數、非垃圾名）。"""
    if not isinstance(lst, list) or len(lst) < 3:
        return -1
    n = 0
    for item in lst[:400]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", item.get("stockCode", ""))).strip()
        if len(code) != 4 or not code.isdigit() or code in ("0098", "2026"):
            continue
        name = str(item.get("name", item.get("stockName", ""))).strip()
        if _is_garbage_name(name):
            continue
        try:
            sh = int(item.get("shares", item.get("quantity", 0)) or 0)
        except (TypeError, ValueError):
            continue
        if sh <= 0:
            continue
        n += 1
    return n


def extract_holdings_list_from_embedded_json(text, min_score=8):
    """從整段 HTML/JS 中，用 JSONDecoder 對齊 `"holdings": [` 後切出陣列，取「看起來最像真持股表」的一筆。

    避免正則 `.*?` 誤匹配頁面上其他小型 JSON 或殘段。min_score 可調低（如 5）供 requests 靜態 HTML。"""
    if not text:
        return None
    dec = json.JSONDecoder()
    best, best_sc = None, -1
    for m in re.finditer(r'"holdings"\s*:\s*\[', text):
        start = m.start() + m.group().rfind("[")
        try:
            data, _end = dec.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        sc = _score_holdings_raw_list(data)
        if sc > best_sc:
            best_sc, best = sc, data
    if best is not None and best_sc >= min_score:
        return best
    return None


def load_previous_holdings(data_file=None, current_date_str=None):
    """載入「上一筆」持股快照做比較：只依 JSON 內 `date`（業務日），嚴格早於今日且該欄位最大者。

    同一業務日若因重複抓取有多個檔，預設取**檔名時間最早**一檔（HHMM 最小），避免晚間誤抓、
    與隔日重疊的數字被當成「昨日基準」。若你希望改取**最晚**一檔，請設環境變數
    `HOLDINGS_PREVIOUS_SNAPSHOT=last`。

    檔名日期僅在無法用 JSON date 篩選時當 fallback。
    候選基準檔僅 `holdings_data_*.json`，不含 `holdings_data.json`（發送流程中該檔即「當前」來源，併入會造成與自己比對）。
    current_date_str：選檔錨點日（通常與 holdings_data.json 的 date 或台灣曆一致）；若省略則用台灣日期。
    data_file：若指定路徑則只讀該檔（不做日期篩選）。"""
    import glob

    base_dir = os.path.dirname(os.path.abspath(__file__))
    taiwan_tz = timezone(timedelta(hours=8))

    def _parse_slash_date(s):
        if not s:
            return None
        raw = str(s).strip().replace("-", "/")
        parts = raw.split("/")
        if len(parts) >= 3:
            try:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2])).date()
            except (ValueError, TypeError):
                return None
        return None

    def _clean_payload(data):
        if data and "holdings" in data:
            clean = [
                h
                for h in data["holdings"]
                if isinstance(h, dict)
                and h.get("code")
                and h.get("name")
                and not _is_garbage_code(str(h.get("code", "")))
                and not _is_garbage_name(str(h.get("name", "")))
            ]
            return {"date": data["date"], "holdings": clean}
        return data

    if data_file is not None:
        if not os.path.exists(data_file):
            return None
        try:
            with open(data_file, encoding="utf-8") as f:
                data = json.load(f)
            return _clean_payload(data)
        except Exception as e:
            print(f"載入歷史數據時發生錯誤: {e}")
            return None

    now_tw = datetime.now(taiwan_tz)
    if current_date_str is None:
        current_date_str = f"{now_tw.year}/{now_tw.month}/{now_tw.day}"
    current_d = _parse_slash_date(current_date_str)
    if current_d is None:
        current_d = now_tw.date()

    _fn_re = re.compile(r"holdings_data_(\d{4})-(\d{2})-(\d{2})_(\d+)\.json$")

    def _path_file_date_time(path):
        m = _fn_re.search(os.path.basename(path))
        if not m:
            return None
        y, mo, d, hhmm = map(int, m.groups())
        return datetime(y, mo, d).date(), hhmm

    def _path_fetch_order_key(path):
        """同日多檔時用來排序：數字越大＝檔名時間越晚；與 min/max 併用。"""
        m = _fn_re.search(os.path.basename(path))
        if m:
            return (0, int(m.group(4)))
        try:
            return (1, os.path.getmtime(path))
        except OSError:
            return (2, 0.0)

    def _finalize(raw, chosen_path, force_same_day=False):
        out = _clean_payload(raw)
        if not out:
            return None
        disp = os.path.basename(chosen_path) if os.path.isfile(str(chosen_path)) else str(chosen_path)
        print(f"[i] 持股變化比較基準：{disp}（{raw.get('date')}）")
        if force_same_day:
            out = dict(out)
            out["_force_compare_with_today"] = True
        return out

    paths = glob.glob(os.path.join(base_dir, "holdings_data_*.json"))
    # 不比對 holdings_data.json：當前持股由該檔讀入；若其 JSON date 仍為昨日，曾被誤列入候選而變成「與自己比」。

    candidates = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not data or "holdings" not in data:
            continue
        d = _parse_slash_date(data.get("date"))
        if d is None or d >= current_d:
            continue
        candidates.append((d, path, data))

    if candidates:
        max_d = max(c[0] for c in candidates)
        same_day = [c for c in candidates if c[0] == max_d]
        pick = (os.getenv("HOLDINGS_PREVIOUS_SNAPSHOT") or "first").strip().lower()
        if pick in ("last", "latest", "max"):
            _, chosen_path, raw = max(same_day, key=lambda c: _path_fetch_order_key(c[1]))
        else:
            _, chosen_path, raw = min(same_day, key=lambda c: _path_fetch_order_key(c[1]))
        try:
            return _finalize(raw, chosen_path, False)
        except Exception as e:
            print(f"載入歷史數據時發生錯誤: {e}")
            return None

    # ── Fallback：JSON 內 date 全是「今天」或清單內無嚴格早於今日時，改依「檔名」 holdings_data_YYYY-MM-DD_HHMM.json
    dated_paths = [
        p
        for p in glob.glob(os.path.join(base_dir, "holdings_data_*.json"))
        if _path_file_date_time(p)
    ]
    fd_prev = []
    for path in dated_paths:
        fd, hhmm = _path_file_date_time(path)
        if fd < current_d:
            fd_prev.append((fd, hhmm, path))
    if fd_prev:
        max_fd = max(x[0] for x in fd_prev)
        pool = [x for x in fd_prev if x[0] == max_fd]
        pick = (os.getenv("HOLDINGS_PREVIOUS_SNAPSHOT") or "first").strip().lower()
        if pick in ("last", "latest", "max"):
            _, _, path = max(pool, key=lambda x: x[1])
        else:
            _, _, path = min(pool, key=lambda x: x[1])
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            print("[i] 提示：以檔名日期選出基準（JSON 內 date 未早於今日之可用檔）；同日多檔取 "
                  + ("最晚" if pick in ("last", "latest", "max") else "最早") + " HHMM")
            return _finalize(raw, path, False)
        except Exception as e:
            print(f"載入歷史數據時發生錯誤: {e}")
            return None

    # ── 同日多次抓取：檔名皆為今日、JSON date 皆為今日且無「早於今日」的 JSON 時，取「當日最早一檔」與 holdings_data.json（通常為最後一次寫入）比
    same_fname_day = []
    for path in dated_paths:
        fd, hhmm = _path_file_date_time(path)
        if fd == current_d:
            same_fname_day.append((hhmm, path))
    same_fname_day.sort()
    if len(same_fname_day) >= 2:
        _, path = same_fname_day[0]
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            print("[i] 提示：使用同日「最早」快照與最新 holdings_data.json 比較持股變化")
            return _finalize(raw, path, True)
        except Exception as e:
            print(f"載入歷史數據時發生錯誤: {e}")
            return None

    print("[i] 找不到可對照的歷史持股檔（需：JSON date 早於今日、或檔名日期早於今日、或同日至少兩個 *_HHMM.json 以最早檔為基準）")
    return None

def save_holdings(holdings, date_str, data_file=None):
    """保存當前持股數據。會寫入：帶日期時間的檔案 + holdings_data.json（供下次比較用）"""
    tw = timezone(timedelta(hours=8))
    now = datetime.now(tw)
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

def _shares_int(val):
    """JSON 可能為字串或浮點，統一為張數整數再比較。"""
    try:
        if val is None:
            return 0
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _report_date_heading(date_str):
    """2026/5/13 → 5/13（表頭用）。"""
    s = (date_str or "").strip().replace("-", "/")
    parts = [p for p in s.split("/") if p]
    if len(parts) >= 3:
        try:
            return f"{int(parts[1])}/{int(parts[2])}"
        except (ValueError, TypeError):
            pass
    return date_str or "—"


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
        curr_shares = _shares_int(curr_holdings[code].get('shares'))
        prev_shares = _shares_int(prev_holdings[code].get('shares'))
        
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

def format_today_holdings(holdings, date_str, send_date_str=None):
    """格式化「今日持股」訊息（供 Telegram 第一則）；僅含乾淨項目，避免 CSS/HTML 混入。

    send_date_str：若與 date_str 不同（例如檔案仍標舊日但實際已於台灣曆某日發送），標題會並列兩者。
    """
    clean = [h for h in holdings
             if isinstance(h, dict) and h.get('name') and h.get('code')
             and not _is_garbage_code(str(h.get('code', '')))
             and not _is_garbage_name(str(h.get('name', '')))]
    if send_date_str and send_date_str != date_str:
        lines = [f"00981A 今日持股明細（資料日 {date_str}｜發送日 {send_date_str}）", ""]
    else:
        lines = [f"00981A 今日持股明細（{date_str}）", ""]
    has_weight = any(_resolve_weight_pct(h) is not None for h in clean)
    total_shares = sum(int(h.get('shares', 0) or 0) for h in clean) or 0
    if has_weight:
        # 有權重時，依市值占比由高到低排列；缺值放最後
        ordered = sorted(
            clean,
            key=lambda x: (_resolve_weight_pct(x) is None, -(_resolve_weight_pct(x) or -1.0), (x.get('name') or ''))
        )
    else:
        # 無權重時，改用持有張數由高到低做估算排序
        ordered = sorted(clean, key=lambda x: (-(int(x.get('shares', 0) or 0)), (x.get('name') or '')))

    for h in ordered:
        w = _resolve_weight_pct(h)
        if has_weight and w is not None:
            lines.append(f"・{h['name']}（{h['code']}）：{h['shares']:,} 張｜{w:.2f}%")
        elif has_weight:
            lines.append(f"・{h['name']}（{h['code']}）：{h['shares']:,} 張｜N/A")
        else:
            pct = (int(h.get('shares', 0) or 0) / total_shares * 100) if total_shares else 0
            lines.append(f"・{h['name']}（{h['code']}）：{h['shares']:,} 張｜持有張數占比(估算) {pct:.2f}%")
    lines.append("")
    if has_weight:
        lines.append("＊百分比使用網站提供之權重欄位（%）整理，僅供參考，未涉及投資建議。")
    else:
        lines.append("＊此頁未提供權重時，以持有張數占比作估算，非真正市值，僅供參考。")
    return "\n".join(lines)

def _format_top10_weight_block(current_holdings, previous_holdings, prev_date, curr_date):
    """依「當日權重」由高取前十大，列前一日與當日權重及差；無足夠權重欄位時回傳空字串。"""
    if not isinstance(current_holdings, list) or not isinstance(previous_holdings, list):
        return ""

    def _row_ok(h):
        if not isinstance(h, dict) or not h.get("code"):
            return False
        n = (h.get("name") or "")
        return bool(n) and not _is_garbage_name(n) and not _is_garbage_code(str(h.get("code", "")))

    prev_map = {str(h["code"]): h for h in previous_holdings if _row_ok(h)}
    if not any(_resolve_weight_pct(h) is not None for h in prev_map.values()):
        return ""

    curr_rows = [h for h in current_holdings if _row_ok(h)]

    scored = []
    for h in curr_rows:
        w = _resolve_weight_pct(h)
        if w is not None:
            scored.append((h, float(w)))
    if not scored:
        return ""

    scored.sort(key=lambda x: -x[1])
    top = scored[:10]

    dp = _report_date_heading(prev_date)
    dc = _report_date_heading(curr_date)
    lines = [
        f"前 10 大權重變化：{dp} → {dc}",
        "",
        f"代號\t名稱\t{dp} 權重\t{dc} 權重\t變化",
    ]
    for h, wc in top:
        code = str(h["code"])
        name = h.get("name") or ""
        ph = prev_map.get(code)
        pw = _resolve_weight_pct(ph) if ph else None
        if pw is None:
            lines.append(f"{code}\t{name}\t—\t{wc:.2f}%\t新進")
        else:
            dw = wc - float(pw)
            lines.append(f"{code}\t{name}\t{pw:.2f}%\t{wc:.2f}%\t{dw:+.2f}%")
    lines.append("")
    lines.append("＊權重為網站揭露之成分比重（%），與上表張數異動分開陳列，僅供參考。")
    return "\n".join(lines)


def format_report(changes, prev_date, curr_date, current_holdings=None, previous_holdings=None):
    """格式化「與前日比較」報告（供 Telegram 第二則）：以**張**為單位，表格式列出差異與判斷。

    JSON 內 `shares` 為「張」；差異與兩日欄位皆為張數。
    若傳入 `current_holdings` / `previous_holdings`（持股 list）且兩日皆具權重欄位，會在文末附加「前 10 大權重變化」表。
    """
    def _ok(h):
        n = (h.get("name") or "")
        return n and not _is_garbage_name(n) and not _is_garbage_code(str(h.get("code", "")))

    def _fmt_zhang(n):
        return f"{int(n):,}"

    added_clean = [h for h in changes["added"] if _ok(h)]
    removed_clean = [h for h in changes["removed"] if _ok(h)]
    increased_clean = [x for x in changes["increased"] if _ok(x)]
    decreased_clean = [x for x in changes["decreased"] if _ok(x)]

    d_prev = _report_date_heading(prev_date)
    d_curr = _report_date_heading(curr_date)

    lines = [
        f"00981A 張數異動（{d_prev} → {d_curr}）",
        "",
        f"代號\t名稱\t{d_prev} 張數\t{d_curr} 張數\t差異（張）\t判斷",
    ]

    added_sorted = sorted(
        added_clean,
        key=lambda h: _shares_int(h.get("shares")),
        reverse=True,
    )
    for h in added_sorted:
        z = _shares_int(h.get("shares"))
        lines.append(f"{h['code']}\t{h['name']}\t{_fmt_zhang(0)}\t{_fmt_zhang(z)}\t+{_fmt_zhang(z)}\t新增")

    increased_sorted = sorted(increased_clean, key=lambda x: x["diff"], reverse=True)
    for item in increased_sorted:
        pz = _shares_int(item["prev"])
        cz = _shares_int(item["curr"])
        dz = cz - pz
        lines.append(
            f"{item['code']}\t{item['name']}\t{_fmt_zhang(pz)}\t{_fmt_zhang(cz)}\t+{_fmt_zhang(dz)}\t加碼"
        )

    decreased_sorted = sorted(decreased_clean, key=lambda x: x["diff"], reverse=True)
    for item in decreased_sorted:
        pz = _shares_int(item["prev"])
        cz = _shares_int(item["curr"])
        dz = pz - cz
        lines.append(
            f"{item['code']}\t{item['name']}\t{_fmt_zhang(pz)}\t{_fmt_zhang(cz)}\t-{_fmt_zhang(dz)}\t減碼"
        )

    removed_sorted = sorted(
        removed_clean,
        key=lambda h: _shares_int(h.get("shares")),
        reverse=True,
    )
    for h in removed_sorted:
        z = _shares_int(h.get("shares"))
        lines.append(f"{h['code']}\t{h['name']}\t{_fmt_zhang(z)}\t{_fmt_zhang(0)}\t-{_fmt_zhang(z)}\t刪除")

    lines.append("")
    lines.append("＊單位為張（1 張＝1,000 股）。僅為持股結構異動說明，未涉及股價或投資建議。")
    body = "\n".join(lines)
    if current_holdings is not None and previous_holdings is not None:
        wblk = _format_top10_weight_block(current_holdings, previous_holdings, prev_date, curr_date)
        if wblk:
            body = body + "\n\n" + wblk
    return body

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
    message_thread_id: 群組內 Topic/討論串 ID，不設則發到一般聊天。
    多層防偵測機制：
      1. 發送前隨機等待（模擬人工操作延遲）
      2. 段落間依內容長度動態計算延遲（越長的訊息等越久）
      3. Rate Limit 429 自動退避重試（最多 3 次，指數 + 隨機抖動）
      4. 每次重試間額外隨機間隔，避免固定週期被識別
    """
    import random, time as _time

    # ── 層級一：發送前隨機暖身延遲（2～10 秒）──
    pre_delay = random.uniform(2.0, 10.0)
    _time.sleep(pre_delay)

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
        # ── 層級二：段落間動態延遲 ──
        # 依「上一段文字長度」計算基礎等待（每 300 字 ≈ 1 秒），再加隨機抖動
        if i > 0:
            prev_len = len(chunks[i - 1])
            base_delay = max(1.5, prev_len / 300)
            jitter = random.uniform(0.8, 3.0)
            _time.sleep(base_delay + jitter)

        data = {"chat_id": chat_id, "text": chunk}
        # Topic（message_thread_id）只對群組有效（群組 chat_id 為負數），私聊不帶此欄位
        if message_thread_id is not None and isinstance(chat_id, int) and chat_id < 0:
            data["message_thread_id"] = int(message_thread_id)

        # ── 層級三：Rate Limit 退避重試（最多 3 次，指數 + 隨機抖動）──
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(send_url, json=data, timeout=15)
                body = response.json() if response.text else {}

                if response.status_code == 429:
                    retry_after = body.get("parameters", {}).get("retry_after", 5 * (2 ** attempt))
                    # 在建議等待秒數上加額外隨機抖動，避免固定週期重試
                    wait = retry_after + random.uniform(1.0, 4.0)
                    print(f"[!] 發送頻率超限（429），等待 {wait:.1f} 秒後重試（第 {attempt+1} 次）...")
                    _time.sleep(wait)
                    continue

                if response.status_code == 200 and body.get("ok"):
                    if len(chunks) > 1:
                        print(f"[OK] 訊息第 {i + 1}/{len(chunks)} 段已發送")
                    else:
                        print("[OK] 消息已成功發送到 Telegram")
                    break
                else:
                    all_ok = False
                    err = body.get("description", response.text or f"HTTP {response.status_code}")
                    print(f"發送失敗: {err}")
                    break
            except Exception as e:
                all_ok = False
                print(f"發送消息時發生錯誤（第 {attempt+1} 次）: {e}")
                if attempt < max_retries - 1:
                    # ── 層級四：異常後隨機間隔再重試 ──
                    _time.sleep(random.uniform(3.0, 8.0))
                else:
                    import traceback
                    traceback.print_exc()

    return all_ok
