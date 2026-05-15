# textscripts · generators/ozon_generator.py — Ozon 每日选品生成器
# 从 scripts/ozon_selector.py 迁移核心逻辑，保持完全兼容

import json
import os
import sys
import re
import hashlib
import logging
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import feedparser

from textscripts.config import BASE_DIR, POSTS_DIR, JSON_PATH, SCRIPTS_DIR
from textscripts.scrapers.wildberries_scraper import (
    fetch_wildberries_products,
    load_previous_data,
    calculate_trend_score,
)
from textscripts.utils.ru_utils import (
    translate_ru,
    generate_recommendation,
    assess_risks,
)
from textscripts.utils.file_ops import load_json, save_json, slugify, today_str

logger = logging.getLogger(__name__)

FEATURED_JSON_PATH = os.path.join(POSTS_DIR, "featured_ozon_pick.json")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


# ====== 汇率 ======

def fetch_rub_cny_rate():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/CNY", timeout=10)
        if r.status_code == 200:
            return r.json().get("rates", {}).get("RUB", 13.5)
    except Exception:
        pass
    return 13.5


# ====== 俄罗斯新闻 RSS ======

def fetch_russian_news(config):
    """抓取俄语 Google News RSS"""
    rss_config = config.get("scrape_sources", {}).get("russian_news_rss", {})
    feeds = rss_config.get("feeds", [])
    articles = []
    seen = set()

    for feed_url in feeds:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(feed_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if len(title) < 10 or link in seen:
                    continue
                seen.add(link)
                source_info = entry.get("source", {})
                source_name = ""
                if isinstance(source_info, dict):
                    source_name = source_info.get("title", "")
                articles.append({
                    "title": title,
                    "link": link,
                    "source_name": source_name,
                    "published": entry.get("published", ""),
                    "summary": (entry.get("summary", "") or "")[:300],
                })
        except Exception as e:
            logger.warning(f"RSS 请求失败: {e}")
    return articles


# ====== 市场概览 ======

def generate_market_summary(products, news_articles, rate):
    """基于采集数据生成当日市场概览"""
    now = datetime.now()
    parts = []
    is_real_data = any(not p.get("is_news_insight", False) for p in products) if products else False

    if is_real_data:
        real_products = [p for p in products if not p.get("is_news_insight", False)]
        total = len(real_products)
        avg_rating = sum(p["rating"] for p in real_products) / total if total else 0
        avg_price = sum(p["price_rub"] for p in real_products) / total if total else 0
        cats = defaultdict(int)
        for p in real_products:
            cats[p.get("cat_cn", "其他")] += 1

        parts.append("## 数据概览")
        parts.append(f"- 数据来源: **Wildberries 平台真实销量排序** (v18 API)")
        parts.append(f"- 搜索关键词: 32个精确商品品类, 覆盖电子配件/运动/美妆/家居/母婴/服装")
        parts.append(f"- 采集商品: {total} 款 (均分 {avg_rating:.1f}/5.0, 均价 {avg_price:.0f} ₽)")
        parts.append(f"- 热门细分类目: {', '.join(f'{c}({n}款)' for c, n in sorted(cats.items(), key=lambda x: -x[1])[:5])}")
        parts.append(f"- 采集时间: {now.strftime('%Y-%m-%d %H:%M')} CST")
    else:
        parts.append("## 数据模式: 新闻趋势分析")
        parts.append(f"- 今日采集俄罗斯电商相关资讯 {len(news_articles) if news_articles else 0} 条")

    if news_articles:
        parts.append("\n## 相关市场动态")
        for n in news_articles[:5]:
            title = n.get("title", "")[:100]
            if title:
                parts.append(f"- {title}")

    parts.append("\n## 参考信息")
    parts.append(f"- 参考汇率: 1 CNY ≈ {rate:.2f} RUB (open.er-api.com)")
    parts.append(f"- 数据时效: 采集于 {now.strftime('%Y-%m-%d %H:%M')} CST")
    parts.append("- > 以上数据均来自 Wildberries 平台公开接口")

    return "\n".join(parts)


# ====== Markdown 生成 ======

def build_featured_md(featured_data):
    """生成置顶选品文章的 Markdown"""
    date_str = featured_data["date"]
    products = featured_data["products"]
    market_summary = featured_data.get("market_summary_cn", "")
    generated_at = featured_data.get("generated_at", "")
    is_real = any(not p.get("is_news_insight", False) for p in products) if products else False

    md = f"""# 🏆 Ozon俄罗斯站每日选品推荐 — {date_str}

> 📊 数据采集: {generated_at or date_str} CST
> 🔍 数据来源: {'**Wildberries 平台真实销量排序** (v18 API)' if is_real else 'Google News 俄罗斯电商资讯'}

---

{market_summary}

---

## 🏅 今日精选推荐

"""

    medals = ["🥇", "🥈", "🥉"] + ["📌"] * 7
    for i, p in enumerate(products):
        medal = medals[i] if i < len(medals) else "📌"
        name = p.get("product_name_cn") or p.get("product_name_ru", "")
        md += f"""### {medal} #{p.get('rank', i+1)} {name}

| 属性 | 值 |
|------|-----|
| 🔢 **WB SKU** | `{p.get('nm_id', 'N/A')}` |
| 🏷 **品牌** | {p.get('brand', 'N/A')} |
| 💰 **价格** | {p.get('price_rub', 0):,} ₽ (≈ {p.get('price_cny', 0)} CNY) |
| ⭐ **评分** | {p.get('rating', 0)} / 5.0 ({p.get('review_count', 0):,} 评价) |
| 📈 **趋势分** | {p.get('trend_score', 0)}/100 {'🔥' if p.get('trend_score', 0) >= 70 else ''} |
| 🏷 **分类** | {p.get('cat_cn', '')} |
| 🔗 **WB 链接** | [查看商品]({p.get('wb_url', '#')}) |

**推荐理由:** {p.get('recommendation_reason_cn', '暂无')}

**⚠️ 风险提示:**
{chr(10).join(f'- {r}' for r in (p.get('risk_warnings_cn', []) if isinstance(p.get('risk_warnings_cn'), list) else [p.get('risk_warnings_cn', '')]))}

---
"""
    md += f"""## 📋 免责声明与方法说明

- 数据来自 Wildberries 公开 API，仅供选品参考
- 趋势评分算法: 销量排序(15分) + 评分(10分) + 评价数(10分) + 价格区间(10分) + 评价增长(10分)
- 价格按当日汇率换算，实际结算以平台为准
- 跨境销售需自行确认 EAC 认证/GOST 合规/品牌授权

*[猫明之主](https://20020426.top) · {date_str}*
"""
    return md


# ====== 保存与索引 ======

def save_featured_post(featured_data, md_content):
    """保存置顶文章并更新 posts.json 索引"""
    slug = featured_data["slug"]
    date_str = featured_data["date"]

    md_path = os.path.join(POSTS_DIR, f"{slug}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    save_json(FEATURED_JSON_PATH, featured_data)

    posts = load_json(JSON_PATH)
    entry = {
        "slug": slug,
        "title": f"🏆 Ozon每日选品推荐 — {date_str}",
        "date": date_str,
        "lastmod": date_str,
        "excerpt": featured_data.get("market_summary_cn", "")[:150] or f"今日推荐{len(featured_data.get('products',[]))}款俄罗斯热销商品",
        "cat": "ozon-pick",
        "sub": "daily-select",
        "featured": True,
        "verified": featured_data.get("verified", False),
        "source": "Wildberries v18 API",
        "source_name": "猫明之主",
    }

    new_posts = []
    for p in posts:
        p.pop("featured", None)
        if p.get("slug") == slug:
            continue
        new_posts.append(p)
    new_posts.insert(0, entry)
    new_posts.sort(key=lambda x: x.get("date", ""), reverse=True)
    save_json(JSON_PATH, new_posts)

    logger.info(f"置顶文章已保存: posts/{slug}.md")
    logger.info(f"posts.json 更新: {len(new_posts)} 篇文章")


# ====== 主编排（6 步流水线）======

def run_selector(config, dry_run=False):
    """Ozon 每日选品主编排

    6 步流水线:
    1. 获取汇率
    2. Wildberries API 采集
    3. 加载昨日数据做趋势对比
    4. Yandex Wordstat (可选, 当前禁用)
    5. 采集俄罗斯电商新闻 RSS
    6. 趋势评分 + 排序 + 生成推荐理由

    Returns:
        featured_data dict (dry_run=True) 或 None (dry_run=False, 已写入文件)
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    slug = f"ozon-daily-pick-{date_str}"

    logger.info(f"{'='*60}")
    logger.info(f"  Ozon 俄罗斯站每日选品 v3 — {date_str}")
    logger.info(f"  数据源: WB v18 API (真实销量排序)")
    logger.info(f"{'='*60}")

    # 1. 汇率
    logger.info("[1/6] 获取汇率...")
    rate = fetch_rub_cny_rate()
    logger.info(f"  1 CNY ≈ {rate:.2f} RUB")

    # 2. WB 采集
    logger.info("[2/6] Wildberries API 采集...")
    all_wb_products = []
    wb_config = config.get("scrape_sources", {}).get("wildberries", {})
    if wb_config.get("enabled", True):
        try:
            all_wb_products = fetch_wildberries_products(config)
            logger.info(f"  总计采集: {len(all_wb_products)} 款商品")
        except Exception as e:
            logger.error(f"WB 采集失败: {e}")
            logger.info("尝试使用昨日数据兜底...")
            prev_data = load_previous_data(BASE_DIR)
            if prev_data:
                all_wb_products = list(prev_data.values())
                logger.info(f"兜底数据: {len(all_wb_products)} 款商品 (昨日)")
    else:
        logger.info("  [SKIP] WB 采集已禁用")

    # 3. 加载昨日数据做趋势对比
    logger.info("[3/6] 加载昨日数据做趋势对比...")
    prev_data = load_previous_data(BASE_DIR)
    logger.info(f"  昨日数据: {len(prev_data)} 款商品")

    # 4. Yandex Wordstat (可选)
    logger.info("[4/6] Yandex Wordstat (可选)...")
    ws_config = config.get("scrape_sources", {}).get("yandex_wordstat", {})
    if ws_config.get("enabled", False):
        logger.info("  [SKIP] Yandex Wordstat 需企业认证, 未启用")
    else:
        logger.info("  [SKIP] Yandex Wordstat 未启用")

    # 5. RSS 新闻
    logger.info("[5/6] 采集俄罗斯电商新闻...")
    news_articles = fetch_russian_news(config)
    logger.info(f"  获取 {len(news_articles)} 条新闻")

    # 6. 趋势评分 + 排序 + 生成推荐
    logger.info("[6/6] 趋势评分 + 生成推荐...")
    for p in all_wb_products:
        p["trend_score"] = calculate_trend_score(p, prev_data)

    all_wb_products.sort(key=lambda x: (x.get("trend_score", 0), x.get("rating", 0)), reverse=True)

    max_products = config.get("output", {}).get("max_products", 10)
    top_products = all_wb_products[:max_products]

    featured_products = []
    for rank, p in enumerate(top_products):
        name_cn = translate_ru(p["product_name_ru"])
        price_cny = round(p["price_rub"] / rate, 1) if rate else 0
        trend_score = p.get("trend_score", 50)

        prod = {
            "rank": rank + 1,
            "nm_id": p.get("nm_id", ""),
            "product_name_ru": p["product_name_ru"],
            "product_name_cn": name_cn,
            "brand": p.get("brand", ""),
            "cat_cn": p.get("cat_cn", ""),
            "cat_key": p.get("cat_key", ""),
            "price_rub": p["price_rub"],
            "price_cny": price_cny,
            "rating": p["rating"],
            "review_count": p["review_count"],
            "trend_score": trend_score,
            "sort_mode": p.get("sort_mode", ""),
            "search_keyword": p.get("search_keyword", ""),
            "wb_url": p.get("wb_url", ""),
            "source_urls": [p.get("wb_url", "")],
            "recommendation_reason_cn": generate_recommendation(
                {"product_name_cn": name_cn, "price_rub": p["price_rub"], "price_cny": price_cny,
                 "rating": p["rating"], "review_count": p["review_count"], "cat_cn": p.get("cat_cn", ""),
                 "sort_mode": p.get("sort_mode", "")}, rank + 1, trend_score
            ),
            "risk_warnings_cn": assess_risks(
                {"cat_cn": p.get("cat_cn", ""), "cat_key": p.get("cat_key", ""),
                 "price_cny": price_cny, "review_count": p["review_count"],
                 "sort_mode": p.get("sort_mode", ""), "nm_id": p.get("nm_id", "")}
            ),
        }
        featured_products.append(prod)

    logger.info(f"  最终推荐: {len(featured_products)} 款商品")

    # 数据不足降级: 新闻趋势分析
    if len(featured_products) < 3:
        logger.info("商品数据不足, 降级为新闻趋势分析...")
        cat_hits = defaultdict(list)
        for a in news_articles:
            title = a.get("title", "").lower()
            for cat_key, keywords in [
                ("audio", ["наушники", "колонка", "гарнитура", "headphone", "speaker", "耳机", "音箱"]),
                ("smart-home", ["умный", "розетка", "лампа", "smart", "智能"]),
                ("sports", ["спорт", "фитнес", "йога", "тренировка", "sport", "fitness", "运动", "健身"]),
                ("beauty", ["косметика", "уход", "красота", "beauty", "美妆", "护肤"]),
                ("home", ["дом", "кухня", "посуда", "home", "kitchen", "家居", "厨房"]),
                ("kids", ["дети", "игрушка", "kids", "toy", "儿童", "玩具"]),
                ("clothing", ["одежда", "обувь", "fashion", "服装", "鞋"]),
            ]:
                if any(kw in title for kw in keywords):
                    cat_hits[cat_key].append(a)
                    break

        cat_names = {"audio": "无线耳机/音箱", "smart-home": "智能家居", "sports": "运动户外",
                     "beauty": "美妆健康", "home": "家居用品", "kids": "母婴玩具", "clothing": "服装鞋包"}
        for rank, (cat_key, articles) in enumerate(sorted(cat_hits.items(), key=lambda x: -len(x[1]))[:10]):
            cat_cn = cat_names.get(cat_key, cat_key)
            ref_prices = {"audio": 2000, "smart-home": 1500, "sports": 1200, "beauty": 800,
                          "home": 1000, "kids": 1200, "clothing": 2000}
            ref_price = ref_prices.get(cat_key, 1200)
            featured_products.append({
                "rank": rank + 1, "nm_id": "",
                "product_name_ru": f"{cat_cn}趋势", "product_name_cn": f"📊 {cat_cn}选品机会",
                "brand": "", "cat_cn": cat_cn, "cat_key": cat_key,
                "price_rub": ref_price, "price_cny": round(ref_price / rate, 1),
                "rating": 0, "review_count": len(articles),
                "trend_score": 30 + len(articles) * 5, "sort_mode": "news",
                "search_keyword": "", "wb_url": "",
                "source_urls": [a.get("link", "") for a in articles[:3] if a.get("link")],
                "recommendation_reason_cn": f"基于 {len(articles)} 条新闻的趋势分析；建议到 WB/Ozon 搜索确认具体商品",
                "risk_warnings_cn": ["此为新闻趋势分析, 非实时商品数据", "建议到 WB/Ozon 平台确认具体 SKU"],
                "is_news_insight": True,
            })
        logger.info(f"  新闻趋势: {len(featured_products)} 条类目趋势")

    # 构建数据
    data_sources = []
    if wb_config.get("enabled", True) and all_wb_products:
        data_sources.append({"name": "Wildberries v18 API (真实销量排序)", "url": "https://search.wb.ru/", "reliability": "high"})
    if news_articles:
        data_sources.append({"name": "Google News RSS (RU+EN)", "url": "https://news.google.com/", "reliability": "medium"})

    market_summary = generate_market_summary(featured_products, news_articles, rate)

    featured_data = {
        "slug": slug, "date": date_str, "generated_at": generated_at,
        "verified": False, "verification_report": None,
        "products": featured_products,
        "market_summary_cn": market_summary,
        "data_sources": data_sources,
    }

    md_content = build_featured_md(featured_data)

    if dry_run:
        logger.info("DRY RUN — 预览 (未写入文件)")
        print(json.dumps(featured_data, ensure_ascii=False, indent=2))
        return featured_data

    save_featured_post(featured_data, md_content)

    # 保存原始数据
    raw_dir = os.path.join(BASE_DIR, config.get("output", {}).get("data_dump_dir", "data/ozon_raw"))
    ensure_dir(raw_dir)
    raw_dump = {
        "date": date_str,
        "generated_at": generated_at,
        "rate_cny_rub": rate,
        "wb_products_all": all_wb_products[:100],
        "news_articles": news_articles[:20],
    }
    save_json(os.path.join(raw_dir, f"raw_{date_str}.json"), raw_dump)
    logger.info(f"原始数据存档: data/ozon_raw/raw_{date_str}.json")

    # 清理过期数据
    keep_days = config.get("output", {}).get("keep_raw_days", 7)
    cutoff = now - timedelta(days=keep_days)
    if os.path.exists(raw_dir):
        for fname in os.listdir(raw_dir):
            if fname.startswith("raw_") and fname.endswith(".json"):
                fpath = os.path.join(raw_dir, fname)
                try:
                    fdate_str = fname[4:14]
                    fdate = datetime.strptime(fdate_str, "%Y-%m-%d")
                    if fdate < cutoff:
                        os.remove(fpath)
                except Exception:
                    pass

    logger.info(f"{'='*60}")
    logger.info(f"  完成! 今日推荐 {len(featured_products)} 款商品")
    logger.info(f"{'='*60}")
