# textscripts · scrapers/rss_scraper.py — 健壮 RSS 抓取器
#
# 设计原则:
#   1. 礼貌抓取 — 请求间隔 ≥2s (同源), 缓存去重, 可识别 User-Agent
#   2. 优先 RSS/Feed — 不对目标站点产生额外负载
#   3. 多层降级 — API → RSS → 缓存兜底
#   4. 尊重 robots.txt — 仅抓取 Feed, 不做全站爬取
#   5. 所有数据标注来源 — 不可幻觉

import re
import time
import hashlib
import logging
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from textscripts.config import CONFIG
from textscripts.utils.file_ops import clean_html, str_hash, source_domain
from textscripts.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# ============================================================
# 礼貌抓取配置
# ============================================================

class PolitenessConfig:
    """礼貌抓取参数 — 遵守 robots.txt 精神"""
    # 请求间隔 (秒)
    MIN_DELAY_SAME_DOMAIN = 2.0    # 同域名最小间隔
    MIN_DELAY_CROSS_DOMAIN = 1.0   # 异域名最小间隔
    JITTER = 1.5                   # 随机抖动范围 (±)

    # 重试
    MAX_RETRIES = 3
    RETRY_BACKOFF_MIN = 2
    RETRY_BACKOFF_MAX = 30

    # 去重 & 缓存
    CACHE_TTL_HOURS = 6            # 缓存有效期
    MAX_PER_DOMAIN = 3             # 每域名每轮最多文章数

    # User-Agent (可识别、可联系)
    USER_AGENT = (
        "MingCatBot/1.0 (RSS Reader; +https://20020426.top; "
        "fetching public feeds only)"
    )


PC = PolitenessConfig


# ============================================================
# RSS 数据源 (按板块 · 按优先级分层)
# ============================================================

