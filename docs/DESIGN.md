# Design

Mission-control console. The globe is the hero. Color means something. Nothing is decorative.

## Tokens

Implemented in `frontend/css/tokens.css`.

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#05070a` | Page |
| `--panel` | `#0a0e13` | Rails, header, timeline |
| `--panel-raised` | `#0f141b` | Cards |
| `--line` / `--line-strong` | `#1b222c` / `#2a3340` | Hairline borders |
| `--text` / `--text-2` / `--text-3` | `#e6eaf0` / `#8a94a3` / `#545e6c` | Copy |
| `--accent` | `#e6eaf0` | Primary actions, focus |
| `--coverage` | `#5ac8fa` | Systematic swaths |
| `--possible` | `#5ac8fa66` | Tasked, always hatched |
| `--gap` | `#f5a524` | Coverage holes |
| `--matched` | `#3dd68c` | AIS-matched detections |
| `--unmatched` | `#ff4d4f` | Potential dark vessels |
| `--protected` | `#9b8afb` | MPA outline only |
| `--font-ui` | Inter | Labels |
| `--font-data` | JetBrains Mono | Numbers, UTC |
| `--radius` | `2px` | Almost square |
| `--ease` | `cubic-bezier(.2,0,0,1)` | Camera 2.5 s |

Numbers use `font-variant-numeric: tabular-nums`. Micro labels are 10px, uppercase, letter-spacing 0.12em.

## Layout

Top bar 44px: `DARKWATCH`, modes `01 ORBIT` … `04 ANALYSIS`, UTC clock, `LIVE`/`SIM` badge, speed, status dot.

Rails 240px / 360px. `[` and `]` collapse them. Timeline 128px with a canvas: 48 h, systematic ticks, hatched gaps, `OBSERVED` marker, playhead. Drag to scrub (pauses; release resumes).

HUD, bottom-left over the globe: cursor lat/lon, camera altitude, provenance chips (`LIVE`, `SNAPSHOT …`, `SCENE PACKAGED`). Cesium credits stay visible, restyled `--text-3`.

## Globe

Esri World Imagery at brightness 0.55, saturation 0.25, contrast 1.15. Toggle to a dark Carto vector basemap. Lighting on. Fog off.

Systematic missions: diamonds + mono labels. Tasked fleets: 3px dots at 50% opacity, labels on hover. Selected satellite: corner-bracket reticle, not Cesium's default indicator. Swaths: 10% fill, 1px edge; tasked strips hatched and labeled `POSSIBLE`. Detections: rings. MPAs: outline only.

## Clock

Default 1× locked to wall-clock UTC (`LIVE`). Speeds 1 / 10 / 60 / 300. Any other speed, pause, or >5 s offset → `SIM` and `T+hh:mm:ss`. `L` returns to live. Coverage and swath requests pass the clock time, not `Date.now()`.

## Copy

Short, factual, no exclamation marks. Labels uppercase; sentences in sentence case. "Potential dark vessel" means not matched to public AIS. If the intent baseline `p_value` is above 0.05, the analysis panel says the sample does not show a pattern beyond chance.

## Anti-patterns (do not reintroduce)

No emojis, gradient buttons, glassmorphism, drop-shadow glows, purple-to-blue "AI" palette, rounded-2xl cards, sparkle icons, placeholder copy, bouncy animation, default Cesium chrome, numbers without units.
