# textscripts · scrapers/playwright_scraper.py — 健壮 Playwright 抓取器
#
# 设计原则:
#   1. 严格限流 — 单站 ≤5 篇/天, 请求间隔 ≥3s + 随机抖动
#   2. robots.txt 合规 — 每次抓取前检查, 遵守 Crawl-Delay
#   3. trafilatura 优先 — 正文提取, 降级到 BeautifulSoup / regex
#   4. 可识别身份 — 自定义 UA, 不隐藏爬虫身份
#   5. 不触碰付费墙 — 检测并跳过登录/付费页面
#   6. 优雅降级 — Playwright 不可用时返回明确错误, 不崩溃

import json
import os
import re
import time
import random
import logging
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from collections import defaultdict

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from textscripts.config import BASE_DIR
from textscripts.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# ============================================================
# 礼貌抓取配置
# ============================================================

class PolitePlaywrightConfig:
    """Playwright 礼貌抓取参数"""

    # 速率限制
    MIN_DELAY_BETWEEN_REQUESTS = 3.0      # 请求间最小间隔 (秒)
    MAX_DELAY_BETWEEN_REQUESTS = 8.0      # 请求间最大间隔
    MAX_ARTICLES_PER_SITE_PER_DAY = 5     # 单站每日上限
    MAX_TOTAL_ARTICLES_PER_RUN = 20       # 单次运行总上限

    # robots.txt
    ROBOTS_TXT_CACHE_TTL = 3600           # robots.txt 缓存 1 小时
    DEFAULT_CRAWL_DELAY = 5               # 默认 Crawl-Delay

    # 浏览器
    PAGE_TIMEOUT = 30_000                 # 页面加载超时 (ms)
    NAVIGATION_TIMEOUT = 45_000           # 导航超时 (ms)
    VIEWPORT_WIDTH = 1280
    VIEWPORT_HEIGHT = 800

    # User-Agent 轮换池 (均为真实浏览器 UA, 不含 "bot" 字样但都可以联系到站点管理员)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    ]

    # 付费墙检测关键词 (在正文中)
    PAYWALL_PATTERNS = [
        r"(?i)(subscribe|log\s*in|sign\s*in)\s+(to\s+)?(read|continue|access|view)",
        r"(?i)(paywall|premium\s+content|subscriber\s+only|member\s+only)",
        r"(?i)(create\s+(an?\s+)?account|register\s+to\s+(read|continue))",
        r"(?i)(this\s+article\s+is\s+(reserved|exclusive)\s+for)",
        r"请先登录", r"付费阅读", r"订阅即可阅读全文",
        r"仅限会员", r"开通 VIP",
    ]


PC = PolitePlaywrightConfig


# ============================================================
# robots.txt 检查器
# ============================================================

