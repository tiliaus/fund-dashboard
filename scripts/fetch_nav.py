"""
fetch_nav.py — 每日自動抓取四檔基金最新淨值
使用網路爬蟲從公開財金網站取得，無需 API Key
來源優先順序：MOPS 公開資訊觀測站 → MoneyDJ → 鉅亨網
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import quote

# ── 設定 ──────────────────────────────────────────────────────────
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
def today_str():
    # 台灣時間 UTC+8
    return (datetime.utcnow() + timedelta(hours=8)).strftime('%Y/%m/%d')

def one_year_ago_str():
    d = datetime.utcnow() + timedelta(hours=8) - timedelta(days=366)
    return d.strftime('%Y/%m/%d')

# ── 資料檔讀寫 ────────────────────────────────────────────────────
def load_nav():
    with open(NAV_FILE, encoding='utf-8') as f:
        return json.load(f)

def save_nav(data):
    with open(NAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def trim_old(data):
    cutoff = one_year_ago_str()
    for fund in FUND_KEYS:
        if fund in data:
            data[fund] = {k: v for k, v in data[fund].items() if k >= cutoff}
    return data

# ── 淨值驗證 ──────────────────────────────────────────────────────
def is_valid_nav(val):
    """台灣基金淨值合理範圍約 5–100000"""
    try:
        v = float(str(val).replace(',', ''))
        return 5 < v < 100000
    except Exception:
        return False

def parse_nav(text):
    """從字串中找出合理的淨值數字"""
    candidates = re.findall(r'\b(\d{1,6}(?:\.\d{1,4})?)\b', str(text).replace(',', ''))
    for c in candidates:
        if is_valid_nav(c):
            return round(float(c), 2)
    return None

# ── 來源 1：公開資訊觀測站 MOPS ───────────────────────────────────
def try_mops(full_name):
    try:
        url = 'https://mops.twse.com.tw/mops/web/fund_net_worth'
        r = requests.post(
            url,
            data={'type': 'fund', 'firstin': '1', 'CNAME': full_name},
            headers=HEADERS,
            timeout=30,
        )
        # MOPS 可能回傳 Big5 或 UTF-8
        for enc in ('utf-8', 'big5', 'cp950'):
            try:
                r.encoding = enc
                text = r.text
                break
            except Exception:
                continue

        soup = BeautifulSoup(text, 'html.parser')
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                row_text = ' '.join(cells)
                # 找含有基金名稱前幾字的列
                if full_name[:4] in row_text:
                    # 從各欄位嘗試解析淨值
                    for cell in reversed(cells):  # 淨值通常在後半段
                        nav = parse_nav(cell)
                        if nav:
                            return nav
        print('    MOPS: 找不到淨值')
    except Exception as e:
        print(f'    MOPS 錯誤: {e}')
    return None

# ── 來源 2：MoneyDJ ───────────────────────────────────────────────
def try_moneydj(full_name):
    try:
        url = f'https://www.moneydj.com/funddj/ya/yp006000.djhtm?a={quote(full_name)}'
        r = requests.get(url, headers=HEADERS, timeout=25)
        for enc in ('utf-8', 'big5', 'cp950'):
            try:
                r.encoding = enc
                text = r.text
                break
            except Exception:
                continue

        soup = BeautifulSoup(text, 'html.parser')

        # 找含有「淨值」的欄位附近的數字
        for pattern in [
            r'最新淨值[^0-9]*?([\d,]+\.[\d]+)',
            r'單位淨值[^0-9]*?([\d,]+\.[\d]+)',
            r'淨值[^0-9]*?([\d,]+\.[\d]+)',
        ]:
            m = re.search(pattern, soup.get_text())
            if m:
                nav = parse_nav(m.group(1))
                if nav:
                    return nav

        print('    MoneyDJ: 找不到淨值')
    except Exception as e:
        print(f'    MoneyDJ 錯誤: {e}')
    return None

# ── 來源 3：鉅亨網 cnyes ──────────────────────────────────────────
def try_cnyes(full_name):
    try:
        # cnyes 有搜尋 API
        api = f'https://fund.cnyes.com/api/basic/search?keyword={quote(full_name)}&limit=5'
        r = requests.get(api, headers={**HEADERS, 'Accept': 'application/json'}, timeout=20)
        data = r.json()

        # 取得第一筆基金的 code
        items = data.get('data', {}).get('items', [])
        if not items:
            print('    cnyes: 搜尋無結果')
            return None

        fund_code = items[0].get('code') or items[0].get('fundId')
        if not fund_code:
            return None

        # 取得淨值
        nav_url = f'https://fund.cnyes.com/api/basic/fund/{fund_code}/nav'
        r2 = requests.get(nav_url, headers={**HEADERS, 'Accept': 'application/json'}, timeout=20)
        nav_data = r2.json()
        price = nav_data.get('data', {}).get('nav') or nav_data.get('data', {}).get('price')
        if price and is_valid_nav(price):
            return round(float(price), 2)

        print('    cnyes: 找不到淨值')
    except Exception as e:
        print(f'    cnyes 錯誤: {e}')
    return None

# ── 主要抓取邏輯 ──────────────────────────────────────────────────
SOURCES = [
    ('MOPS 公開資訊觀測站', try_mops),
    ('MoneyDJ', try_moneydj),
    ('鉅亨網', try_cnyes),
]

def fetch_nav_for_fund(fund_key):
    full_name = FUND_FULL[fund_key]
    print(f'\n  [{fund_key}] {full_name}')
    for source_name, fn in SOURCES:
        print(f'    嘗試 {source_name}…')
        nav = fn(full_name)
        if nav:
            print(f'    ✓ {source_name} 取得淨值：{nav}')
            return nav
        time.sleep(1.5)
    print(f'    ✗ 所有來源均失敗')
    return None

# ── 主程式 ────────────────────────────────────────────────────────
def main():
    today = today_str()
    print(f'=== 基金淨值更新 {today} ===')

    data = load_nav()
    missing = [f for f in FUND_KEYS if today not in data.get(f, {})]

    if not missing:
        print('所有基金今日資料已存在，略過。')
        return

    print(f'待更新：{missing}')

    updated, failed = [], []

    for fund in missing:
        nav = fetch_nav_for_fund(fund)
        if nav:
            data.setdefault(fund, {})[today] = nav
            updated.append(f'{fund}: {nav}')
        else:
            failed.append(fund)
        time.sleep(2)

    if not updated:
        print(f'\n錯誤：無法取得任何淨值資料，失敗基金：{failed}')
        sys.exit(1)

    print(f'\n已更新：{", ".join(updated)}')
    if failed:
        print(f'未取得：{", ".join(failed)}')

    data = trim_old(data)
    data['last_updated'] = today
    save_nav(data)
    print('nav.json 儲存完成。')


if __name__ == '__main__':
    main()
