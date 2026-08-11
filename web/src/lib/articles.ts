import type { CollectionEntry } from "astro:content";
import { SUPPORTED_LANGUAGES, type Language } from "./i18n";

export const PAGE_SIZE = 6;
export { SUPPORTED_LANGUAGES, type Language } from "./i18n";

export function articleSlug(article: CollectionEntry<"articles">) {
  const languagePrefix = new RegExp(`^(?:${SUPPORTED_LANGUAGES.join("|")})/`);
  return article.id.replace(languagePrefix, "").replace(/\.md$/, "");
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

/**
 * Finds the equivalent tag in another language by matching translated articles.
 * Tags are display text, so their translated values cannot safely be reused in
 * a language-prefixed URL.
 */
export function translatedTag(
  articles: CollectionEntry<"articles">[],
  sourceLanguage: Language,
  tag: string,
  targetLanguage: Language,
) {
  if (sourceLanguage === targetLanguage) return tag;

  const sourceArticles = articlesForLanguage(articles, sourceLanguage)
    .filter((article) => article.data.tags.includes(tag));
  const targetArticles = articlesForLanguage(articles, targetLanguage);

  for (const sourceArticle of sourceArticles) {
    const tagIndex = sourceArticle.data.tags.indexOf(tag);
    const translationId = sourceArticle.data.translationOf ?? articleSlug(sourceArticle);
    const targetArticle = targetArticles.find(
      (article) => (article.data.translationOf ?? articleSlug(article)) === translationId,
    );
    const targetTag = targetArticle?.data.tags[tagIndex];
    if (targetTag) return targetTag;
  }

  return undefined;
}

export function sortArticles(articles: CollectionEntry<"articles">[]) {
  return articles.sort((a, b) => b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf());
}
