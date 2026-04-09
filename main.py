import flet as ft
import json
import datetime
import time
import random
import threading
import asyncio
from lxml import etree
from urllib.parse import urljoin
import requests

# ======================
# 配置
# ======================
url = "https://www.zgfp.com/search/searchprice.aspx?"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Referer": url,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive"
}

# 城市编码字典
CITY_DICT = {
    "菏泽": 5318,
    "济宁": 5310,
    "济南": 5302,
    "聊城": 5316,
    "枣庄": 5305,
    "潍坊": 5307,
    "日照": 5312,
    "泰安": 5311,
    "德州": 5314,
    "淄博": 5304,
}

# ======================
# 爬虫核心函数（支持城市选择）
# ======================
def fetch_data(city_name, city_code):
    """执行爬虫，返回 (all_result, web_page_time, fetch_time)"""
    web_page_time = ""
    fetch_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 动态构建请求参数
    base_params = {
        "page": 1,
        "ChannelId": 8,
        "cid": 0,
        "e": 2,
        "a": city_code,
    }

    def get_latest_valid_date():
        nonlocal web_page_time
        today = datetime.date.today()
        for day_offset in range(7):
            check_date = today - datetime.timedelta(days=day_offset)
            date_str = f"{check_date.year}/{check_date.month}/{check_date.day}"
            try:
                time.sleep(random.uniform(0.5, 1.5))
                response = requests.get(url=url, headers=headers, params=base_params, timeout=10)
                response.encoding = "gb2312"
                tree = etree.HTML(response.text)
                # 使用城市名称过滤（表格第二列）
                tr_list = tree.xpath(f'//table[@id="gvArticleList"]//tr[contains(td[2], "{city_name}") and contains(td[4], "{date_str}")]')
                if len(tr_list) > 0:
                    web_page_time = date_str
                    return date_str, tree
            except Exception as e:
                print(f"检查日期 {date_str} 失败: {e}")
                continue
        return f"{today.year}/{today.month}/{today.day}", None

    valid_date, tree = get_latest_valid_date()
    if tree is None:
        response = requests.get(url=url, headers=headers, params=base_params, timeout=10)
        response.encoding = "gb2312"
        tree = etree.HTML(response.text)

    tr_list = tree.xpath(f'//table[@id="gvArticleList"]//tr[contains(td[2], "{city_name}") and contains(td[4], "{valid_date}")]')
    print(f"🎯 城市: {city_name}, 网页数据时间: {web_page_time}")
    print(f"📅 本次获取时间: {fetch_time}")
    print(f"📊 {city_name}价格条数: {len(tr_list)}")

    def get_detail_table(full_url):
        try:
            time.sleep(random.uniform(0.5, 1.0))
            res = requests.get(full_url, headers=headers, timeout=10)
            res.encoding = "gb2312"
            tree = etree.HTML(res.text)
            tables = tree.xpath('//div[@class="content_zw"]//table')
            if not tables:
                return []
            table = tables[0]
            rows = table.xpath('.//tr')
            data = []
            for tr in rows:
                tds = tr.xpath('./td/text()')
                if len(tds) >= 3:
                    data.append({
                        "品种": tds[0].strip(),
                        "最低价": tds[1].strip(),
                        "最高价": tds[2].strip()
                    })
            return data
        except Exception as e:
            print(f"详情页爬取失败: {e}")
            return []

    all_result = {}
    for index, tr in enumerate(tr_list, 1):
        try:
            category = tr.xpath('./td[1]/text()')[0].strip()
            title = tr.xpath('./td[3]/a/text()')[0].strip()
            href = tr.xpath('./td[3]/a/@href')[0].strip()
            full_url = urljoin("https://www.zgfp.com/", href)
            print(f"===== 第{index}条 =====")
            print(f"品类: {category}")
            print(f"标题: {title}")
            print(f"链接: {full_url}")
            table_data = get_detail_table(full_url)
            print(f"表格数据: {table_data}")
            all_result[category] = {
                "title": title,
                "url": full_url,
                "table": table_data
            }
            print("-" * 40)
        except Exception as e:
            print(f"跳过错误项: {e}")
            continue

    return all_result, web_page_time, fetch_time


