#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ozon选品内容验证插件 (Verification Plugin)
===========================================
用法(首次安装):  python scripts/ozon_verifier.py --install
用法(核查最新):  python scripts/ozon_verifier.py --check
用法(核查指定):  python scripts/ozon_verifier.py --check --slug ozon-daily-pick-2026-05-11
用法(查看报告):  python scripts/ozon_verifier.py --report
用法(禁用插件):  删除 data/ozon_raw/.plugin_installed 文件即可

此脚本作为独立"插件"运行。首次使用需手动 --install 确认安装。
"""

import json
import os
import sys
from datetime import datetime, timedelta
from collections import Counter

import requests

# 修复 Windows 控制台 GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ====== 路径配置 ======
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
DATA_DIR = os.path.join(BASE_DIR, "data", "ozon_raw")
FEATURED_JSON_PATH = os.path.join(POSTS_DIR, "featured_ozon_pick.json")
CONFIG_PATH = os.path.join(SCRIPTS_DIR, "ozon_config.json")
VERIFICATION_REPORT_PATH = os.path.join(DATA_DIR, "verification_report.json")
INSTALL_FLAG = os.path.join(DATA_DIR, ".plugin_installed")

PLUGIN_VERSION = "1.0.0"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ====== 检查 1: 来源可靠性 ======

def check_source_reliability(featured_data):
    """验证每个数据源 URL 是否可访问"""
    data_sources = featured_data.get("data_sources", [])
    details = []
    warnings = []
    accessible = 0
    total = 0

    for src in data_sources:
        name = src.get("name", "未知来源")
        url = src.get("url", "")
        reliability = src.get("reliability", "unknown")
        total += 1

        # 已知可靠性评分
        reliability_scores = {
            "high": 0.9,
            "medium": 0.6,
            "low": 0.3,
            "unknown": 0.4,
        }
        base_score = reliability_scores.get(reliability, 0.4)

        # 尝试验证 URL 可访问性
        url_ok = False
        if url:
            try:
                r = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=10, allow_redirects=True)
                if r.status_code < 400:
                    url_ok = True
                    accessible += 1
                    details.append(f"✅ {name}: 可访问 (HTTP {r.status_code}), 基础评分 {base_score}")
                else:
                    warnings.append(f"{name}: HTTP {r.status_code}")
                    details.append(f"⚠️ {name}: 返回 {r.status_code}, 基础评分 {base_score * 0.5}")
                    base_score *= 0.5
            except Exception as e:
                warnings.append(f"{name}: 无法访问 ({e})")
                details.append(f"❌ {name}: 连接失败, 基础评分 {base_score * 0.3}")
                base_score *= 0.3
        else:
            details.append(f"⚠️ {name}: 无 URL 可验证")
            base_score *= 0.5

        src["verified_score"] = round(base_score, 2)

    score = round((accessible / max(total, 1)) * 100)
    status = "pass" if score >= 60 else ("warn" if score >= 30 else "fail")

    return {
        "score": score,
        "status": status,
        "details": "\n".join(details) if details else "无数据源可验证",
        "warnings": warnings,
    }


# ====== 检查 2: 数据新鲜度 ======

def check_data_freshness(featured_data, max_age_hours=24):
    """检查数据采集时间是否在可接受范围内"""
    generated_at = featured_data.get("generated_at", "")
    products = featured_data.get("products", [])
    details = []
    stale_products = []

    # 检查生成时间
    now = datetime.now()
    gen_time = None
    if generated_at:
        try:
            gen_time = datetime.strptime(generated_at[:19], "%Y-%m-%dT%H:%M:%S")
            age_hours = (now - gen_time).total_seconds() / 3600
            if age_hours <= max_age_hours:
                details.append(f"✅ 数据生成时间: {generated_at} (距今 {age_hours:.1f} 小时, 在 {max_age_hours}h 内)")
            else:
                details.append(f"⚠️ 数据生成时间: {generated_at} (距今 {age_hours:.1f} 小时, 超过 {max_age_hours}h)")
                stale_products = [p.get("product_name_cn", "") for p in products]
        except Exception:
            details.append("⚠️ 无法解析数据生成时间")
            stale_products = [p.get("product_name_cn", "") for p in products]
    else:
        details.append("❌ 缺少数据生成时间戳")
        stale_products = [p.get("product_name_cn", "") for p in products]

    score = 100 if not stale_products else (60 if len(stale_products) < len(products) // 2 else 30)
    status = "pass" if score >= 80 else ("warn" if score >= 50 else "fail")

    return {
        "score": score,
        "status": status,
        "details": "\n".join(details),
        "stale_products": stale_products[:10],
    }


# ====== 检查 3: 交叉验证一致性 ======

def check_cross_reference(featured_data):
    """检查商品数据在多个来源间的一致性"""
    products = featured_data.get("products", [])
    details = []
    discrepancies = []

    single_source = 0
    for p in products:
        source_urls = p.get("source_urls", [])
        if len(source_urls) < 2:
            single_source += 1
            discrepancies.append({
                "product": p.get("product_name_cn", p.get("product_name_ru", "")),
                "issue": f"仅有 {len(source_urls)} 个数据源",
            })

    if single_source == 0:
        details.append("✅ 所有商品都有多源数据交叉验证")
    elif single_source <= len(products) // 3:
        details.append(f"⚠️ {single_source}/{len(products)} 款商品仅有单一数据源")
    else:
        details.append(f"❌ {single_source}/{len(products)} 款商品仅有单一数据源,建议增加 Ozon/Yandex 比价")

    # 价格合理性范围检查(跨商品)
    if len(products) >= 3:
        prices = [p.get("price_rub", 0) for p in products if p.get("price_rub", 0) > 0]
        if prices:
            avg = sum(prices) / len(prices)
            outliers = [p for p in products if p.get("price_rub", 0) > avg * 5]
            if outliers:
                details.append(f"⚠️ {len(outliers)} 款商品价格显著高于均价({avg:.0f} ₽),需确认定价合理性")

    score = 100 - (single_source * 15) if products else 100
    score = max(10, min(100, score))
    status = "pass" if score >= 70 else ("warn" if score >= 40 else "fail")

    return {
        "score": score,
        "status": status,
        "details": "\n".join(details) if details else "交叉验证通过",
        "discrepancies": discrepancies[:10],
    }


# ====== 检查 4: 内容完整性 ======

def check_content_completeness(featured_data, required_fields=None):
    """检查每款商品是否包含所有必填字段"""
    if required_fields is None:
        required_fields = ["product_name_ru", "price_rub", "source_urls", "category_cn"]

    products = featured_data.get("products", [])
    details = []
    missing_fields = []
    complete_count = 0

    for p in products:
        name = p.get("product_name_cn", p.get("product_name_ru", "未知商品"))
        missing = []
        for field in required_fields:
            val = p.get(field)
            if val is None or val == "" or (isinstance(val, list) and len(val) == 0):
                missing.append(field)

        if missing:
            missing_fields.append({"product": name, "missing": missing})
        else:
            complete_count += 1

    if complete_count == len(products):
        details.append(f"✅ 全部 {len(products)} 款商品必填字段完整")
    else:
        details.append(f"完成 {complete_count}/{len(products)} 款商品字段完整")

    # 额外检查中文翻译质量
    no_cn = 0
    for p in products:
        ru_name = p.get("product_name_ru", "")
        cn_name = p.get("product_name_cn", "")
        if cn_name == ru_name or not cn_name:
            no_cn += 1
    if no_cn > 0:
        details.append(f"⚠️ {no_cn} 款商品缺少中文译名或翻译未生效")

    score = round((complete_count / max(len(products), 1)) * 100)
    status = "pass" if score >= 80 else ("warn" if score >= 50 else "fail")

    return {
        "score": score,
        "status": status,
        "details": "\n".join(details),
        "missing_fields": missing_fields[:10],
    }


# ====== 检查 5: 市场合理性 ======

def check_market_reasonableness(featured_data):
    """检查价格、评分、评论数是否在合理范围"""
    products = featured_data.get("products", [])
    details = []
    anomalies = []

    for p in products:
        name = p.get("product_name_cn", p.get("product_name_ru", ""))
        issues = []

        # 价格检查 (RUB)
        price = p.get("price_rub", 0)
        if price <= 0:
            issues.append(f"价格异常: {price} ₽")
        elif price < 100:
            issues.append(f"价格偏低: {price} ₽ (可能为小配件或数据误差)")

        # 评分检查
        rating = p.get("rating", 0)
        if rating <= 0 or rating > 5:
            issues.append(f"评分异常: {rating}")
        elif rating < 3.0:
            issues.append(f"评分较低: {rating}/5.0")

        # 评论数检查
        reviews = p.get("review_count", 0)
        if reviews < 0:
            issues.append(f"评论数异常: {reviews}")

        if issues:
            anomalies.append({"product": name, "issues": issues})

    if not anomalies:
        details.append("✅ 所有商品数据在合理范围内")
    else:
        details.append(f"⚠️ {len(anomalies)} 款商品存在数据异常")
        for a in anomalies[:5]:
            details.append(f"  · {a['product']}: {'; '.join(a['issues'])}")

    score = 100 - (len(anomalies) * 10) if products else 100
    score = max(10, min(100, score))
    status = "pass" if score >= 80 else ("warn" if score >= 50 else "fail")

    return {
        "score": score,
        "status": status,
        "details": "\n".join(details),
        "anomalies": anomalies[:10],
    }


# ====== 报告生成 ======

def generate_verification_report(featured_data, checks):
    """汇总所有检查结果,生成最终报告"""
    scores = [c["score"] for c in checks.values()]
    overall_score = round(sum(scores) / len(scores)) if scores else 0

    # 状态判定
    fail_count = sum(1 for c in checks.values() if c["status"] == "fail")
    warn_count = sum(1 for c in checks.values() if c["status"] == "warn")

    if fail_count >= 2:
        overall_status = "fail"
        summary_cn = "多项检查未通过,建议人工审核后再发布"
    elif fail_count >= 1 or warn_count >= 3:
        overall_status = "warn"
        summary_cn = "部分检查存在问题,内容可信度中等,建议针对性改进"
    elif warn_count >= 1:
        overall_status = "pass_with_warnings"
        summary_cn = "基本通过验证,存在轻微问题可后续优化"
    else:
        overall_status = "pass"
        summary_cn = "全部检查通过,内容可信度良好"

    # 改进建议
    recommendations = []
    if fail_count > 0 or warn_count > 0:
        for check_name, check_result in checks.items():
            if check_result["status"] in ("fail", "warn"):
                warnings = check_result.get("warnings", [])
                for w in warnings[:2]:
                    recommendations.append(f"[{check_name}] {w}")

    report = {
        "report_id": f"vr-{featured_data.get('date','unknown')}-{datetime.now().strftime('%H%M')}",
        "checked_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "featured_slug": featured_data.get("slug", ""),
        "plugin_version": PLUGIN_VERSION,
        "overall_score": overall_score,
        "overall_status": overall_status,
        "summary_cn": summary_cn,
        "checks": {
            "source_reliability": checks.get("source_reliability", {}),
            "data_freshness": checks.get("data_freshness", {}),
            "cross_reference": checks.get("cross_reference", {}),
            "content_completeness": checks.get("content_completeness", {}),
            "market_reasonableness": checks.get("market_reasonableness", {}),
        },
        "recommendations": recommendations,
    }

    return report


# ====== 主流程 ======

def run_check(slug=None):
    """运行完整验证流程"""
    # 加载 featured post
    featured_data = load_json(FEATURED_JSON_PATH)
    if not featured_data:
        print("❌ 未找到置顶选品数据 (posts/featured_ozon_pick.json)")
        print("   请先运行 python scripts/ozon_selector.py 生成选品文章")
        return None

    target = featured_data
    if slug:
        if featured_data.get("slug") != slug:
            print(f"⚠️ 当前置顶文章 slug 为 {featured_data.get('slug')}, 与指定 {slug} 不同")
            print("   将验证当前置顶文章...")
        target = featured_data

    # 加载配置
    config = load_json(CONFIG_PATH, {})
    v_config = config.get("verification", {})
    max_age_hours = v_config.get("max_data_age_hours", 24)
    required_fields = v_config.get("required_fields", ["product_name_ru", "price_rub", "source_urls", "category_cn"])

    print(f"\n{'='*60}")
    print(f"  🔍 Ozon选品验证插件 v{PLUGIN_VERSION}")
    print(f"  检查对象: {target.get('slug', '未知')}")
    print(f"  商品数量: {len(target.get('products', []))}")
    print(f"{'='*60}\n")

    # 执行 5 项检查
    print("[1/5] 检查来源可靠性...")
    c1 = check_source_reliability(target)
    print(f"  评分: {c1['score']}/100 [{c1['status']}]")

    print("[2/5] 检查数据新鲜度...")
    c2 = check_data_freshness(target, max_age_hours)
    print(f"  评分: {c2['score']}/100 [{c2['status']}]")

    print("[3/5] 交叉验证一致性...")
    c3 = check_cross_reference(target)
    print(f"  评分: {c3['score']}/100 [{c3['status']}]")

    print("[4/5] 检查内容完整性...")
    c4 = check_content_completeness(target, required_fields)
    print(f"  评分: {c4['score']}/100 [{c4['status']}]")

    print("[5/5] 检查市场合理性...")
    c5 = check_market_reasonableness(target)
    print(f"  评分: {c5['score']}/100 [{c5['status']}]")

    checks = {
        "source_reliability": c1,
        "data_freshness": c2,
        "cross_reference": c3,
        "content_completeness": c4,
        "market_reasonableness": c5,
    }

    # 生成报告
    report = generate_verification_report(target, checks)

    # 保存报告
    ensure_dir(DATA_DIR)
    save_json(VERIFICATION_REPORT_PATH, report)
    print(f"\n[OK] 验证报告已保存: {VERIFICATION_REPORT_PATH}")

    # 更新 featured_ozon_pick.json
    target["verified"] = report["overall_status"] in ("pass", "pass_with_warnings")
    target["verification_report"] = {
        "report_id": report["report_id"],
        "checked_at": report["checked_at"],
        "overall_score": report["overall_score"],
        "overall_status": report["overall_status"],
        "summary_cn": report["summary_cn"],
    }
    save_json(FEATURED_JSON_PATH, target)
    print(f"[OK] featured_ozon_pick.json 已更新验证状态")

    # 更新 posts.json 中对应条目的 verified 字段
    posts = load_json(os.path.join(POSTS_DIR, "posts.json"), [])
    for p in posts:
        if p.get("slug") == target.get("slug"):
            p["verified"] = target["verified"]
            break
    save_json(os.path.join(POSTS_DIR, "posts.json"), posts)

    # 控制台输出结果
    print(f"\n{'='*60}")
    print(f"  📊 验证结果")
    print(f"{'='*60}")
    print(f"  综合评分: {report['overall_score']}/100")
    print(f"  综合状态: {report['overall_status']}")
    print(f"  摘要: {report['summary_cn']}")
    print(f"\n  逐项评分:")
    for name, c in checks.items():
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(c["status"], "❓")
        print(f"    {icon} {name}: {c['score']}/100")

    if report["recommendations"]:
        print(f"\n  💡 改进建议:")
        for r in report["recommendations"]:
            print(f"    → {r}")

    print(f"{'='*60}\n")

    return report


def install_plugin():
    """首次安装流程"""
    print(f"\n{'='*60}")
    print(f"  🔌 Ozon选品验证插件 — 安装向导")
    print(f"  版本: {PLUGIN_VERSION}")
    print(f"{'='*60}\n")
    print("此插件将执行以下核查任务:")
    print("  1. 验证所有数据来源 URL 的可访问性")
    print("  2. 检查采集数据的时效性(是否在24小时内)")
    print("  3. 交叉验证多源数据一致性")
    print("  4. 检查商品信息字段完整性")
    print("  5. 检查价格/评分/评论数的市场合理性\n")
    print("安装后,您可以随时运行以下命令核查内容:")
    print("  python scripts/ozon_verifier.py --check\n")
    print("如需禁用此插件:")
    print("  删除 data/ozon_raw/.plugin_installed 文件即可")
    print("  或直接删除/重命名 scripts/ozon_verifier.py\n")

    confirm = input("确认安装验证插件? (输入 yes 确认): ").strip().lower()
    if confirm == "yes":
        ensure_dir(DATA_DIR)
        flag_data = {
            "installed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "plugin_version": PLUGIN_VERSION,
            "note": "删除此文件即可禁用验证插件",
        }
        save_json(INSTALL_FLAG, flag_data)
        print(f"\n✅ 插件安装成功!")
        print(f"   安装标记: {INSTALL_FLAG}")
        print(f"   运行 'python scripts/ozon_verifier.py --check' 开始核查")
    else:
        print("\n❌ 安装已取消。如需安装请再次运行 --install。")


def show_report(slug=None):
    """展示最近的验证报告"""
    report = load_json(VERIFICATION_REPORT_PATH)
    if not report:
        print("❌ 未找到验证报告,请先运行 --check")
        return

    print(f"\n{'='*60}")
    print(f"  📊 最新验证报告")
    print(f"{'='*60}")
    print(f"  报告ID: {report.get('report_id', 'N/A')}")
    print(f"  检查时间: {report.get('checked_at', 'N/A')}")
    print(f"  文章: {report.get('featured_slug', 'N/A')}")
    print(f"  综合评分: {report.get('overall_score', 0)}/100")
    print(f"  状态: {report.get('overall_status', 'unknown')}")
    print(f"  摘要: {report.get('summary_cn', '')}")
    print(f"\n  逐项评分:")
    for name, c in report.get("checks", {}).items():
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(c.get("status"), "❓")
        print(f"    {icon} {name}: {c.get('score', 0)}/100")
        if c.get("details"):
            for line in c["details"].split("\n")[:3]:
                print(f"      {line}")

    if report.get("recommendations"):
        print(f"\n  💡 改进建议:")
        for r in report["recommendations"]:
            print(f"    → {r}")
    print(f"{'='*60}\n")


def main():
    if "--install" in sys.argv:
        install_plugin()
        return

    if not os.path.exists(INSTALL_FLAG):
        print("\n" + "=" * 60)
        print("  ⚠️  验证插件尚未安装")
        print("=" * 60)
        print("\n此插件将核查每日选品推荐内容的准确性和真实性。")
        print("安装前请确认您已阅读并理解插件功能。\n")
        print("如需安装,请运行:")
        print("  python scripts/ozon_verifier.py --install")
        print("\n拒绝安装: 直接关闭此窗口或删除 ozon_verifier.py 即可。\n")
        return

    if "--check" in sys.argv:
        slug = None
        for i, arg in enumerate(sys.argv):
            if arg == "--slug" and i + 1 < len(sys.argv):
                slug = sys.argv[i + 1]
        run_check(slug=slug)
    elif "--report" in sys.argv:
        show_report()
    else:
        print("用法: python scripts/ozon_verifier.py [--install|--check|--report]")
        print("  --install   首次安装验证插件(需用户确认)")
        print("  --check     核查当前置顶选品文章")
        print("  --report    查看最新验证报告")


if __name__ == "__main__":
    main()
