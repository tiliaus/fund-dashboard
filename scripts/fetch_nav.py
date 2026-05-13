"""
fetch_nav.py — 每日 22:00 自動執行
・從 MoneyDJ 抓取四檔基金最新淨值（ya/yp010000）
・每月抓取一次前十大持股（yp/yp013000），只保留最新一期
・淨值保留最近一年，超過自動刪除
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime, timedelta

# ── 基金設定 ──────────────────────────────────────────────────────
FUND_KEYS = ['安聯台灣科技', '安聯台灣大壩', '統一奔騰', '統一黑馬']
NAV_FILE  = 'data/nav.json'

CODES = {
    '安聯台灣科技': 'ACDD04',
    '安聯台灣大壩': 'ACDD01',
    '統一奔騰':    'ACPS10',
    '統一黑馬':    'ACPS02',
}

NAV_URL      = 'https://www.moneydj.com/funddj/ya/yp010000.djhtm?a={}'
HOLDINGS_URL = 'https://www.moneydj.com/funddj/yp/yp013000.djhtm?a={}'

HEADERS = {
    'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
    'Referer':         'https://www.moneydj.com/',
    'Accept':          'text/html,application/xhtml+xml,*/*;q=0.8',
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
    # 儲存前將每檔基金的日期由新到舊排序
    sorted_data = {}
    for k, v in data.items():
        if isinstance(v, dict) and k in FUND_KEYS:
            sorted_data[k] = dict(sorted(v.items(), reverse=True))
        else:
            sorted_data[k] = v
    with open(NAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=2)

def trim_old_nav(data):
    cutoff = one_year_ago()
    for fund in FUND_KEYS:
        if fund in data and isinstance(data[fund], dict):
            data[fund] = {k: v for k, v in data[fund].items() if k >= cutoff}
    return data

# ── HTTP 工具 ─────────────────────────────────────────────────────
def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    for enc in ('utf-8', 'big5', 'cp950'):
        try:
            return BeautifulSoup(r.content.decode(enc), 'html.parser')
        except Exception:
            pass
    return BeautifulSoup(r.text, 'html.parser')

# ── 淨值解析 ──────────────────────────────────────────────────────
def parse_nav(code):
    """
    淨值頁 ya/yp010000：
    表格標題列 ['淨值日期','最新淨值',...] → 下一列第 2 格即為最新淨值
    """
    soup = fetch(NAV_URL.format(code))
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for i, row in enumerate(rows):
            cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
            if '最新淨值' in cells:
                # 取下一列的第 2 格（index 1）
                if i + 1 < len(rows):
                    data_cells = [td.get_text(strip=True) for td in rows[i+1].find_all(['td', 'th'])]
                    if len(data_cells) >= 2:
                        try:
                            nav = round(float(data_cells[1].replace(',', '')), 2)
                            date = data_cells[0]   # 淨值日期，例如 2026/05/12
                            return nav, date
                        except Exception:
                            pass
    return None, None

# ── 持股解析 ──────────────────────────────────────────────────────
def parse_holdings(code):
    """
    持股頁 yp/yp013000：
    表格標題 ['投資名稱','投資(千股)','比例','增減','投資名稱',...] （8欄）
    每列資料：[名稱1, 千股1, 比例1, 增減1, 名稱2, 千股2, 比例2, 增減2]
    取全部持股，按比例排序後回傳前 10 大
    同時取得資料日期（資料日期：YYYY/MM/DD）
    """
    soup = fetch(HOLDINGS_URL.format(code))

    # 找資料日期
    data_date = ''
    for td in soup.find_all('td'):
        txt = td.get_text(strip=True)
        m = re.search(r'資料日期[：:]\s*(\d{4}/\d{2}/\d{2})', txt)
        if m:
            data_date = m.group(1)
            break

    # 找持股表格（標題含「投資名稱」且有 8 欄）
    holdings = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        header = [td.get_text(strip=True) for td in rows[0].find_all(['td', 'th'])]
        if header.count('投資名稱') >= 1 and '比例' in header:
            # 找到持股表格
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                if len(cells) >= 3:
                    # 左欄：index 0=名稱, 2=比例
                    try:
                        name1 = cells[0].strip()
                        pct1  = float(cells[2].replace(',', ''))
                        if name1 and 0 < pct1 < 100:
                            holdings.append({'name': name1, 'pct': pct1})
                    except Exception:
                        pass
                if len(cells) >= 7:
                    # 右欄：index 4=名稱, 6=比例
                    try:
                        name2 = cells[4].strip()
                        pct2  = float(cells[6].replace(',', ''))
                        if name2 and 0 < pct2 < 100:
                            holdings.append({'name': name2, 'pct': pct2})
                    except Exception:
                        pass
            break

    # 按比例排序，取前 10
    holdings.sort(key=lambda x: x['pct'], reverse=True)
    return holdings[:10], data_date

# ── 主程式 ────────────────────────────────────────────────────────
def main():
    today      = today_str()
    this_month = fmt_month(tw_now())
    now        = tw_now()

    print(f'=== MoneyDJ 基金資料更新 ===')
    print(f'台灣時間：{today} {now.strftime("%H:%M")}')

    data = load_nav()

    missing_nav   = [f for f in FUND_KEYS if today not in data.get(f, {})]
    need_holdings = data.get('holdings_updated', '') != this_month

    print(f'待更新淨值：{missing_nav if missing_nav else "全部已有"}')
    print(f'持股更新：{"需要" if need_holdings else f"本月({this_month})已更新，略過"}')

    if not missing_nav and not need_holdings:
        print('所有資料已是最新，略過。')
        return

    nav_ok, nav_fail, holdings_ok = [], [], []

    for fund in FUND_KEYS:
        need_nav = fund in missing_nav
        if not need_nav and not need_holdings:
            continue

        code = CODES[fund]
        print(f'\n  [{fund}]（代碼 {code}）')

        # ── 淨值 ──
        if need_nav:
            try:
                nav, nav_date = parse_nav(code)
                if nav:
                    data.setdefault(fund, {})[today] = nav
                    nav_ok.append(f'{fund}: {nav}（{nav_date}）')
                    print(f'    淨值 ✓  {nav}（{nav_date}）')
                else:
                    nav_fail.append(fund)
                    print(f'    淨值 ✗  找不到')
            except Exception as e:
                nav_fail.append(fund)
                print(f'    淨值 ✗  錯誤: {e}')

        # ── 持股 ──
        if need_holdings:
            try:
                holdings, h_date = parse_holdings(code)
                if holdings:
                    data.setdefault('holdings', {})[fund] = holdings
                    holdings_ok.append(fund)
                    top3 = ', '.join(f'{h["name"]}({h["pct"]}%)' for h in holdings[:3])
                    print(f'    持股 ✓  {len(holdings)} 筆（資料日期 {h_date}）：{top3}…')
                    if h_date and not data.get('holdings_date'):
                        data['holdings_date'] = h_date
                else:
                    # 保留舊資料
                    old = data.get('holdings', {}).get(fund)
                    if old:
                        data.setdefault('holdings', {})[fund] = old
                    print(f'    持股 ✗  找不到，保留舊資料')
            except Exception as e:
                print(f'    持股 ✗  錯誤: {e}')

        time.sleep(2)

    # ── 儲存 ──
    if not nav_ok and not holdings_ok:
        print('\n警告：無任何資料更新（可能尚未公布）。')
        return

    data = trim_old_nav(data)
    data['last_updated'] = today

    if need_holdings and len(holdings_ok) == len(FUND_KEYS):
        data['holdings_updated'] = this_month
        print(f'\n持股全數更新完成，標記為 {this_month}')
    elif need_holdings and holdings_ok:
        print(f'\n持股部分更新（{len(holdings_ok)}/{len(FUND_KEYS)} 檔）')

    save_nav(data)
    print(f'\n✓ 淨值更新 {len(nav_ok)} 檔：{", ".join(nav_ok)}')
    if nav_fail:
        print(f'✗ 淨值失敗：{", ".join(nav_fail)}')
    print('nav.json 儲存完成。')


if __name__ == '__main__':
    main()
