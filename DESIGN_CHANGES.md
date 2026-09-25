# Design Changes

Reference: `design/Veyro.bundle.html` (original), unpacked to `design/_src/`. The concept is kept exactly: a cosy light pixel office, the same 8 animals and names, the same dialogue-box style, the same palette family and the same flow. Only the execution changed.

| # | Area | Before | After | Why |
|---|---|---|---|---|
| 1 | Sprites | 21×23 art; Tank had no shell; Pip read as a red blob with a dark X; Bolt read as a child with antennae; the eye shine was mirrored (cross-eyed) | Original 24×26 redraw from shared data: Tank has a visible shell **and a yellow safety helmet** (the risk officer); Pip has a hooked cream beak, white face patches and blue wing hands; Bolt has thick curved horns and a nose ring; Leo has a crown and mane; the eye shine is consistent | Sprites didn't read clearly as their animal |
| 2 | Expressions | Blink only | Blink, talking mouth, **happy (^^ + blush)** and **worried (raised brows + sweat drop)** overlays | Needed for market-mood reactions |
| 3 | Layout | Leo's desk sat on top of the whiteboard; the dialogue box covered the back row's name plates and roles | Leo sits at a gold-trimmed head desk under the board; the back row moved to y=342; the dialogue box sits at y=578 | Overlapping elements |
| 4 | Stray element | A leftover "Your text here" label | Removed | Artifact of editing |
| 5 | Roles | English role labels under Arabic UI | Roles in the screen's language | Language purity |
| 6 | Emote bubble | Above the head, colliding with the row above when hopping | Beside the head | Overlap |
| 7 | Whiteboard | A decorative static line | A real 3-month close chart (Yahoo), ▲/▼ with the real % change and date, and a DEMO tag moved to the corner | No fabricated data; the old DEMO tag overlapped the % chip |
| 8 | Clock | Decorative | **New York market time**; the ring is green when the market is open and red when closed, with a label | Everything linked to the market (owner's request) |
| 9 | Windows/plants | Always sunny | Sunny with a pulsing sun on a rally; grey clouds when down; **rain** in a slump; plants droop when down; night gives a moon and stars | Market mood |
| 10 | Night mode | None | A full night palette; laptops glow; warm lamp light on the floor | Owner's request (day/night) |
| 11 | Start | Instant | Lights flicker on, a ticker banner drops in, a jingle plays | "Satisfying start sequence" |
| 12 | Motion | Fixed | Calm/Normal/Lively intensity; `prefers-reduced-motion` and an in-app toggle stop every animation (static frames stay readable) | Long sessions and accessibility |
| 13 | Contrast | White text on light fills (e.g. the start button, the green "save") | Dark-brown text on orange (#3B2410 on #F2A43A) and dark green on mint; darker muted text (#7A6147) | WCAG AA |
| 14 | Header | Provider pill "online" (not real) | Real market status chip, execution mode badge (PAPER/MOCK/LIVE), language, day/night and sound buttons | No fake status |
| 15 | Screens | Office only | Office, Report, History (honest scoreboard vs SPY), Orders (optional execution) and Settings/About, all in both languages | Brief |
| 16 | RTL | Mixed | `dir` and `lang` follow the language; numbers, tickers and prices are isolated LTR runs; the room stage is a fixed LTR scene scaled to fit | RTL bugs |
| 17 | Mobile | Fixed 1440 px | The stage scales to width; the side panel stacks; no horizontal scroll at 390 px | Responsive |

Design canvas (for review): https://claude.ai/artifact/UEdaF56Hd31MFqbFFbbySu. It has these artboards: Office in Arabic by day (interactive), Office in English at night (interactive), Cast, Report, History and Settings/About.

## Later additions (owner feedback)
| # | Area | Before | After | Why |
|---|---|---|---|---|
| 18 | New character | 8 characters | **Albie**, an albatross news courier (aviator cap, goggles, long hooked bill, navy courier vest), on his own "World news" page. He glides past the office windows with a newspaper and flies in to perch on the whiteboard for his "global link" before each verdict | Owner request |
| 19 | Walking | None | Walking frames with alternating legs; Leo, Tank, Pip and Benny stroll their screens | Owner request |
| 20 | Walking bug | Characters seemed to grow and shrink | Two causes fixed: (a) the second walking frame's class `wb` collided with the whiteboard class `.wb`, so every other step inherited 340×122 px; renamed to `wka`/`wkb`. (b) The turn-around flip was animated across the whole walk, squashing the sprite; flipping was removed. The walker is now a constant 72×78 px (measured in the browser) | "Some characters grow and shrink" |
| 21 | Simplicity | Every option on the Settings screen | The analyst team, extra data sources and Alpaca execution are folded under "Advanced settings (optional)"; Leo's 3-step first-visit guide | "I want it easy and fun" |
| 22 | Hidden screens | The Office stayed rendered under other screens (`.stack{display:flex}` overrode `[hidden]`) | `[hidden]{display:none!important}` | Other screens were appearing below the office |
| 23 | About | The full license text was expandable | Veyro's own story with 9 characters, plus a one-line credit to TradingAgents (Apache-2.0 requires attribution) | Owner request |
