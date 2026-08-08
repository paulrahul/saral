# EasyTutor Web

Static Astro site for EasyTutor articles.

## Content publishing

The agent writes raw drafts to `../llm/content.json`. Choose one draft and its metadata in `../llm/approved_content.json`, then run:

```bash
python ../scripts/export_articles.py
```

The exporter writes Markdown to `src/content/articles/`. Commit those changes with a message beginning `content(publish):` to trigger the deployment workflow.

## Commands

```bash
npm run dev
npm run build
```

Set `SITE_URL` in the deployment environment before publishing so canonical social-preview URLs use the real domain.
