#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理 posts.json 和 sitemap.xml 中的异常日期
用法:
  python scripts/fix_dates.py --dry-run    # 预览异常日期
  python scripts/fix_dates.py --apply       # 修复异常日期
"""

import json
import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_JSON = os.path.join(BASE_DIR, "posts", "posts.json")

TODAY = datetime.now().date()
FUTURE_LIMIT = TODAY + timedelta(days=7)  # 7天以内的未来日期可以接受(时区差异)


def is_anomalous_date(date_str):
    """判断日期是否异常"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        if d.year < 2024:
            return True, f"年份过旧: {date_str}"
        if d > FUTURE_LIMIT:
            return True, f"未来日期: {date_str}"
        return False, ""
    except (ValueError, TypeError):
        return True, f"格式错误: {date_str}"


def fix_date(post, dry_run=True):
    """尝试修复异常日期"""
    slug = post.get("slug", "")
    # 从 slug 中提取日期 (格式: ...-YYYY-MM-DD 或 ...-YYYY-MM-DD-N)
    parts = slug.split("-")
    for i in range(len(parts) - 2):
        try:
            candidate = f"{parts[i]}-{parts[i+1].zfill(2)}-{parts[i+2].zfill(2)}"
            datetime.strptime(candidate, "%Y-%m-%d")
            if dry_run:
                return candidate
            post["date"] = candidate
            if not post.get("lastmod"):
                post["lastmod"] = candidate
            return candidate
        except (ValueError, IndexError):
            continue
    return None


def main():
    dry_run = "--apply" not in sys.argv

    if not os.path.exists(POSTS_JSON):
        print("❌ posts.json 不存在")
        return

    posts = []
    with open(POSTS_JSON, "r", encoding="utf-8") as f:
        posts = json.load(f)

    anomalies = []
    fixed = 0

    for p in posts:
        date_val = p.get("date", "")
        is_bad, reason = is_anomalous_date(date_val)
        if is_bad:
            new_date = fix_date(p, dry_run=dry_run)
            anomalies.append({
                "slug": p.get("slug", "?"),
                "title": p.get("title", "?")[:60],
                "old_date": date_val,
                "new_date": new_date or "无法修复",
                "reason": reason,
            })
            if new_date:
                fixed += 1

    print(f"总计: {len(posts)} 篇文章")
    print(f"异常日期: {len(anomalies)} 篇")
    print(f"可修复: {fixed} 篇\n")

    for a in anomalies[:20]:
        icon = "✅" if a["new_date"] != "无法修复" else "❌"
        print(f"  {icon} [{a['reason']}] {a['slug']}")
        print(f"     {a['old_date']} -> {a['new_date']}")

    if not dry_run and anomalies:
        # 实际写入
        for p in posts:
            date_val = p.get("date", "")
            is_bad, _ = is_anomalous_date(date_val)
            if is_bad:
                fix_date(p, dry_run=False)
        with open(POSTS_JSON, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存 — {fixed} 篇文章日期已修复")

    if dry_run:
        print("\n(Dry-run 模式 — 未修改文件。添加 --apply 执行实际修复)")


if __name__ == "__main__":
    main()
