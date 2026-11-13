---
name: RoomChat
description: Paste-up Night. Real-time chat rooms pinned to a board of copy paper, tape and one fluorescent yellow.
colors:
  fluoro: "#e3ef3c"
  fluoro-hover: "#d6e32c"
  toner: "#17140f"
  light-board: "#e4e1d8"
  light-board-deep: "#d6d2c6"
  light-sheet: "#fbfaf6"
  light-sheet-tint: "#efece4"
  light-ink-2: "#2b2620"
  light-muted: "#5a5248"
  light-rule: "#c9c3b5"
  light-rule-2: "#ddd8cc"
  light-tape: "rgb(217 230 47 / 0.75)"
  wall: "#1f1b17"
  wall-deep: "#16130f"
  wall-sheet: "#2e2924"
  wall-sheet-tint: "#39332d"
  wall-ink: "#f0ebe0"
  wall-ink-2: "#ddd6c8"
  wall-muted: "#b8af9f"
  wall-rule: "#4b433b"
  wall-rule-2: "#3c352f"
  wall-offset: "#0b0907"
  wall-tape: "rgb(227 239 60 / 0.6)"
  black-board: "#141414"
  black-board-deep: "#0e0e0e"
  black-sheet: "#1f1f1f"
  black-sheet-tint: "#2a2a2a"
  black-ink: "#ececec"
  black-ink-2: "#d4d4d4"
  black-muted: "#a3a3a3"
  black-rule: "#3a3a3a"
  black-rule-2: "#2e2e2e"
  black-offset: "#000000"
  black-tape: "rgb(227 239 60 / 0.55)"
  own-light: "#eef2c0"
  own-dark: "#dfe5a4"
  own-muted: "#4d463c"
  error-light: "#b3341d"
  success-light: "#1f8a4c"
  error-dark: "#ff8a73"
  success-dark: "#6fd896"
  room-rose: "#f3c5c5"
  room-blue: "#bfd6f2"
  room-green: "#c7e8c9"
  room-lilac: "#e7d3f4"
  room-peach: "#f3d0b5"
  room-aqua: "#bfe6e6"
typography:
  display:
    fontFamily: "League Gothic, Impact, sans-serif"
    fontSize: "clamp(4rem, 5.5vw + 1rem, 5.5rem)"
    fontWeight: 400
    lineHeight: 0.92
    letterSpacing: "0.01em"
  section:
    fontFamily: "League Gothic, Impact, sans-serif"
    fontSize: "clamp(3rem, 4.5vw + 1rem, 5.25rem)"
    fontWeight: 400
    lineHeight: 0.95
    letterSpacing: "0.01em"
  headline:
    fontFamily: "League Gothic, Impact, sans-serif"
    fontSize: "44px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.01em"
  title:
    fontFamily: "League Gothic, Impact, sans-serif"
    fontSize: "34px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.01em"
  code-figure:
    fontFamily: "League Gothic, Impact, sans-serif"
    fontWeight: 400
    lineHeight: 0.95
    letterSpacing: "0.06em"
  lead:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "clamp(1.125rem, 0.35vw + 1rem, 1.3125rem)"
    fontWeight: 400
    lineHeight: 1.45
  body:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body-card:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.625
  subhead:
    fontFamily: "Newsreader, Georgia, serif"
    fontWeight: 500
    lineHeight: 1.2
  label:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "15px"
    fontWeight: 500
    lineHeight: 1.25
  mono-note:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.625
  mono-sticker:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 500
rounded:
  none: "0px"
  pin: "50%"
spacing:
  3xs: "2px"
  2xs: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  2xl: "64px"
  3xl: "96px"
  4xl: "144px"
  gutter: "48px"
  container: "1360px"
