import os, re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests

TOKEN = os.environ["TG_BOT_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]

TAIPEI_TZ = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
INFO = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"

def send_message(text: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=30).raise_for_status()

def extract_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
    if not m:
        return "(no title)"
    return re.sub(r"\s+", " ", m.group(1)).strip()

def pick_token(html: str) -> str | None:
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, flags=re.I)
    return m.group(1) if m else None

def find_script_srcs(html: str):
    # 找 <script src="...">
    return re.findall(r'<script[^>]+src="([^"]+)"', html, flags=re.I)

def find_export_like_urls(text: str):
    # 抓出所有看起來像 export / xlsx 的路徑片段
    pats = [
        r'/(ETF/Fund/[^"\'\s]+Export[^"\'\s]+)',
        r'/(ETF/Fund/[^"\'\s]+xlsx[^"\'\s]+)',
        r'/(ETF/Fund/Export[^"\'\s]+)',
    ]
    out = set()
    for p in pats:
        for m in re.findall(p, text, flags=re.I):
            out.add("/" + m.lstrip("/"))
    return sorted(out)

def try_download(session: requests.Session, url: str, token: str | None, date: str):
    # 會同時嘗試 GET / POST，以及 token 放 data/header 的變體
    headers_base = {
        "User-Agent": UA,
        "Referer": INFO,
        "Origin": "https://www.ezmoney.com.tw",
        "Accept": "*/*",
    }

    payload = {"fundCode": "49YTW", "date": date}
    if token:
        payload["__RequestVerificationToken"] = token

    variants = []

    # GET
    variants.append(("GET", None, None))
    # POST data
    variants.append(("POST", payload, None))
    # POST token in header（ASP.NET 有時吃這種）
    if token:
        variants.append(("POST", {"fundCode": "49YTW", "date": date}, {"RequestVerificationToken": token}))
        variants.append(("POST", {"fundCode": "49YTW", "date": date}, {"X-CSRF-TOKEN": token}))
        variants.append(("POST", payload, {"RequestVerificationToken": token}))

    for method, data, extra_h in variants:
        h = dict(headers_base)
        if method == "POST":
            h["Content-Type"] = "application/x-www-form-urlencoded"
            h["X-Requested-With"] = "XMLHttpRequest"
        if extra_h:
            h.update(extra_h)

        try:
            if method == "GET":
                r = session.get(url, headers=h, timeout=60, allow_redirects=True)
            else:
                r = session.post(url, headers=h, data=data, timeout=60, allow_redirects=True)
        except Exception as e:
            return f"{method}: EXC {type(e).__name__}: {e}"

        ct = (r.headers.get("Content-Type") or "").lower()
        cd = (r.headers.get("Content-Disposition") or "").lower()
        size = len(r.content)
        head = r.content[:80]

        if "spreadsheetml" in ct or "attachment" in cd:
            return f"{method}: ✅ XLSX!! status={r.status_code}, ct={ct}, cd={cd}, size={size}"

        # 不是 xlsx：回傳一些提示
        if "text/html" in ct:
            return f"{method}: ❌ HTML status={r.status_code}, size={size}, title={extract_title(r.text)} head={head!r}"
        return f"{method}: ❌ status={r.status_code}, ct={ct}, cd={cd}, size={size}, head={head!r}"

def main():
    s = requests.Session()

    # 日期先用今天（之後再做 T-1）
    date = datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d")

    # 1) GET Info
    r = s.get(INFO, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6"}, timeout=60, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    token = pick_token(html)

    # 2) 從 HTML 找 export URL 線索
    rels = set(find_export_like_urls(html))

    # 3) 抓 JS 再掃一次（只抓前幾個，避免太慢）
    srcs = [urljoin(INFO, x) for x in find_script_srcs(html)]
    js_scanned = 0
    for js in srcs[:8]:
        try:
            jr = s.get(js, headers={"User-Agent": UA}, timeout=60)
            if jr.status_code == 200 and len(jr.text) > 200:
                for rel in find_export_like_urls(jr.text):
                    rels.add(rel)
                js_scanned += 1
        except Exception:
            pass

    rels = sorted(rels)
    if not rels:
        send_message("❌ 在 HTML/JS 都找不到任何 Export/xlsx 線索（可能是 inline script 或按鈕是純前端產生）")
        return

    # 4) 逐一試（最多前 10 個）
    lines = []
    lines.append("🔎 自動掃描匯出端點")
    lines.append(f"token={'有' if token else '沒有'}; js_scanned={js_scanned}; candidates={len(rels)}")
    lines.append(f"date={date}")
    lines.append("")

    for rel in rels[:10]:
        url = urljoin(INFO, rel)
        res = try_download(s, url, token, date)
        lines.append(f"- {url}")
        lines.append(f"  {res}")
        # 如果已經成功就停
        if "✅ XLSX" in res:
            break

    send_message("\n".join(lines)[:3800])

if __name__ == "__main__":
    main()
