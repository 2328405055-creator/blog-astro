# textscripts · scrapers/firecrawl_scraper.py — Firecrawl 抓取 + 内容富化

import re
import time
import logging

from firecrawl import V1FirecrawlApp
from tenacity import retry, stop_after_attempt, wait_exponential

from textscripts.config import CONFIG, FC_KEY, ENRICH
from textscripts.utils.llm import summarize_article, _get_ai_client

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def scrape_article_content(url):
    """用 Firecrawl 抓取完整文章，返回 {markdown, images}。失败返回 None"""
    if not FC_KEY:
        return None
    try:
        app = V1FirecrawlApp(api_key=FC_KEY)
        result = app.scrape_url(
            url,
            formats=["markdown", "html"],
            timeout=CONFIG["scrape_timeout"] * 1000,
        )
        md = getattr(result, "markdown", "") or ""
        if not md or len(md) < 100:
            return None
        images = []
        html = getattr(result, "html", "") or ""
        if html:
            img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
            images = [u for u in img_urls if not u.endswith(('.gif', '.svg')) and len(u) > 20][:5]
        max_chars = CONFIG["target_words"] * 8
        if len(md) > max_chars:
            md = md[:max_chars] + "\n\n...(内容已截断)"
        return {"markdown": md, "images": images, "url": url}
    except Exception as e:
        logger.warning(f"Firecrawl 抓取失败 {url[:60]}: {e}")
        return None


def cluster_articles(entries):
    """按主题相似度将文章分组为 clusters"""
    if len(entries) <= 3:
        return [[e] for e in entries]

    def keywords(title):
        words = re.findall(r"[\w一-鿿]{2,}", title.lower())
        stop = {
            'the', 'and', 'for', 'you', 'can', 'how', 'to', 'in', 'with', 'your',
            'this', 'that', 'from', 'are', 'get', 'fit', 'best', 'new', 'out',
            'its', 'all', 'not', 'one', 'use', 'will', 'what', 'more', 'have',
            'been', 'some', 'into', 'just', 'like', 'about', 'make', 'need',
            'does', 'work', 'good', 'well', 'also', 'very', 'each', 'than',
            'over', 'take', 'know', 'much', 'our', 'day', 'way', 'see', 'back',
            'come', 'has', 'two', 'top', 'try', 'say', 'any', 'set', 'put',
            'big', 'own', 'may', 'had',
        }
        return [w for w in words if w not in stop]

    clusters = []
    used = set()
    for i, e1 in enumerate(entries):
        if i in used:
            continue
        k1 = set(keywords(e1["title"]))
        cluster = [e1]
        used.add(i)
        for j, e2 in enumerate(entries):
            if j in used or e1["section"] != e2["section"]:
                continue
            k2 = set(keywords(e2["title"]))
            if not k1 or not k2:
                continue
            overlap = len(k1 & k2)
            if overlap >= 2:
                cluster.append(e2)
                used.add(j)
        clusters.append(cluster)

    return [c[:3] for c in clusters]


def synthesize_cluster(cluster, section):
    """多源交叉合成：Firecrawl 抓取 + AI 交叉印证总结"""
    if len(cluster) == 1:
        entry = cluster[0]
        scraped = scrape_article_content(entry["link"])
        if scraped:
            summary = summarize_article(
                entry["title"], entry["source_name"], scraped["markdown"], section
            )
            entry["enriched"] = summary
            entry["_images"] = scraped.get("images", [])
        return

    sources = []
    all_content = []
    all_images = []
    for entry in cluster:
        scraped = scrape_article_content(entry["link"])
        if scraped:
            sources.append(f"**{entry['title']}** (来源: {entry['source_name']})")
            all_content.append(scraped["markdown"])
            all_images.extend(scraped.get("images", [])[:2])
        time.sleep(0.5)

    if len(sources) < 2:
        if sources and cluster:
            entry = cluster[0]
            entry["enriched"] = summarize_article(
                entry["title"],
                entry["source_name"],
                all_content[0] if all_content else "",
                section,
            )
            entry["_images"] = all_images
        return

    combined = "\n\n---\n\n".join(
        f"### 来源 {i+1}: {s}\n{c[:4000]}"
        for i, (s, c) in enumerate(zip(sources, all_content))
    )

    system_prompt = (
        "你是一位专业的内容编辑。下面有{0}篇关于同一主题的文章。请交叉印证、对比分析，"
        "整合成一篇600-1000字的纯中文综合教程。要求:\n"
        "1. 优先采用{0}篇文章共同提到的观点和方法\n"
        "2. 如果文章之间有矛盾，指出分歧并给出建议\n"
        "3. 补充各文章独有的有价值的细节\n"
        "4. 用 ## 分节，有实质性内容\n"
        "5. 结尾给一个「综合建议」\n"
        "只输出教程正文。"
    ).format(len(sources))

    try:
        client, model = _get_ai_client(False)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请整合以下{len(sources)}篇文章:\n\n{combined[:12000]}"},
            ],
            max_tokens=2500,
            temperature=0.7,
        )
        body = resp.choices[0].message.content.strip()
        key_points = re.findall(r"^##\s+(.+)", body, re.MULTILINE)[:5]
        enriched = {
            "content": body,
            "key_points": key_points if key_points else ["详见正文"],
            "word_count": len(body),
            "model": "Qianwen",
            "source_count": len(sources),
        }
        cluster[0]["enriched"] = enriched
        cluster[0]["_images"] = all_images[:5]
        cluster[0]["_sources"] = sources
        for e in cluster[1:]:
            e["enriched"] = False
        logger.info(f"交叉合成: {len(sources)}篇 -> {len(body)}字")
    except Exception as e:
        logger.warning(f"交叉合成失败: {e}")
        if all_content and cluster:
            entry = cluster[0]
            entry["enriched"] = summarize_article(
                entry["title"], entry["source_name"], all_content[0], section
            )
            entry["_images"] = all_images


def enrich_batch(entries):
    """批量富化：先聚类 -> 每簇交叉合成或单篇总结"""
    if not ENRICH:
        return entries

    total = len(entries)
    logger.info(f"内容富化: {total} 篇 -> {len(cluster_articles(entries))} 个主题簇...")

    clusters = cluster_articles(entries)
    multi = sum(1 for c in clusters if len(c) > 1)
    if multi:
        logger.info(f"发现 {multi} 个多源主题簇")

    for ci, cluster in enumerate(clusters):
        section = cluster[0]["section"]
        if len(cluster) > 1:
            logger.info(f"[Cluster {ci+1}/{len(clusters)}] {len(cluster)}篇 -> 交叉合成...")
        else:
            logger.info(f"[Cluster {ci+1}/{len(clusters)}] 单篇 -> 总结...")
        synthesize_cluster(cluster, section)

    ok = sum(1 for e in entries if e.get("enriched"))
    logger.info(f"富化完成: {ok}/{total} 篇成功 ({multi} 个交叉合成)")
    return entries
