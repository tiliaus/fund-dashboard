"""
fetch_nav.py — 每日自動抓取四檔基金最新淨值（無需 API Key）
來源：公開資訊觀測站 MOPS → MoneyDJ → 鉅亨網
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import quote

FUND_KEYS = ['安聯台灣科技', '安聯台灣大壩', '統一奔騰', '統一黑馬']
NAV_FILE  = 'data/nav.json'

FUND_FULL = {
    '安聯台灣科技': '安聯台灣科技基金',
    '安聯台灣大壩': '安聯台灣大壩基金',
    '統一奔騰':    '統一奔騰基金',
    '統一黑馬':    '統一黑馬基金',
}

HEADERS = {
    'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    'Accept':          'text/html,application/xhtml+xml,*/*;q=0.8',
}

# ── 日期工具 ──────────────────────────────────────────────────────
def tw_now():
    return datetime.utcnow() + timedelta(hours=8)

def fmt(d):
    return d.strftime('%Y/%m/%d')

def target_date():
    """
    決定要抓哪一天的淨值。
    台灣基金淨值通常在當日下午 4–6 點公布。
    若現在台灣時間 < 18:30，改用前一個交易日（週一–五）。
    """
    now = tw_now()
    if now.hour < 18 or (now.hour == 18 and now.minute < 30):
        d = now - timedelta(days=1)
    else:
        d = now
    # 若落在週末，再往前找最近的週五
    while d.weekday() >= 5:   # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return fmt(d)

def one_year_ago():
    return fmt(tw_now() - timedelta(days=366))

# ── 資料檔讀寫 ────────────────────────────────────────────────────
def load_nav():
    with open(NAV_FILE, encoding='utf-8') as f:
        return json.load(f)

def save_nav(data):
    with open(NAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def trim_old(data):
    cutoff = one_year_ago()
    for fund in FUND_KEYS:
        if fund in data:
            data[fund] = {k: v for k, v in data[fund].items() if k >= cutoff}
    return data

# ── 淨值解析 ──────────────────────────────────────────────────────
def is_valid(val):
    try:
        v = float(str(val).replace(',', ''))
        return 5 < v < 99999
    except Exception:
        return False

def first_valid(cells):
    """從 cells 列表中，找出第一個合理的淨值數字"""
    for cell in cells:
        for token in re.findall(r'[\d]+\.[\d]+', cell.replace(',', '')):
            if is_valid(token):
                return round(float(token), 2)
    return None

def decode(content):
    for enc in ('utf-8', 'big5', 'cp950'):
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode('utf-8', errors='replace')

# ── 來源 1：公開資訊觀測站 MOPS ───────────────────────────────────
def try_mops(full_name):
    try:
        r = requests.post(
            'https://mops.twse.com.tw/mops/web/fund_net_worth',
            data={'type': 'fund', 'firstin': '1', 'CNAME': full_name},
            headers=HEADERS,
            timeout=30,
        )
        soup = BeautifulSoup(decode(r.content), 'html.parser')
        keyword = full_name[:4]          # 用前 4 字比對
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = [td.get_text(strip=True) for td in row.find_all('td')]
                if any(keyword in c for c in cells):
                    nav = first_valid(cells)
                    if nav:
                        return nav
    except Exception as e:
        print(f'    MOPS 錯誤: {e}')
    return None

# ── 來源 2：MoneyDJ ───────────────────────────────────────────────
def try_moneydj(full_name):
    try:
        # 嘗試 MoneyDJ 基金搜尋頁
        url = f'https://www.moneydj.com/funddj/yp/yp000010.djhtm?a={quote(full_name)}'
        r = requests.get(url, headers=HEADERS, timeout=25)
        soup = BeautifulSoup(decode(r.content), 'html.parser')

        # 找基金代碼連結，再進詳細頁
        link = soup.find('a', href=re.compile(r'yp011\.djhtm'))
        if link:
            detail_url = 'https://www.moneydj.com' + link['href']
            r2 = requests.get(detail_url, headers=HEADERS, timeout=25)
            soup2 = BeautifulSoup(decode(r2.content), 'html.parser')
            text = soup2.get_text()
            for pat in [r'最新淨值[^0-9]*([\d,]+\.[\d]+)',
                        r'單位淨值[^0-9]*([\d,]+\.[\d]+)',
                        r'淨值[^0-9]*([\d,]+\.[\d]+)']:
                m = re.search(pat, text)
                if m and is_valid(m.group(1)):
                    return round(float(m.group(1).replace(',', '')), 2)

        # 直接在搜尋結果頁找數字
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = [td.get_text(strip=True) for td in row.find_all('td')]
                if any(full_name[:4] in c for c in cells):
                    nav = first_valid(cells)
                    if nav:
                        return nav
    except Exception as e:
        print(f'    MoneyDJ 錯誤: {e}')
    return None

# ── 來源 3：鉅亨網 cnyes ──────────────────────────────────────────
def try_cnyes(full_name):
    try:
        # 使用 cnyes 基金搜尋 API
        r = requests.get(
            'https://fund.cnyes.com/api/basic/search',
            params={'keyword': full_name, 'limit': '5'},
            headers={**HEADERS, 'Accept': 'application/json'},
            timeout=20,
        )
        items = r.json().get('data', {}).get('items', [])
        if not items:
            return None
        fund_id = items[0].get('fundId') or items[0].get('code')
        if not fund_id:
            return None

        # 取最新淨值
        r2 = requests.get(
            f'https://fund.cnyes.com/api/basic/fund/{fund_id}/nav',
            headers={**HEADERS, 'Accept': 'application/json'},
            timeout=20,
        )
        d = r2.json().get('data', {})
        price = d.get('nav') or d.get('price') or d.get('latestNav')
        if price and is_valid(price):
            return round(float(price), 2)
    except Exception as e:
        print(f'    cnyes 錯誤: {e}')
    return None

# ── 各來源清單 ────────────────────────────────────────────────────
SOURCES = [
    ('MOPS 公開資訊觀測站', try_mops),
    ('MoneyDJ',             try_moneydj),
    ('鉅亨網',              try_cnyes),
]

def fetch_fund(fund_key):
    full_name = FUND_FULL[fund_key]
    print(f'\n  [{fund_key}]')
    for name, fn in SOURCES:
        print(f'    試 {name}…', end=' ', flush=True)
        try:
            nav = fn(full_name)
        except Exception as e:
            nav = None
            print(f'例外: {e}', end=' ')
        if nav:
            print(f'✓ {nav}')
            return nav
        print('✗')
        time.sleep(1.5)
    return None

# ── 主程式 ────────────────────────────────────────────────────────
def main():
    date = target_date()
    now  = tw_now()
    print(f'=== 基金淨值更新 ===')
    print(f'台灣時間：{fmt(now)} {now.strftime("%H:%M")}')
    print(f'目標日期：{date}')

    data    = load_nav()
    missing = [f for f in FUND_KEYS if date not in data.get(f, {})]

    if not missing:
        print('所有基金資料已是最新，略過。')
        return          # exit 0，workflow 顯示 Success

    print(f'待更新：{missing}')

    updated, failed = [], []
    for fund in missing:
        nav = fetch_fund(fund)
        if nav:
            data.setdefault(fund, {})[date] = nav
            updated.append(f'{fund}: {nav}')
        else:
            failed.append(fund)
        time.sleep(2)

    # 若完全抓不到，但只是因為今天資料尚未公布，不算錯誤
    if not updated:
        print(f'\n警告：所有來源均無法取得資料（可能尚未公布）。')
        print(f'失敗基金：{failed}')
        # 不 exit 1，讓 workflow 顯示 Success，避免誤報
        return

    print(f'\n已更新：{", ".join(updated)}')
    if failed:
        print(f'未取得：{", ".join(failed)}（將於下次重試）')

    data = trim_old(data)
    data['last_updated'] = date
    save_nav(data)
    print('nav.json 儲存完成。')

if __name__ == '__main__':
    main()
