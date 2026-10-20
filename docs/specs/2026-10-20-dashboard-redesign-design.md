# Dashboard redesign: warm, professional look and a first-visit intro

Date: 20 Oct 2026. Builds on the M3 dashboard (spec `2026-10-13-lead-agent-design.md`, Section 8).
Mockups Yash approved, kept beside this file:
- `2026-10-20-dashboard-redesign/visual-style-options.html`: three styles; **option C (warm and friendly)** was chosen.
- `2026-10-20-dashboard-redesign/intro-animation.html`: the intro animation, **approved as is ("don't change anything")**.

**Product name: VidyaDesk** (Yash's choice). It appears on the login page, in the browser tab title and the
sidebar, and in the admin's intro. The Python package, CLI and repo keep their current names.

## Why

Before publishing the project or pitching it to institutes, Yash wants the dashboard to look professional and
simple. Two moments matter:

1. **The pitch.** The first time an institute owner opens the dashboard, it should impress them (the intro
   animation), then show a clean, friendly dashboard.
2. **Every day after.** The owner checks it on a phone between classes. It must open straight to what needs
   them, with no animation and nothing slow.

## Goals

- Every dashboard page restyled in one consistent look (option C): login, a new Home, Leads, lead
  conversation, Documents, Facts, Stats, admin Institutes.
- A first-visit intro animation exactly like the approved mockup.
- A new **Home** screen that answers "what needs me now?".
- Phone first; also good on a laptop.

## Non-goals

- No new features beyond the Home screen. Every page keeps doing what it does now (filters, CSV export,
  resume / close / delete, upload, facts editing, stats, admin add / switch).
- Telegram messages (alerts, morning summary, bot replies) are not changed in this round (Yash: "stay on web
  pages only"); added to the backlog.
- No React or front-end build step; pages stay server-rendered Jinja2 in the existing FastAPI app.
- No dark mode in this round.

## Anti-goals (a failure even if it works)

- The animation plays every time the owner opens the dashboard.
- Pages get slow or heavy on a phone over mobile data.
- Any existing security behaviour weakens: the 404 for other institutes, HTML escaping of student text, CSV
  formula guard, upload name checks, login throttle. Every existing test stays green.
- It looks like a generic admin template rather than a product made for a coaching institute.

## Constraints

- Server-rendered Jinja2 templates in `leadagent/dashboard/templates/`, routes in
  `leadagent/dashboard/routes.py`. Autoescape stays on; never use `|safe` on user-written text.
- All changes still by POST forms; no new JavaScript is needed for any action to work. JavaScript is only for
  the intro and small touches, and every page must work if it fails.
- Works at 360 px phone width with no sideways page scroll (wide tables may scroll inside their own box).
- Respect `prefers-reduced-motion`: no animation at all for those users.
- No hardcoded absolute paths. No new Python dependency.

## Decided: the look (option C, warm and friendly)

Colour tokens, taken from the approved mockups:

| Token | Value | Use |
|---|---|---|
| background | `#fbf8f3` (cream) | page |
| ink | `#2b2118` | main text |
| muted | `#8a7766` | secondary text |
| faint | `#a8937d` | section labels |
| accent | `#c2410c` (saffron) | links, active tab, buttons, focus |
| accent-soft | `#ffe8cc` | initials circles, icon backgrounds |
| card | `#ffffff` | cards, rows |
| border | `#efe6da` | dividers |
| card shadow | `0 1px 3px rgba(60,40,20,.08)` | cards and rows |

Badges (pill shape): Hot `#ffe4e1` / `#c0262d`; Waiting (handed off) `#fff1c2` / `#8a5a00`; New `#dff3ec` /
`#0f766e`. Warm, cold, qualified, collecting and closed get their own quiet badges (builder picks, same family).

Shapes: rounded corners (cards 14–16 px, pills fully round), white cards with the soft shadow, generous
spacing. Each lead is shown with a round initials circle (first letters of the name; "?" when no name).
Section labels are small uppercase with letter spacing, as in the mockup.

## Decided: navigation

- Phone: a bottom tab bar (Home, Leads, Docs, Facts, Stats), active tab in saffron, as in the mockup. The
  institute name and an initials avatar sit at the top; log out is reachable from the top.
- Laptop: a left sidebar with the same items, the institute name at the top, log out at the bottom.
- Admin also gets "Institutes"; when the admin opens an institute's pages, that institute's tabs show.

## Decided: Home screen (new)

The owner lands here after login (and `/dash` redirects here for owners). Content, top to bottom, as in the
mockup:

1. Institute name and avatar.
2. Three number cards: **new today** (leads created since local midnight in the institute's timezone),
   **hot** (interest hot and not closed), **waiting** (handed off, i.e. waiting for the owner).
3. **Needs you**: the handed-off leads, oldest waiting first, each a row with name, class · course · reason,
   and a Waiting badge, linking to the lead's conversation. An empty state when there are none ("Nothing waiting.
   The assistant is handling every enquiry.").
4. **Latest leads**: the newest few leads (about 5–10) as rows with badges, and a "See all leads" link to the
   Leads tab.

The admin's landing page stays the Institutes list.

## Decided: the intro animation

Exactly the approved mockup `intro-animation.html` (about 6.5 s):

1. A soft saffron glow, a ring drawing itself around an open-book icon.
2. "WELCOME" then the **owner's institute name** slide up (the admin sees the product name, **VidyaDesk**,
   instead).
3. The quote, word by word from a blur: *"Education is the most powerful weapon which you can use to change the
   world."* and the attribution **Nelson Mandela**. Always this quote.
4. The intro lifts away and the Home screen builds itself: number cards rise and count up, then the rows appear.

Rules:
- Plays only on the first visit **per browser**: after it plays (or is skipped) once, that browser never shows it
  again. Remembered in the browser (e.g. `localStorage`); a new phone or laptop shows it once, which suits the
  pitch. If storage is unavailable, show it at most once per page load and never block the page.
- A visible **Skip** link ends it at once.
- Never plays for `prefers-reduced-motion` users.
- It plays over the real Home page, so the numbers and rows in the build-up are the institute's real data.
  Without JavaScript the Home page simply shows.

## Decided: the other pages

- **Login**: the same warm style, centred card with the book mark, product name, email and password fields,
  one saffron button. Error messages keep their current wording.
- **Leads**: the existing filters (stage, interest, days) and CSV link restyled; on a phone each lead is a row
  card like Home; on a laptop a clean table. Same data and behaviour.
- **Lead conversation**: the transcript as chat bubbles (student on one side, assistant on the other, owner
  messages marked), the lead's details as a card, and the Resume / Close / Delete buttons as proper buttons
  (Delete visibly destructive, still confirmed).
- **Documents, Facts, Stats, Institutes**: same content, restyled (Stats keeps its per-day bars, in saffron).
- Flash messages and errors as small styled banners.

## Calls made after the builder check (Claude's, for Yash to check)

- Home lives at `/dash/<slug>/home`. Owner login and `/dash` redirect there (the two existing auth tests that
  expect `/dash/<slug>/leads` are updated: an intended change). The admin opening an institute gets the same Home
  through its slug; the admin's own landing page stays Institutes.
- "Hot" = interest hot and stage not closed, all time. "Waiting" = stage handed off, all time. "New today" =
  created since local midnight.
- "Needs you" is ordered by the student's last message, oldest first (no handoff timestamp exists; adding one is
  backlog, not this round).
- Home's numbers and lists come from a few small new `repo` functions with tests; no schema change, no caching.
- The intro overlay is hidden by default and JavaScript reveals it only when the browser's flag is unset, so a
  returning visit or a page without JavaScript never flashes it. One flag per browser (not per account), set when
  it ends or is skipped. Timings and effects copied from the approved mockup; the Home build-up animates the real
  page's number cards and rows.
- The mockups use no web font; the pages use the system font stack, the same as the mockups.

## Left to the builder

- The exact CSS organisation (one stylesheet is fine), icons (inline SVG, no icon font needed), font choice
  (the system font stack is acceptable; a web font only if it does not slow the phone noticeably), spacing values,
  how the laptop table and phone cards switch, and the quiet badge colours for the other stages.
- The exact number of rows in "Latest leads".
- How the intro is put on the page (an overlay on the Home template is the natural fit).

## Testing

- All current tests pass unchanged in meaning (isolation 404s, escaping, CSV guard, upload names, login throttle).
- New tests for the Home route: shows only this institute's numbers and leads, 404 for another institute's slug,
  student-written names are escaped, the owner's login and `/dash` land on Home.
- The intro is checked by hand on a phone and a laptop (first visit plays, second does not, Skip works, reduced
  motion shows nothing).

## Backlog additions (spec Section 15)

- Telegram messages (hot-lead alert, handoff alert, morning summary) made neater: Yash chose to keep them as they
  are for this round.
- Dark mode.
