# textscripts · utils/sitemap_generator.py — sitemap.xml 生成

import os
from datetime import datetime, timedelta

from textscripts.config import BASE_DIR
from textscripts.utils.file_ops import load_json, today_str


def generate_sitemap():
    """从 posts.json 生成 sitemap.xml，使用真实日期和合理 changefreq/priority"""
    posts = load_json(
        os.path.join(BASE_DIR, "posts", "posts.json")
    )
    base = "https://20020426.top"
    now = today_str()
    today_date = datetime.now().date()

    urls = [
        f'  <url><loc>{base}</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{base}/#section/cross-border</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base}/#section/fitness</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base}/#section/ai-news</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{base}/#section/ozon-pick</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>',
    ]

    for p in posts:
        # 优先使用 lastmod，回退到 date
        lastmod = p.get("lastmod") or p.get("date", now)
        date_str = p.get("date", now)

        # 计算文章年龄
        try:
            article_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            age_days = (today_date - article_date).days
        except (ValueError, TypeError):
            age_days = 365

        # changefreq 和 priority 根据年龄动态调整
        if age_days <= 7:
            changefreq = "weekly"
            priority = "0.7"
        elif age_days <= 30:
            changefreq = "monthly"
            priority = "0.6"
        else:
            changefreq = "yearly"
            priority = "0.5"

        urls.append(
            f'  <url><loc>{base}/#post/{p["slug"]}/{p["cat"]}</loc><lastmod>{lastmod}</lastmod><changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>'
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )

    path = os.path.join(BASE_DIR, "sitemap.xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"sitemap.xml 已更新 ({len(posts)} 篇文章, 日期: {now})")
