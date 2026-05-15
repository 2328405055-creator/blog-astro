# textscripts · scrapers/news_scraper.py — RSS 新闻采集

import re
import logging
import urllib.parse

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from textscripts.config import CONFIG
from textscripts.utils.file_ops import clean_html, str_hash, source_domain

logger = logging.getLogger(__name__)

# ============================================================
# 信息源配置
# ============================================================

RSS_SOURCES = {
    "cross-border": [
        "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+Ozon+%E6%95%99%E7%A8%8B+%E5%85%A5%E9%97%A8+%E5%AE%9E%E6%93%8D&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=Ozon+%E8%BF%90%E8%90%A5+%E6%8A%80%E5%B7%A7+%E6%8C%87%E5%8D%97+%E9%80%89%E5%93%81+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+%E4%BF%84%E7%BD%97%E6%96%AF+%E9%80%89%E5%93%81+%E6%95%99%E7%A8%8B+%E7%BB%8F%E9%AA%8C&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83+%E7%89%A9%E6%B5%81+%E4%BF%84%E7%BD%97%E6%96%AF+%E5%AE%9E%E6%93%8D+%E6%96%B9%E6%B3%95&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E7%94%B5%E5%95%86+%E9%93%BA%E8%B4%A7+Ozon+%E6%95%99%E7%A8%8B+%E6%8A%80%E5%B7%A7&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E4%BF%84%E7%BD%97%E6%96%AF+%E7%94%B5%E5%95%86+%E5%B9%B3%E5%8F%B0+%E8%A7%84%E5%88%99+%E6%94%BF%E7%AD%96+%E5%85%A5%E9%A9%BB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=Wildberries+%E9%87%8E%E8%8E%93+%E4%BF%84%E7%BD%97%E6%96%AF+%E5%8D%96%E5%AE%B6+%E5%85%A5%E9%A9%BB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E4%BF%84%E7%BD%97%E6%96%AF+%E6%94%B6%E6%AC%BE+%E5%9B%9E%E6%AC%BE+%E5%8D%A2%E5%B8%83+%E6%B1%87%E7%8E%87+%E8%B7%A8%E5%A2%83&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=Ozon+FBO+FBS+%E6%B5%B7%E5%A4%96%E4%BB%93+%E5%8F%91%E8%B4%A7+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+%E9%80%89%E5%93%81+%E6%95%B0%E6%8D%AE+%E5%88%86%E6%9E%90+%E5%B7%A5%E5%85%B7&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    ],
    "ai-news": [
        "https://news.google.com/rss/search?q=AI+%E6%95%99%E7%A8%8B+%E5%85%A5%E9%97%A8+%E5%AD%A6%E4%B9%A0+%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=AI%E5%B7%A5%E5%85%B7+%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B+%E6%95%99%E5%AD%A6+%E5%AE%9E%E6%93%8D&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=AI+%E7%94%B5%E5%95%86+%E5%BA%94%E7%94%A8+%E6%95%99%E7%A8%8B+%E6%96%B9%E6%B3%95&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=AI+tutorial+guide+how-to+artificial+intelligence+learning&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=AI+%E7%BC%96%E7%A8%8B+%E5%BC%80%E5%8F%91+copilot+cursor+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=AI+%E8%AE%BE%E8%AE%A1+%E7%BB%98%E7%94%BB+midjourney+stable+diffusion+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=machine+learning+deep+learning+tutorial+beginner+guide&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=AI+automation+workflow+productivity+tools+tutorial&hl=en&gl=US&ceid=US:en",
    ],
    "fitness": [
        "https://news.google.com/rss/search?q=%E5%BE%92%E6%89%8B%E5%81%A5%E8%BA%AB+%E8%87%AA%E9%87%8D%E8%AE%AD%E7%BB%83+%E6%95%99%E7%A8%8B+%E4%BF%AF%E5%8D%A7%E6%92%91+%E6%B7%B1%E8%B9%B2&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=%E6%A0%B8%E5%BF%83%E8%AE%AD%E7%BB%83+%E7%91%9C%E4%BC%BD%E5%9E%AB+%E8%85%B9%E8%82%8C+%E5%81%A5%E8%BA%AB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=bodyweight+workout+home+routine+beginner+no+equipment&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=calisthenics+bodyweight+exercise+tutorial+plan&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=HIIT+workout+home+no+equipment+bodyweight+fat+burn&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=yoga+stretch+flexibility+beginner+routine+home+mat&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%E5%81%A5%E8%BA%AB+%E9%A5%AE%E9%A3%9F+%E8%90%A5%E5%85%BB+%E5%87%8F%E8%84%82+%E5%BE%92%E6%89%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=resistance+band+workout+tutorial+home+full+body&hl=en&gl=US&ceid=US:en",
    ],
}

BLACKLIST_FITNESS = [
    "明星", "演员", "刘亦菲", "死亡", "减肥药", "保险",
    "金融", "股票", "理财", "信用卡", "贷款", "基金", "投资",
    "celeb", "hollywood", "surgery", "weight loss drug",
    "insurance", "stock", "finance", "bankrupt",
]


def build_search_link(title, domain):
    """构建在源站搜索文章的直连"""
    q = urllib.parse.quote(title[:60])
    domain_clean = domain.replace("www.", "")
    search_templates = {
        "ebrun.com": f"https://www.ebrun.com/search?keyword={q}",
        "cifnews.com": f"https://www.cifnews.com/search?keyword={q}",
        "jiemian.com": f"https://www.jiemian.com/search/?keyword={q}",
        "sina.com.cn": f"https://search.sina.com.cn/?q={q}",
        "sohu.com": f"https://search.sohu.com/?keyword={q}",
        "163.com": f"https://search.163.com/search?keyword={q}",
    }
    for key, url in search_templates.items():
        if key in domain_clean:
            return url
    return f"https://www.google.com/search?q={q}+site:{domain_clean}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _fetch_feed(url):
    """抓取单个 RSS 源 (带重试)"""
    resp = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise requests.HTTPError(f"HTTP {resp.status_code}")
    return feedparser.parse(resp.content)


def fetch_all_feeds(section, limit_per_feed=8):
    """抓取 RSS 源，返回去重文章列表"""
    entries = []
    seen_links = set()

    for url in RSS_SOURCES.get(section, []):
        try:
            feed = _fetch_feed(url)
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)

                title = clean_html(entry.get("title", ""))
                if not title or len(title) < 10:
                    continue

                title_lower = title.lower()
                if section == "fitness":
                    if any(w in title_lower for w in BLACKLIST_FITNESS):
                        continue
                if any(w in title_lower for w in ["广告", "sponsored", "advertisement"]):
                    continue

                source = entry.get("source", {})
                source_href = source.get("href", "") if isinstance(source, dict) else ""
                source_name = source.get("title", "") if isinstance(source, dict) else ""
                if not source_name:
                    source_name = source_domain(link)

                summary_html = entry.get("summary", entry.get("description", ""))
                summary_text = clean_html(summary_html)[:300]

                entries.append({
                    "title": title,
                    "link": link,
                    "source_name": source_name,
                    "source_href": source_href,
                    "domain": source_domain(source_href) or source_domain(link),
                    "summary": summary_text,
                    "published": entry.get("published", ""),
                    "section": section,
                })
        except Exception as e:
            logger.warning(f"RSS 源抓取失败 {url[:60]}...: {e}")
            continue

    # 按来源去重
    unique = []
    domain_counts = {}
    for e in sorted(entries, key=lambda x: x.get("published", ""), reverse=True):
        domain = e["domain"]
        if domain_counts.get(domain, 0) >= 3:
            continue
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        unique.append(e)

    return unique