# ======================
# Flet APP界面（异步更新UI）
# ======================
def main(page: ft.Page):
    page.title = "再生王 - 再生资源今日行情"
    page.window_width = 420
    page.window_height = 780
    page.padding = 15
    page.spacing = 10
    page.scroll = ft.ScrollMode.AUTO

    # 状态变量
    data = {}
    web_time = ""
    fetch_time_str = ""

    # 界面控件
    market_list = ft.ListView(expand=True, spacing=10)
    status_text = ft.Text("", size=12)

    # 城市下拉框
    city_dropdown = ft.Dropdown(
        label="选择城市",
        options=[ft.dropdown.Option(name) for name in CITY_DICT.keys()],
        value="菏泽",
        width=150,
    )
    refresh_btn = ft.ElevatedButton("刷新行情", on_click=lambda e: refresh_data())

    # 计算器相关控件
    type_drop = ft.Dropdown(label="选择品类", expand=True)
    weight_input = ft.TextField(label="重量(kg)", expand=True, keyboard_type=ft.KeyboardType.NUMBER)
    result_text = ft.Text("总价：0.00 元", size=18, weight=ft.FontWeight.BOLD)

    # ========== 异步UI更新函数 ==========
    async def update_market_view():
        market_list.controls.clear()
        market_list.controls.append(ft.Text("📦 再生行情实时版", size=28, weight=ft.FontWeight.BOLD))
        current_city = city_dropdown.value
        market_list.controls.append(ft.Text(f"当前城市：{current_city}", size=14, weight=ft.FontWeight.BOLD))
        market_list.controls.append(ft.Text(f"网页数据时间: {web_time}", size=14))
        market_list.controls.append(ft.Text(f"本次获取时间: {fetch_time_str}", size=12))
        market_list.controls.append(ft.Divider())

        if not data:
            market_list.controls.append(ft.Text("❌ 未获取到数据，请点击「刷新行情」", size=16))
            await page.update_async()
            return

        for category_name, category_info in data.items():
            market_list.controls.append(ft.Text(f"🏷️ {category_name}", size=20, weight=ft.FontWeight.BOLD))
            table_data = category_info.get("table", [])
            if not table_data:
                market_list.controls.append(ft.Text("   暂无报价", italic=True))
                continue
            for item in table_data:
                variety = item.get("品种", "未知品种")
                min_price = item.get("最低价", "-")
                max_price = item.get("最高价", "-")
                price_text = f"¥ {min_price} - {max_price} /吨"
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Row([
                            ft.Text(f"📌 {variety}", size=17, weight=ft.FontWeight.BOLD),
                            ft.Text(price_text, size=16)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        padding=15
                    ),
                    margin=ft.margin.only(bottom=6)
                )
                market_list.controls.append(card)
            market_list.controls.append(ft.Divider(height=10))
        await page.update_async()

    async def update_calc_dropdown():
        varieties = []
        for cat_info in data.values():
            for item in cat_info.get("table", []):
                if item.get("品种"):
                    varieties.append(item.get("品种"))
        type_drop.options = [ft.dropdown.Option(v) for v in varieties]
        await page.update_async()

    async def set_status_text(msg):
        status_text.value = msg
        await page.update_async()

    async def set_refresh_btn_state(disabled: bool):
        refresh_btn.disabled = disabled
        await page.update_async()

    # 计算回调
    def calc_total(e):
        try:
            target_price_str = None
            for cat_info in data.values():
                for item in cat_info.get("table", []):
                    if item.get("品种") == type_drop.value:
                        target_price_str = item.get("最高价", item.get("最低价", "0"))
                        break
                if target_price_str:
                    break
            if not target_price_str:
                result_text.value = "未找到价格"
                page.update()
                return
            price_str = ''.join(c for c in str(target_price_str) if c.isdigit() or c == '.')
            price_per_ton = float(price_str)
            weight_kg = float(weight_input.value)
            total = (price_per_ton / 1000) * weight_kg
            result_text.value = f"总价：{total:.2f} 元"
        except:
            result_text.value = "输入错误"
        page.update()

    # 刷新数据（后台线程）
    def refresh_data():
        refresh_btn.disabled = True
        status_text.value = "正在获取数据，请稍候..."
        page.update()

        selected_city = city_dropdown.value
        city_code = CITY_DICT.get(selected_city, 5318)

        def task():
            nonlocal data, web_time, fetch_time_str
            try:
                new_data, new_web_time, new_fetch_time = fetch_data(selected_city, city_code)
                data = new_data
                web_time = new_web_time
                fetch_time_str = new_fetch_time

                asyncio.run_coroutine_threadsafe(update_market_view(), page.loop)
                asyncio.run_coroutine_threadsafe(update_calc_dropdown(), page.loop)
                asyncio.run_coroutine_threadsafe(set_status_text(f"更新成功：{web_time} ({selected_city})"), page.loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(set_status_text(f"更新失败：{str(e)}"), page.loop)
            finally:
                asyncio.run_coroutine_threadsafe(set_refresh_btn_state(False), page.loop)

        threading.Thread(target=task, daemon=True).start()

    # 构建界面布局
    top_row = ft.Row(
        [city_dropdown, refresh_btn, status_text],
        alignment=ft.MainAxisAlignment.START,
        spacing=10,
    )
    market_column = ft.Column(
        [top_row, market_list],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    calc_column = ft.Column([
        ft.Text("🧮 卖货计算器", size=24, weight=ft.FontWeight.BOLD),
        ft.Divider(),
        ft.Text("价格单位：元/吨 | 计算单位：千克", size=12),
        type_drop, weight_input,
        ft.ElevatedButton("计算", on_click=calc_total, expand=True),
        ft.Divider(height=20),
        result_text
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    container = ft.Container(content=market_column, expand=True)
    selected_tab = 0

    def switch_tab(index):
        nonlocal selected_tab
        selected_tab = index
        container.content = market_column if index == 0 else calc_column
        page.update()

    page.bottom_appbar = ft.BottomAppBar(
        content=ft.Row([
            ft.TextButton("今日行情", on_click=lambda e: switch_tab(0)),
            ft.TextButton("卖货计算", on_click=lambda e: switch_tab(1)),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
    )

    page.add(container)
    # 启动时自动刷新一次
    refresh_data()


if __name__ == "__main__":
    ft.app(target=main)
