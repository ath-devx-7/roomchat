# Design: RoomChat

The locked system. Every Hallmark run reads this first and pages share it. Change it on purpose; the file is the rule.

## System
- Genre: playful (friendly, interactive)
- Shape of the first page: Bento Grid (`/`); the other four screens are app screens
- Theme: Paste-up. Light: the kraft board with white copy-paper sheets. Dark: the "black wall" board with grey-paper sheets (switch: `data-mode` on `<html>`, else the OS setting; kraft is the default)
- Axes: mid/display-condensed/chromatic-yellow · posture: committed

## Tokens
`frontend/src/tokens.css` is the source of truth. The roles (kraft; the black-wall block re-derives them):
```css
:root {
  --color-paper: oklch(73% 0.068 70);  --color-paper-2: oklch(66% 0.072 68);  --color-paper-3: oklch(97% 0.008 90);
  --color-ink: oklch(17% 0.01 60);  --color-ink-2: oklch(24% 0.014 60);  --color-muted: oklch(28% 0.026 62);  --color-rule: oklch(50% 0.055 68);
  --color-accent: oklch(93% 0.2 112);  --color-accent-ink: oklch(17% 0.01 60);  --color-focus: oklch(17% 0.01 60);
  --font-display: "League Gothic", Impact, sans-serif;  --font-body: "Newsreader", Georgia, serif;
  --radius-card: 0;  --radius-pill: 999px;  --rule-hair: 1px;  --shadow-card: (paper lift);  --shadow-sheet: (raised sheet);
}
```
App roles on top: `--color-offset` (the hard shadow under controls), `--color-hover`, `--color-overlay`, `--color-own` (your chat bubble), `--color-room-1..6` + `--color-room-ink` (coloured copy paper per room and person, `lib/format.js paperFor`), error and success.
Every text pair passes 4.5:1 on both boards.

## Rules
- Paper, not boxes: content sits on copy sheets (`.sheet`, `.sheet-raised`); at most three tilted surfaces a screen; inputs, tables and long reading stay square.
- The fluorescent is a paper: it fills the primary control and one sheet a screen (`.sheet-fluoro`), always with toner type; never a word or a band.
- League Gothic capitals only at 28px and up (heads, room codes); everything else is Newsreader, sentence case, untracked. No mono.
- Rooms and people each keep one coloured paper, picked from their code or name.

## Controls
- Primary: fluorescent, toner text, square, on a hard `4px 4px 0` offset; drops 1px on hover and into the offset on press
- Secondary: copy paper on the same offset · Ghost: lifts a sheet under itself on hover
- Focus: the global 2px toner outline (light toner on the black wall), instant

## Motion
- Character: paper physics. Button press; a live chat message drops in; a joining member's row flashes a fluorescent edge; "Copied" pops; the tab marker slides. All off under reduced motion. The hero recording has a pause control and starts paused under reduced motion.

## Exports
`frontend/src/tokens.css` in this project. shadcn's variables are mapped onto the tokens in `frontend/src/index.css`, and the Tailwind names (`paper`, `ink`, `rule`, `signal`, `room`, `offset`, shadows `card`/`sheet`/`offset`) in `frontend/tailwind.config.js`.
