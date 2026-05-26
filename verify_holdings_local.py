#!/usr/bin/env python3
"""
本機驗證 00981A 抓取（Selenium）：不寫死持股表。
用法（Windows 若 SSL 問題）：set ETF_REQUESTS_VERIFY_SSL=0
     python verify_holdings_local.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 本機 pocket 常需關閉 requests SSL 驗證；Selenium 內 API 試連亦會讀此變數
os.environ.setdefault("ETF_REQUESTS_VERIFY_SSL", "0")


def _check_top(holdings):
    by = {h["code"]: h for h in holdings}
    ts = by.get("2330")
    if not ts:
        return False, "缺少 2330"
    sh = int(ts.get("shares") or 0)
    wt = float(ts.get("weight_pct") or 0)
    # 合理區間（依官網表「張／權重」量級，非寫死正解）
    if not (8000 <= sh <= 20000):
        return False, f"2330 張數異常: {sh}"
    if not (7.5 <= wt <= 11.0):
        return False, f"2330 權重異常: {wt}"
    gj = by.get("2327")
    if gj:
        gsh = int(gj.get("shares") or 0)
        if gsh < 15000 or gsh > 22000:
            return False, f"2327 張數異常: {gsh}"
    return True, f"2330 OK shares={sh} wt={wt}%, n={len(holdings)}"


def main():
    from scraper_selenium import fetch_holdings_selenium
    from holdings_common import (
        compare_holdings,
        format_report,
        load_previous_holdings,
        validate_fetched_holdings,
    )

    print("▶ Selenium 抓取中…")
    h, d = fetch_holdings_selenium()
    print("▶ page_date:", d, "holdings:", len(h) if h else 0)
    if not h:
        print("FAIL 無資料")
        return 1
    ok, msg = validate_fetched_holdings(h)
    print("▶ 檢查:", msg)
    if not ok:
        return 2

    tw = datetime.now(timezone(timedelta(hours=8)))
    today_str = f"{tw.year}/{tw.month}/{tw.day}"
    prev = load_previous_holdings(current_date_str=d or today_str)
    if prev:
        prev_plain = {k: v for k, v in prev.items() if not str(k).startswith("_")}
        ch = compare_holdings(h, prev_plain)
        if ch:
            rep = format_report(
                ch,
                prev.get("date", ""),
                d or today_str,
                current_holdings=h,
                previous_holdings=prev_plain.get("holdings"),
            )
            print("\n--- 變化摘要（前 800 字）---\n")
            print(rep[:800])
    else:
        print("（無歷史檔可比較）")
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
