import sys
import os

# 将 packages 目录添加到 Python 路径
packages_dir = os.path.join(os.path.dirname(__file__), 'packages')
if os.path.exists(packages_dir):
    sys.path.insert(0, packages_dir)
# main.py 修复版
import flet as ft
import json
import datetime
import requests
from lxml import etree
from urllib.parse import urljoin
from datetime import timedelta

# ==============================================
# 全局配置
# ==============================================
url = "https://www.zgfp.com/search/searchprice.aspx?"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": url,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "close"
}

params = {
    "page": 1,
    "ChannelId": 8,
    "cid": 0,
    "e": 2,
    "a": 5318
}


# ==============================================
# 核心：获取网站上【最新有数据的日期】
# ==============================================
def get_latest_available_date():
    """自动获取网站上最新有数据的日期，当天没有就往前找"""
    current_date = datetime.date.today()

    # 先获取一次页面，拿到所有菏泽数据
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.encoding = "gb2312"
        tree = etree.HTML(res.text)
        all_heze_tr = tree.xpath('//table[@id="gvArticleList"]//tr[contains(td[2], "菏泽")]')

        if len(all_heze_tr) == 0:
            print("❌ 页面上没有找到任何菏泽数据")
            return None, None

        # 提取所有日期，取最新的那个
        dates_found = []
        for tr in all_heze_tr:
            td_date = tr.xpath('./td[4]/text()')
            if len(td_date) > 0:
                date_str = td_date[0].strip()
                if len(date_str) > 0:
                    dates_found.append(date_str)

        if len(dates_found) > 0:
            latest_date = max(dates_found)
            print(f"✅ 网站上最新的日期是: {latest_date}")
            return latest_date, tree

    except Exception as e:
        print("获取页面失败:", e)

    return None, None


# ==============================================
# 执行爬取
# ==============================================
today, tree = get_latest_available_date()
tr_list = []
if today and tree:
    tr_list = tree.xpath(f'//table[@id="gvArticleList"]//tr[contains(td[2], "菏泽") and contains(td[4], "{today}")]')

print(f"📊 菏泽价格条数: {len(tr_list)}")
print("=" * 50)


# ==============================================
# 爬详情页表格（优化稳定性）
# ==============================================
def get_detail_table(full_url):
    try:
        res = requests.get(full_url, headers=headers, timeout=10)
        res.encoding = "gb2312"
        tree = etree.HTML(res.text)
        tables = tree.xpath('//div[@class="content_zw"]//table')
        if len(tables) == 0:
            return []

        data = []
        for tr in tables[0].xpath('.//tr'):
            tds = tr.xpath('./td/text()')
            if len(tds) >= 3:
                data.append({
                    "品种": tds[0].strip(),
                    "最低价": tds[1].strip(),
                    "最高价": tds[2].strip()
                })
        return data
    except:
        return []


# ==============================================
# 批量抓取所有数据
# ==============================================
all_result = {}
for idx, tr in enumerate(tr_list, 1):
    try:
        cate = tr.xpath('./td[1]/text()')[0].strip()
        title = tr.xpath('./td[3]/a/text()')[0].strip()
        href = tr.xpath('./td[3]/a/@href')[0].strip()
        full_url = urljoin("https://www.zgfp.com/", href)

        print(f"第{idx}条: {cate}")
        table = get_detail_table(full_url)
        all_result[cate] = {
            "title": title,
            "url": full_url,
            "table": table
        }
    except:
        continue

# ==============================================
# 保存 JSON
# ==============================================
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(all_result, f, ensure_ascii=False, indent=2)

print("\n✅ 数据抓取完成!")


# ==============================================
# Flet APP 界面
# ==============================================
def load_data():
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def main(page: ft.Page):
    page.title = "破烂王 - 今日废品行情"
    page.window_width = 420
    page.window_height = 780
    page.padding = 15
    page.spacing = 10
    data = load_data()
    selected_tab = 0

    # 行情页面
    def build_market():
        items = [
            ft.Text("📦 破烂王行情实时版", size=28, weight=ft.FontWeight.BOLD),
            ft.Text(f"最新数据日期: {today if today else '无'}", size=14),
            ft.Text(f"更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", size=12),
            ft.Divider()
        ]

        if not data:
            items.append(ft.Text("⚠️ 暂无数据，请稍后再试", size=18))
            return ft.ListView(controls=items, expand=True, spacing=10)

        for cate_name, info in data.items():
            items.append(ft.Text(f"🏷️ {cate_name}", size=20, weight=ft.FontWeight.BOLD))
            for item in info.get("table", []):
                variety = item.get("品种", "未知")
                min_p = item.get("最低价", "-")
                max_p = item.get("最高价", "-")
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Row([
                            ft.Text(f"📌 {variety}", size=17, weight=ft.FontWeight.BOLD),
                            ft.Text(f"¥ {min_p} - {max_p} /吨", size=16)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        padding=15
                    ),
                    margin=ft.margin.only(bottom=6)
                )
                items.append(card)
            items.append(ft.Divider(height=10))

        return ft.ListView(controls=items, expand=True, spacing=10)

    # 计算器页面
    def build_calc():
        varieties = []
        for info in data.values():
            for item in info.get("table", []):
                if item.get("品种"):
                    varieties.append(item.get("品种"))

        type_drop = ft.Dropdown(label="选择品类", options=[ft.dropdown.Option(v) for v in varieties], expand=True)
        weight_input = ft.TextField(label="重量(kg)", expand=True, keyboard_type=ft.KeyboardType.NUMBER)
        result_text = ft.Text("总价: 0.00 元", size=18, weight=ft.FontWeight.BOLD)

        def calc(e):
            try:
                price = None
                for info in data.values():
                    for item in info.get("table", []):
                        if item.get("品种") == type_drop.value:
                            p_str = item.get("最高价", item.get("最低价", "0"))
                            price = float(''.join(c for c in p_str if c.isdigit() or c == "."))
                            break
                    if price:
                        break

                kg = float(weight_input.value)
                total = (price / 1000) * kg
                result_text.value = f"总价: {total:.2f} 元"
            except:
                result_text.value = "输入错误"
            page.update()

        return ft.Column([
            ft.Text("🧮 卖货计算器", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            type_drop, weight_input,
            ft.ElevatedButton("计算", on_click=calc),
            ft.Divider(),
            result_text
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    market = build_market()
    calc = build_calc()
    container = ft.Container(content=market, expand=True)

    def switch_tab(i):
        nonlocal selected_tab
        selected_tab = i
        container.content = market if i == 0 else calc
        page.update()

    page.bottom_appbar = ft.BottomAppBar(
        content=ft.Row([
            ft.TextButton("今日行情", on_click=lambda _: switch_tab(0)),
            ft.TextButton("卖货计算", on_click=lambda _: switch_tab(1)),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
    )

    page.add(container)
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
