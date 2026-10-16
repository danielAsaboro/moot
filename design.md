# design.md

Brand feel: evidence, plain, unsentimental. A ledger, not a chat bubble.
Visual direction: editorial paper. Serif display (Iowan/Palatino) for titles, system sans for body, mono only for ids, dates and verdict badges.
References: a printed audit ledger; a newspaper correction box; a court docket.

Tokens (web/styles.css `:root`, light and dark): paper / paper-2 surfaces · ink / ink-2 / ink-3 text · rule for lines · chip for selection.
Colour discipline: ~85% neutral paper and ink, one accent. The accent (`--accent`, a brick red) means **MOOT / contradicted** only. It is never a general CTA except the single approval button, which is the one action that writes to the graph. HOLDS green and DISPUTED amber appear only inside badges and evidence rows.
Type scale: wordmark 40 / decision title 24 / section 22 / body 15 / meta 13 / mono 11–12.
Spacing 4px base; radius 6; no shadows; one-pixel rules.
Components: Ledger row (id, title, owner + systems, badge) · Verdict badge (outlined; filled only for the selected decision) · Path chain (Decision → Premise → … ← Evidence, the sponsor's work on screen) · Premise block (state, hops, evidence rows) · Draft ticket (mono, dashed box) · Approve button (accent).
Do: show the path for every verdict; say "not in the graph" plainly; keep the first screen to the one-liner, the ask box and the ledger.
Don't: force-directed graph blobs, brain icons, cards inside cards, a second accent.
