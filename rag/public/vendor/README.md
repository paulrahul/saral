# Bundled Markdown libraries

These browser distributions are pinned and served locally; chat does not load
third-party JavaScript from a CDN at runtime. There is no Node build step.

- Marked 18.0.7: `https://cdn.jsdelivr.net/npm/marked@18.0.7/lib/marked.umd.js`
  (MIT; see `MARKED-LICENSE`).
- DOMPurify 3.4.14: `https://cdn.jsdelivr.net/npm/dompurify@3.4.14/dist/purify.min.js`
  (Apache-2.0; see `DOMPURIFY-LICENSE`).

Keep their license files when updating. Update the versioned filenames and
script URLs in `chat/index.html` together. All parsed Markdown is sanitized
with a restricted tag/attribute list before insertion. Images, scripts, forms,
inline styles, and unsafe link protocols are not allowed in chat responses.
