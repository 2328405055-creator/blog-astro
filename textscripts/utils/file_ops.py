# textscripts · utils/file_ops.py — 文件操作 + 工具函数

import json
import os
import re
import hashlib
from datetime import datetime


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def slugify(title):
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[-\s]+", "-", s)
    return s[:80]


def str_hash(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]


def today_str():
    """统一日期源: 返回当前真实日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def source_domain(href):
    """从 URL 提取域名"""
    m = re.search(r"https?://(?:www\.)?([^/]+)", href)
    return m.group(1) if m else ""


def clean_html(text):
    """去除 HTML 标签"""
    from html import unescape as _unescape

    return re.sub(r"<[^>]+>", "", _unescape(text or "")).strip()
