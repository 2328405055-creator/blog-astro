#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 posts.json 历史文章补充 lastmod 字段
用法:
  python scripts/migrate_add_lastmod.py --dry-run    # 预览变更
  python scripts/migrate_add_lastmod.py --apply       # 执行迁移
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_JSON = os.path.join(BASE_DIR, "posts", "posts.json")


def load_posts():
    if os.path.exists(POSTS_JSON):
        with open(POSTS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posts(posts):
    with open(POSTS_JSON, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def migrate(dry_run=True):
    posts = load_posts()
    updated = 0
    already_ok = 0

    for p in posts:
        if "lastmod" not in p or not p.get("lastmod"):
            # 回退策略: 使用 date 字段的值作为 lastmod
            p["lastmod"] = p.get("date", "")
            updated += 1
            if dry_run:
                print(f"  [DRY] {p.get('slug', '?')}: lastmod -> {p['lastmod']}")
        else:
            already_ok += 1

    print(f"\n总计: {len(posts)} 篇文章")
    print(f"  已有 lastmod: {already_ok}")
    print(f"  待补充: {updated}")

    if not dry_run:
        save_posts(posts)
        print(f"\n✅ 已保存 — {updated} 篇文章补充了 lastmod 字段")
    else:
        print("\n(Dry-run 模式 — 未修改文件。添加 --apply 执行实际迁移)")


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    migrate(dry_run=dry_run)
