"""The small Gradio presentation layer for Saral's experimental chatbot."""

from __future__ import annotations

from html import escape
from typing import Protocol

import gradio as gr

from .rag import RagResult, RagService


SARAL_CSS = """
:root {
  color-scheme: light;
  --saral-paper: #dce5dc;
  --saral-surface: #f2efe3;
  --saral-surface-raised: #faf6e9;
  --saral-chat-surface: #e8eee8;
  --saral-ink: #273a31;
  --saral-heading: #193027;
  --saral-muted: #52665c;
  --saral-line: #758a7e;
  --saral-green: #2f7559;
  --saral-green-dark: #1e6047;
  --saral-green-soft: #cfe0d5;
  --saral-yellow-soft: #ead9a5;
  --saral-on-accent: #fffdf7;
  --saral-focus: #9c3e00;
  --body-background-fill: var(--saral-paper);
  --background-fill-primary: var(--saral-surface);
  --background-fill-secondary: var(--saral-green-soft);
  --block-background-fill: var(--saral-surface);
  --block-border-color: var(--saral-line);
  --border-color-primary: var(--saral-line);
  --border-color-accent: var(--saral-green);
  --body-text-color: var(--saral-ink);
  --body-text-color-subdued: var(--saral-muted);
  --block-label-text-color: var(--saral-muted);
  --input-background-fill: var(--saral-surface);
  --input-border-color: var(--saral-line);
  --button-secondary-background-fill: var(--saral-surface);
  --button-secondary-text-color: var(--saral-green-dark);
  --color-accent: var(--saral-green);
  --link-text-color: var(--saral-green-dark);
}

.gradio-container,
[class*="gradio-container-"] {
  color-scheme: light !important;
  --body-background-fill: var(--saral-paper) !important;
  --background-fill-primary: var(--saral-surface) !important;
  --background-fill-secondary: var(--saral-green-soft) !important;
  --block-background-fill: var(--saral-surface) !important;
  --block-border-color: var(--saral-line) !important;
  --block-label-text-color: var(--saral-green-dark) !important;
  --block-title-text-color: var(--saral-green-dark) !important;
  --block-title-background-fill: var(--saral-surface-raised) !important;
  --border-color-primary: var(--saral-line) !important;
  --border-color-accent: var(--saral-green) !important;
  --body-text-color: var(--saral-ink) !important;
  --body-text-color-subdued: var(--saral-muted) !important;
  --input-background-fill: var(--saral-surface-raised) !important;
  --input-border-color: var(--saral-line) !important;
  --button-secondary-background-fill: var(--saral-surface) !important;
  --button-secondary-text-color: var(--saral-green-dark) !important;
  --color-accent: var(--saral-green) !important;
  --link-text-color: var(--saral-green-dark) !important;
}

body, .gradio-container {
  background: var(--saral-paper) !important;
  color: var(--saral-ink) !important;
  font-family: Arial, Helvetica, sans-serif !important;
}

.gradio-container {
  max-width: 920px !important;
  margin-inline: auto !important;
  padding: clamp(14px, 3vw, 30px) !important;
}

#saral-chat-shell {
  gap: 16px !important;
}

.saral-chat-header {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 18px 20px;
  border: 2px solid var(--saral-line);
  border-radius: 12px;
  background: var(--saral-surface);
  box-shadow: 0 5px 16px rgba(25, 48, 39, .12);
}

.saral-chat-header img {
  display: block;
  width: 154px;
  height: auto;
}

.saral-chat-header h1 {
  margin: 0;
  color: var(--saral-heading);
  font-size: clamp(1.45rem, 4vw, 2rem);
  font-weight: 650;
  line-height: 1.15;
}

.saral-chat-header p {
  margin: 6px 0 0;
  color: var(--saral-muted);
  font-size: 1rem;
}

.saral-scope-note {
  margin-top: 14px;
  padding: 14px 17px;
  border: 1px solid #9cb3a5;
  border-left: 6px solid var(--saral-green);
  border-radius: 0 8px 8px 0;
  background: var(--saral-green-soft);
  color: var(--saral-ink);
  line-height: 1.5;
}

.saral-scope-note strong {
  color: var(--saral-green-dark);
  font-weight: 650;
}

#saral-chatbot {
  overflow: hidden;
  border: 2px solid var(--saral-line) !important;
  border-radius: 12px !important;
  background: var(--saral-chat-surface) !important;
  box-shadow: 0 6px 18px rgba(25, 48, 39, .14) !important;
}

#saral-chatbot > div,
#saral-chatbot .bubble-wrap {
  background: var(--saral-chat-surface) !important;
}

#saral-chatbot .message-wrap .message,
#saral-chatbot .message {
  color: var(--saral-ink) !important;
  font-size: 1rem !important;
  line-height: 1.5 !important;
}

#saral-chatbot .prose,
#saral-chatbot .prose :not(a) {
  color: var(--saral-ink) !important;
}

#saral-chatbot .pending,
#saral-chatbot [data-testid="status-tracker"] {
  background: var(--saral-green-soft) !important;
  color: var(--saral-ink) !important;
}

#saral-chatbot .bot,
#saral-chatbot [data-testid="bot"] {
  border: 1px solid #9fb7a8 !important;
  background: #d2e3d7 !important;
}

#saral-chatbot .user,
#saral-chatbot [data-testid="user"] {
  border: 1px solid #bda968 !important;
  background: var(--saral-yellow-soft) !important;
}

#saral-question {
  padding: 4px !important;
  border: 2px solid var(--saral-line) !important;
  border-radius: 10px !important;
  background: var(--saral-surface-raised) !important;
  box-shadow: 0 3px 10px rgba(25, 48, 39, .1) !important;
  color: var(--saral-green-soft) !important;
}

#saral-question label,
#saral-question .block-label,
#saral-question .label-wrap,
#saral-question .label-wrap span,
#saral-question > span,
#saral-question span.has-info {
  color: var(--saral-green-dark) !important;
  font-weight: 650 !important;
}

#saral-question textarea {
  min-height: 52px !important;
  border-color: transparent !important;
  border-radius: 8px !important;
  background: var(--saral-surface-raised) !important;
  color: var(--saral-heading) !important;
  font-size: 1rem !important;
}

#saral-question textarea:focus {
  border-color: var(--saral-focus) !important;
  box-shadow: 0 0 0 2px rgba(156, 62, 0, .16) !important;
}

#saral-ask-button {
  align-self: flex-end !important;
  min-height: 52px !important;
  border: 1px solid var(--saral-green-dark) !important;
  border-radius: 8px !important;
  background: var(--saral-green-dark) !important;
  color: var(--saral-on-accent) !important;
  font-size: 1rem !important;
  font-weight: 650 !important;
}

#saral-ask-button:hover {
  background: var(--saral-green) !important;
}

#saral-question-row {
  align-items: flex-end !important;
}

#saral-clear-button {
  min-height: 44px !important;
  border: 2px solid var(--saral-line) !important;
  border-radius: 8px !important;
  background: var(--saral-surface) !important;
  color: var(--saral-green-dark) !important;
  font-weight: 600 !important;
}

#saral-clear-button:hover {
  border-color: var(--saral-green) !important;
  background: var(--saral-green-soft) !important;
}

.saral-chat-caution {
  margin: 0;
  color: var(--saral-muted);
  font-size: .9rem;
  text-align: center;
}

.saral-chat-caution + .saral-chat-caution {
  margin-top: 6px;
}

.saral-chat-caution a,
#saral-chatbot a {
  color: var(--saral-green-dark) !important;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 4px;
}

.saral-chat-caution a:hover,
#saral-chatbot a:hover {
  color: var(--saral-heading) !important;
  text-decoration-thickness: 2px;
}

.saral-chat-caution a:focus-visible,
#saral-chatbot a:focus-visible {
  border-radius: 3px;
  outline: 3px solid var(--saral-focus);
  outline-offset: 3px;
}

.gradio-container footer {
  display: none !important;
}

@media (max-width: 620px) {
  .gradio-container {
    padding: 10px !important;
  }

  .saral-chat-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
    padding: 15px;
  }

  .saral-chat-header img {
    width: 126px;
  }
}
"""

