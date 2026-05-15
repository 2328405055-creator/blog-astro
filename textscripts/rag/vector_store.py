# textscripts · rag/vector_store.py — JSON 文件向量存储

import json
import os
import logging
from textscripts.config import BASE_DIR

logger = logging.getLogger(__name__)

VECTOR_STORE_PATH = os.path.join(BASE_DIR, "data", "embeddings.json")


def _load() -> dict:
    """加载向量库"""
    if os.path.exists(VECTOR_STORE_PATH):
        with open(VECTOR_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"articles": {}, "meta": {"dim": 0, "updated": "", "count": 0}}


def _save(data: dict):
    """保存向量库"""
    os.makedirs(os.path.dirname(VECTOR_STORE_PATH), exist_ok=True)
    with open(VECTOR_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add(slug: str, embedding: list[float], cat: str = "", date: str = "", word_count: int = 0):
    """添加或更新一个向量"""
    data = _load()
    dim = len(embedding)

    data["articles"][slug] = {
        "slug": slug,
        "embedding": embedding,
        "cat": cat,
        "date": date,
        "word_count": word_count,
    }
    data["meta"]["dim"] = dim
    data["meta"]["count"] = len(data["articles"])
    data["meta"]["updated"] = _now()
    _save(data)
    logger.debug(f"向量已存储: {slug} ({dim}d)")


def remove(slug: str):
    """删除一个向量"""
    data = _load()
    if slug in data["articles"]:
        del data["articles"][slug]
        data["meta"]["count"] = len(data["articles"])
        data["meta"]["updated"] = _now()
        _save(data)


def load_all() -> dict[str, dict]:
    """加载所有向量记录，返回 {slug: record}"""
    return _load()["articles"]


def get_meta() -> dict:
    """获取向量库元信息"""
    return _load()["meta"]


def clear():
    """清空向量库"""
    _save({"articles": {}, "meta": {"dim": 0, "updated": _now(), "count": 0}})


def count() -> int:
    return _load()["meta"].get("count", 0)


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
