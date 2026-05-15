# textscripts · scrapers/wildberries_scraper.py — Wildberries API 采集 + 趋势分析

import json
import os
import time
import random
import hashlib
import urllib.parse
import logging
from datetime import datetime, timedelta
from collections import defaultdict

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# UA 轮换池 (扩大至 7 个)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def random_ua():
    return random.choice(USER_AGENTS)


def random_delay(min_s=2, max_s=8):
    time.sleep(random.uniform(min_s, max_s))


# 无代理 Session
_NO_PROXY_SESSION = None


def _get_no_proxy_session():
    global _NO_PROXY_SESSION
    if _NO_PROXY_SESSION is None:
        _NO_PROXY_SESSION = requests.Session()
        _NO_PROXY_SESSION.trust_env = False
    return _NO_PROXY_SESSION


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20))
def _fetch_wb_page(url, headers):
    """抓取 WB API 页面 (带重试)"""
    resp = _get_no_proxy_session().get(url, headers=headers, timeout=25)
    if resp.status_code == 429:
        raise requests.HTTPError("429 Too Many Requests")
    if resp.status_code != 200:
        raise requests.HTTPError(f"HTTP {resp.status_code}")
    return resp.json()


def fetch_wildberries_products(config):
    """使用 WB v18 API 搜索关键词，获取真实热门商品"""
    wb_config = config.get("scrape_sources", {}).get("wildberries", {})
    base_url = wb_config.get("base_url")
    dest = wb_config.get("dest", "-1257786")
    delay = wb_config.get("request_delay_seconds", 8)
    min_rating = wb_config.get("min_rating", 4.0)
    min_reviews = wb_config.get("min_reviews", 30)
    spp = wb_config.get("products_per_page", 60)
    queries = wb_config.get("queries", [])

    all_products = []
    seen_ids = set()

    for qi, query_item in enumerate(queries):
        keyword = query_item["keyword"]
        cat_cn = query_item.get("cat_cn", "")
        cat_key = query_item.get("cat_key", "")

        for sort_mode in ["popular", "newly"]:
            params = {
                "appType": "1",
                "curr": "rub",
                "dest": dest,
                "page": "1",
                "query": keyword,
                "resultset": "catalog",
                "sort": sort_mode,
                "spp": str(spp),
                "suppressSpellcheck": "False",
            }
            url = base_url + "?" + urllib.parse.urlencode(params)

            for attempt in range(3):
                try:
                    headers = {
                        "User-Agent": random_ua(),
                        "Accept": "application/json",
                        "Accept-Language": "ru-RU,ru;q=0.9",
                        "Origin": "https://www.wildberries.ru",
                        "Referer": "https://www.wildberries.ru/",
                    }
                    data = _fetch_wb_page(url, headers)

                    products = data.get("products", [])
                    if not products:
                        products = data.get("data", {}).get("products", [])

                    if attempt == 0:
                        total = data.get("total", data.get("data", {}).get("total", 0))
                        logger.info(f"[{sort_mode}] {keyword}: {len(products)}件 (总计{total:,}件)")

                    for p in products:
                        nm_id = str(p.get("id", ""))
                        if nm_id in seen_ids:
                            continue
                        seen_ids.add(nm_id)

                        name = p.get("name", "")
                        if not name or len(name) < 5:
                            continue

                        rating = float(p.get("reviewRating", 0) or 0)
                        reviews = int(p.get("feedbacks", 0) or 0)
                        if rating < min_rating or reviews < min_reviews:
                            continue

                        price_kop = 0
                        sizes = p.get("sizes", [])
                        if sizes:
                            sp = sizes[0].get("price", {})
                            price_kop = int(sp.get("product", 0) or sp.get("basic", 0) or 0)
                        if price_kop == 0:
                            price_kop = int(p.get("salePriceU") or p.get("priceU") or 0)
                        if price_kop < 5000:
                            continue
                        price_rub = price_kop // 100

                        brand = p.get("brand", "")
                        all_products.append({
                            "nm_id": nm_id,
                            "product_name_ru": name,
                            "brand": brand,
                            "price_rub": price_rub,
                            "rating": round(rating, 1),
                            "review_count": reviews,
                            "wb_url": f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
                            "cat_cn": cat_cn,
                            "cat_key": cat_key,
                            "sort_mode": sort_mode,
                            "search_keyword": keyword,
                        })
                        break  # 每关键词每排序模式只取TOP1
                    break  # 成功，退出重试循环

                except requests.HTTPError as e:
                    if "429" in str(e) and attempt < 2:
                        wait = delay * (2 + attempt) + random.random() * 8
                        logger.warning(f"限流 {keyword}, 等待 {wait:.0f}s...")
                        time.sleep(wait)
                    elif attempt >= 2:
                        logger.warning(f"跳过 {keyword} ({sort_mode}): {e}")
                        break
                    else:
                        time.sleep(2)
                except Exception as e:
                    if attempt < 2:
                        time.sleep((2 ** attempt) * 3)
                    else:
                        logger.error(f"抓取失败 {keyword} ({sort_mode}): {e}")

            random_delay(2, 8)  # 请求间随机延迟

    return all_products


# ====== 趋势评分 ======

def load_previous_data(base_dir, date_str=None):
    """加载前一天的数据用于趋势对比；如果不存在则尝试找最近的数据"""
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    raw_dir = os.path.join(base_dir, "data", "ozon_raw")
    raw_path = os.path.join(raw_dir, f"raw_{date_str}.json")

    prev = None
    if os.path.exists(raw_path):
        with open(raw_path, "r", encoding="utf-8") as f:
            prev = json.load(f)
    else:
        # 兜底：查找最近可用的原始数据
        if os.path.exists(raw_dir):
            files = sorted([f for f in os.listdir(raw_dir) if f.startswith("raw_") and f.endswith(".json")], reverse=True)
            for fname in files:
                fpath = os.path.join(raw_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        prev = json.load(f)
                    if prev:
                        logger.info(f"兜底数据: 使用 {fname} 作为昨日数据")
                        break
                except Exception:
                    continue

    if prev:
        prev_products = prev.get("wb_products_all", [])
        return {p.get("nm_id", ""): p for p in prev_products}
    return {}


def calculate_trend_score(product, prev_data):
    """计算趋势分数 (0-100)"""
    score = 50
    nm_id = product.get("nm_id", "")
    rating = product.get("rating", 0)
    reviews = product.get("review_count", 0)
    price = product.get("price_rub", 0)
    sort_mode = product.get("sort_mode", "")

    if sort_mode == "popular":
        score += 15
    if sort_mode == "newly":
        score += 5
    if rating >= 4.7:
        score += 10
    elif rating >= 4.3:
        score += 5
    if 100 <= reviews <= 3000:
        score += 10
    elif 50 <= reviews < 100:
        score += 5
    elif reviews > 5000:
        score -= 5
    if 500 <= price <= 4000:
        score += 10
    elif 4000 < price <= 8000:
        score += 5
    if nm_id in prev_data:
        prev = prev_data[nm_id]
        prev_reviews = prev.get("review_count", 0)
        if prev_reviews > 0 and reviews > prev_reviews:
            growth = (reviews - prev_reviews) / prev_reviews
            if growth > 0.1:
                score += 10
            elif growth > 0.03:
                score += 5
        if rating > prev.get("rating", 0) + 0.05:
            score += 3
    else:
        score += 5

    return min(100, max(10, score))
