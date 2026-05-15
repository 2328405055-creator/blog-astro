// ============================================================
// lib/schema.ts — SEO Schema 生成器
// 覆盖: Article + BreadcrumbList + FAQ + HowTo + Product
// ============================================================

export interface ArticleMeta {
  slug: string;
  title: string;
  description: string;
  date: string;
  lastmod?: string;
  category: string;
  tags: string[];
  coverImage?: string;
  readingTime?: string; // "8 分钟"
  wordCount?: number;
}

export interface FAQItem {
  question: string;
  answer: string;
}

export interface BreadcrumbItem {
  name: string;
  url: string;
}

const SITE_NAME = "猫明之主";
const SITE_URL = "https://20020426.top";

// ============================================================
// Article Schema
// ============================================================
export function buildArticleSchema(article: ArticleMeta): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.description,
    datePublished: article.date,
    dateModified: article.lastmod || article.date,
    author: {
      "@type": "Person",
      name: "明猫",
      url: SITE_URL,
    },
    publisher: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
      logo: {
        "@type": "ImageObject",
        url: `${SITE_URL}/favicon.svg`,
      },
    },
    image: article.coverImage || `${SITE_URL}/images/default-og.png`,
    url: `${SITE_URL}/post/${article.slug}`,
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": `${SITE_URL}/post/${article.slug}`,
    },
    isAccessibleForFree: true,
    ...(article.wordCount ? { wordCount: article.wordCount } : {}),
  };
}

// ============================================================
// BreadcrumbList Schema
// ============================================================
export function buildBreadcrumbSchema(items: BreadcrumbItem[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

// Homepage breadcrumb
export function getHomeBreadcrumb(category?: string, categoryLabel?: string): BreadcrumbItem[] {
  const items: BreadcrumbItem[] = [
    { name: "首页", url: SITE_URL },
  ];
  if (category && categoryLabel) {
    items.push({ name: categoryLabel, url: `${SITE_URL}/category/${category}` });
  }
  return items;
}

// ============================================================
// FAQ Schema
// ============================================================
export function buildFAQSchema(faqs: FAQItem[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };
}

// 从 Markdown 自动提取 FAQ (匹配 "## 常见问题" 下的 Q&A)
export function extractFAQs(markdown: string): FAQItem[] {
  const faqs: FAQItem[] = [];
  // 定位 FAQ 节
  const faqSection = markdown.match(/##\s*常见问题[\s\S]*?(?=##\s|\n---|\n\*\[猫明之主)/);
  if (!faqSection) return faqs;

  // 匹配 Q&A 模式: **Q: ...** / **A: ...** 或 ### ...
  const qaPattern = /\*\*Q:\s*(.+?)\*\*\s*[\s\S]*?\*\*A:\s*([\s\S]+?)(?=\*\*Q:|\*\*$|###|$)/g;
  let match: RegExpExecArray | null;
  while ((match = qaPattern.exec(faqSection[0])) !== null) {
    faqs.push({
      question: match[1].trim(),
      answer: match[2].trim().slice(0, 300),
    });
  }

  // 降级: 匹配 ### 标题 + 段落
  if (faqs.length === 0) {
    const altPattern = /###\s+(.+?)\n([\s\S]+?)(?=###|$)/g;
    while ((match = altPattern.exec(faqSection[0])) !== null) {
      const q = match[1].trim();
      const a = match[2].trim().slice(0, 300);
      if (q.length > 5 && a.length > 10) {
        faqs.push({ question: q, answer: a });
      }
    }
  }

  return faqs.slice(0, 6);
}

// ============================================================
// HowTo Schema (用于教程类文章)
// ============================================================
export interface HowToStep {
  name: string;
  text: string;
  image?: string;
}

export function buildHowToSchema(
  name: string,
  description: string,
  steps: HowToStep[]
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name,
    description,
    step: steps.map((step, i) => ({
      "@type": "HowToStep",
      position: i + 1,
      name: step.name,
      text: step.text,
      ...(step.image ? { image: step.image } : {}),
    })),
  };
}

// ============================================================
// CollectionPage Schema (首页 / 分类页)
// ============================================================
export function buildCollectionPageSchema(
  name: string,
  description: string,
  articleUrls: string[]
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name,
    description,
    url: SITE_URL,
    hasPart: articleUrls.map((url) => ({
      "@type": "Article",
      url,
    })),
  };
}

// ============================================================
// 拼接所有 JSON-LD
// ============================================================
export function renderSchemas(schemas: Record<string, unknown>[]): string {
  return schemas
    .map((s) => `<script type="application/ld+json">${JSON.stringify(s)}</script>`)
    .join("\n");
}
