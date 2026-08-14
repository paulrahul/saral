import { defineCollection, z } from "astro:content";
import { LANGUAGE_VALUES } from "./lib/i18n";

const generationCall = z.object({
  modelName: z.string(),
  model: z.string(),
  provider: z.string().optional(),
  requestWallTimeMs: z.number().int().nonnegative().optional(),
  costStatus: z.enum(["reported", "partial", "unavailable"]),
  costUsd: z.number().nonnegative().optional(),
  inputTokens: z.number().int().nonnegative().optional(),
  outputTokens: z.number().int().nonnegative().optional(),
  totalTokens: z.number().int().nonnegative().optional(),
  cachedTokens: z.number().int().nonnegative().optional(),
  reasoningTokens: z.number().int().nonnegative().optional(),
  latencyMs: z.number().int().nonnegative().optional(),
  generationTimeMs: z.number().int().nonnegative().optional(),
});

const generationStage = z.object({
  key: z.string(),
  status: z.enum(["completed", "cached", "skipped", "failed"]),
  wallTimeMs: z.number().int().nonnegative(),
  costUsd: z.number().nonnegative(),
  costStatus: z.enum(["reported", "partial"]),
  requestCount: z.number().int().nonnegative(),
  calls: z.array(generationCall),
});

const generationCost = z.object({
  totalUsd: z.number().nonnegative(),
  wallTimeMs: z.number().int().nonnegative(),
  requestCount: z.number().int().nonnegative(),
  costStatus: z.enum(["reported", "partial"]),
  stages: z.array(generationStage),
});

const articles = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    publishedAt: z.coerce.date(),
    language: z.enum(LANGUAGE_VALUES).default("en"),
    translationOf: z.string().optional(),
    tags: z.array(z.string()),
    image: z.string(),
    imageAlt: z.string(),
    imageWidth: z.number().int().positive().default(1200),
    imageHeight: z.number().int().positive().default(630),
    imageMediaType: z.enum(["image/png", "image/jpeg", "image/webp"]).optional(),
    socialImage: z.string().optional(),
    sourceModel: z.string(),
    generationCost: generationCost.optional(),
  }),
});

export const collections = { articles };