components:
  button-primary:
    backgroundColor: "{colors.fluoro}"
    textColor: "{colors.toner}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-primary-lg:
    backgroundColor: "{colors.fluoro}"
    textColor: "{colors.toner}"
    rounded: "{rounded.none}"
    padding: "0 24px"
    height: "48px"
  button-outline:
    backgroundColor: "{colors.light-sheet}"
    textColor: "{colors.toner}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-destructive:
    backgroundColor: "{colors.error-light}"
    textColor: "{colors.light-sheet}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-ghost:
    textColor: "{colors.toner}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-ghost-hover:
    backgroundColor: "{colors.light-sheet}"
  input:
    backgroundColor: "{colors.light-sheet}"
    textColor: "{colors.toner}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "4px 12px"
    height: "40px"
  sheet:
    backgroundColor: "{colors.light-sheet}"
    textColor: "{colors.toner}"
    rounded: "{rounded.none}"
    padding: "36px 24px 24px"
  sheet-fluoro:
    backgroundColor: "{colors.fluoro}"
    textColor: "{colors.toner}"
    rounded: "{rounded.none}"
    padding: "40px 24px 24px"
  own-message:
    backgroundColor: "{colors.own-light}"
    textColor: "{colors.toner}"
    typography: "{typography.body-card}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
  other-message:
    backgroundColor: "{colors.light-sheet}"
    textColor: "{colors.toner}"
    typography: "{typography.body-card}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
  theme-toggle:
    backgroundColor: "{colors.light-sheet-tint}"
    textColor: "{colors.light-muted}"
    rounded: "{rounded.none}"
    padding: "2px"
  theme-toggle-active:
    backgroundColor: "{colors.fluoro}"
    textColor: "{colors.toner}"
    width: "36px"
    height: "32px"
  sticker:
    backgroundColor: "{colors.light-sheet-tint}"
    textColor: "{colors.toner}"
    typography: "{typography.mono-sticker}"
    rounded: "{rounded.none}"
    padding: "6px 10px"
---

# Design System: RoomChat

## Overview

**Creative North Star: "Paste-up Night"**

RoomChat is a paste-up board worked on late: copy-paper sheets pinned and taped to a wall, a single fluorescent yellow marker, condensed poster capitals for heads and room codes, and a newspaper serif for everything you read. The main theme is the black wall (dark); light is a warm-grey board with white sheets; black is the same board in neutral grey. Every element exists in all three, and only the board and sheet stocks change.

Depth comes from paper, not boxes: sheets lift off the board on soft shadows, controls sit on a hard ink offset and press into it, pinned sheets rest at small tilts. The landing page is an Evidence Board: cards on a fixed-size canvas, joined by yellow tape lines, that a visitor can drag (the tape follows). The app screens (login, register, dashboard, room) use the same sheets, pins, tape and motion, but nothing on them moves under the pointer. Under 900px a board stacks its cards in reading order with no tape and no dragging.

Motion is paper physics: sheets drop onto the board as they scroll in, stamps thunk down, a new chat message drops in like a slip, a joining member's row flashes a fluorescent edge, a swapped label pops. All of it stops under `prefers-reduced-motion`.

**Key Characteristics:**
- Three boards switched by `data-mode` on `<html>` (light, dark, black); with nothing stored, the OS picks light or dark.
- One fluorescent yellow, used as paper (a fill with toner type), never as a text colour.
- Square corners everywhere; only pushpins are round.
- League Gothic capitals for heads and codes, Newsreader for reading, Geist Mono only for technical notes, frames and data.
- Soft paper lifts under sheets, a hard 4px ink offset under buttons.
- Draggable evidence board on the landing; static boards in the app.

## Colors

One loud fluorescent on quiet paper and toner, re-stocked per board.

### Primary
- **Fluorescent Yellow** (fluoro): the primary button, the current theme in the theme switch, the one fluorescent sheet on a screen, pushpins, search-match highlights, live wires and packets in the architecture diagram, the caret. Always with toner type on it. Hover deepens to **Fluorescent Hover** (fluoro-hover).

### Neutral
- **Toner** (toner): ink on the light board, and the type on anything fluorescent or own-message yellow in every theme. Also the hard offset colour on the light board.
- **Warm Grey Board** (light-board), **Deep Board** (light-board-deep): the light theme's wall and its recessed areas (muted panels). Never replaced by plain white.
- **White Copy Paper** (light-sheet), **Tinted Paper** (light-sheet-tint): sheets, cards, inputs and popovers on the light board; the tint is for hover, stickers and code blocks inside a sheet.
- **Ink 2 / Muted** (light-ink-2, light-muted): secondary text and captions.
- **Rule / Rule 2** (light-rule, light-rule-2): borders and list dividers.
- **The Black Wall** (wall, wall-deep, wall-sheet, wall-sheet-tint, wall-ink, wall-ink-2, wall-muted, wall-rule, wall-rule-2, wall-offset): the main theme. A warm near-black board with lighter grey paper sheets and warm off-white ink. Tape lines turn fluorescent here.
- **Neutral Black** (black-board … black-offset): the same roles without the warm cast.