MAX_HISTORY_MESSAGES = 10


class AnswerGenerator(Protocol):
    async def generate(self, question: str, chunks): ...


def _sources_markdown(result: RagResult) -> str:
    if not result.sources:
        return ""
    lines = ["\n\n**Related Saral lessons**"]
    seen_urls: set[str] = set()
    for source in result.sources:
        if source.article_url not in seen_urls:
            lines.append(f"- [{source.article_title}]({source.article_url})")
            seen_urls.add(source.article_url)
    return "\n".join(lines)


def create_ui(service: RagService, generator: AnswerGenerator, *, logo_url: str) -> gr.Blocks:
    """Create a framework-owned chat interface over the shared service instance."""

    async def respond(message: str, history: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        message = message.strip()
        if not message:
            return "", history
        result = await service.ask(message, generator, limit=3)
        assistant_message = (result.answer or "I could not prepare an answer.") + _sources_markdown(result)
        updated_history = [
            *history,
            {"role": "user", "content": message},
            {"role": "assistant", "content": assistant_message},
        ]
        return "", updated_history[-MAX_HISTORY_MESSAGES:]

    safe_logo_url = escape(logo_url, quote=True)
    with gr.Blocks(
        title="Ask Saral",
        elem_id="saral-chat-shell",
        analytics_enabled=False,
    ) as interface:
        gr.HTML(
            f"""
            <header class="saral-chat-header">
              <img src="{safe_logo_url}" alt="Saral" width="640" height="181">
              <div>
                <!--h1>Ask Saral</h1-->
                <p>Technology made simple, so no one is left behind.</p>
              </div>
            </header>
            <div class="saral-scope-note" role="note">
              <strong>What this chatbot knows:</strong>
              It can answer only questions covered by lessons published on Saral.
              It cannot answer general questions outside Saral's content.
              Conversations are state-less i.e. conversational history is not
              remembered by the system.
            </div>
            """
        )
        chatbot = gr.Chatbot(
            height=430,
            label="Conversation",
            placeholder="Ask a question about any content published on Saral.",
            elem_id="saral-chatbot",
        )
        with gr.Row(elem_id="saral-question-row"):
            message = gr.Textbox(
                label="Your question",
                placeholder="For example: How can I stay safe when using AI?",
                scale=5,
                elem_id="saral-question",
            )
            submit = gr.Button("Ask Saral", variant="primary", scale=1, elem_id="saral-ask-button")
        clear = gr.Button("Clear conversation", elem_id="saral-clear-button")
        gr.HTML(
            '<p class="saral-chat-caution">Experimental and English-only. '
            "Please do not share personal or sensitive information.</p>"
            '<p class="saral-chat-caution">'
            '<a href="https://paulrahul.github.io/#contact">'
            "Contact the creator of this site</a></p>"
        )

        submit.click(respond, inputs=[message, chatbot], outputs=[message, chatbot], queue=False)
        message.submit(respond, inputs=[message, chatbot], outputs=[message, chatbot], queue=False)
        clear.click(lambda: ("", []), outputs=[message, chatbot], queue=False)
    return interface
