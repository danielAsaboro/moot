# design.md

Brand feel: evidence, plain, unsentimental. A ledger, not a chat bubble. The graph decides; the page shows its work.
Visual direction: calm frame, one exhibit. Apple-style structure (inset grouped lists, sentence case, tinted pills, sheets) around Moot's own exhibits: the 3D ruled ledger, the isometric decision drawing, the exhibit cards, the lanyard badge and the extruded wordmark.
References: Apple HIG (Layout, Typography, Lists and tables, Sheets, Color); apple.com product pages; a printed audit ledger; a patent drawing; the moodboard (private, hackathon/moodboard).

## Stack
Next.js (App Router, TypeScript) in `frontend/`, built as a static export (`output: "export"`) and served by FastAPI at `/`. The API is unchanged; every number on screen comes from a FastAPI route. 3D with three.js through React Three Fiber and drei, loaded client-side only.

## The rule: calm frame, one exhibit
1. **Every screen (or landing section) has one hero**: a plain sentence, or one expressive component. Never several competing. Everything else is quiet structure.
2. **Quiet structure is Apple's:** inset grouped lists (title, grey subtitle, trailing pill, chevron), section headers in small grey sentence case, borderless cards on a slightly different ground, large radii (14 / 22 / 28), generous space on an 8 px grid, one prominent action per screen, details on tap (pushed views, segmented controls, sheets).
3. **The 3D and exhibits stay, and only show real rows.** They appear as the hero or on interaction, never as decoration.
4. **Three type voices, one job each:** the display serif (Newsreader) for large titles and the verdict; the system sans for everything you read; mono **only** for ids (`D01`, `PR-412`, `p_gateway_limit`). No uppercase mono labels, no letter-spaced caps: use `.t-footnote` / `.t-eyebrow` sentence case instead.
5. **Say it once.** A verdict appears once per screen as a pill (or one solid pill on a detail page). The gate appears as one row. No repeated badges, field lists that restate the sentence, or docket strips.
6. **Colour is meaning:** paper and ink everywhere; brick red only for Moot / Deny / expired / contradicting evidence and the single write action; green and amber only inside pills. The landing page has exactly two coloured bands: the red "blast radius" band and the dark "drawing" band.
7. **Motion only when it means something:** on arrival, hover, drag or a step. No ambient loops. Respect reduced motion.

## Tokens and primitives
- `frontend/src/app/globals.css` (light and dark): `--ground` (app background), `--surface` (cards, list groups), `--surface-2` (a group inside a card), `--fill` (search, segmented, neutral pill), `--separator`, `--label/-2/-3`, tints `--moot-tint/--moot-ink`, `--holds-*`, `--disputed-*`, `--neutral-*`, `--night*` (the dark drawing band), radii `--r-sm 10 / --r-group 14 / --r-card 22 / --r-hero 28 / --r-pill`. Type ramp: `.t-hero .t-display .t-large .t-title1 .t-title2 .t-title3 .t-headline .t-body .t-callout .t-sub .t-footnote .t-caption .t-eyebrow .t-lead`, `.lead-in` (bold lead phrase), `.id` (mono id). Buttons: `.btn` (ink capsule), `.btn.ghost` (fill capsule), `.btn.accent` (the one write action), `.btn.plain` (text button in accent), `.link`.
- `frontend/src/components/ui/index.tsx`: `Pill`, `VerdictBadge` (sentence-case pill; `fill` = solid, once per screen), `GateBadge`, `StateTag`, `PathChain`, `decidingEvent`, `SectionHead`, `Wordmark`, `Docket` (a calm stat row), `ThemeToggle`, `Group` + `Row` (inset grouped list; `href` uses next/link), `Card`, `Segmented`, `SearchField`, `StatCard`, `Sheet`, `VERDICT_WORD`, `GATE_WORD`, `STATE_WORD`, `cx`.

## 3D rules
- Isometric line drawing, not blobs: thin ink lines, flat paper faces, one accent for what is contradicted. Orthographic camera at a fixed isometric angle; orbit is limited and optional.
- Every shape comes from a row the API returned (a decision, premise, evidence edge). If a shape cannot be traced to a row it is decoration and goes.
- An expired reason is drawn as an unplugged cable. Callouts with hairline leaders cite evidence ids and dates.
- Always lazy-loaded and client-only; the page must read correctly before the canvas arrives.

