"""
debug_moneydj_v3.py — 檢查淨值頁和持股頁的正確 HTML 結構
"""
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
    'Referer': 'https://www.moneydj.com/',
}

def decode(content):
    for enc in ('utf-8', 'big5', 'cp950'):
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode('utf-8', errors='replace')

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    print(f'狀態碼: {r.status_code}  長度: {len(r.content)}')
    return decode(r.content)

# ══════════════════════════════════════════════════════════════
print('=' * 60)
print('【1. 淨值頁面】ya/yp010000')
html = fetch('https://www.moneydj.com/funddj/ya/yp010000.djhtm?a=ACPS02')
soup = BeautifulSoup(html, 'html.parser')

print('\n--- 所有表格（前6列）---')
for i, table in enumerate(soup.find_all('table')):
    rows = table.find_all('tr')[:6]
    data = [[td.get_text(strip=True) for td in row.find_all(['td','th'])] for row in rows]
    data = [r for r in data if any(c.strip() for c in r)]
    if data:
        print(f'  表格 {i}:')
        for row in data:
            print(f'    {row}')

print('\n--- 數值 > 100 的 td ---')
for td in soup.find_all('td'):
    txt = td.get_text(strip=True).replace(',', '')
    try:
        v = float(txt)
        if 100 < v < 99999:
            pr = td.find_parent('tr')
            row_cells = [x.get_text(strip=True) for x in pr.find_all(['td','th'])] if pr else []
            cls = td.get('class', '')
            print(f'  值={v}  class={cls}  同列={row_cells}')
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('【2. 持股頁面】yp/yp013000')
html2 = fetch('https://www.moneydj.com/funddj/yp/yp013000.djhtm?a=ACPS02')
soup2 = BeautifulSoup(html2, 'html.parser')

print('\n--- 所有表格（前12列）---')
for i, table in enumerate(soup2.find_all('table')):
    rows = table.find_all('tr')[:12]
    data = [[td.get_text(strip=True) for td in row.find_all(['td','th'])] for row in rows]
    data = [r for r in data if any(c.strip() for c in r)]
    if data:
        print(f'  表格 {i}:')
        for row in data:
            print(f'    {row}')
