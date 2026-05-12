"""
fetch_nav.py — 每日自動抓取四檔基金最新淨值並更新 data/nav.json
由 GitHub Actions 排程執行
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta

import anthropic


FUND_KEYS = ['安聯台灣科技', '安聯台灣大壩', '統一奔騰', '統一黑馬']
NAV_FILE = 'data/nav.json'


def today_str():
    # 台灣時間 UTC+8
    return (datetime.utcnow() + timedelta(hours=8)).strftime('%Y/%m/%d')


def one_year_ago_str():
    d = datetime.utcnow() + timedelta(hours=8) - timedelta(days=366)
    return d.strftime('%Y/%m/%d')


def load_nav():
    with open(NAV_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_nav(data):
    with open(NAV_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def trim_old_data(data):
    cutoff = one_year_ago_str()
    for fund in FUND_KEYS:
        if fund in data:
            data[fund] = {k: v for k, v in data[fund].items() if k >= cutoff}
    return data


def fetch_nav_from_api(today):
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=1000,
        system=(
            '你是基金淨值查詢助手。使用 web_search 搜尋台灣基金淨值。'
            '只輸出純 JSON，不含任何說明文字、markdown 或程式碼區塊。'
        ),
        tools=[{'type': 'web_search_20250305', 'name': 'web_search'}],
        messages=[{
            'role': 'user',
            'content': (
                f'請搜尋今日（{today}）四檔基金最新淨值，只回傳此 JSON（找不到填 null）：\n'
                '{"安聯台灣科技":數字,"安聯台灣大壩":數字,"統一奔騰":數字,"統一黑馬":數字}\n\n'
                '搜尋來源建議：安聯台灣科技基金淨值、安聯台灣大壩基金淨值、'
                '統一奔騰基金淨值、統一黑馬基金淨值'
            )
        }]
    )

    text = ''.join(c.text for c in response.content if c.type == 'text')
    match = re.search(r'\{[^{}]+\}', text)
    if not match:
        print('ERROR: No JSON found in API response')
        print('Response:', text[:500])
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f'ERROR: JSON parse failed: {e}')
        return None


def main():
    today = today_str()
    print(f'Running NAV update for {today}')

    data = load_nav()

    # Check if all funds already have today's data
    missing = [f for f in FUND_KEYS if today not in data.get(f, {})]
    if not missing:
        print(f'All funds already have data for {today}, skipping API call.')
        return

    print(f'Missing data for: {missing}')

    navs = fetch_nav_from_api(today)
    if not navs:
        print('Failed to fetch NAV data, exiting without changes.')
        sys.exit(1)

    updated = []
    for fund in FUND_KEYS:
        nav_value = navs.get(fund)
        if nav_value and isinstance(nav_value, (int, float)) and nav_value > 0:
            if fund not in data:
                data[fund] = {}
            data[fund][today] = round(float(nav_value), 2)
            updated.append(f'{fund}: {nav_value}')
        else:
            print(f'WARNING: No valid NAV found for {fund} (got: {nav_value})')

    if not updated:
        print('No valid NAV values found, exiting without changes.')
        sys.exit(1)

    print('Updated:', ', '.join(updated))

    # Trim data older than 1 year
    data = trim_old_data(data)

    # Update last_updated timestamp
    data['last_updated'] = today

    save_nav(data)
    print(f'nav.json saved successfully.')


if __name__ == '__main__':
    main()
