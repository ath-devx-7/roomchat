---
version: 1
slug: "frontend-src-pages-landing-jsx"
primary_target: "frontend/src/pages/Landing.jsx"
related_targets: ["frontend/src/pages/Login.jsx","frontend/src/pages/Register.jsx","frontend/src/pages/Dashboard.jsx","frontend/src/pages/ChatRoom.jsx"]
---

## Scope

Every page of the RoomChat SPA (frontend/src/pages: Landing, Login, Register, Dashboard, ChatRoom) and the shared shell (theme switch, brand, toasts). Landing is Persuade (audience: recruiters/interviewers); the four app screens are Operate (mostly desktop).

## Confirmed decisions (owner, 2026-11-01)

- World: Paste-up Night (the incumbent paste-up theme, rebuilt around its dark mode). Layout: Evidence Board.
- Three themes via a three-way segmented control in every header: Light (warm-grey board, white sheets; never plain white), Dark (the black wall, main theme), Black (neutral grey, same elements). First visit follows the OS: dark → Dark, light → Light. Choice stored in localStorage.
- Landing: draggable pinned cards joined by tape; app screens use the same sheets/pins/tape/motion but nothing is draggable.
- Content-rich landing with real technical detail; a simulated demo room, clearly labelled; only true numbers.
- Browser-only extras approved: search friends (dashboard), search loaded messages (chat). Nothing else new.
- Old hero video/screenshots: keep files and backend keys, stop using them. No backend changes.
- No functionality may break; every change to which controls/pages exist is the owner's decision.

## Direction contract

THESIS: The landing is a case-file wall: the live room, the code, the numbers and the tech are pinned evidence joined by yellow tape, and the visitor can move them. It refuses the split hero over a row of equal cards.

OWN-WORLD: Warm near-black board, grey copy-paper sheets with paper lifts, one fluorescent yellow (#e3ef3c) for the primary control and one sheet per screen, yellow pushpins and tape lines, League Gothic capitals for heads and codes, Newsreader body, Geist Mono only for technical notes and frames, square corners, hard 4px ink offset under buttons, tech stickers and rubber stamps.

STORY: A recruiter sees in one viewport that this is a live, real-time system (the demo room runs, frames appear), understands the code-is-the-room idea, scrolls through features with their mechanisms and an illustrated tech board, and can sign up or type a code at any point.

FIRST VIEWPORT: Nav strip sheet across the top (logo, links, theme switch, Log in, Sign up). Below a "drag" hint: the headline card (poster head "Where your people gather to talk.", lead, Create account / Log in) pinned left; Exhibit A, the live demo room, pinned right and taped to it; Exhibit B, the six counting facts, bottom-left; the fluorescent "Got a code?" card with the six-cell code box bottom-right. Primary action: Create account on the headline card; the code box is the second working action.

FORM: Evidence Board, position 3 on my ordered list of seven Paste-up Night layouts; seed:37497e690c25b30a. Signature interaction: drag a pinned card and its tape follows; sending a message in the demo flies packets through the architecture diagram. Motion grammar: paper drops in on reveal, stamps thunk, joining members flash, numbers count up, cursor tilt on sheets; all off under reduced motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Mobile layout of the landing board (cards stack; dragging disabled under ~900px) to be confirmed at review.
