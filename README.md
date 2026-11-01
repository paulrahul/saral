# Saral

Saral is a multilingual learning site that explains everyday technology and AI
in simple language. It is designed primarily for elderly people, people with
disabilities, and readers who are not confident with technology.

Live site: https://saralai-seven.vercel.app

Built with Python, the OpenAI Agents SDK, OpenRouter, FastAPI, and Astro.

The repository contains four connected parts:

- an AI-assisted article-generation pipeline;
- the static Astro website that publishes the lessons;
- a small retrieval-augmented generation (RAG) chatbot grounded in the English
  lessons; and
- maintenance tools for safely rebuilding existing content.

## Repository structure

| Path                          | Purpose                                                                                                               |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `llm/`                      | Generates topics, articles, tags, illustrations, Hindi and Bengali translations, cost reports, and exported Markdown. |
| `rag/`                      | Builds the English lesson search index and hosts the FastAPI chatbot and its custom web interface.                    |
| `web/`                      | The Astro website, article Markdown, localized interface strings, images, and other public assets.                    |
| `tools/`                    | Maintenance commands, currently including the controlled `rerun_topics` workflow.                                   |
| `docs/`                     | Design and operational documentation shared across packages.                                                          |
| `tests/` and `rag/tests/` | Automated tests for the generation/export and RAG code respectively.                                                  |

### `llm/`: article generation

`llm.main.EasyTutorAgent` coordinates the content pipeline. Its main areas are:

- `configuration/`: active and alternative model mappings in `models.json`;
- `generator/`: topic, article, tag, and illustration generation;
- `evaluator/`: topic, content, and tag evaluation;
- `translator/`: parallel translation into the configured lesson languages;
- `publishing/`: Markdown export plus bounded Git commit, push, and deployment
  verification;
- `observability/`: per-stage OpenRouter cost and latency reports;
- `generated/`: local JSON caches and cost reports. This directory is ignored
  by Git; and
- `ingestion.py`: refreshes the RAG index after an article is generated.

The model choices for every generation stage live in
`llm/configuration/models.json`. Each entry maps a readable model name to its
OpenRouter model ID.

### `rag/`: retrieval and chatbot

The RAG package contains:

- `scripts/ingest.py`: reads English article Markdown, splits it into chunks,
  creates embeddings through OpenRouter, and writes the retrieval artifacts;
- `data/`: `chunks.json`, `embeddings.npy`, and `index-manifest.json`;
- `app/retrieval.py` and `app/rag.py`: similarity search and structured
  responses for supported questions;
- `app/llm.py`: source-bound answer generation through OpenRouter;
- `app/main.py`: the FastAPI application and `/ask` API; and
- `public/`: the custom HTML, CSS, and JavaScript chat interface.

Normal article generation and `rerun_topics` refresh the RAG artifacts
automatically. The ingestion command is still useful for inspecting or
rebuilding them manually.

### `web/`: public website

The Astro project reads lessons from `web/src/content/articles/`:

- English files are stored directly in `articles/`;
- Hindi files are stored in `articles/hi/`; and
- Bengali files are stored in `articles/bn/`.

Article illustrations and site branding live under `web/public/`. Interface
translations are centralized in `web/src/lib/i18n.ts`. See
[`web/docs/adding-a-language.md`](web/docs/adding-a-language.md) before adding a
new language.

### `tools/`: maintenance workflows

`tools/rerun_topics.py` rebuilds previously used topics while preserving their
queue state. It creates a restorable local backup before changing files,
refreshes the RAG index once after the selected topics succeed, and publishes
only when `--publish` is explicitly supplied.

## How the pieces fit together

```text
topic queue
  -> generation and evaluation
  -> approved English lesson + tags + illustration
  -> Hindi and Bengali translations
  -> Markdown and images in web/
  -> chunks and embeddings in rag/data/
  -> Astro website and Saral chatbot
```

## Local setup

