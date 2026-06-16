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

## Verified links (decoded from the brochure QR codes)
All payment/social destinations were decoded from the brochure QR codes (OpenCV WeChat
detector) and wired into `index.html` — no placeholders remain.

| Item      | Destination                                                                 |
|-----------|------------------------------------------------------------------------------|
| PayPal    | `https://www.paypal.com/qrcodes/managed/4506c7e5-3630-48ef-b00d-09afbb209fe7` |
| Zelle     | `https://enroll.zellepay.com/qr-codes?data=…` (recipient token from QR)       |
| Cash App  | `https://cash.app/$WellnessBeyondLLJC`                                        |
| Facebook  | `https://www.facebook.com/profile.php?id=61571447918292`                      |
| Instagram | `https://www.instagram.com/wellness_beyond_lljc`                             |
| TikTok    | `https://www.tiktok.com/@wellness_beyond_lljc`                               |

> Worth a final human spot-check by scanning the printed brochure, but each was decoded
> directly from the QR bitmaps, so confidence is high.

## Confirmed values (from brochure)
- Email: wellness.beyond.lljc@gmail.com
- Website: wellnessbeyondlljc.org
- Crisis: 988 (call/text) · Crisis Text Line: text HOME to 741741

## Notes
- No `bags.html` was built — the "Wellness Bag" program appears in the earlier AI handoff doc
  but **not** on the actual brochure. Add it only if it's a real program.
- Check color contrast if you adjust the palette (WCAG AA), especially muted text and the
  coral 988 accent.
