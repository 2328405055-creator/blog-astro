# textscripts · scrapers/base.py — BaseScraper 抽象类

from abc import ABC, abstractmethod
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """所有数据采集器的抽象基类

    提供统一的: 重试策略 / UA 轮换 / 限流 / 日志
    """

    user_agents: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ]
    max_retries: int = 3
    min_wait: int = 2
    max_wait: int = 15
    timeout: int = 15
    max_per_domain: int = 3  # 每域名最多保留文章数

    @abstractmethod
    def fetch(self, *args, **kwargs) -> list[dict]:
        """采集数据，返回条目 dict 列表"""
        ...

    def _default_retry(self):
        """默认重试装饰器"""
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=self.min_wait, max=self.max_wait),
        )

    def _dedup_by_domain(self, entries: list[dict], domain_key: str = "domain") -> list[dict]:
        """按域名去重，每域名最多 max_per_domain 条"""
        counts: dict[str, int] = {}
        result = []
        for e in entries:
            d = e.get(domain_key, "")
            if counts.get(d, 0) >= self.max_per_domain:
                continue
            counts[d] = counts.get(d, 0) + 1
            result.append(e)
        return result