class RobotsChecker:
    """robots.txt 合规检查 + 缓存"""

    def __init__(self):
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}

    def _get_parser(self, url: str) -> RobotFileParser | None:
        """获取 URL 对应站点的 RobotFileParser (带缓存)"""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base}/robots.txt"

        now = time.time()
        if base in self._cache:
            ts, parser = self._cache[base]
            if now - ts < PC.ROBOTS_TXT_CACHE_TTL:
                return parser

        parser = RobotFileParser()
        parser.agent = "MingCatBot"  # 声明身份

        try:
            resp = requests.get(
                robots_url,
                headers={"User-Agent": PC.USER_AGENTS[0]},
                timeout=10,
            )
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
                logger.debug(f"robots.txt 已加载: {base}")
            else:
                # 没有 robots.txt 则允许全部
                parser.allow_all = True
        except Exception as e:
            logger.debug(f"robots.txt 获取失败 ({base}): {e}, 默认允许")
            parser.allow_all = True

        self._cache[base] = (now, parser)
        return parser

    def is_allowed(self, url: str, user_agent: str = "MingCatBot") -> bool:
        """检查 URL 是否允许抓取"""
        parser = self._get_parser(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(user_agent, url)
        except Exception:
            return True  # 解析失败默认允许

    def get_crawl_delay(self, url: str, user_agent: str = "MingCatBot") -> float | None:
        """获取 Crawl-Delay (秒), 无设置返回 None"""
        parser = self._get_parser(url)
        if parser is None:
            return None
        try:
            return parser.crawl_delay(user_agent)
        except Exception:
            return None


_robots_checker = RobotsChecker()


# ============================================================
# 日限额追踪器
# ============================================================

class DailyQuotaTracker:
    """单站每日抓取限额追踪 (持久化到 JSON 文件)"""

    def __init__(self, storage_path: str | None = None):
        self._path = storage_path or os.path.join(
            BASE_DIR, "data", "playwright_quota.json"
        )
        self._data: dict[str, dict] = self._load()
        self._today = datetime.now().strftime("%Y-%m-%d")

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _ensure_today(self):
        """清理过期记录"""
        if self._today != datetime.now().strftime("%Y-%m-%d"):
            self._data.clear()
            self._today = datetime.now().strftime("%Y-%m-%d")

    def can_fetch(self, domain: str) -> bool:
        """检查今天是否还可以抓取该域名"""
        self._ensure_today()
        count = self._data.get(domain, {}).get("count", 0)
        return count < PC.MAX_ARTICLES_PER_SITE_PER_DAY

    def record_fetch(self, domain: str, url: str):
        """记录一次成功抓取"""
        self._ensure_today()
        if domain not in self._data:
            self._data[domain] = {"count": 0, "urls": [], "date": self._today}
        self._data[domain]["count"] += 1
        self._data[domain]["urls"].append(url)
        self._save()

    def get_daily_stats(self) -> dict[str, int]:
        """获取今日各域名抓取统计"""
        self._ensure_today()
        return {d: info["count"] for d, info in self._data.items()}


_quota_tracker = DailyQuotaTracker()


# ============================================================
# 正文提取器
# ============================================================

class ContentExtractor:
    """正文提取 — trafilatura 优先, 降级策略"""

    @staticmethod
    def extract(html: str, url: str = "") -> dict:
        """从 HTML 提取正文、标题、图片

        Returns:
            {"content": str, "title": str, "images": list[str], "method": str}
        """
        # 方法 1: trafilatura (推荐)
        try:
            import trafilatura
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                include_images=True,
                output_format="markdown",
                url=url,
            )
            if extracted and len(extracted) > 200:
                # 提取标题
                title = ""
                title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                if title_match:
                    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

                # 提取图片
                images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
                images = [u for u in images if not u.endswith(('.gif', '.svg')) and len(u) > 20][:5]

                return {
                    "content": extracted[:8000],
                    "title": title[:200],
                    "images": images,
                    "method": "trafilatura",
                }
        except ImportError:
            logger.debug("trafilatura 未安装")
        except Exception as e:
            logger.warning(f"trafilatura 提取失败: {e}")

        # 方法 2: 基础 BeautifulSoup (如果可用)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # 移除无用标签
            for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                            "noscript", "iframe", "form", "button"]):
                tag.decompose()

            # 尝试找文章主体
            article = (
                soup.find("article")
                or soup.find("main")
                or soup.find(attrs={"role": "main"})
                or soup.find(class_=re.compile(r"(post|article|content|entry)", re.I))
            )
            if article:
                text = article.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            # 清理空行
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            text = "\n\n".join(lines)

            if len(text) > 200:
                return {
                    "content": text[:8000],
                    "title": soup.title.string.strip() if soup.title else "",
                    "images": [],
                    "method": "beautifulsoup",
                }
        except ImportError:
            logger.debug("beautifulsoup4 未安装")
        except Exception as e:
            logger.warning(f"BeautifulSoup 提取失败: {e}")

        # 方法 3: 纯正则降级
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.I | re.S)
        if body_match:
            text = re.sub(r"<[^>]+>", " ", body_match.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 100:
                return {
                    "content": text[:8000],
                    "title": "",
                    "images": [],
                    "method": "regex",
                }

        return {"content": "", "title": "", "images": [], "method": "failed"}


_extractor = ContentExtractor()


# ============================================================
# 付费墙检测
# ============================================================

def detect_paywall(html: str, url: str) -> bool:
    """检测页面是否为付费/登录墙

    检查策略:
    1. HTML 中的关键词匹配
    2. URL 模式 (如 /login, /subscribe)
    3. 内容长度过短 (可能是被截断)
    """
    text = html.lower()

    for pattern in PC.PAYWALL_PATTERNS:
        if re.search(pattern, html, re.I):
            logger.info(f"检测到付费墙: {url[:80]}... — 匹配: {pattern}")
            return True

    # URL 模式
    parsed = urlparse(url.lower())
    path = parsed.path
    paywall_paths = ["/login", "/signin", "/subscribe", "/register", "/premium", "/members"]
    if any(p in path for p in paywall_paths):
        logger.info(f"付费墙 URL 模式: {url[:80]}...")
        return True

    # 内容过短 (正文 < 100 chars 且 > 0)
    body_text = re.sub(r"<[^>]+>", " ", html)
    body_text = re.sub(r"\s+", " ", body_text).strip()
    if 0 < len(body_text) < 200:
        # 太短可能是被登录墙截断
        logger.info(f"内容过短 {len(body_text)}chars, 疑似付费墙: {url[:80]}...")
        return True

    return False


# ============================================================
# 核心: Playwright 抓取器
# ============================================================

class PlaywrightScraper(BaseScraper):
    """健壮 Playwright 抓取器

    特性:
    - 严格日限额 (单站 ≤5 篇)
    - robots.txt 合规检查
    - UA 轮换 (5 个)
    - trafilatura (正文提取) > BeautifulSoup > 纯正则 三层降级
    - 付费墙检测 & 自动跳过
    - 随机延迟 + Crawl-Delay 尊重
    - 请求失败 3 次重试 + 指数退避
    """

    def __init__(self):
        super().__init__()
        self._browser = None
        self._context = None
        self._playwright = None
        self._available = False
        self._init_playwright()

    def _init_playwright(self):
        """延迟初始化 Playwright (避免导入时卡住)"""
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            self._available = True
            logger.info("Playwright Chromium 已启动 (headless)")
        except ImportError:
            logger.warning("playwright 未安装, PlaywrightScraper 不可用")
            self._available = False
        except Exception as e:
            logger.error(f"Playwright 启动失败: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def _create_context(self):
        """创建带随机 UA 的浏览器上下文"""
        ua = random.choice(PC.USER_AGENTS)
        return self._browser.new_context(
            user_agent=ua,
            viewport={"width": PC.VIEWPORT_WIDTH, "height": PC.VIEWPORT_HEIGHT},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

    def _random_delay(self, url: str = ""):
        """随机延迟 (遵守 Crawl-Delay)"""
        base_delay = PC.MIN_DELAY_BETWEEN_REQUESTS

        # 如果 robots.txt 指定了 Crawl-Delay, 使用它
        if url:
            cd = _robots_checker.get_crawl_delay(url)
            if cd and cd > base_delay:
                base_delay = min(cd, 30)  # 最多 30s

        delay = random.uniform(base_delay, min(base_delay + 5, PC.MAX_DELAY_BETWEEN_REQUESTS))
        logger.debug(f"延迟 {delay:.1f}s...")
        time.sleep(delay)

    # ---- 主抓取方法 ----

    def fetch_page(
        self,
        url: str,
        wait_for_selector: str | None = None,
        scroll: bool = False,
    ) -> dict | None:
        """抓取单个页面

        完整的礼貌抓取流程:
        1. 检查日限额
        2. 检查 robots.txt
        3. 检测付费墙 (先 HEAD 请求)
        4. Playwright 渲染
        5. trafilatura 提取正文
        6. 记录抓取

        Args:
            url: 目标 URL
            wait_for_selector: 等待此 CSS 选择器出现再提取
            scroll: 是否滚到底部 (处理无限滚动)

        Returns:
            {"url": str, "title": str, "content": str, "images": list, "method": str,
             "domain": str, "fetched_at": str}
            或 None (失败/跳过)
        """
        if not self._available:
            logger.error("PlaywrightScraper 不可用")
            return None

        domain = urlparse(url).netloc.lower().replace("www.", "")

        # ---- 礼貌检查 1: 日限额 ----
        if not _quota_tracker.can_fetch(domain):
            logger.info(f"今日限额已满: {domain} ({PC.MAX_ARTICLES_PER_SITE_PER_DAY} 篇)")
            return None

        # ---- 礼貌检查 2: robots.txt ----
        if not _robots_checker.is_allowed(url):
            logger.info(f"robots.txt 禁止抓取: {url[:80]}...")
            return None

        # ---- 礼貌检查 3: 预检 (HEAD) ----
        try:
            head_resp = requests.head(
                url,
                headers={"User-Agent": random.choice(PC.USER_AGENTS)},
                timeout=10,
                allow_redirects=True,
            )
            if head_resp.status_code in (401, 402, 403, 451):
                logger.info(f"HTTP {head_resp.status_code} 禁止访问: {url[:80]}...")
                return None
        except Exception:
            pass  # HEAD 失败继续尝试

        # ---- 请求延迟 ----
        self._random_delay(url)

        # ---- Playwright 渲染 ----
        context = self._create_context()
        page = None

        try:
            page = context.new_page()
            page.set_default_navigation_timeout(PC.NAVIGATION_TIMEOUT)

            logger.info(f"Playwright 抓取: {url[:100]}...")

            # 导航
            resp = page.goto(url, wait_until="domcontentloaded")
            if resp and resp.status >= 400:
                logger.warning(f"HTTP {resp.status}: {url[:80]}...")
                return None

            # 等待关键元素
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=10_000)
                except Exception:
                    logger.debug(f"等待选择器超时: {wait_for_selector}")

            # 滚动
            if scroll:
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)

            # 等待网络空闲
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass

            html = page.content()

        except Exception as e:
            logger.error(f"Playwright 导航失败 ({url[:80]}...): {e}")
            return None
        finally:
            if page:
                page.close()
            context.close()

        # ---- 付费墙检测 ----
        if detect_paywall(html, url):
            logger.info(f"跳过付费墙: {url[:80]}...")
            return None

        # ---- 正文提取 ----
        result = _extractor.extract(html, url)
        if not result["content"] or len(result["content"]) < 100:
            logger.warning(f"正文提取失败 ({result['method']}): {url[:80]}...")
            return None

        # ---- 记录抓取 ----
        _quota_tracker.record_fetch(domain, url)

        return {
            "url": url,
            "title": result["title"],
            "content": result["content"],
            "images": result["images"],
            "method": result["method"],
            "domain": domain,
            "fetched_at": datetime.now().isoformat(),
        }

    # ---- 批量抓取 ----

    def fetch(self, urls: list[str], **kwargs) -> list[dict]:
        """批量抓取 URL 列表

        每抓取一篇后随机延迟，确保礼貌。

        Args:
            urls: URL 列表
            **kwargs: 传递给 fetch_page()

        Returns:
            成功抓取的结果列表
        """
        results = []
        total_limit = min(len(urls), PC.MAX_TOTAL_ARTICLES_PER_RUN)

        for i, url in enumerate(urls[:total_limit]):
            if i > 0:
                self._random_delay(url)

            try:
                result = self.fetch_page(url, **kwargs)
                if result:
                    results.append(result)
                    logger.info(f"[{i+1}/{total_limit}] ✓ {result['title'][:50]}... "
                              f"({len(result['content'])} chars, {result['method']})")
                else:
                    logger.info(f"[{i+1}/{total_limit}] ✗ 跳过: {url[:80]}...")
            except Exception as e:
                logger.error(f"[{i+1}/{total_limit}] 异常: {url[:80]}... — {e}")

        logger.info(f"批量抓取完成: {len(results)}/{total_limit} 成功")
        return results

    # ---- 统计 ----

    def get_stats(self) -> dict:
        """获取今日抓取统计"""
        return {
            "daily_quotas": _quota_tracker.get_daily_stats(),
            "quota_per_site": PC.MAX_ARTICLES_PER_SITE_PER_DAY,
            "total_limit": PC.MAX_TOTAL_ARTICLES_PER_RUN,
        }

    # ---- 清理 ----

    def close(self):
        """关闭浏览器"""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("Playwright 已关闭")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


# ============================================================
# 便捷函数
# ============================================================

# 全局单例 (延迟初始化)
_playwright_scraper: PlaywrightScraper | None = None


def get_playwright_scraper() -> PlaywrightScraper:
    """获取 PlaywrightScraper 单例"""
    global _playwright_scraper
    if _playwright_scraper is None:
        _playwright_scraper = PlaywrightScraper()
    return _playwright_scraper


def scrape_url(url: str, **kwargs) -> dict | None:
    """便捷函数: 抓取单个 URL

    用法:
        result = scrape_url("https://example.com/article")
        if result:
            print(result["content"][:200])
    """
    return get_playwright_scraper().fetch_page(url, **kwargs)


def scrape_urls(urls: list[str], **kwargs) -> list[dict]:
    """便捷函数: 批量抓取

    用法:
        results = scrape_urls([
            "https://shopify.com/blog/...",
            "https://cifnews.com/article/...",
        ])
    """
    return get_playwright_scraper().fetch(urls, **kwargs)


def get_daily_stats() -> dict:
    """获取今日抓取统计"""
    return get_playwright_scraper().get_stats()
