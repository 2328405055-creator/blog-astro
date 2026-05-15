# textscripts · config.py — 配置加载与校验

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
JSON_PATH = os.path.join(POSTS_DIR, "posts.json")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
CONFIG_PATH = os.path.join(SCRIPTS_DIR, "config.json")


def load_config():
    config = {
        "firecrawl_api_key": "",
        "primary_api_key": "",
        "primary_api_base": "",
        "primary_model": "qwen-plus",
        "backup_api_key": "",
        "backup_api_base": "",
        "backup_model": "deepseek-chat",
        "enrich_enabled": False,
        "target_words": 700,
        "scrape_timeout": 30,
        "embedding_api_base": "",
        "embedding_model": "text-embedding-v1",
    }
    # 1. 从 .env 文件加载
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    key_name = k.strip()
                    if key_name.startswith("BLOG_"):
                        cfg_key = key_name[5:].lower()
                        val = v.strip().strip('"').strip("'")
                        if cfg_key in config:
                            if cfg_key in ("target_words", "scrape_timeout"):
                                config[cfg_key] = int(val)
                            elif cfg_key == "enrich_enabled":
                                config[cfg_key] = val.lower() in ("1", "true", "yes")
                            else:
                                config[cfg_key] = val
    # 2. 从 config.json 补充
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            file_cfg = json.load(f)
            for k, v in file_cfg.items():
                if k in config and not config[k]:
                    config[k] = v
    # 3. 系统环境变量覆盖
    for key in config:
        env_val = os.environ.get(f"BLOG_{key.upper()}")
        if env_val is not None:
            if key in ("target_words", "scrape_timeout"):
                config[key] = int(env_val)
            elif key == "enrich_enabled":
                config[key] = env_val.lower() in ("1", "true", "yes")
            else:
                config[key] = env_val
    return config


# 全局配置实例
CONFIG = load_config()
FC_KEY = CONFIG["firecrawl_api_key"]
ENRICH = bool(CONFIG["enrich_enabled"] and FC_KEY and CONFIG["primary_api_key"])