Run Python commands from the repository root. Python 3.12 is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r rag/requirements.txt
```

Create a root `.env` file for local AI operations:

```dotenv
OPENROUTER_API_KEY=your-openrouter-key
OPENAI_API_KEY=your-openai-key-for-agent-tracing
SARAL_SITE_URL=https://saralai-seven.vercel.app
```

`OPENROUTER_API_KEY` is used for generation, image generation, embeddings, chat
answers, and cost reconciliation. `OPENAI_API_KEY` is used by the Agents SDK for
tracing. Do not commit `.env`.

For the website, use Node.js 20.19 or another version allowed by
`web/package.json`:

```bash
cd web
npm ci
```

## Run the content agent - generate topics or articles

Generate or refresh the ranked topic queue:

```bash
python -m llm.main --generate_subtopic
```

The short form is:

```bash
python -m llm.main -gt
```

Generate one article from the next ranked cached topic without committing or
pushing it:

```bash
python -m llm.main --no-publish
```

This performs content generation/evaluation, tags, image generation,
translations, Markdown export, cost metering, and RAG ingestion. Because it is
a local run, the topic remains queued so it can be run again.

Generate and publish the next article:

```bash
python -m llm.main
```

**Important:** publishing is the default. This command creates a bounded
`content(publish): ...` Git commit, pushes the current branch, waits for the
configured site to contain the new latest article, and then marks the topic as
used locally. Use `--no-publish` while developing or checking a generation.

If there are no ranked topics left, generate a new topic batch with `-gt`
before running the article pipeline again.

## Rerun existing topics

Always inspect the plan first:

```bash
python tools/rerun_topics.py --dry-run
```

Without `--topic`, the tool selects **all used topics**. Without a stage flag,
it runs the normal article pipeline using every available cache.

Common examples:

```bash
# Rebuild one article's Markdown from cached data
python tools/rerun_topics.py --topic "What is AI?" --markdown

# Regenerate all supported translations for one topic
python tools/rerun_topics.py --topic "What is AI?" --translations

# Regenerate an image and refresh the article image references
python tools/rerun_topics.py --topic "What is AI?" --images

# Recompute public cost metadata from existing reports; makes no model calls
python tools/rerun_topics.py --topic "What is AI?" --costs

# Regenerate every supported stage for one topic
python tools/rerun_topics.py --topic "What is AI?" --all
```

The main stage flags are:

| Flag               | Effect                                                          |
| ------------------ | --------------------------------------------------------------- |
| `--content`      | Regenerate content and invalidate all downstream artifacts.     |
| `--evaluation`   | Re-evaluate content and regenerate downstream artifacts.        |
| `--images`       | Regenerate illustrations and rebuild their Markdown references. |
| `--translations` | Regenerate translated article Markdown.                         |
| `--markdown`     | Rebuild Markdown from caches without translating again.         |
| `--costs`        | Recompute Markdown cost metadata without model calls.           |
| `--all`          | Regenerate every supported stage.                               |

Add `--publish` only when the final results should be committed and pushed. Add
`--yes` for a non-interactive run. To restore files from the most recent local
rerun backup, use:

```bash
python tools/rerun_topics.py --restore
```

Restoring a backup cannot undo a commit that has already been pushed.

## Run the website

From `web/`:

```bash
npm run dev
```

The local site is normally available at [http://localhost:4321/](http://localhost:4321/). Other useful
commands are:

```bash
npm run build
npm run preview
```

Set `SITE_URL` to the public website origin in the deployment environment so
canonical links and Open Graph preview URLs are generated correctly.

## Build or test the RAG index locally

Rebuild chunks and reuse unchanged embeddings where possible:

```bash
python -m rag.scripts.ingest
```

Generate only human-readable chunks and the manifest, without making embedding
requests:

```bash
python -m rag.scripts.ingest --skip-embeddings
```

Force every chunk to receive a new embedding:

```bash
python -m rag.scripts.ingest --full-rebuild
```

Search the generated index without asking an answer model:

```bash
python -m rag.app.rag "How can I protect my privacy when using AI?"
```

Generate a source-grounded answer as well:

```bash
python -m rag.app.rag \
  "How can I protect my privacy when using AI?" \
  --answer \
  --model "z-ai/glm-5.3-flash"
```

Run the FastAPI service and chat page locally:

```bash
uvicorn rag.app.main:app --reload --port 8000
```

Then open [http://localhost:8000/chat/](http://localhost:8000/chat/). For retrieval-only server testing, set
`SARAL_CHAT_RETRIEVAL_ONLY=true`; semantic questions can still require a small
OpenRouter query-embedding request.

Chatbot architecture, configuration, and deployment details are documented in
[`docs/saral-chatbot-design.md`](docs/saral-chatbot-design.md).

## Roadmap

Planned work is listed in [`ROADMAP.md`](ROADMAP.md).

## License

Released under the [MIT License](LICENSE).
