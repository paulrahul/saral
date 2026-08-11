# Saral Web

Static Astro site for Saral articles.

## Content publishing

The agent writes raw drafts and approvals to `../llm/generated/`, then exports approved Markdown to `src/content/articles/`. Commit those changes with a message beginning `content(publish):` to trigger the deployment workflow.

## Languages

See [Adding a language](docs/adding-a-language.md) for the complete UI and
lesson-translation workflow, including a copyable model prompt and Tamil
example.

## Commands

```bash
npm run dev
npm run build
```

Set `SITE_URL` in the deployment environment before publishing so canonical social-preview URLs use the real domain.
