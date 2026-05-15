# textscripts · rag/indexer.py — 文章向量索引构建（全量 / 增量）

import os
import logging
from textscripts.config import BASE_DIR, POSTS_DIR
from textscripts.utils.file_ops import load_json
from textscripts.rag.embedder import get_embedding_or_fallback
from textscripts.rag.vector_store import add, clear, count, load_all

logger = logging.getLogger(__name__)


def index_one(slug: str, title: str = "", excerpt: str = "", cat: str = "", date: str = "") -> bool:
    """索引单篇文章：读取 .md + 生成 embedding -> 写入向量库

    Args:
        slug: 文章 slug
        title: 标题（用于 embedding 输入）
        excerpt: 摘要（与标题拼接作为 embedding 输入）
        cat: 分类
        date: 日期

    Returns:
        True 成功 / False 失败
    """
    # 拼接用于 embedding 的文本
    text = f"{title}\n{excerpt}"

    # 如果 .md 文件存在，读取前 2000 字符以获取更丰富的语义
    md_path = os.path.join(POSTS_DIR, f"{slug}.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            body = f.read()[:3000]
            text += f"\n{body}"

    embedding = get_embedding_or_fallback(text)
    if not embedding:
        logger.warning(f"跳过 {slug}：无法生成 embedding")
        return False

    word_count = len(text)
    add(slug, embedding, cat=cat, date=date, word_count=word_count)
    logger.info(f"已索引: {slug} ({len(embedding)}d, {word_count} chars)")
    return True


def build_index(force: bool = False) -> dict:
    """全量构建向量索引（从 posts.json + posts/*.md）

    Args:
        force: True 时清空重建，False 时仅索引新文章

    Returns:
        {"total": N, "indexed": N, "skipped": N, "errors": N}
    """
    posts = load_json(os.path.join(POSTS_DIR, "posts.json"))
    existing_slugs = set(load_all().keys()) if not force else set()

    stats = {"total": len(posts), "indexed": 0, "skipped": 0, "errors": 0}

    for p in posts:
        slug = p.get("slug", "")
        if not slug:
            stats["errors"] += 1
            continue

        if slug in existing_slugs and not force:
            stats["skipped"] += 1
            continue

        if index_one(
            slug=slug,
            title=p.get("title", ""),
            excerpt=p.get("excerpt", ""),
            cat=p.get("cat", ""),
            date=p.get("date", ""),
        ):
            stats["indexed"] += 1
        else:
            stats["errors"] += 1

    logger.info(f"索引构建完成: {stats['indexed']} 新增 / {stats['skipped']} 跳过 / {stats['errors']} 失败")
    return stats


def rebuild_index() -> dict:
    """清空并重建整个向量索引"""
    logger.info("清空向量库并重建...")
    clear()
    return build_index(force=True)
