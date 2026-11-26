# Abinaya chat widget (frontend)

React + TypeScript + Vite. The build produces **one self-contained file, `dist/widget.js`** (React and CSS
inlined, ~73 KB gzipped), that any allowed website embeds with one tag:

```html
<script src="https://abinaya-chatbot.pages.dev/widget.js" defer></script>
```

| Attribute (optional) | Default |
|---|---|
| `data-api-url` | `VITE_API_URL` at build time |
| `data-turnstile-site-key` | `VITE_TURNSTILE_SITE_KEY` at build time |
| `data-title` | `Abinaya Garments` |
| `data-primary-color` | `#26335f` (the website's indigo) |
| `data-position` | `right` (or `left`) |

## How it works

- `src/widget.tsx` defines `<abinaya-chat>` once (safe to include the script twice) and appends it to the page.
- React renders inside the element's **Shadow DOM**; the CSS (`src/styles.css`) is injected there, so the host
  site's styles can't reach in and ours can't leak out.
- **Turnstile** can't run inside a shadow root, so its container is a light-DOM child **slotted** into the chat
  window (`<slot name="turnstile">`). It runs in `interaction-only` mode, which is usually invisible.
- `services/session.ts` exchanges a Turnstile token for a 15-minute session (kept in `sessionStorage`), renews it
  a minute before expiry, and renews silently once if the API answers `401`.
- `services/api.ts` streams `POST /api/chat` with `fetch()` and parses the SSE events
  (`start` → `token`* → `complete` | `error`); `EventSource` can't send POST bodies or headers.
- Stop button: aborts the fetch; the Worker then aborts Gemini too.

## Commands

```bash
npm install
npm run dev     # http://localhost:5173: needs the local Worker on :8787 (uses Turnstile TEST key)
npm test        # vitest
npm run build   # dist/widget.js + dist/index.html (playground)
```

Environment: `.env.development` (local Worker + test site key) and `.env.production` (deployed Worker + real
site key). The Turnstile **site** key is public; the secret key exists only in the Worker.
