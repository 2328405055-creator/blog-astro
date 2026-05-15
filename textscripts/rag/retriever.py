# textscripts · rag/retriever.py — 语义检索：相关文章推荐 + 素材回溯

import logging
from textscripts.rag.embedder import get_embedding_or_fallback
from textscripts.rag.vector_store import load_all
from textscripts.rag.deduplicator import cosine_similarity

logger = logging.getLogger(__name__)


def find_related(slug: str, k: int = 3) -> list[dict]:
    """找到与指定文章最相似的 k 篇文章（排除自身）

    Returns:
        [{"slug": "...", "similarity": 0.78}, ...]
    """
    existing = load_all()
    if slug not in existing:
        logger.warning(f"文章不在向量库中: {slug}")
        return []

    target = existing[slug]
    target_emb = target.get("embedding", [])
    if not target_emb:
        return []

    scored = []
    for other_slug, record in existing.items():
        if other_slug == slug:
            continue
        rec_emb = record.get("embedding", [])
        if not rec_emb:
            continue
        sim = cosine_similarity(target_emb, rec_emb)
        if sim > 0.5:  # 最低相关度阈值
            scored.append({"slug": other_slug, "similarity": round(sim, 3)})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top = scored[:k]

    if top:
        logger.debug(f"相关文章: {slug} -> {[s['slug'] for s in top]}")
    return top


def search_by_query(query: str, k: int = 5, cat_filter: str = "") -> list[dict]:
    """用自然语言查询搜索相似文章

    Args:
        query: 搜索查询文本
        k: 返回结果数
        cat_filter: 可选，按分类过滤 (cross-border | fitness | ai-news | ozon-pick)

    Returns:
        [{"slug": "...", "cat": "...", "similarity": 0.82}, ...]
    """
    existing = load_all()
    if not existing:
        return []

    query_emb = get_embedding_or_fallback(query)
    if not query_emb:
        return []

    scored = []
    for slug, record in existing.items():
        if cat_filter and record.get("cat", "") != cat_filter:
            continue
        rec_emb = record.get("embedding", [])
        if not rec_emb:
            continue
        sim = cosine_similarity(query_emb, rec_emb)
        if sim > 0.4:
            scored.append({
                "slug": slug,
                "cat": record.get("cat", ""),
                "similarity": round(sim, 3),
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]


def build_related_links_section(slug: str, posts_index: dict[str, dict], k: int = 2) -> str:
    """生成「相关阅读」Markdown 段落，用于插入文章末尾

    Args:
        slug: 当前文章 slug
        posts_index: {slug: {title, cat}} — 从 posts.json 加载的元数据
        k: 推荐数量
    """
    related = find_related(slug, k=k)
    if not related:
        return ""

    lines = ["\n---\n\n## 📖 相关阅读\n"]
    for r in related:
        info = posts_index.get(r["slug"], {})
        title = info.get("title", r["slug"])
        cat = info.get("cat", "")
        lines.append(f"- [{title}](/#post/{r['slug']}/{cat})")
    return "\n".join(lines) + "\n"
