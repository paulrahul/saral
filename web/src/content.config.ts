import { defineCollection, z } from "astro:content";

const articles = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    publishedAt: z.coerce.date(),
    tags: z.array(z.string()),
    image: z.string(),
    imageAlt: z.string(),
    sourceModel: z.string(),
  }),
});

export const collections = { articles };
