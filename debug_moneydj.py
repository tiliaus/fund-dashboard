"""
debug_moneydj.py — 檢查 MoneyDJ 頁面 HTML 結構
在 GitHub Actions 執行，輸出關鍵 HTML 片段幫助找出正確的 NAV 和持股位置
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

url = 'https://www.moneydj.com/funddj/yp/yp011000.djhtm?a=ACDD04'
print(f'抓取：{url}')
r = requests.get(url, headers=HEADERS, timeout=30)
print(f'狀態碼：{r.status_code}')
html = decode(r.content)

soup = BeautifulSoup(html, 'html.parser')
print(f'頁面標題：{soup.title.get_text() if soup.title else "無"}')
print(f'HTML 長度：{len(html)} 字元')
print()

# 找所有包含「淨值」的元素
print('=== 含「淨值」的 HTML 片段 ===')
for tag in soup.find_all(string=re.compile('淨值')):
    parent = tag.parent
    print(f'標籤：<{parent.name}> 內容：{parent.get_text(strip=True)[:100]}')
    # 印出祖父元素的完整 HTML
    gp = parent.parent
    if gp:
        print(f'父元素：{str(gp)[:300]}')
    print()

# 印出所有表格的前 5 列
print('=== 所有表格（前5列）===')
for i, table in enumerate(soup.find_all('table')):
    rows = table.find_all('tr')[:5]
    cells_list = []
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all(['td','th'])]
        if cells:
            cells_list.append(cells)
    if cells_list:
        print(f'表格 {i}：')
        for c in cells_list:
            print(f'  {c}')
    print()

# 印出所有數字超過 100 的 td 內容（可能是淨值）
print('=== 所有數值 > 100 的 td ===')
for td in soup.find_all('td'):
    txt = td.get_text(strip=True).replace(',','')
    try:
        v = float(txt)
        if v > 100:
            print(f'  {v}  (class={td.get("class")}, id={td.get("id")})')
            parent_row = td.find_parent('tr')
            if parent_row:
                row_cells = [x.get_text(strip=True) for x in parent_row.find_all(['td','th'])]
                print(f'    同列：{row_cells}')
    except Exception:
        pass