def fetch_fill(needed, exclude_hashes):
    """补充搜索 — 当主抓取不够时使用"""
    fill_urls = [
        ("cross-border", "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+%E4%BF%84%E7%BD%97%E6%96%AF+%E9%80%89%E5%93%81+%E8%BF%90%E8%90%A5+%E7%89%A9%E6%B5%81&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
        ("fitness", "https://news.google.com/rss/search?q=%E5%BE%92%E6%89%8B+%E8%87%AA%E9%87%8D+%E8%AE%AD%E7%BB%83+%E6%95%99%E7%A8%8B+%E4%BF%AF%E5%8D%A7%E6%92%91+%E6%B7%B1%E8%B9%B2+%E7%91%9C%E4%BC%BD+%E5%81%A5%E8%BA%AB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
        ("ai-news", "https://news.google.com/rss/search?q=AI+%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD+%E5%B7%A5%E5%85%B7+%E6%95%99%E7%A8%8B+%E5%BA%94%E7%94%A8&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ]

    results = []
    for section, url in fill_urls:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                link = entry.get("link", "")
                title = clean_html(entry.get("title", ""))
                if not title or len(title) < 10:
                    continue
                if str_hash(title) in exclude_hashes:
                    continue
                exclude_hashes.add(str_hash(title))
                source = entry.get("source", {})
                source_href = source.get("href", "") if isinstance(source, dict) else ""
                source_name = source.get("title", "") if isinstance(source, dict) else ""

                results.append({
                    "title": title,
                    "link": link,
                    "source_name": source_name or source_domain(link),
                    "source_href": source_href,
                    "domain": source_domain(source_href) or source_domain(link),
                    "summary": clean_html(entry.get("summary", ""))[:300],
                    "section": section,
                })
                if len(results) >= needed:
                    break
        except Exception as e:
            logger.warning(f"补充抓取失败: {e}")
    return results