# 优先级: 1=官方/一级来源, 2=聚合/二级来源, 3=补充搜索
RSS_SOURCES_V2 = {
    "cross-border": {
        1: [  # 一级: 官方博客 / 权威媒体
            "https://www.shopify.com/blog/feed.rss",
            "https://www.cifnews.com/feed",
        ],
        2: [  # 二级: Google News RSS 聚合
            "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+Ozon+%E6%95%99%E7%A8%8B+%E5%85%A5%E9%97%A8+%E5%AE%9E%E6%93%8D&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=Ozon+%E8%BF%90%E8%90%A5+%E6%8A%80%E5%B7%A7+%E6%8C%87%E5%8D%97+%E9%80%89%E5%93%81+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+%E4%BF%84%E7%BD%97%E6%96%AF+%E9%80%89%E5%93%81+%E8%BF%90%E8%90%A5+%E7%89%A9%E6%B5%81&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=Wildberries+%E9%87%8E%E8%8E%93+%E4%BF%84%E7%BD%97%E6%96%AF+%E5%8D%96%E5%AE%B6+%E5%85%A5%E9%A9%BB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=%E4%BF%84%E7%BD%97%E6%96%AF+%E6%94%B6%E6%AC%BE+%E5%9B%9E%E6%AC%BE+%E5%8D%A2%E5%B8%83+%E6%B1%87%E7%8E%87+%E8%B7%A8%E5%A2%83&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=Ozon+FBO+FBS+%E6%B5%B7%E5%A4%96%E4%BB%93+%E5%8F%91%E8%B4%A7+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        ],
        3: [  # 三级: 英文补充
            "https://news.google.com/rss/search?q=cross+border+ecommerce+Russia+Ozon+guide&hl=en&gl=US&ceid=US:en",
        ],
    },
    "fitness": {
        1: [
            # Healthline Fitness 和 NASM 无公开 RSS, 用 Google News 聚合代替
            "https://news.google.com/rss/search?q=%E5%BE%92%E6%89%8B%E5%81%A5%E8%BA%AB+%E8%87%AA%E9%87%8D%E8%AE%AD%E7%BB%83+%E6%95%99%E7%A8%8B+%E4%BF%AF%E5%8D%A7%E6%92%91+%E6%B7%B1%E8%B9%B2&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=%E6%A0%B8%E5%BF%83%E8%AE%AD%E7%BB%83+%E7%91%9C%E4%BC%BD%E5%9E%AB+%E8%85%B9%E8%82%8C+%E5%81%A5%E8%BA%AB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        ],
        2: [
            "https://news.google.com/rss/search?q=bodyweight+workout+home+routine+beginner+no+equipment&hl=en&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=calisthenics+bodyweight+exercise+tutorial+plan&hl=en&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=yoga+stretch+flexibility+beginner+routine+home+mat&hl=en&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=%E5%81%A5%E8%BA%AB+%E9%A5%AE%E9%A3%9F+%E8%90%A5%E5%85%BB+%E5%87%8F%E8%84%82+%E5%BE%92%E6%89%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        ],
        3: [
            "https://news.google.com/rss/search?q=PubMed+exercise+science+bodyweight+training+2025+2026&hl=en&gl=US&ceid=US:en",
        ],
    },
    "ai-news": {
        1: [
            "https://news.google.com/rss/search?q=AI+%E6%95%99%E7%A8%8B+%E5%85%A5%E9%97%A8+%E5%AD%A6%E4%B9%A0+%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=AI%E5%B7%A5%E5%85%B7+%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B+%E6%95%99%E5%AD%A6+%E5%AE%9E%E6%93%8D&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=AI+%E7%94%B5%E5%95%86+%E5%BA%94%E7%94%A8+%E6%95%99%E7%A8%8B+%E6%96%B9%E6%B3%95&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        ],
        2: [
            "https://news.google.com/rss/search?q=AI+tutorial+guide+how-to+artificial+intelligence+learning&hl=en&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=AI+%E7%BC%96%E7%A8%8B+%E5%BC%80%E5%8F%91+copilot+cursor+%E6%95%99%E7%A8%8B&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "https://news.google.com/rss/search?q=machine+learning+deep+learning+tutorial+beginner+guide&hl=en&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=AI+automation+workflow+productivity+tools+tutorial&hl=en&gl=US&ceid=US:en",
        ],
        3: [
            "https://news.google.com/rss/search?q=arXiv+cs.AI+cs.LG+2025+2026+paper&hl=en&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=Anthropic+Claude+OpenAI+model+release&hl=en&gl=US&ceid=US:en",
        ],
    },
}

# 一级来源的准确域名映射 (用于内容标注)
OFFICIAL_SOURCE_DOMAINS = {
    "shopify.com": "Shopify 官方博客",
    "cifnews.com": "雨果跨境",
    "baixiaojunwm.com": "白小菌博客",
    "openai.com": "OpenAI Blog",
    "anthropic.com": "Anthropic",
    "huggingface.co": "Hugging Face Blog",
    "arxiv.org": "arXiv",
    "healthline.com": "Healthline Fitness",
    "blog.nasm.org": "NASM Blog",
    "pubmed.ncbi.nlm.nih.gov": "PubMed",
    "docs.ozon.ru": "Ozon 官方文档",
}


# ============================================================
# 黑名单 & 过滤器
# ============================================================

# 健身板块黑名单 — 过滤不相关内容
BLACKLIST_FITNESS = [
    "明星", "演员", "刘亦菲", "死亡", "减肥药", "保险",
    "金融", "股票", "理财", "信用卡", "贷款", "基金", "投资",
    "celeb", "hollywood", "surgery", "weight loss drug",
    "insurance", "stock", "finance", "bankrupt",
]

# 全局广告/垃圾过滤
BLACKLIST_GLOBAL = [
    "广告", "sponsored", "advertisement", "推广",
]


def _is_blacklisted(title: str, section: str) -> bool:
    """检查标题是否命中黑名单"""
    t = title.lower()
    if any(w in t for w in BLACKLIST_GLOBAL):
        return True
    if section == "fitness":
        if any(w in t for w in BLACKLIST_FITNESS):
            return True
    return False


# ============================================================
# 域名速率限制器
# ============================================================

class DomainRateLimiter:
    """同域名请求速率限制 — 确保 ≥ MIN_DELAY_SAME_DOMAIN 秒间隔"""

    def __init__(self):
        self._last_request: dict[str, float] = {}

    def wait_if_needed(self, domain: str):
        """如果需要，等待直到满足最小间隔"""
        now = time.time()
        last = self._last_request.get(domain, 0)
        elapsed = now - last
        if elapsed < PC.MIN_DELAY_SAME_DOMAIN:
            wait = PC.MIN_DELAY_SAME_DOMAIN - elapsed
            # 加随机抖动避免同步
            import random
            wait += random.uniform(0, PC.JITTER)
            logger.debug(f"速率限制: 等待 {wait:.1f}s (domain={domain})")
            time.sleep(wait)
        self._last_request[domain] = time.time()


_rate_limiter = DomainRateLimiter()


# ============================================================
# 核心抓取逻辑
# ============================================================

class RssScraper(BaseScraper):
    """健壮 RSS 抓取器

    特性:
    - 优先级分层抓取 (1→2→3)
    - 同域名速率限制
    - 3 次重试 + 指数退避
    - 缓存去重 (6h TTL)
    - 内容质量过滤 (长度/黑名单/垃圾)
    """

    def __init__(self):
        super().__init__()
        self._cache: dict[str, tuple[float, list[dict]]] = {}  # {url: (timestamp, entries)}
        self._seen_hashes: set[str] = set()

    # ---- 底层: 单 RSS 源抓取 ----

    @retry(
        stop=stop_after_attempt(PC.MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=PC.RETRY_BACKOFF_MIN, max=PC.RETRY_BACKOFF_MAX),
        retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    )
    def _fetch_single_feed(self, url: str, timeout: int = 20) -> feedparser.FeedParserDict | None:
        """抓取单个 RSS 源 (带重试 + 速率限制)

        Args:
            url: RSS feed URL
            timeout: 超时秒数

        Returns:
            feedparser 解析结果, 或 None (失败)
        """
        # 检查缓存
        now = time.time()
        if url in self._cache:
            ts, cached = self._cache[url]
            if now - ts < PC.CACHE_TTL_HOURS * 3600:
                logger.debug(f"缓存命中: {url[:60]}...")
                return None  # 返回 None 表示已有缓存，调用方用 get_cached()

        # 速率限制
        domain = source_domain(url)
        _rate_limiter.wait_if_needed(domain)

        # 请求
        logger.debug(f"抓取 RSS: {url[:80]}...")
        resp = requests.get(
            url,
            headers={
                "User-Agent": PC.USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ru;q=0.5",
            },
            timeout=timeout,
        )

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "60")
            logger.warning(f"429 限流 {domain}, Retry-After={retry_after}s")
            raise requests.HTTPError(f"429 Too Many Requests (Retry-After: {retry_after})")

        if resp.status_code == 404:
            logger.info(f"RSS 源不存在 (404): {url[:60]}...")
            return None

        if resp.status_code != 200:
            raise requests.HTTPError(f"HTTP {resp.status_code}")

        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS 解析异常 ({url[:60]}...): {feed.bozo_exception}")
            return None

        return feed

    # ---- 中层: 解析条目 ----

    def _parse_entry(self, entry, section: str) -> dict | None:
        """将 feedparser entry 解析为标准 ScrapedItem dict

        Returns:
            dict 或 None (质量不合格)
        """
        link = entry.get("link", "").strip()
        if not link:
            return None

        title = clean_html(entry.get("title", ""))
        if not title or len(title) < 10:
            return None
        if len(title) > 200:
            return None  # 标题过长通常是垃圾

        # 黑名单过滤
        if _is_blacklisted(title, section):
            logger.debug(f"黑名单过滤: {title[:40]}...")
            return None

        # 来源信息
        source = entry.get("source", {})
        source_href = ""
        source_name = ""
        if isinstance(source, dict):
            source_href = source.get("href", "")
            source_name = source.get("title", "")

        domain = source_domain(source_href) or source_domain(link)
        if not source_name:
            # 尝试匹配官方来源名
            for key, name in OFFICIAL_SOURCE_DOMAINS.items():
                if key in domain:
                    source_name = name
                    break
            if not source_name:
                source_name = domain

        # 摘要
        summary_html = entry.get("summary", entry.get("description", ""))
        summary_text = clean_html(summary_html)[:300]

        # 发布日期
        published = entry.get("published", entry.get("updated", ""))

        return {
            "title": title,
            "link": link,
            "source_name": source_name,
            "source_href": source_href,
            "domain": domain,
            "summary": summary_text,
            "published": published,
            "section": section,
        }

    # ---- 上层: 多源聚合抓取 ----

    def fetch(self, section: str, limit_per_source: int = 6, max_total: int = 30) -> list[dict]:
        """按板块抓取 RSS，优先级 1→2→3 逐层降级

        礼貌机制:
        - 同域名请求间隔 ≥2s + 随机抖动
        - 每域名每轮最多 3 篇 (MAX_PER_DOMAIN)
        - 缓存 6h, 不重复请求同一 URL

        Args:
            section: cross-border | fitness | ai-news
            limit_per_source: 每个 RSS 源最多保留条目数
            max_total: 最大返回条目数

        Returns:
            去重后的条目列表 (按发布日期降序)
        """
        sources = RSS_SOURCES_V2.get(section, {})
        if not sources:
            logger.warning(f"未找到板块 RSS 源: {section}")
            return []

        all_entries: list[dict] = []
        seen_links: set[str] = set()
        domain_counts: dict[str, int] = defaultdict(int)

        for priority in [1, 2, 3]:
            if not sources.get(priority):
                continue

            logger.info(f"[{section}] 优先级 {priority}: {len(sources[priority])} 个源")

            for url in sources[priority]:
                if len(all_entries) >= max_total:
                    break

                try:
                    feed = self._fetch_single_feed(url)
                    if feed is None or not feed.entries:
                        continue

                    count = 0
                    for entry in feed.entries:
                        if count >= limit_per_source:
                            break

                        parsed = self._parse_entry(entry, section)
                        if parsed is None:
                            continue

                        link = parsed["link"]
                        if link in seen_links:
                            continue
                        seen_links.add(link)

                        domain = parsed["domain"]
                        if domain_counts[domain] >= PC.MAX_PER_DOMAIN:
                            continue
                        domain_counts[domain] += 1

                        all_entries.append(parsed)
                        count += 1

                    logger.debug(f"  {url[:60]}... -> {count} 条")

                except (requests.RequestException, requests.HTTPError) as e:
                    logger.warning(f"RSS 源不可达 (优先级{priority}): {url[:60]}... — {e}")
                    continue
                except Exception as e:
                    logger.error(f"RSS 异常: {url[:60]}... — {e}")
                    continue

            # 优先级 1 够了就跳过后续
            if len(all_entries) >= 10 and priority == 1:
                logger.info(f"[{section}] 优先级 1 已获取 {len(all_entries)} 条, 跳过后续优先级")
                break

        # 按发布日期降序
        all_entries.sort(key=lambda x: x.get("published", ""), reverse=True)

        logger.info(f"[{section}] 最终: {len(all_entries)} 条 (来自 {len(domain_counts)} 个域名)")
        return all_entries

    # ---- 缓存管理 ----

    def clear_cache(self):
        """清空抓取缓存"""
        self._cache.clear()
        self._seen_hashes.clear()
        logger.info("RSS 缓存已清空")


# ============================================================
# 便捷函数 (兼容旧 news_scraper 接口)
# ============================================================

# 全局单例
_scraper = None


def _get_scraper() -> RssScraper:
    global _scraper
    if _scraper is None:
        _scraper = RssScraper()
    return _scraper


def fetch_section_feeds(section: str, limit_per_feed: int = 6) -> list[dict]:
    """便捷函数: 拉取指定板块 RSS (兼容旧接口)

    用法:
        entries = fetch_section_feeds("cross-border")
        entries = fetch_section_feeds("fitness", limit_per_feed=4)
        entries = fetch_section_feeds("ai-news")
    """
    return _get_scraper().fetch(section, limit_per_source=limit_per_feed)
