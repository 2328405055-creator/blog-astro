# textscripts · models.py — Pydantic 数据模型（全链路类型安全）

from datetime import date as Date
from typing import Optional, Any
from pydantic import BaseModel, Field


class ArticleEntry(BaseModel):
    """posts.json 中每篇文章的完整元数据"""
    slug: str
    title: str
    date: str
    lastmod: Optional[str] = None
    excerpt: str = ""
    cat: str  # cross-border | fitness | ai-news | ozon-pick
    sub: str = ""
    featured: bool = False
    verified: bool = False
    source: str = ""
    source_name: str = ""
    has_content: bool = False
    word_count: int = 0
    quality_score: Optional[int] = None
    related_slugs: list[str] = []


class ScrapedItem(BaseModel):
    """RSS/搜索抓取的原始条目"""
    title: str
    link: str
    source_name: str
    source_href: str = ""
    domain: str = ""
    summary: str = ""
    published: str = ""
    section: str  # cross-border | fitness | ai-news


class EnrichedContent(BaseModel):
    """Firecrawl 深度抓取 + AI 总结后的富化内容"""
    content: str = ""
    key_points: list[str] = []
    word_count: int = 0
    model: str = ""
    source_count: int = 1
    images: list[str] = []
    sources: list[str] = []


class GateResult(BaseModel):
    """质量门禁检查结果"""
    passed: bool
    failures: list[str] = []
    warnings: list[str] = []
    score: int = 0  # 0-100


class PublishReport(BaseModel):
    """发布操作报告"""
    published: list[str] = []  # 成功发布的 slug 列表
    skipped: list[str] = []    # 跳过的 slug（含原因）
    sitemap_updated: bool = False
    git_pushed: bool = False
    commit_hash: str = ""
    errors: list[str] = []


class ProductEntry(BaseModel):
    """Ozon/WB 商品条目"""
    nm_id: str
    product_name_ru: str
    product_name_cn: str = ""
    brand: str = ""
    price_rub: int = 0
    rating: float = 0.0
    review_count: int = 0
    wb_url: str = ""
    cat_cn: str = ""
    cat_key: str = ""
    sort_mode: str = ""  # popular | newly
    search_keyword: str = ""
    trend_score: int = 0
    recommendation: str = ""
    risks: str = ""


class EmbeddingRecord(BaseModel):
    """RAG 向量记录"""
    slug: str
    embedding: list[float]
    cat: str = ""
    date: str = ""
    word_count: int = 0

    class Config:
        # 允许大列表以提高性能
        arbitrary_types_allowed = True
