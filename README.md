# Wellness Beyond #LLJC — website

Static site (no build step). Serve locally with Bun:

```bash
bun run dev                          # http://wbl.local  (also http://localhost:3150)
HOST=0.0.0.0 PORT=8080 bun run dev   # override host/port
```

The dev server listens on `127.0.0.1:3150`; a Caddy reverse proxy maps the short URL
`http://wbl.local/` (port 80) → `:3150`. Host/port come from the mywheel hub registry for
this spoke: short URL `wbl.local`, primary port `3150` (reserved block 3150–3159).

On startup the server runs a pre-flight check: if anything is already LISTENing on the
port (always a stale dev server, since the port is dedicated to this spoke) it kills it and
binds clean. It uses `ss` to target only the listening socket, so the shared Caddy proxy is
never touched.

## Files
- `index.html` — home (mission, awareness, what we do, get involved, donate, vision, connect)
- `resources.html` — crisis support (988, Crisis Text Line) + warning signs
- `assets/css/styles.css` — design system: tokens, light + dark themes, components
- `assets/js/theme.js` — theme toggle (remembers choice; defaults to system) + mobile nav
- `server.ts` / `package.json` — Bun static dev server (`bun run dev`)

## Content source
All copy is taken **verbatim** from the brochure in `resources/`. Visual design follows
`resources/usable-asset-inspiration.png` (gold + coral accents, serif display, script accents).

## ⚠️ Before launch — verify these (marked `data-todo` in the HTML)
The brochure shows these only as **QR codes / icons**, so the real destinations could not be
read from the images. Each is currently a `#` placeholder labelled "verify":

| Item            | Where                       | What to fill in                          |
|-----------------|-----------------------------|------------------------------------------|
| PayPal          | `index.html` → `#support`   | PayPal.me link or donate URL             |
| Zelle           | `index.html` → `#support`   | Zelle email/phone (likely the org email) |
| Cash App        | `index.html` → `#support`   | `$cashtag`                               |
| Facebook        | `index.html` → `#connect`   | Profile URL                              |
| Instagram       | `index.html` → `#connect`   | Profile URL                              |
| TikTok          | `index.html` → `#connect`   | Profile URL                              |

Find them all quickly: `grep -rn "data-todo" .`

## Confirmed values (from brochure)
- Email: wellness.beyond.lljc@gmail.com
- Website: wellnessbeyondlljc.org
- Crisis: 988 (call/text) · Crisis Text Line: text HOME to 741741

## Notes
- No `bags.html` was built — the "Wellness Bag" program appears in the earlier AI handoff doc
  but **not** on the actual brochure. Add it only if it's a real program.
- Check color contrast if you adjust the palette (WCAG AA), especially muted text and the
  coral 988 accent.
