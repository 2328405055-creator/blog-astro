# 猫明之主小站 · Astro 重构版

跨境电商实战 · 徒手健身 · AI学习 · Ozon选品

## 技术栈
- Astro 5 (SSG)
- 纯静态输出 (GitHub Pages)

## 开发
```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # 构建到 dist/
```

## 部署
GitHub Actions 自动部署到 GitHub Pages (20020426.top)

## 项目结构
```
src/
  pages/          # 页面路由
  components/     # Astro 组件
  lib/            # 数据层 + Schema
  styles/         # 全局样式
public/
  posts/          # Markdown 文章
  data/           # RAG 向量 + Ozon 数据
```

