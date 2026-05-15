# textscripts · utils/ru_utils.py — 俄语翻译 + 电商术语词典

import urllib.parse
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# 俄语→中文 常用电商术语词典
RU_CN_DICT = {
    "беспроводные наушники": "无线耳机", "наушники": "耳机",
    "умная розетка": "智能插座", "умный дом": "智能家居",
    "фитнес-браслет": "智能手环", "смарт-часы": "智能手表",
    "портативная колонка": "便携蓝牙音箱", "колонка": "音箱",
    "power bank": "充电宝", "внешний аккумулятор": "充电宝",
    "кабель зарядный": "充电线", "type-c": "Type-C",
    "стекло защитное": "钢化膜", "чехол": "手机壳",
    "держатель телефон": "手机支架", "автомобиль": "车载",
    "коврик для йоги": "瑜伽垫", "гантели разборные": "可调节哑铃",
    "гантели": "哑铃", "эспандер": "弹力带", "фитнес резинка": "健身带",
    "скакалка": "跳绳", "бутылка для воды": "运动水杯",
    "термос": "保温杯", "кружка": "杯子",
    "контейнер для еды": "便当盒", "ланч-бокс": "饭盒",
    "органайзер": "收纳盒", "косметика": "化妆品",
    "массажер для лица": "面部按摩仪", "массажер": "按摩器",
    "щетка электрическая": "电动牙刷", "зубная": "牙刷",
    "фен для волос": "电吹风", "фен": "吹风机",
    "подушка для сна": "睡眠枕头", "подушка": "枕头",
    "светильник": "台灯", "светодиодный": "LED",
    "носки": "袜子", "кроссовки": "运动鞋",
    "шапка": "帽子", "зима": "冬季",
    "рюкзак городской": "城市双肩包", "рюкзак": "双肩包",
    "игрушка развивающая": "益智玩具", "игрушка": "玩具",
    "конструктор магнитный": "磁力积木", "конструктор": "积木",
    "пазл": "拼图", "мыло ручной работы": "手工皂",
    "ароматизатор": "香薰", "для дома": "家用",
    "нож кухонный": "厨房刀具", "набор": "套装",
    "ремень мужской": "男士皮带", "кожаный": "真皮",
    # 品牌
    "xiaomi": "小米", "huawei": "华为", "samsung": "三星",
    "apple": "苹果", "sony": "索尼", "jbl": "JBL",
    "iphone": "iPhone", "airpods": "AirPods",
}


def translate_ru(text):
    """俄语→中文翻译 (词典优先，Google Translate 降级)"""
    text_lower = text.lower().strip()

    if text_lower in RU_CN_DICT:
        return RU_CN_DICT[text_lower]

    # 部分匹配
    result = text_lower
    for ru_word, cn_word in sorted(RU_CN_DICT.items(), key=lambda x: -len(x[0])):
        if ru_word in result:
            result = result.replace(ru_word, cn_word)
    if result != text_lower:
        return result

    # Google Translate 降级
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=ru&tl=zh-CN&dt=t&q=" + urllib.parse.quote(text)
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            parts = r.json()
            translated = "".join(p[0] for p in parts[0] if p[0])
            if translated and translated != text:
                return translated
    except Exception as e:
        logger.debug(f"Google Translate 降级失败: {e}")

    return text


# ====== 推荐理由生成 ======

def generate_recommendation(product, rank, trend_score):
    """根据真实数据生成中文推荐理由"""
    price_cny = product.get("price_cny", 0)
    rating = product.get("rating", 0)
    reviews = product.get("review_count", 0)
    sort_mode = product.get("sort_mode", "")

    reasons = []

    if sort_mode == "popular":
        reasons.append("数据来源: Wildberries真实销量排序(популярности), 反映当前热销趋势")
    elif sort_mode == "newly":
        reasons.append("数据来源: Wildberries新品排序(новинки), 捕捉早期选品机会")

    if price_cny < 50:
        reasons.append(f"低价位(¥{price_cny}), 适合新手试水, 资金压力小")
    elif price_cny < 150:
        reasons.append(f"中等价位(¥{price_cny}), 预估利润率30-50%, 性价比突出")
    elif price_cny < 400:
        reasons.append(f"中高价位(¥{price_cny}), 单品利润可观, 适合精品运营")
    else:
        reasons.append(f"高客单价(¥{price_cny}), 需注意物流保险和售后成本")

    if reviews >= 1000:
        reasons.append(f"市场高度认可({reviews}条真实评价, {rating}分), 需求强劲但竞争也大")
    elif reviews >= 200:
        reasons.append(f"有一定市场验证({reviews}条评价, {rating}分), 竞争适中")
    else:
        reasons.append(f"新兴商品({reviews}条评价, {rating}分), 竞争较少, 蓝海潜力")

    if trend_score >= 75:
        reasons.append(f"趋势评分{trend_score}/100(高), 多维度信号积极, 强烈推荐关注")
    elif trend_score >= 60:
        reasons.append(f"趋势评分{trend_score}/100(中高), 综合信号良好")
    else:
        reasons.append(f"趋势评分{trend_score}/100, 建议进一步人工验证")

    return "；".join(reasons)


def assess_risks(product):
    """基于真实数据生成风险提示"""
    risks = []
    price_cny = product.get("price_cny", 0)
    reviews = product.get("review_count", 0)
    sort_mode = product.get("sort_mode", "")
    nm_id = product.get("nm_id", "")

    risks.append(f"数据采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} CST, 价格/库存以 Wildberries 实时数据为准")

    if reviews > 5000:
        risks.append(f"头部商品({reviews}条评价), 已形成竞争壁垒, 建议分析差异化切入点后再入场")
    elif reviews > 1000:
        risks.append(f"中等竞争({reviews}条评价), 建议研究TOP10竞品的定价/卖点策略")

    cert_map = {
        "audio": "需 EAC 认证",
        "smart-home": "需 EAC 认证",
        "wearables": "需 EAC 认证",
        "accessories": "需 EAC 声明",
        "auto": "需 EAC 认证 + 部分需 FSS 通知",
        "sports": "一般需 EAC 声明, 防护类需严格认证",
        "beauty": "需 EAC 声明, 部分需卫生注册",
        "home": "食品接触类需 EAC 声明, 电子类需认证",
        "clothing": "需 EAC 声明, 儿童服装额外要求",
        "kids": "严格认证, 需 GOST 测试",
    }
    cert = cert_map.get(product.get("cat_key", ""), "请确认具体认证要求")
    risks.append(f"认证要求: {cert}")

    if sort_mode == "newly" and reviews < 100:
        risks.append("新品上架, 评价较少, 建议少量首批试单验证市场反应")

    if price_cny > 300:
        risks.append("高客单价商品退货/售后成本较高, 建议购买物流保险")
    if price_cny < 20:
        risks.append("超低价商品利润率薄, 需走量且有供应链优势才能盈利")

    risks.append(f"SKU: {nm_id}, 可在 WB 搜索验证: wildberries.ru/catalog/{nm_id}/detail.aspx")

    return risks
