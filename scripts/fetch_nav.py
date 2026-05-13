"""
fetch_nav.py — 每日 22:00 自動執行
・每日抓取四檔基金最新淨值（MoneyDJ）
・每月抓取一次前十大持股（MoneyDJ），只保留最新一期
・淨值保留最近一年，超過自動刪除
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import sys
import time
from datetime import datetime, timedelta

# ── 基金設定 ──────────────────────────────────────────────────────
FUND_KEYS = ['安聯台灣科技', '安聯台灣大壩', '統一奔騰', '統一黑馬']
NAV_FILE  = 'data/nav.json'

MONEYDJ = {
    '安聯台灣科技': 'ACDD04',
    '安聯台灣大壩': 'ACDD01',
    '統一奔騰':    'ACPS10',
    '統一黑馬':    'ACPS02',
}
BASE_URL = 'https://www.moneydj.com/funddj/yp/yp011000.djhtm?a='

HEADERS = {
    'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
    'Referer':      'https://www.moneydj.com/',
    'Accept':       'text/html,application/xhtml+xml,*/*;q=0.8',
}

# ── 日期工具 ──────────────────────────────────────────────────────
def tw_now():
    return datetime.utcnow() + timedelta(hours=8)

def fmt_date(d):
    return d.strftime('%Y/%m/%d')

def fmt_month(d):
    return d.strftime('%Y/%m')

def today_str():
    return fmt_date(tw_now())

def one_year_ago():
    return fmt_date(tw_now() - timedelta(days=366))

# ── 資料檔 ────────────────────────────────────────────────────────
def load_nav():
    with open(NAV_FILE, encoding='utf-8') as f:
        return json.load(f)

def save_nav(data):
    with open(NAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def trim_old_nav(data):
    """刪除一年前的淨值"""
    cutoff = one_year_ago()
    for fund in FUND_KEYS:
        if fund in data and isinstance(data[fund], dict):
            data[fund] = {k: v for k, v in data[fund].items() if k >= cutoff}
    return data

# ── 工具 ─────────────────────────────────────────────────────────
def is_valid_nav(val):
    try:
        v = float(str(val).replace(',', ''))
        return 5 < v < 99999
    except Exception:
        return False

def decode_response(r):
    content = r.content
    for enc in ('utf-8', 'big5', 'cp950'):
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode('utf-8', errors='replace')

def fetch_page(code):
    url = BASE_URL + code
    r = requests.get(url, headers=HEADERS, timeout=30)
    return decode_response(r)

# ── 淨值解析 ──────────────────────────────────────────────────────
def parse_nav(html):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()

    # 依優先順序嘗試不同的關鍵字模式
    patterns = [
        r'最新淨值[^\d]{0,10}([\d,]+\.[\d]+)',
        r'單位淨值[^\d]{0,10}([\d,]+\.[\d]+)',
        r'淨值[^\d]{0,10}([\d,]+\.[\d]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = m.group(1).replace(',', '')
            if is_valid_nav(val):
                return round(float(val), 2)

    # Fallback：從表格找數字
    for table in soup.find_all('table'):
        for td in table.find_all('td'):
            cell = td.get_text(strip=True).replace(',', '')
            try:
                v = float(cell)
                if is_valid_nav(v):
                    return round(v, 2)
            except Exception:
                pass
    return None

# ── 持股解析 ──────────────────────────────────────────────────────
def parse_holdings(html):
    soup = BeautifulSoup(html, 'html.parser')
    holdings = []

    # 找含有「持股」或「比重」的表格區塊
    for table in soup.find_all('table'):
        table_text = table.get_text()
        if not any(kw in table_text for kw in ['持股', '比重', '持有']):
            continue

        rows = table.find_all('tr')
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
            if len(cells) < 2:
                continue

            name = None
            pct  = None

            for cell in cells:
                # 嘗試解析百分比
                pct_m = re.search(r'^([\d]+\.?[\d]*)%?$', cell.replace(',', ''))
                if pct_m:
                    v = float(pct_m.group(1))
                    if 0 < v <= 100:
                        pct = round(v, 2)
                # 擷取名稱（排除純數字和空白）
                elif cell and not cell.isdigit() and len(cell) >= 2 and name is None:
                    # 排除明顯的標頭列
                    if cell not in ('股票名稱', '名稱', '持股比重', '比重', '排名', '持有比例'):
                        name = cell

            if name and pct:
                holdings.append({'name': name, 'pct': pct})

        if len(holdings) >= 3:
            break

    # 若上述方法無效，嘗試正則從全文提取
    if not holdings:
        text = soup.get_text()
        # 尋找「名稱 XX.XX%」的模式
        matches = re.findall(r'([^\d\s%,]{2,20})\s+([\d]+\.[\d]+)%', text)
        for name, pct_str in matches[:10]:
            pct = float(pct_str)
            if 0 < pct <= 100:
                holdings.append({'name': name.strip(), 'pct': pct})

    return holdings[:10]

# ── 主程式 ────────────────────────────────────────────────────────
def main():
    today        = today_str()
    this_month   = fmt_month(tw_now())
    now          = tw_now()

    print(f'=== MoneyDJ 基金資料更新 ===')
    print(f'台灣時間：{today} {now.strftime("%H:%M")}')

    data = load_nav()

    # 判斷哪些基金需要更新
    missing_nav      = [f for f in FUND_KEYS if today not in data.get(f, {})]
    need_holdings    = data.get('holdings_updated', '') != this_month
    existing_holdings = data.get('holdings', {})

    print(f'待更新淨值：{missing_nav if missing_nav else "全部已有"}')
    print(f'持股更新：{"需要" if need_holdings else f"本月({this_month})已更新，略過"}')

    if not missing_nav and not need_holdings:
        print('所有資料已是最新，略過。')
        return

    nav_ok       = []
    nav_fail     = []
    holdings_ok  = []

    for fund in FUND_KEYS:
        need_nav  = fund in missing_nav
        if not need_nav and not need_holdings:
            continue

        code = MONEYDJ[fund]
        print(f'\n  [{fund}]（代碼 {code}）')

        try:
            html = fetch_page(code)

            # ── 淨值 ──
            if need_nav:
                nav = parse_nav(html)
                if nav:
                    data.setdefault(fund, {})[today] = nav
                    nav_ok.append(f'{fund}: {nav}')
                    print(f'    淨值 ✓ {nav}')
                else:
                    nav_fail.append(fund)
                    print(f'    淨值 ✗ 找不到')

            # ── 持股 ──
            if need_holdings:
                holdings = parse_holdings(html)
                if holdings:
                    data.setdefault('holdings', {})[fund] = holdings
                    holdings_ok.append(fund)
                    print(f'    持股 ✓ {len(holdings)} 筆：' +
                          ', '.join(f'{h["name"]}({h["pct"]}%)' for h in holdings[:3]) + '…')
                else:
                    # 保留舊資料
                    if fund in existing_holdings:
                        data.setdefault('holdings', {})[fund] = existing_holdings[fund]
                    print(f'    持股 ✗ 找不到，保留舊資料')

        except Exception as e:
            print(f'    錯誤: {e}')
            if need_nav:
                nav_fail.append(fund)

        time.sleep(2)

    # ── 儲存 ──
    if not nav_ok and not holdings_ok:
        print('\n警告：無任何資料更新（可能尚未公布）。')
        return

    data = trim_old_nav(data)
    data['last_updated'] = today

    if need_holdings and len(holdings_ok) == len(FUND_KEYS):
        data['holdings_updated'] = this_month
        print(f'\n持股更新完成，標記為 {this_month}')
    elif need_holdings and holdings_ok:
        print(f'\n持股部分更新（{len(holdings_ok)}/{len(FUND_KEYS)} 檔）')

    save_nav(data)

    print(f'\n✓ 淨值更新 {len(nav_ok)} 檔：{", ".join(nav_ok)}')
    if nav_fail:
        print(f'✗ 淨值失敗 {len(nav_fail)} 檔：{", ".join(nav_fail)}')
    print('nav.json 儲存完成。')


if __name__ == '__main__':
    main()
