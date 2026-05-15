# textscripts · rag/deduplicator.py — 语义去重

import logging
from textscripts.rag.embedder import get_embedding_or_fallback
from textscripts.rag.vector_store import load_all

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.85  # 余弦相似度阈值


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度（无 numpy 依赖）"""
    if len(a) != len(b):
        # 维度不一致时截断到较短的
        min_len = min(len(a), len(b))
        a, b = a[:min_len], b[:min_len]

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def check_duplicate(title: str, threshold: float = DEFAULT_THRESHOLD) -> dict | None:
    """检查标题是否与已有文章语义重复

    Returns:
        None: 没有重复
        {"slug": "...", "title": "...", "similarity": 0.92}: 发现重复
    """
    existing = load_all()
    if not existing:
        return None

    emb = get_embedding_or_fallback(title)
    if not emb:
        return None

    best = None
    best_sim = 0.0

    for slug, record in existing.items():
        rec_emb = record.get("embedding", [])
        if not rec_emb:
            continue
        sim = cosine_similarity(emb, rec_emb)
        if sim > best_sim:
            best_sim = sim
            best = slug

    if best_sim >= threshold and best:
        logger.info(f"发现重复: '{title[:50]}...' ≈ [{best}] (sim={best_sim:.3f})")
        return {"slug": best, "similarity": round(best_sim, 3)}

    return None


def is_duplicate(title: str, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """快捷方法：标题是否重复"""
    return check_duplicate(title, threshold) is not None
