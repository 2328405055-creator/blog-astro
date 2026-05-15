# textscripts · generators/base.py — BaseGenerator 抽象类

from abc import ABC, abstractmethod
from typing import Optional
import logging
from textscripts.models import ArticleEntry, GateResult

logger = logging.getLogger(__name__)


class BaseGenerator(ABC):
    """所有内容生成器的抽象基类

    定义标准流水线: collect -> enrich -> compose -> validate -> save
    """

    section: str = ""  # 子类必须设置: cross-border | fitness | ai-news | ozon-pick

    @abstractmethod
    def collect(self, limit: int = 5) -> list[dict]:
        """采集原始数据，返回 ScrapedItem dict 列表"""
        ...

    @abstractmethod
    def enrich(self, entries: list[dict]) -> list[dict]:
        """内容富化：Firecrawl 抓取 / AI 总结 / 交叉合成"""
        ...

    @abstractmethod
    def compose(self, entry: dict, date_str: str) -> tuple[str, str]:
        """将富化后的条目构建为 Markdown 字符串，返回 (md_content, sub_category)"""
        ...

    def validate(self, md_content: str, title: str) -> GateResult:
        """质量门禁：检查文章是否满足发布标准"""
        failures = []
        warnings = []
        score = 100

        if len(md_content) < 400:
            failures.append(f"字数不足: {len(md_content)} < 400")
            score -= 40
        elif len(md_content) < 600:
            warnings.append(f"字数偏少: {len(md_content)} (建议 ≥600)")
            score -= 15

        h2_count = md_content.count("\n## ")
        if h2_count < 2:
            warnings.append(f"H2 节不足: {h2_count} 个 (建议 ≥2)")
            score -= 10

        if "http" not in md_content:
            failures.append("缺少来源链接")
            score -= 30

        if not title or len(title) < 5:
            failures.append("标题过短或为空")
            score -= 30

        score = max(0, score)
        passed = len(failures) == 0
        return GateResult(passed=passed, failures=failures, warnings=warnings, score=score)

    @abstractmethod
    def save(self, slug: str, md_content: str, entry: dict, date_str: str) -> str:
        """写入 .md 文件 + 更新 posts.json，返回 slug"""
        ...

    def run(self, limit: int = 5, date_str: Optional[str] = None) -> list[dict]:
        """执行完整流水线，返回成功生成的文章列表"""
        from textscripts.utils.file_ops import today_str

        if date_str is None:
            date_str = today_str()

        logger.info(f"[{self.section}] 开始流水线...")

        entries = self.collect(limit=limit)
        logger.info(f"[{self.section}] 采集: {len(entries)} 条")

        enriched = self.enrich(entries)

        results = []
        for entry in enriched:
            if entry.get("enriched") is False:
                continue

            md_content, sub_cat = self.compose(entry, date_str)
            gate = self.validate(md_content, entry.get("title", ""))

            if not gate.passed:
                logger.warning(
                    f"[{self.section}] 质量门禁未通过: {entry.get('title', '?')[:40]}... "
                    f"失败: {gate.failures}"
                )
                if gate.score < 40:
                    continue

            slug = self.save(None, md_content, entry, date_str)
            results.append({"title": entry.get("title", ""), "slug": slug, "cat": self.section})

        logger.info(f"[{self.section}] 完成: {len(results)} 篇")
        return results
