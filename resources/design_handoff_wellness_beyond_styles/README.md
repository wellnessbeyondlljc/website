# Handoff: Wellness Beyond #LLJC — Website Style System

## Overview
This package defines the visual style system for the **Wellness Beyond #LLJC** website — a youth-focused nonprofit centered on mental wellness, grief & emotional support, suicide awareness/prevention, and community connection. The system is derived directly from the organization's printed tri-fold brochure (included as reference images) and translates that look & feel into a reusable web style guide: color, typography, the heart motif, iconography, and core UI components.

The goal of this handoff is to let a developer apply this style consistently across the live site.

## About the Design Files
The files in this bundle are **design references created in HTML** — a prototype style sheet showing the intended look, tokens, and component treatments. **They are not production code to copy verbatim.** The task is to **recreate this style system in the target codebase's existing environment** (React, Vue, Astro, WordPress theme, plain HTML/CSS, etc.) using its established patterns. If no front-end environment exists yet, pick the most appropriate framework for a small nonprofit marketing site and implement the tokens/components there.

`Wellness Beyond Style Sheet.dc.html` is authored as a "Design Component" (a streaming HTML format). You do **not** need that runtime — read it as an HTML/CSS reference for exact values, or open it in a browser to view the rendered guide. All styling is inline; there is no external CSS to extract.

## Fidelity
**High-fidelity (hifi).** Colors, typography, spacing, and component treatments are final and intended to be matched closely. Recreate pixel-accurately using the codebase's libraries. The only placeholders are: (1) Unicode glyphs standing in for icons, and (2) a striped box standing in for the community/sunset hero photo — see **Assets**.

---

## Design Tokens

### Colors
| Token | Hex | Usage |
|---|---|---|
| Charcoal | `#0C0A09` | Primary page background (dark) |
| Panel | `#16120E` | Cards, raised surfaces on dark |
| Metallic Gold | `#D6A24A` | Primary accent — headers, rings, links, borders |
| Bronze | `#B8772E` | Deep gold — borders, icon rings, dividers |
| Soft Gold | `#E6B65A` | Script type, glow/highlight |
| Coral Red | `#E0364C` | Hearts, emphasis words, crisis/urgent CTA |
| Cream | `#F4EDE0` | Body text on dark backgrounds |
| Off-White | `#FDFAF4` | Headings on dark backgrounds |
| Warm Gray | `#A89E8E` | Secondary/body text |
| Muted Gray | `#8A8070` | Captions, labels, eyebrows |

### Gradients
- **Gold Foil** (headers, accent fills): `linear-gradient(100deg, #F4D27A, #D6A24A 50%, #B8772E)`
- **Sunset** (imagery overlays, hero base): `linear-gradient(180deg, #3A1D22, #7A2E1F 55%, #D6A24A)`
- **Charcoal Panel**: `linear-gradient(160deg, #16120E, #0C0A09)`
- **Hero background**: `linear-gradient(180deg, #0C0A09 0%, #1A0E07 60%, #3A1D0E 100%)`

### Typography
Fonts (Google Fonts):
- **Display / Headings — `Cinzel`** (serif, engraved caps). Weights 400–700. Used UPPERCASE with letter-spacing `0.06em`–`0.14em`. This is the brand-lockup face (WELLNESS BEYOND).
- **Script — `Great Vibes`** (cursive). Emotional taglines & accents ONLY (e.g. "You are not alone", "Hope. Help. Healing."). Never body or UI.
- **Subhead — `Cormorant Garamond`** (serif, often italic). Warm literary section intros.
- **Body / UI — `Lato`** (sans-serif). Weights 300/400/700/900. Default for all paragraphs, buttons, labels.

Type scale (px): Display 82 · H1 46 · H2 30 · H3 18 · Body 16 · Caption 13. (Brand lockup can scale fluidly: `clamp(40px, 7vw, 82px)`.)

Conventions:
- Eyebrow labels: Lato 700, 12px, `text-transform:uppercase`, `letter-spacing:0.2em`, color Muted Gray.
- Section numbers/headers: Cinzel 600, `letter-spacing:0.08em`.
- Buttons: Lato 700, 14px, uppercase, `letter-spacing:0.08em`.

### Spacing
Section vertical padding `52px 0`; page gutters `48px`; card padding `30px 28px`; button padding `15px 34px`. Card/section gaps `16–22px`. The system is roughly on a 4px base.

### Radius
- Cards / panels: `14–18px`
- Buttons / pills: `40px` (full pill)
- Icon discs: `50%`
- Brushstroke header: irregular — `40px 32px 44px 30px / 30px 40px 28px 38px`

### Shadows / effects
- Gold button: `0 6px 20px rgba(214,162,74,0.25)`
- Coral button: `0 6px 20px rgba(224,54,76,0.30)`
- Icon disc inner shadow: `inset 0 0 18px rgba(0,0,0,0.6)`
- Glow heart: `filter: drop-shadow(0 2px 8px rgba(230,182,90,0.4))`
- Dividers / borders on dark: `1px solid rgba(214,162,74,0.16–0.20)`

