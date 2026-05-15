// ============================================================
// lib/posts.ts — 文章数据加载
// SSG 构建时从文件系统读取, 运行时从 fetch
// ============================================================
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface Post {
  slug: string;
  title: string;
  date: string;
  lastmod?: string;
  excerpt: string;
  cat: string;
  sub: string;
  featured?: boolean;
  verified?: boolean;
  source: string;
  source_name: string;
  has_content?: boolean;
  word_count?: number;
  quality_score?: number;
  related_slugs?: string[];
  tags?: string[];
}

export interface PostWithBody extends Post {
  body: string;      // Markdown 原文
  headings: Heading[];
}

export interface Heading {
  depth: number;
  text: string;
  id: string;
}

// 缓存
let _cache: Post[] | null = null;

// ============================================================
// 加载所有文章
// ============================================================
function getProjectRoot(): string {
  // 从 src/lib/posts.ts 向上 2 级到项目根目录
  return join(import.meta.dirname, '..', '..');
}

export async function getAllPosts(): Promise<Post[]> {
  if (_cache) return _cache;

  try {
    const root = getProjectRoot();
    const jsonPath = join(root, 'public', 'posts', 'posts.json');
    const raw = readFileSync(jsonPath, 'utf-8');
    const posts: Post[] = JSON.parse(raw);
    posts.sort((a, b) => b.date.localeCompare(a.date));
    _cache = posts;
    return posts;
  } catch (e) {
    console.error('Failed to load posts.json:', e);
    return [];
  }
}

// ============================================================
// 按分类获取
// ============================================================
export async function getPostsByCat(cat: string): Promise<Post[]> {
  const posts = await getAllPosts();
  return posts.filter((p) => p.cat === cat);
}

// ============================================================
// 获取单篇文章 (含 Markdown 正文)
// ============================================================
export async function getPostBySlug(slug: string): Promise<PostWithBody | null> {
  const posts = await getAllPosts();
  const post = posts.find((p) => p.slug === slug);
  if (!post) return null;

  let body = '';
  try {
    const root = getProjectRoot();
    const mdPath = join(root, 'public', 'posts', `${slug}.md`);
    body = readFileSync(mdPath, 'utf-8');
  } catch {
    body = `# ${post.title}\n\n文章内容加载失败。`;
  }

  return {
    ...post,
    body,
    headings: extractHeadings(body),
  };
}

// ============================================================
// 提取 Markdown 标题
// ============================================================
export function extractHeadings(md: string): Heading[] {
  const headings: Heading[] = [];
  const regex = /^(#{2,3})\s+(.+)$/gm;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(md)) !== null) {
    const text = match[2].replace(/[#*`\[\]~]/g, '').trim();
    const id = text
      .toLowerCase()
      .replace(/[^\w一-鿿]+/g, '-')
      .replace(/-+$/g, '');
    headings.push({ depth: match[1].length, text, id });
  }
  return headings;
}

// ============================================================
// 分页
// ============================================================
export function paginatePosts(posts: Post[], page: number, perPage: number = 10) {
  const total = Math.ceil(posts.length / perPage);
  const start = (page - 1) * perPage;
  return {
    items: posts.slice(start, start + perPage),
    total,
    page,
    hasPrev: page > 1,
    hasNext: page < total,
  };
}

// ============================================================
// 分类映射
// ============================================================
export const CAT_LABELS: Record<string, { name: string; icon: string }> = {
  'cross-border': { name: '跨境教程', icon: '🌏' },
  fitness: { name: '每日健身', icon: '💪' },
  'ai-news': { name: 'AI学习', icon: '🤖' },
  'ozon-pick': { name: 'Ozon选品', icon: '🛒' },
};

export function getCatLabel(cat: string) {
  return CAT_LABELS[cat] || { name: cat, icon: '📄' };
}

// ============================================================
// 获取静态路径 (用于 [slug].astro)
// ============================================================
export async function getPostSlugs() {
  const posts = await getAllPosts();
  return posts.map((p) => ({ slug: p.slug }));
}

export async function getCatSlugs() {
  const posts = await getAllPosts();
  const cats = [...new Set(posts.map((p) => p.cat))];
  return cats.map((cat) => ({ cat }));
}

// ============================================================
// 清空缓存 (开发时)
// ============================================================
export function clearCache() {
  _cache = null;
}
