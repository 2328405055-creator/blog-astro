# textscripts · rag/embedder.py — 嵌入向量生成
# 复用现有 AI API，不引入新付费服务

import hashlib
import logging
from textscripts.config import CONFIG
from textscripts.utils.llm import _get_ai_client

logger = logging.getLogger(__name__)

# 默认 embedding 配置
EMBEDDING_API_BASE = CONFIG.get("embedding_api_base") or CONFIG.get("primary_api_base", "")
EMBEDDING_MODEL = CONFIG.get("embedding_model", "text-embedding-v1")


def get_embedding(text: str) -> list[float] | None:
    """调用 DashScope embedding API 生成文本向量

    DashScope embedding endpoint 遵循 OpenAI 兼容格式:
      POST /compatible-mode/v1/embeddings
      模型: text-embedding-v1 / text-embedding-v2 / text-embedding-v3

    Fallback: 如果 API 不可用，返回 None（调用方应降级到关键词匹配）
    """
    if not text or not text.strip():
        return None

    text = text.strip()[:8000]  # 截断到 8K chars

    try:
        from openai import OpenAI

        api_key = CONFIG.get("primary_api_key", "")
        if not api_key:
            logger.warning("缺少 API key，无法生成 embedding")
            return None

        # 使用 embedding 专用 base_url，fallback 到 primary_api_base
        base_url = EMBEDDING_API_BASE or CONFIG.get("primary_api_base", "")
        if not base_url:
            logger.warning("缺少 API base URL")
            return None

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        embedding = resp.data[0].embedding
        logger.debug(f"Embedding 生成成功: dim={len(embedding)}")
        return embedding

    except Exception as e:
        logger.warning(f"Embedding API 失败: {e}")
        return None


def get_keyword_vector(text: str) -> list[float]:
    """纯本地降级方案：用关键词哈希生成伪向量

    当 embedding API 不可用时使用。生成 256 维的 pseudo-embedding，
    两个语义相似的文本会产生相似的关键词集合，从而有相近的余弦相似度。

    这不是真正的语义 embedding，但在小语料库去重场景下可用。
    """
    import re

    # 提取 2-4 字的中文词 + 英文单词
    words = re.findall(r"[\w]{2,}", text.lower())

    # 用词频哈希构建 256 维向量
    dim = 256
    vec = [0.0] * dim

    for w in words:
        h = int(hashlib.md5(w.encode()).hexdigest()[:8], 16)
        idx = h % dim
        vec[idx] += 1.0

    # L2 归一化
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]

    return vec


def get_embedding_or_fallback(text: str) -> list[float]:
    """获取 embedding，API 失败时自动降级到关键词向量"""
    emb = get_embedding(text)
    if emb is not None:
        return emb
    logger.info("降级到关键词向量")
    return get_keyword_vector(text)