---

## Components

### Heart motif (signature mark)
- **Divider**: gold hairline — coral heart `♥` — gold hairline, centered.
- **Bullets**: coral `♥` preceding list items (replaces standard bullets).
- **Hero glow mark**: large Soft Gold `♥` with drop-shadow glow.
Use sparingly — it is an emphasis device, not decoration on every element.

### Brushstroke section header
Inline-block pill with **Gold Foil** gradient fill, irregular border-radius (see Radius), padding `14px 38px`. Text: Cinzel 700, 26px, uppercase, color `#2A1C0A` (dark brown for contrast on gold). Mirrors the brochure's painted-stroke headings.

### Buttons
- **Primary (Donate)**: Gold Foil fill, text `#2A1C0A`, pill, gold shadow. Hover: `filter:brightness(1.08)`.
- **Secondary (Volunteer)**: transparent fill, `1.5px solid #D6A24A` border, off-white text. Hover: `background:rgba(214,162,74,0.12)`.
- **Crisis (Get Help)**: solid `#E0364C` fill, white text, coral shadow, trailing `♥`. Hover: `brightness(1.06)`.
- **Text link**: `#D6A24A`, bottom border `rgba(214,162,74,0.4)`, trailing `→`.

### Program / feature card
Panel `#16120E`, `1px solid rgba(214,162,74,0.16)` border, radius 16px, padding `30px 28px`. Top: 60px icon disc. Title Cinzel 18px off-white. Body Lato 14.5px Warm Gray, `line-height:1.6`. Hover: border → `rgba(214,162,74,0.45)`.

### Icon disc
78px (60px in cards) circle, `radial-gradient(circle at 35% 30%, #1F1810, #100C08)` fill, `1.5px solid #B8772E` ring, inner shadow. Icon glyph centered — coral for emotion/care icons, gold for the rest.

### Crisis support banner (988)
Full-width panel, `linear-gradient(135deg, #1A130D, #241006)`, `1px solid rgba(224,54,76,0.3)`, radius 18px, centered. Soft-gold heart → supportive line (Cream 16px) → **988** in Cinzel 700, 54px, Coral Red → caption → Great Vibes tagline "Hope. Help. Healing." in Soft Gold. This block is a recurring, high-priority pattern site-wide.

### Homepage hero
Hero-gradient background, centered. Glow heart → headline (Cinzel uppercase, `clamp(30px,4vw,52px)`) → script subline → supporting paragraph (Cream, max-width ~560px) → button pair (Primary + Secondary) → full-bleed community photo at the base.

---

## Interactions & Behavior
- **Hover** transitions on buttons (brightness) and cards (border color); keep ~150–200ms ease.
- No complex animation in this system — keep motion gentle and minimal, in keeping with the dignified tone.
- **Responsive**: card grids use `repeat(auto-fit, minmax(220–250px, 1fr))`; headline sizes use `clamp()`. Single-column stack on narrow viewports. Maintain generous whitespace.
- **Accessibility**: this is sensitive subject matter — ensure the 988 banner is reachable/visible, keep text contrast high (Cream/Off-white on Charcoal passes), and don't rely on color alone for the coral emphasis words (they're also bolded in the brochure).

## State Management
None required — this is a static marketing style system. (The prototype exposes one optional `showValues` boolean that toggles hex labels in the swatch grid; that is a documentation aid only, not a site feature.)

## Voice & Tone
Compassionate, hopeful, dignified. Meet young people with warmth, never judgment. Even on hard topics, point toward light. Taglines: "Building Resilience · Teaching Compassion · Creating Hope" and "Helping kids heal, grow, and thrive."

## Assets
Provide/replace these in the real build:
- **Icons**: prototype uses Unicode glyphs (`♥ ✋ ✿ ★ ✉ ✦`) as stand-ins. Use a real line-icon set (e.g. brain, praying figure, sprout/plant, hands holding heart, people group, star, open book, calendar, megaphone, handshake) styled inside the gold icon disc. Match the brochure's thin, rounded gold line style.
- **Hero/section imagery**: striped placeholder marks where a **community-at-sunset photo** belongs (silhouetted group, warm sunset). Source real photography.
- **Logo**: the brochure lotus/meditation-figure-with-leaves mark in gold is the brand logo — obtain the vector from the client.
- Reference brochure scans included: `reference_brochure_front.jpg`, `reference_brochure_inside.jpg`.

## Files
- `Wellness Beyond Style Sheet.dc.html` — the rendered style guide (HTML reference; inline styles hold all exact values).
- `reference_brochure_front.jpg` / `reference_brochure_inside.jpg` — source brochure for fidelity checks.
