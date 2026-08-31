/* Display-only conversation state. Each request sends just the current question. */
(() => {
  "use strict";

  const form = document.querySelector("#chat-form");
  const question = document.querySelector("#question");
  const send = document.querySelector("#send-button");
  const clear = document.querySelector("#clear-button");
  const messages = document.querySelector("#messages");
  const emptyState = document.querySelector("#empty-state");
  const status = document.querySelector("#status");
  const errorMessage = document.querySelector("#error-message");
  const MAX_MESSAGES = 10;
  let activeRequest = null;

  function safeUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const url = new URL(value, window.location.origin);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function secureLink(link, url) {
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }

  function renderAnswer(body, text) {
    // Fall back to text if either library is unavailable; never render raw HTML.
    if (!window.marked || !window.DOMPurify?.isSupported) {
      body.classList.add("plain-text");
      body.textContent = text;
      return;
    }
    try {
      const html = window.marked.parse(text, { async: false, gfm: true, breaks: true });
      const fragment = window.DOMPurify.sanitize(html, {
        RETURN_DOM_FRAGMENT: true,
        ALLOWED_TAGS: ["p", "br", "strong", "em", "del", "ul", "ol", "li", "a", "code", "pre", "blockquote", "h2", "h3", "h4", "hr", "table", "thead", "tbody", "tr", "th", "td"],
        ALLOWED_ATTR: ["href", "title", "start"],
        ALLOW_DATA_ATTR: false,
        ALLOW_ARIA_ATTR: false,
      });
      for (const link of fragment.querySelectorAll("a")) {
        const url = safeUrl(link.getAttribute("href"));
        if (url) secureLink(link, url);
        else link.replaceWith(document.createTextNode(link.textContent));
      }
      body.append(fragment);
    } catch {
      body.classList.add("plain-text");
      body.textContent = text;
    }
  }

  function appendSources(message, sources) {
    const list = document.createElement("ul");
    const seen = new Set();
    for (const source of sources) {
      if (!source || typeof source.title !== "string") continue;
      const url = safeUrl(source.url);
      if (!url || seen.has(url)) continue;
      seen.add(url);
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.textContent = source.title;
      secureLink(link, url);
      item.append(link);
      list.append(item);
    }
    if (!list.children.length) return;
    const section = document.createElement("div");
    section.className = "sources";
    const label = document.createElement("p");
    label.textContent = "Related Saral lessons";
    section.append(label, list);
    message.append(section);
  }

  function addMessage(role, text, sources = []) {
    const followLatest = role === "user" || messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
    emptyState.remove();
    const message = document.createElement("article");
    message.className = `message message-${role}`;
    const label = document.createElement("p");
    label.className = "message-label";
    label.textContent = role === "user" ? "You" : "Saral";
    const body = document.createElement("div");
    body.className = "message-body";
    if (role === "user") body.textContent = text;
    else renderAnswer(body, text);
    message.append(label, body);
    if (role === "assistant") appendSources(message, sources);
    messages.append(message);
    while (messages.children.length > MAX_MESSAGES) messages.firstElementChild.remove();
    if (followLatest) {
      messages.scrollTop += message.getBoundingClientRect().top - messages.getBoundingClientRect().top - 12;
    }
  }

  function syncControls() {
    const busy = activeRequest !== null;
    status.classList.toggle("is-busy", busy);
    question.readOnly = busy;
    send.disabled = busy || !question.value.trim();
    send.textContent = busy ? "Please wait…" : "Ask Saral";
    clear.disabled = !busy && !question.value && !messages.querySelector(".message");
  }

  function showError(text) {
    errorMessage.textContent = text;
    errorMessage.hidden = false;
  }

  question.addEventListener("input", syncControls);
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = question.value.trim();
    if (activeRequest || !text) return;
    if (text.length > 1000) {
      showError("Please keep your question to 1,000 characters or fewer.");
      return;
    }
    errorMessage.hidden = true;
    const request = { controller: new AbortController(), timedOut: false };
    activeRequest = request;
    question.value = "";
    addMessage("user", text);
    syncControls();
    status.textContent = "Looking through Saral's lessons…";
    const timeout = window.setTimeout(() => {
      request.timedOut = true;
      request.controller.abort();
    }, 90000);

    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
        signal: request.controller.signal,
      });
      if (!response.ok) {
        const errors = {
          413: "Your question is too long. Please shorten it and try again.",
          422: "Please enter a question of up to 1,000 characters.",
          429: "Saral is receiving too many questions. Please wait a moment before trying again.",
        };
        throw new Error(errors[response.status] || "Saral could not prepare an answer right now. Please try again later.");
      }
      const result = await response.json();
      if (typeof result.answer !== "string" || !result.answer.trim() || !Array.isArray(result.sources)) {
        throw new Error("Saral returned an unexpected response. Please try again later.");
      }
      if (activeRequest !== request) return;
      addMessage("assistant", result.answer, result.sources);
      status.textContent = "Answer ready.";
    } catch (error) {
      if (activeRequest !== request) return;
      const detail = request.timedOut
        ? "The response took too long. You can try again; the previous request may still finish on the server."
        : error instanceof TypeError
          ? "Could not connect to Saral. Check your connection and try again."
          : error.message || "Something went wrong. Please try again later.";
      showError(detail);
      question.value = text;
      status.textContent = "No answer received.";
    } finally {
      window.clearTimeout(timeout);
      if (activeRequest === request) {
        activeRequest = null;
        syncControls();
        if (document.activeElement === send) question.focus();
      }
    }
  });

  clear.addEventListener("click", () => {
    const wasPending = activeRequest !== null;
    activeRequest?.controller.abort();
    activeRequest = null;
    messages.replaceChildren(emptyState);
    question.value = "";
    errorMessage.hidden = true;
    status.textContent = wasPending
      ? "Conversation cleared. The previous request may still finish on the server."
      : "Conversation cleared.";
    syncControls();
    question.focus();
  });

  question.disabled = false;
  syncControls();

  // Only public branding settings are read. The static defaults keep the page
  // usable if this optional configuration request fails.
  fetch("/chat-config", { cache: "no-store" })
    .then((response) => response.ok ? response.json() : null)
    .then((config) => {
      if (!config) return;
      const siteUrl = safeUrl(config.siteUrl);
      const logoUrl = safeUrl(config.logoUrl);
      if (siteUrl) document.querySelector("#back-link").href = siteUrl;
      if (logoUrl) document.querySelector("#saral-logo").src = logoUrl;
    })
    .catch(() => {});
})();
