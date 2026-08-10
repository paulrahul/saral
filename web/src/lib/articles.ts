import type { CollectionEntry } from "astro:content";

export const PAGE_SIZE = 6;
export const SUPPORTED_LANGUAGES = ["en", "hi", "bn"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

export function articleSlug(article: CollectionEntry<"articles">) {
  return article.id.replace(/^(?:en|hi|bn)\//, "").replace(/\.md$/, "");
}

export function articlesForLanguage(articles: CollectionEntry<"articles">[], language: Language) {
  return articles.filter((article) => article.data.language === language);
}

export function languagePrefix(language: Language) {
  return language === "en" ? "" : `/${language}`;
}

export function articleUrl(article: CollectionEntry<"articles">) {
  return `${languagePrefix(article.data.language)}/articles/${articleSlug(article)}/`;
}

export function tagUrl(tag: string, language: Language) {
  return `${languagePrefix(language)}/tags/${encodeURIComponent(tag)}/`;
}

export function sortArticles(articles: CollectionEntry<"articles">[]) {
  return articles.sort((a, b) => b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf());
}
