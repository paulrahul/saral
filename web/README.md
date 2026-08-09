# Saral Web

Static Astro site for Saral articles.

## Content publishing

The agent writes raw drafts and approvals to `../llm/generated/`, then exports approved Markdown to `src/content/articles/`. Commit those changes with a message beginning `content(publish):` to trigger the deployment workflow.

## Commands

```bash
npm run dev
npm run build
```

Set `SITE_URL` in the deployment environment before publishing so canonical social-preview URLs use the real domain.
