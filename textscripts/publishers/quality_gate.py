# textscripts · publishers/quality_gate.py — 发布前质量门禁

import re
import logging
from textscripts.models import GateResult

logger = logging.getLogger(__name__)


def check_word_count(md_content: str, min_chars: int = 400) -> tuple[bool, str, int]:
    """检查正文字数"""
    # 去掉 Markdown 标记和空行
    clean = re.sub(r"[#*>\-\|\n\s]+", "", md_content)
    actual = len(clean)
    if actual < min_chars:
        return False, f"字数不足: {actual} < {min_chars}", actual
    return True, "", actual


def check_source_links(md_content: str, is_ozon: bool = False) -> tuple[bool, str]:
    """检查是否包含来源链接"""
    urls = re.findall(r"https?://[^\s\)]+", md_content)
    if not urls and not is_ozon:
        return False, "缺少来源链接"
    if not urls and is_ozon:
        return False, "缺少 WB/Ozon 商品链接"
    return True, ""


def check_title(title: str) -> tuple[bool, str]:
    """检查标题有效性"""
    if not title or len(title.strip()) < 5:
        return False, "标题过短或为空"
    if len(title) > 120:
        return False, f"标题过长: {len(title)} > 120"
    return True, ""


def check_structure(md_content: str, min_h2: int = 2) -> tuple[bool, str, int]:
    """检查内容结构 (H2 节数量)"""
    h2_count = len(re.findall(r"^##\s+", md_content, re.MULTILINE))
    if h2_count < min_h2:
        return False, f"H2 节不足: {h2_count} < {min_h2}", h2_count
    return True, "", h2_count


def check_date(date_str: str) -> tuple[bool, str, str]:
    """检查日期字段"""
    if not date_str:
        from textscripts.utils.file_ops import today_str
        return True, "日期自动填入", today_str()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False, f"日期格式错误: {date_str}", date_str
    return True, "", date_str


def check_ai_enrichment(enriched: dict | None, enrich_enabled: bool) -> tuple[bool, str]:
    """检查 AI 富化状态"""
    if not enrich_enabled:
        return True, "富化未启用"
    if enriched and enriched.get("content"):
        return True, ""
    return False, "AI 富化启用但未生成内容，降级到模板模式"


def run_quality_gate(
    md_content: str,
    title: str = "",
    date_str: str = "",
    is_ozon: bool = False,
    enriched: dict | None = None,
    enrich_enabled: bool = True,
    strict: bool = True,
) -> GateResult:
    """执行完整质量门禁链

    Args:
        md_content: Markdown 正文
        title: 文章标题
        date_str: 日期
        is_ozon: Ozon 板块特殊处理
        enriched: AI 富化结果
        enrich_enabled: 是否启用富化
        strict: True 时 failures 阻止发布

    Returns:
        GateResult: passed + failures + warnings + score
    """
    failures = []
    warnings = []
    score = 100

    # 1. 标题检查
    ok, msg = check_title(title)
    if not ok:
        failures.append(msg)
        score -= 20
    else:
        score += 0

    # 2. 字数检查
    ok, msg, wc = check_word_count(md_content)
    if not ok:
        if strict:
            failures.append(msg)
            score -= 40
        else:
            warnings.append(msg)
            score -= 15

    # 3. 来源链接
    ok, msg = check_source_links(md_content, is_ozon=is_ozon)
    if not ok:
        if strict:
            failures.append(msg)
            score -= 30
        else:
            warnings.append(msg)
            score -= 10

    # 4. 结构检查
    ok, msg, h2c = check_structure(md_content)
    if not ok:
        warnings.append(msg)
        score -= 10

    # 5. 日期检查
    ok, msg, fixed_date = check_date(date_str)
    if not ok:
        failures.append(msg)
        score -= 10

    # 6. AI 富化
    ok, msg = check_ai_enrichment(enriched, enrich_enabled)
    if not ok:
        warnings.append(msg)
        score -= 5

    score = max(0, min(100, score))
    passed = len(failures) == 0

    result = GateResult(passed=passed, failures=failures, warnings=warnings, score=score)

    if not passed:
        logger.warning(f"质量门禁未通过 (score={score}): {failures}")
    else:
        logger.info(f"质量门禁通过 (score={score})")

    return result