## Landing page `/`, in order (one idea per viewport)
1. **Nav**: blurred bar, wordmark, four quiet links, one ink capsule "Open the ledger".
2. **Hero**: eyebrow, the headline (hero size, centred), one lead sentence, "Open the ledger" + "See how it works ›". Below it the **3D ruled ledger** in a borderless rounded frame, with a one-line caption and a small scrubber.
3. **How it works**: left, "Every rule has a reason. Reasons expire." and a short story with a bold lead-in ending "So the rule is [Moot]"; right, the **D01 record chain** (decision → reason → reason behind it ← PR-412), built step by step.
4. **Blast radius (red band)**: the D01 line drawing (expired reason dashed, D02 and D03 falling) beside "One reason breaks. Three rules fall."
5. **The drawing (dark band)**: "Every verdict comes with its drawing.", then the **isometric 3D graph of D01**, interactive.
6. **Proof**: one keynote number, three quiet stat cards and one footnote with the method and the synthetic-data note. All numbers from `/api/evals`.
7. **Agents ask first**: a quiet card "Can an agent act on Cap file uploads at 10 MB?" → Deny pill, two reasons, the one call `GET /api/gate/D01` / MCP `check_action`.
8. **Try it**: the live ask box in a calm framed window; the answer inline.
9. **Real world**: an inset grouped list of five public records and "See all 25 records ›".
10. **Footer**: "Ask why your team does something." + capsule, the **extruded M~~oo~~t wordmark**, one quiet line of links and the disclosure.

## App `/app/` (grouped background `--ground`)
- **Ask** (`/app/`, the front door): one search bar on an empty page, six example questions, one quiet line of counts. A question picks one read-only tool (`POST /api/answer`: rules, or a model choosing from the same list) and the page shows the tool step (tool, why, input, every query with rows and time; Running, then Completed) and the one component that fits that tool: the decision panel, the gate card, the what-if wiring, the owner ID card, the exhibit cards, the re-open memo with its approval, or a ledger list. Then "Ask next" follow-ups that name their tool. The question lives in the URL (`?q=`), so Back and links work; `?d=D01` opens that decision's panel. Say "Nothing in the graph matches" plainly; never guess.
- **Shell**: quiet top bar: wordmark, segmented-style nav (Ask, Ledger, Agent gate, Owners, What-if, Real world), an "As of" capsule menu (date + depth), theme toggle. On phones the nav scrolls sideways.
- **Ledger** (`/app/ledger/`, for browsing everything; questions go to Ask): large title; three `StatCard`s (Moot with a rot sparkline, Disputed, Holds; tap to filter); the full rot chart in a sheet; the ledger as `Group`s per verdict.
- **Decision** (right on desktop, pushed view on phone): id and system, large serif title, one solid verdict pill, **one plain sentence** that says why, one grey line. Then the **isometric drawing as the hero** ("Explore in 3D ›"), and a `Segmented` control: Summary / Graph / Steps / Queries. Summary = "Why it was made" (reasons as rows, deeper reasons inset), "The evidence" (the **exhibit cards**, flip to read), "Can an agent act on it?" (one row), "Also resting on this reason". One prominent action: "Re-open with <name>…", which opens the re-open memo in a sheet with Approve / Cancel.
- **Agent gate**: summary sentence, three `StatCard`s, grouped lists per outcome, "Ask it yourself" as a quiet card.
- **Owners**: per leaver one calm card with the **ID card** (LEFT stamp) and the reporting line; decisions as rows with their **lanyard badge** (drag to hand over); approval in a sheet.
- **What-if**: search field; "If … broke today, N standing decisions would fall."; the unplugged-cable figure; riskiest reasons as a grouped list.
- **Real world**: one sentence, stat row, filter `Segmented`, grouped list of 25.
- **Empty states**: small wireframe machine drawings, centred, sentence-case copy.

Do: show the path for every verdict; say "not in the graph" plainly; keep one hero per screen.
Don't: force-directed graph blobs, brain icons, glowing gradients, cards inside cards, a second accent, numbers the API did not return.
