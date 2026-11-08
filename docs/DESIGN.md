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

Globe is edge-to-edge. Floating chrome only: wordmark, UTC, `LIVE`/`SIM`, speed. A left dock holds Kattegat, Satellites, AIS, Detections. Click a satellite or detection for a 280px card. Timeline is a 72px strip that appears after Kattegat: 48 h, systematic ticks, hatched gaps, one gap number. Drag to scrub.

HUD, bottom-left: cursor lat/lon, camera altitude, provenance chips (`SNAPSHOT …`, `SCENE PACKAGED`). Cesium credits stay visible, restyled `--text-3`.

## Globe

Esri World Imagery, lightly graded (brightness 1.02, saturation 0.92). Lighting on from altitude. Atmosphere `brightnessShift` −0.08. Fog off.

Satellites are a `PointPrimitiveCollection` updated on `scene.preRender`. Selected satellite: one orbit Primitive rotated by −ΔGMST, plus an approximate swath. No fleet labels. Detections: rings. MPAs: outline only.

## Clock

Default 1× locked to wall-clock UTC (`LIVE`). Speeds 1 / 10 / 60 / 300. Any other speed, pause, or >5 s offset → `SIM` and `T+hh:mm:ss`. `L` returns to live. Coverage and swath requests pass the clock time, not `Date.now()`.

## Copy

Short, factual, no exclamation marks. Labels uppercase; sentences in sentence case. "Potential dark vessel" means not matched to public AIS. That line lives on the unmatched detection card.

## Anti-patterns (do not reintroduce)

No emojis, gradient buttons, glassmorphism, drop-shadow glows, purple-to-blue "AI" palette, rounded-2xl cards, sparkle icons, placeholder copy, bouncy animation, default Cesium chrome, numbers without units.
