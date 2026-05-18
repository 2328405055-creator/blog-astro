# Shopify 后台启用 Google Analytics 4 教程

> 📂 分类: 选品技巧
> 📅 采集日期: 2026-05-18
> 📰 来源: **Shopify**（shopify.com）

---

## 一、GA4 账户创建与媒体资源配置  
登录 [Google Analytics 官网](https://analytics.google.com/analytics/web/provision/#/provision)，用 Google 账号注册 GA4 账户。进入「管理」→「媒体资源」→「创建媒体资源」，选择「网站」类型，填写店铺域名（如 `yourstore.myshopify.com`）、业务名称和时区（俄罗斯市场建议选 `Moscow Time (UTC+3)`）。完成设置后，系统自动生成 **GA4 测量 ID**（格式为 `G-XXXXXXXXXX`）和完整 `gtag.js` 代码段。务必复制整段代码（含 `<script>` 标签），这是后续部署的唯一凭证。

## 二、Shopify 后台代码嵌入实操  
登录 Shopify 后台 →「在线商店」→「主题」→「操作」→「编辑代码」。在左侧文件列表中找到 `theme.liquid`，定位到 `<head>` 标签内（通常为第3–5行）。将复制的 `gtag.js` 代码**精准粘贴至 `<head>` 开始位置**（不可放在 `</head>` 后或 `<body>` 内）。保存后，立即访问店铺首页、商品页、结账页各3次以上，等待15分钟。打开 GA4 实时报告，检查「实时用户数」是否显示 ≥1，且「事件计数」中出现 `page_view`、`scroll`、`click` 等基础事件——达标即表示埋点成功。

## 三、关键转化事件增强配置  
仅基础埋点无法追踪订单数据。需手动补充电商事件：在 Shopify 后台「设置」→「支付」→「添加自定义脚本」，粘贴以下代码（替换 `G-XXXXXXXXXX` 为你的测量ID）：  
```html
<script>
gtag('event', 'purchase', {
  'transaction_id': '{{ order.order_number }}',
  'value': {{ order.total_price | money_without_currency }},
  'currency': '{{ order.currency }}',
  'items': [{% for item in order.line_items %}{
    'item_id': '{{ item.product_id }}',
    'item_name': '{{ item.title }}',
    'quantity': {{ item.quantity }}
  }{% unless forloop.last %},{% endunless %}{% endfor %}]
});
</script>
```  
配置后，在 GA4「配置」→「事件」中验证 `purchase` 事件是否出现在「已启用事件」列表，且「转化路径」中可查看订单金额、商品SKU等字段。

## 四、新手三大致命错误及规避方案  
**错误1：混淆 UA 与 GA4 代码混用**  
→ 表现：GA4 实时报告无数据，但旧版 UA 有流量。  
→ 规避：彻底删除 Shopify 后台「在线商店」→「偏好设置」中残留的 UA 跟踪 ID（UA-XXXXX），仅保留 GA4 的 `gtag.js`。  

**错误2：`gtag.js` 粘贴位置错误**  
→ 表现：首页有数据，但商品页/结账页无事件。  
→ 规避：必须插入 `theme.liquid` 的 `<head>` 内（非 `theme.scss.liquid` 或 `product.liquid`），确保全站加载。  

**错误3：忽略支付页面事件权限**  
→ 表现：GA4 显示访客数正常，但转化率始终为0%。  
→ 规避：Shopify 支付页面属第三方 iframe，必须通过「设置→支付→添加自定义脚本」注入 purchase 事件，不可依赖全局 gtag。

## 今日行动建议  
立即执行三步：① 访问 [GA4 注册页](https://analytics.google.com/analytics/web/provision/#/provision) 创建账户，获取测量ID；② 登录 Shopify 后台，将 `gtag.js` 粘贴至 `theme.liquid` 的 `<head>` 中并保存；③ 打开 GA4 实时报告，用手机/电脑各访问3个不同页面，确认15分钟内出现 `page_view` 事件。完成即获基础数据监控能力，为后续俄语站用户行为分析打下根基。

## 核心要点

- 一、GA4 账户创建与媒体资源配置  
- 二、Shopify 后台代码嵌入实操  
- 三、关键转化事件增强配置  
- 四、新手三大致命错误及规避方案  
- 今日行动建议  

---

## 查看原文

📎 **原文链接:** [点击查看原文](https://news.google.com/rss/articles/CBMibkFVX3lxTE8yUUNfcEx2Y0N5Sl9GYmo1dnRXc1V2dWljQkpRd2cxd3NxbE52TlBibnkxVVBxS2w5Y3EyOGd0WkZQaHMzU2V4NVZHc0JtWFlWSzdDSzdwQkt6R2Q3MVdUdndGNC1aY1lYRS1JeFNR?oc=5)
🔍 **站内搜索:** [在 Shopify 站内搜索本文](https://www.google.com/search?q=Shopify%20%E5%90%8E%E5%8F%B0%E5%90%AF%E7%94%A8%20Google%20Analytics%204%20%E6%95%99%E7%A8%8B+site:shopify.com)

> 📚 本文内容来自 **Shopify**，版权归原来源所有。
