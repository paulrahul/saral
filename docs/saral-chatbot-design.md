# Saral Experimental RAG Chatbot

## Purpose

Saral's English-only experimental chatbot answers questions from published Saral lessons. It is a learning and showcase feature, not a critical service.

The first version is deliberately small:

- Stateless answers: conversation history is displayed only in the browser and is not sent to the answer model.
- No agent framework, tool selection, uploads, or vector database.
- Precomputed document embeddings with exact local cosine retrieval.
- One low-cost OpenRouter answer call only when retrieval is relevant.
- Links to the source Saral lessons in each answer.

## Architecture

```text
Local article-generation workflow
├── exports English Markdown to web/src/content/articles/
└── runs rag.scripts.ingest
        ├── creates chunks.json
        ├── creates embeddings.npy through OpenRouter Embeddings
        └── writes index-manifest.json
                 │
                 ▼
GitHub repository
├── Saral Astro site
└── RAG application and generated index artifacts
                 │
                 ▼
Vercel project: Saral Chat (Root Directory: rag)
├── FastAPI POST /ask
├── Gradio interface at /chat
├── OpenRouter query embedding
├── exact cosine retrieval against the bundled index
└── OpenRouter answer generation
```

The main Saral website is an independent Vercel project. Its English navigation links to the chatbot at `https://saral-chatbot.vercel.app/chat/`.

## Source Structure

```text
rag/
├── index.py                 # Vercel ASGI entrypoint
├── app/
│   ├── embeddings.py         # OpenRouter document/query embeddings
│   ├── main.py               # FastAPI and mounted Gradio app
│   ├── ui.py                 # Experimental Gradio interface
│   ├── rag.py                # Interface-independent RAG service
│   ├── retrieval.py          # Exact cosine retrieval
│   └── llm.py                # OpenRouter answer generation
├── scripts/
│   └── ingest.py             # Local ingestion entrypoint
├── data/
│   ├── chunks.json
│   ├── embeddings.npy
│   └── index-manifest.json
├── requirements.txt
├── .python-version
└── .vercelignore
```

`rag/data` is generated, reviewed locally, and committed with the article changes. It is bundled read-only into the Vercel Function. Vercel does not create embeddings during deployment.

## Ingestion

Run the local ingestion command after English article Markdown changes:

```bash
python -m rag.scripts.ingest
```

It reads canonical English articles, creates heading-aware chunks, and batches document-embedding requests through OpenRouter. The default embedding model is `openai/text-embedding-3-small`; the model identifier and vector dimensions are recorded in `index-manifest.json`.

The runtime always uses the model recorded in the manifest for question embeddings. A document index and runtime query embedding therefore cannot accidentally use different models.

`--skip-embeddings` is useful only for inspecting chunks. An index created that way cannot answer semantic retrieval questions.

## Runtime Request Flow

1. The user submits a bounded English question through Gradio or `POST /ask`.
2. Deterministic topic and cost questions are answered directly from indexed metadata when possible.
3. Other questions are embedded through OpenRouter using the model in the manifest.
4. The service performs exact cosine similarity against the bundled vectors and selects at most three relevant chunks.
5. Below-threshold retrieval is refused without an answer-generation call.
6. Otherwise, one fixed low-cost OpenRouter chat model answers only from the selected excerpts.
7. The response includes source lesson links.

## Vercel Deployment

Create a separate Vercel project from the same repository with:

```text
Root Directory: rag
Python version: 3.12
Entrypoint: index.py
```

Required Vercel environment variables:

```dotenv
OPENROUTER_API_KEY=...
SARAL_CHAT_MODEL=deepseek/deepseek-v4-flash-0731
SARAL_ALLOWED_ORIGINS=https://saralai-seven.vercel.app
SARAL_LOGO_URL=https://saralai-seven.vercel.app/saral-logo.png
GRADIO_ANALYTICS_ENABLED=false
```

For retrieval-only smoke testing, set `SARAL_CHAT_RETRIEVAL_ONLY=true`. This avoids the answer-generation call but still creates a small OpenRouter embedding request for non-deterministic questions.

Validate a deployment at:

```text
/health
/chat/
```

## Automated ingestion

Normal article generation refreshes the RAG index after the final English
Markdown and its generation-cost metadata have been written. The article,
image, translations, and all three `rag/data` artifacts are committed and
pushed together. Both Vercel projects therefore deploy from the same source
revision.

Ingestion is incremental. It compares the exact text sent to the embedding
model with the existing index, reuses matching vectors, embeds only new or
changed chunks, and removes obsolete chunks. Changing the embedding model
automatically recreates every vector. A manual full rebuild remains available:

```bash
python -m rag.scripts.ingest --full-rebuild
```

`tools/rerun_topics.py` defers ingestion in its child article processes and
refreshes the index once after the complete rerun batch succeeds. This also
applies to Markdown or cost-only reruns, since generation-cost chunks can
change even when lesson text does not.

Every ingestion writes a separate report under
`llm/generated/cost-reports/ingestion/`. The report records embedding calls,
OpenRouter usage and cost, wall time, and the numbers of embedded, reused, and
removed chunks. Rerun batch reports link this ingestion report and include its
cost in the batch total. Ingestion costs are kept separate from article
`generationCost` frontmatter so adding the cost cannot invalidate the index
that produced it.

If ingestion fails, article publication stops and the previous deployed index
remains active. The locally generated article caches can be reused on the next
run.

## Remaining Work

### Low priority: abuse protection

- Set a low OpenRouter key spend limit.
- Enforce per-IP request rate limits using a suitable shared store or Vercel protection feature.
- Keep question and answer limits small.
- Monitor Vercel function usage and OpenRouter activity.
- Keep OpenRouter credentials server-side only.

## Completion Criteria

- The index contains every canonical English article.
- Relevant questions retrieve appropriate lesson excerpts and working links.
- Clearly unrelated questions are declined without an answer-generation call.
- The chatbot operates independently of the main Saral site deployment.
- Article changes and their regenerated index artifacts are versioned together.
