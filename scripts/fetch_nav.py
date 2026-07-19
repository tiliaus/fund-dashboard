"""
fetch_nav.py — 每日自動執行
・從 MoneyDJ 抓取四檔基金最新淨值（ya/yp010000）
・從 MoneyDJ 抓取 00981A ETF 最新淨值（ETF/X/Basic/Basic0003.xdjhtm）
・每月抓取一次前十大持股（yp/yp013000），各基金分別記錄資料月份
・淨值保留最近一年，超過自動刪除
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from datetime import datetime, timedelta

# ── 基金設定 ──────────────────────────────────────────────────────
FUND_KEYS = ['安聯台灣科技', '安聯台灣大壩', '統一奔騰', '統一黑馬', '統一全球新科技', '安聯台灣智慧']
ETF_KEYS  = ['00981A', '00990A', '00982A', '00984A', '00993A', '00991A']
ALL_KEYS  = FUND_KEYS + ETF_KEYS
NAV_FILE  = 'data/nav.json'

CODES = {
    '安聯台灣科技': 'ACDD04',
    '安聯台灣大壩': 'ACDD01',
    '統一奔騰':    'ACPS10',
    '統一黑馬':    'ACPS02',
    '統一全球新科技': 'ACPS38',
    '安聯台灣智慧': 'ACDD19',
}

NAV_URL      = 'https://www.moneydj.com/funddj/ya/yp010000.djhtm?a={}'
HOLDINGS_URL = 'https://www.moneydj.com/funddj/yp/yp013000.djhtm?a={}'
ETF_URL      = 'https://www.moneydj.com/ETF/X/Basic/Basic0003.xdjhtm?etfid={}.TW'

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

def roc_to_gregorian(roc_date):
    """將民國年日期（115/05/13）轉換為西元（2026/05/13）"""
    parts = roc_date.strip().split('/')
    if len(parts) == 3:
        try:
            year = int(parts[0]) + 1911
            return f'{year}/{parts[1].zfill(2)}/{parts[2].zfill(2)}'
        except Exception:
            pass
    return roc_date

# ── 資料檔 ────────────────────────────────────────────────────────
def load_nav():
    with open(NAV_FILE, encoding='utf-8') as f:
        return json.load(f)

def save_nav(data):
    """儲存前將各基金/ETF 淨值日期由新到舊排序"""
    sorted_data = {}
    for k, v in data.items():
        if isinstance(v, dict) and k in ALL_KEYS:
            sorted_data[k] = dict(sorted(v.items(), reverse=True))
        else:
            sorted_data[k] = v
    with open(NAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=2)

def trim_old_nav(data):
    """刪除一年前的淨值"""
    cutoff = one_year_ago()
    for key in ALL_KEYS:
        if key in data and isinstance(data[key], dict):
            data[key] = {k: v for k, v in data[key].items() if k >= cutoff}
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

# ── 基金淨值解析 ──────────────────────────────────────────────────
def parse_nav(code):
    """淨值頁 ya/yp010000：標題列含「最新淨值」→ 下一列第1格=日期，第2格=淨值"""
    soup = fetch(NAV_URL.format(code))
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for i, row in enumerate(rows):
            cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
            if '最新淨值' in cells and i + 1 < len(rows):
                data_cells = [td.get_text(strip=True) for td in rows[i+1].find_all(['td', 'th'])]
                if len(data_cells) >= 2:
                    try:
                        nav  = round(float(data_cells[1].replace(',', '')), 2)
                        date = data_cells[0]
                        return nav, date
                    except Exception:
                        pass
    return None, None

# ── ETF 淨值解析 ──────────────────────────────────────────────────
def parse_etf_nav(etf_id):
    """
    ETF 頁面：找含「淨值」的列（非市價），取第 2 格（價格欄）的數值
    日期從第 1 格括號內取得，如「淨值(2026/05/14)」
    """
    soup = fetch(ETF_URL.format(etf_id))
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
            if len(cells) >= 2 and '淨值' in cells[0] and '市價' not in cells[0]:
                # 第 2 格是價格，去除「(台幣)」等文字
                price_str = re.sub(r'[^\d.]', '', cells[1])
                try:
                    val = round(float(price_str), 2)
                    if 5 < val < 99999:
                        # 從第 1 格取日期，如「淨值(2026/05/14)」
                        m = re.search(r'(\d{4}/\d{2}/\d{2})', cells[0])
                        date_str = m.group(1) if m else today_str()
                        return val, date_str
                except Exception:
                    pass
    return None, None

# ── 持股解析 ──────────────────────────────────────────────────────
def parse_holdings(code):
    """
    持股頁 yp/yp013000：
    在投資明細表格之後找「資料月份」或「資料日期」
    """
    soup = fetch(HOLDINGS_URL.format(code))
    tables = soup.find_all('table')

    holdings = []
    holdings_table_idx = -1

    for i, table in enumerate(tables):
        tr = table.find('tr')
        header = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])] if tr else []
        if header.count('投資名稱') >= 1 and '比例' in header:
            holdings_table_idx = i
            rows = table.find_all('tr')
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                if len(cells) >= 3:
                    try:
                        name1 = cells[0].strip()
                        pct1  = float(cells[2].replace(',', ''))
                        if name1 and 0 < pct1 < 100:
                            holdings.append({'name': name1, 'pct': pct1})
                    except Exception:
                        pass
                if len(cells) >= 7:
                    try:
                        name2 = cells[4].strip()
                        pct2  = float(cells[6].replace(',', ''))
                        if name2 and 0 < pct2 < 100:
                            holdings.append({'name': name2, 'pct': pct2})
                    except Exception:
                        pass
            break

    data_date = ''
    search_tables = tables[holdings_table_idx+1:] if holdings_table_idx >= 0 else tables
    for table in search_tables:
        for td in table.find_all('td'):
            m = re.search(r'資料[月日][份期][：:]\s*(\d{4}/\d{2}/\d{2})', td.get_text(strip=True))
            if m:
                data_date = m.group(1)
                break
        if data_date:
            break

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
    missing_etf   = [e for e in ETF_KEYS  if today not in data.get(e, {})]
    need_holdings = data.get('holdings_updated', '') != this_month

    print(f'待更新基金淨值：{missing_nav if missing_nav else "全部已有"}')
    print(f'待更新ETF淨值：{missing_etf if missing_etf else "全部已有"}')
    print(f'持股更新：{"需要" if need_holdings else f"本月({this_month})已更新，略過"}')

    if not missing_nav and not missing_etf and not need_holdings:
        print('所有資料已是最新，略過。')
        return

    nav_ok, nav_fail, holdings_ok = [], [], []

    # ── 四檔基金淨值 ──
    for fund in FUND_KEYS:
        if fund not in missing_nav and not need_holdings:
            continue

        code = CODES[fund]
        print(f'\n  [{fund}]（代碼 {code}）')

        if fund in missing_nav:
            try:
                nav, nav_date = parse_nav(code)
                if nav and nav_date:
                    fund_data = data.setdefault(fund, {})
                    if nav_date in fund_data:
                        print(f'    淨值 ✗  MoneyDJ 最新為 {nav_date}（已存），今日淨值尚未公布')
                        nav_fail.append(fund)
                    else:
                        fund_data[nav_date] = nav
                        nav_ok.append(f'{fund}: {nav}（{nav_date}）')
                        print(f'    淨值 ✓  {nav}（{nav_date}）')
                else:
                    nav_fail.append(fund)
                    print(f'    淨值 ✗  找不到')
            except Exception as e:
                nav_fail.append(fund)
                print(f'    淨值 ✗  錯誤: {e}')

        if need_holdings:
            try:
                holdings, h_date = parse_holdings(code)
                if holdings:
                    data.setdefault('holdings', {})[fund] = {'date': h_date, 'data': holdings}
                    holdings_ok.append(fund)
                    top3 = ', '.join(f'{h["name"]}({h["pct"]}%)' for h in holdings[:3])
                    print(f'    持股 ✓  {len(holdings)} 筆（資料月份 {h_date}）：{top3}…')
                else:
                    old = data.get('holdings', {}).get(fund)
                    if old:
                        data.setdefault('holdings', {})[fund] = old
                    print(f'    持股 ✗  找不到，保留舊資料')
            except Exception as e:
                print(f'    持股 ✗  錯誤: {e}')

        time.sleep(2)

    # ── ETF 淨值 ──
    for etf in ETF_KEYS:
        if etf not in missing_etf:
            continue
        print(f'\n  [ETF {etf}]')
        try:
            nav, nav_date = parse_etf_nav(etf)
            if nav and nav_date:
                etf_data = data.setdefault(etf, {})
                if nav_date in etf_data:
                    print(f'    淨值 ✗  MoneyDJ 最新為 {nav_date}（已存），今日淨值尚未公布')
                    nav_fail.append(etf)
                else:
                    etf_data[nav_date] = nav
                    nav_ok.append(f'{etf}: {nav}（{nav_date}）')
                    print(f'    淨值 ✓  {nav}（{nav_date}）')
            else:
                nav_fail.append(etf)
                print(f'    淨值 ✗  找不到')
        except Exception as e:
            nav_fail.append(etf)
            print(f'    淨值 ✗  錯誤: {e}')
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
