import type { CollectionEntry } from "astro:content";

export const PAGE_SIZE = 6;

export function articleSlug(article: CollectionEntry<"articles">) {
  return article.id.replace(/\.md$/, "");
}

export function sortArticles(articles: CollectionEntry<"articles">[]) {
  return articles.sort((a, b) => b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf());
}
