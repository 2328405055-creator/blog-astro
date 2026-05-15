#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日内容生成器 — thin wrapper，实际逻辑在 textscripts/ 包中
用法: python scripts/daily_generator.py [--push]
"""

import sys, os

# 确保项目根目录在 Python path 中
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from textscripts.cli import main

if __name__ == "__main__":
    main()
