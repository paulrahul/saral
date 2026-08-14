import type { CollectionEntry } from "astro:content";
import { articleSlug } from "./articles";
import { locale, type Language } from "./i18n";

export type GenerationCost = NonNullable<CollectionEntry<"articles">["data"]["generationCost"]>;
const USD_TO_INR = 95.31;

export function canonicalArticle(
  article: CollectionEntry<"articles">,
  articles: CollectionEntry<"articles">[],
) {
  if (article.data.language === "en") return article;
  const canonicalSlug = article.data.translationOf ?? articleSlug(article);
  return articles.find(
    (candidate) => candidate.data.language === "en" && articleSlug(candidate) === canonicalSlug,
  );
}

export function costForArticle(
  article: CollectionEntry<"articles">,
  articles: CollectionEntry<"articles">[],
): GenerationCost | undefined {
  return canonicalArticle(article, articles)?.data.generationCost;
}

export function formatUsd(cost: number, language: Language) {
  const currency = language === "en" ? "USD" : "INR";
  const convertedCost = currency === "INR" ? cost * USD_TO_INR : cost;
  return new Intl.NumberFormat(locale(language).dateLocale, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(convertedCost);
}

export function formatDuration(milliseconds: number, language: Language) {
  const seconds = Math.round(milliseconds / 1000);
  if (seconds < 60) return `${seconds} ${locale(language).ui.seconds}`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder
    ? `${minutes} ${locale(language).ui.minutes} ${remainder} ${locale(language).ui.seconds}`
    : `${minutes} ${locale(language).ui.minutes}`;
}
