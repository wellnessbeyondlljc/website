# Wellness Beyond #LLJC — website

Static site (no build step). Open `index.html` in a browser, or serve locally:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## Files
- `index.html` — home (mission, awareness, what we do, get involved, donate, vision, connect)
- `resources.html` — crisis support (988, Crisis Text Line) + warning signs
- `assets/css/styles.css` — design system: tokens, light + dark themes, components
- `assets/js/theme.js` — theme toggle (remembers choice; defaults to system) + mobile nav

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