### Tertiary
- **Own-message Paper** (own-light on the light board, own-dark on the wall and the black board): your own chat messages. It is light stock in every theme, so its text is reset to toner, toner-2 and **Own Muted** (own-muted) inside it.
- **Copy-paper Stocks** (room-rose, room-blue, room-green, room-lilac, room-peach, room-aqua): one per room and per person, picked by hashing the code or name. Light stock in every theme, always with toner type.
- **Tape** (light-tape, wall-tape, black-tape): translucent fluorescent strips across sheet tops.
- **Error / Success** (error-light, success-light on light; error-dark, success-dark on the dark boards): destructive buttons, form errors, the rubber stamp's ink, success notes.

### Named Rules
**The One Fluorescent Rule.** Fluorescent yellow fills the primary control and at most one sheet per screen, always with toner type. It is paper, never a word colour.

**The Own Paper Rule.** Your own messages are yellow-tinted copy paper with toner ink in every theme; other people's are plain sheet paper.

**The Never Plain White Rule.** The light board is warm grey with white sheets on it. White is a sheet, never the board.

## Typography

**Display Font:** League Gothic (with Impact, sans-serif)
**Body Font:** Newsreader (with Georgia, serif)
**Label/Mono Font:** Geist Mono (with ui-monospace, monospace)

**Character:** Condensed poster capitals shout the heads and room codes like a paste-up headline; a soft optical-size serif carries everything you read. Mono is the technical annotation in the margin.

### Hierarchy
- **Display** (400, clamp(4rem, 5.5vw + 1rem, 5.5rem), 0.92): the landing headline. Auth pages use a smaller clamp (3.5rem to 4.5rem) on the same face.
- **Section** (400, clamp(3rem, 4.5vw + 1rem, 5.25rem), 0.95): landing section heads, set left with their standfirst on the right.
- **Headline** (400, 44px, 1): card and sheet heads (Join a room, Got a code?).
- **Title** (400, 34px, 1): panel heads in the app (Friends, Activity, the room name).
- **Code figure** (400, letter-spacing 0.06em): room codes set as poster figures, from 20px in a note up to 64px on a sheet.
- **Lead** (400, clamp(1.125rem to 1.3125rem), 1.45, max 52ch): standfirsts.
- **Body** (400, 1rem, 1.5, max 65ch): running text. Card copy sits at 15px with relaxed leading.
- **Subhead** (500, 1.2): Newsreader h3s inside sheets.
- **Label** (500, 15px): buttons and form labels, sentence case.
- **Mono note** (400, 0.75rem): technical notes, frame logs, data, figure captions. Stickers use 500 at 12px.

### Named Rules
**The Poster Caps Rule.** League Gothic is always uppercase and only for heads, codes, stamps and big counted figures; it never sets a sentence of body text.

**The Mono Is Technical Rule.** Geist Mono appears only for technical notes, protocol frames, data and captions. Never for headings or prose.

**The Caption Below Rule.** Labels and captions go under the thing they describe ("Fig. 2: …"). No kicker or eyebrow line above a heading.

## Layout

The page container is 1360px wide with a 48px gutter (24px under 60rem, 16px under 40rem). Spacing follows a fixed scale from 2px to 144px.

The landing is an Evidence Board: a design-size canvas (1264px wide, fixed height per board) on which pinned cards sit at absolute positions. The canvas scales down to fit its column, and above 900px cards can be dragged by their handle strip, with tape lines redrawn from card to card. Under 900px the board stacks the cards in reading order, drops the tape, disables dragging and hides the stickers.

App screens are static boards: CSS grids of sheets (dashboard is a 7/5 split of main column and aside on large screens; the room is messages beside a members panel). Sheets keep their small resting tilts and pins but never move with the pointer. Auth pages pair a tilted pitch sheet with the form on a raised, taped sheet.

## Elevation & Depth

Hybrid: soft paper lifts for sheets, a hard ink offset for controls. The shadows are tokens that re-derive per board (stronger on the dark boards).

