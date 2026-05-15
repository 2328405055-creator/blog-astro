// ============================================================
// lib/related.ts — 内链推荐算法 (Astro 适配版)
// 降级链: 预计算向量JSON > 同分类最新 > 标签匹配
// ============================================================

export interface PostEntry {
  slug: string;
  title: string;
  date: string;
  cat: string;
  sub?: string;
  excerpt?: string;
  tags?: string[];
}

let _cache: PostEntry[] = [];

export function setPostsCache(posts: PostEntry[]) {
  _cache = posts;
}

// ============================================================
// 1. 预计算向量检索 (从 data/embeddings.json 加载)
// ============================================================
let _embeddings: Record<string, number[]> | null = null;
let _embeddingsLoaded = false;

async function loadEmbeddings(): Promise<Record<string, number[]> | null> {
  if (_embeddingsLoaded) return _embeddings;
  _embeddingsLoaded = true;
  try {
    const res = await fetch('/data/embeddings.json');
    if (res.ok) {
      const data = await res.json();
      const articles = data.articles || {};
      _embeddings = {};
      for (const [slug, rec] of Object.entries(articles)) {
        _embeddings[slug] = (rec as any).embedding || [];
      }
      return _embeddings;
    }
  } catch { /* no embeddings file yet */ }
  return null;
}

function cosineSimilarity(a: number[], b: number[]): number {
  const minLen = Math.min(a.length, b.length);
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < minLen; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

async function getRelatedByEmbeddings(
  slug: string,
  k: number = 3
): Promise<(PostEntry & { similarity: number })[]> {
  const embeddings = await loadEmbeddings();
  if (!embeddings || !embeddings[slug]) return [];

  const targetEmb = embeddings[slug];
  const scored: { slug: string; similarity: number }[] = [];

  for (const [otherSlug, emb] of Object.entries(embeddings)) {
    if (otherSlug === slug) continue;
    const sim = cosineSimilarity(targetEmb, emb);
    if (sim > 0.5) scored.push({ slug: otherSlug, similarity: Math.round(sim * 1000) / 1000 });
  }

  scored.sort((a, b) => b.similarity - a.similarity);

  return scored.slice(0, k).map((r) => {
    const post = _cache.find((p) => p.slug === r.slug);
    return post ? { ...post, similarity: r.similarity } : null;
  }).filter(Boolean) as (PostEntry & { similarity: number })[];
}

// ============================================================
// 2. 同分类降级
// ============================================================
function getRelatedByCategory(currentSlug: string, cat: string, k: number = 3): PostEntry[] {
  return _cache
    .filter((p) => p.slug !== currentSlug && p.cat === cat)
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, k);
}

// ============================================================
// 3. 标签交集降级
// ============================================================
function getRelatedByTags(
  currentSlug: string,
  tags: string[],
  k: number = 3
): (PostEntry & { matchedTags: number })[] {
  if (!tags.length) return [];
  return _cache
    .filter((p) => p.slug !== currentSlug)
    .map((p) => ({
      ...p,
      matchedTags: (p.tags || []).filter((t) => tags.includes(t)).length,
    }))
    .filter((p) => p.matchedTags > 0)
    .sort((a, b) => b.matchedTags - a.matchedTags)
    .slice(0, k);
}

// ============================================================
// 4. 综合推荐 (三层降级)
// ============================================================
export async function getRelatedPosts(
  currentSlug: string,
  currentCat: string,
  tags: string[] = [],
  k: number = 3
): Promise<(PostEntry & { similarity?: number })[]> {
  // Layer 1: 预计算向量 (Python pipeline 生成 data/embeddings.json)
  const vecResults = await getRelatedByEmbeddings(currentSlug, k);
  if (vecResults.length >= k) return vecResults;

  // Layer 2: 同分类最新
  const existing = new Set(vecResults.map((r) => r.slug));
  const catResults = getRelatedByCategory(currentSlug, currentCat, k * 2)
    .filter((p) => !existing.has(p.slug));
  const combined = [...vecResults, ...catResults.slice(0, k - vecResults.length)];

  if (combined.length >= k) return combined;

  // Layer 3: 标签匹配
  const existing2 = new Set(combined.map((r) => r.slug));
  const tagResults = getRelatedByTags(currentSlug, tags, k)
    .filter((p) => !existing2.has(p.slug));

  return [...combined, ...tagResults].slice(0, k);
}
