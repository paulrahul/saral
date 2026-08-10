import { defineCollection, z } from "astro:content";

const articles = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    publishedAt: z.coerce.date(),
    language: z.enum(["en", "hi", "bn"]).default("en"),
    translationOf: z.string().optional(),
    tags: z.array(z.string()),
    image: z.string(),
    imageAlt: z.string(),
    socialImage: z.string().optional(),
    sourceModel: z.string(),
  }),
});

export const collections = { articles };