### Shadow Vocabulary
- **Card lift** (`--shadow-card`, light: `0 1px 0 rgb(0 0 0 / 0.08), 0 6px 16px rgb(0 0 0 / 0.1)`): a sheet lying on the board, chat messages, the ghost button's hover.
- **Sheet lift** (`--shadow-sheet`, light: `0 18px 36px rgb(0 0 0 / 0.18), 0 2px 4px rgb(0 0 0 / 0.1)`): raised sheets, the fluorescent sheet, forms, popovers.
- **Ink offset** (`4px 4px 0 var(--color-offset)`, then 3px on hover, 2px for stickers): the hard shadow under primary, outline and destructive buttons. Native to the paste-up world.

### Named Rules
**The Press Into The Offset Rule.** A button sits on a 4px ink offset, drops 1px toward it on hover, and presses fully into it on click.

**The Small Tilt Rule.** Pinned sheets rest at tilts between about -1.5deg and 2.5deg; stickers and stamps may go to about 6deg. Inputs, tables and long reading stay square.

## Shapes

Paper is cut square: every radius is 0, enforced by replacing Tailwind's whole radius scale. The only round thing is the pushpin (a 14px fluorescent circle with an ink drop shadow). Other recurring forms: tape strips (72x22px, -3deg) across a sheet top, a torn receipt edge under frame logs, rubber stamps (condensed caps in a 3px box, inked in the error colour, -6deg), deleted messages as a dashed outline.

## Components

### Buttons
Tactile paper keys on a hard offset.
- **Shape:** square (0).
- **Primary:** fluorescent with toner type, 40px tall, 16px side padding (48px and 24px for large), Newsreader 500 at 15px.
- **Hover / Focus:** drops 1px into a 3px offset on hover, fully in on press (120ms). Focus is the global 2px outline in the focus colour (toner on light, light ink on the dark boards), offset 2px.
- **Outline:** sheet paper on the same offset. **Destructive:** error colour on the same offset. **Secondary:** sheet paper on a card lift. **Ghost:** no fill; lifts a sheet under itself on hover.
- **Disabled:** 50% opacity and a not-allowed cursor; a disabled primary turns to sheet paper with muted text.

### Inputs / Fields
- **Style:** square sheet-paper field, 1px ink border, 40px tall, muted placeholder.
- **Focus:** the global 2px outline; the border width never changes.
- **Code box:** six League Gothic cells on the fluorescent sheet, the next empty cell lifting while focused.

### Cards / Containers
- **Corner Style:** square.
- **Background:** sheet paper; one fluorescent sheet per screen.
- **Shadow Strategy:** card lift at rest, sheet lift when raised.
- **Border:** none; edges come from the lift.
- **Internal Padding:** 24px sides with about 36-40px on top to clear the pin or tape.

### Navigation
- **Theme switch:** a three-way segmented control (sun, moon, filled circle) in every header, tinted paper with a rule border; the current theme sits on the fluorescent with toner type.
- **Landing nav:** a strip sheet across the top with logo, links, theme switch, Log in and Sign up.

### Chat messages
Your own messages are own-message paper with toner type; others are sheet paper. Both carry the card lift and drop in when they arrive live. Replies show a quoted preview behind a 2px rule. Others get a coloured-paper initial tile.

### Evidence Board and Pin
A fixed-size canvas of pinned sheets joined by tape lines, scaled to fit. Draggable only on the landing. Stacks under 900px.

### Stickers and Stamps
Mono stickers (tinted paper, fluorescent or outline) carry protocol facts on the landing board and sit on a 2px offset. Rubber stamps count things (pending invitations) and thunk in.

## Do's and Don'ts

### Do:
- **Do** put toner type on every fluorescent, own-message and coloured-paper surface, in all three themes.
- **Do** keep fluorescent to the primary control and one sheet per screen.
- **Do** give every element a value in all three boards through the tokens; never hardcode a board colour.
- **Do** set captions in Geist Mono under the thing they label.
- **Do** keep dragging to the landing's Evidence Board; app screens are static.
- **Do** stop every animation under `prefers-reduced-motion`, and show revealed content at full opacity.

### Don't:
- **Don't** use plain white as the light board; white is for sheets.
- **Don't** put a kicker or eyebrow line above a heading.
- **Don't** use Geist Mono for headings or prose.
- **Don't** round corners; only pushpins are round.
- **Don't** use fluorescent yellow as a text colour on the board.
- **Don't** tilt inputs, tables or long reading.
