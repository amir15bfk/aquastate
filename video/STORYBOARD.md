# AquaState — 30s storyboard

Format: 1920×1080, 30 fps, 30.00 s, H.264/AAC.
Cut points are word-boundary hits from the narration (edge-tts timings).

| # | In | Out | Picture | On-screen text | Voice |
|---|---|---|---|---|---|
| 1 | 0.00 | 1.49 | NASA Blue Marble 2012 on black, slow push-in; thin cyan rule. | `01 — ORIGIN` · **Water shaped the world.** · `H₂O · 71% OF EARTH'S SURFACE` | Water shaped the world. |
| 2 | 1.49 | 3.73 | Nile at night from the ISS; city lights trace the river; Soyuz frames the top. Text lower-right over dark ocean. | `02 — CIVILIZATION` · **Every civilization grew along a river.** · `CITY LIGHTS ALONG THE NILE` · `NASA / ESA · S. ADENOT · ISS` | Every civilization grew along a river. |
| 3 | 3.73 | 6.15 | Lake Mead 2021, receding shoreline; warm grade, slow reveal. | `03 — CLIMATE CHANGE / DROUGHT` · **A changing climate is rewriting the map.** | A changing climate is rewriting the map. |
| 4 | 6.15 | 8.61 | Same Lake Mead shot; first headline fades, second replaces it. | **Some farmers find** / **no water.** (amber) | Some farmers find no water. |
| 5 | 8.61 | 11.44 | FEMA aerial: farm buildings under Mississippi floodwater, cool grade, push-in. Text in the lower water area. | `04 — FLOOD` · **Elsewhere, floods take the harvest — and the city.** · `MISSISSIPPI RIVER · 2008 · FEMA` | Elsewhere, floods take the harvest, and the city. |
| 6 | 11.44 | 16.10 | Cut to black; wordmark and wave mark. WCRI ring draws to 61.5 at right; ghost world map behind. | `AquaState / THE WATER LEDGER` · `NASA EARTH DATA / ONE INDEX` · **Water-Climate Resilience Index** · `WCRI-2.0` · `61.5 / 100` · `GLOBAL AVERAGE · WCRI-2.0` · `249 COUNTRIES SCORED · 82,394 DAMS CATALOGUED` | AquaState turns NASA's Earth data into one Water-Climate Resilience Index. |
| 7 | 16.10 | 21.85 | World dashboard, slow pan from the choropleth to the country ledger. Big data beats on the left. | `THE PLANET, IN ONE LEDGER` · **249** COUNTRIES SCORED · **4** LIVE PRESSURES (Drought 50 / Flood 32 / Wildfire 26 / Desertification 34) · **82,394** DAMS CATALOGUED · `172 COUNTRIES · 33 MONITORED` | 249 countries. Four live pressures. 82,394 dams. |
| 8 | 21.85 | 23.51 | Hard cut to the light Algeria country sheet; slow push to the index card. Dark lower-third. | `COUNTRY SHEET / ALGERIA` · **45.6** `/ 100 · WCRI-2.0` · `WATCH · RANK 232 OF 249` | Your country. Your number. |
| 9 | 23.51 | 26.42 | Beni Haroun dam page; ring 81.0. At "are we covered", the page dims and the question appears. | `THE ONE QUESTION` · **Are we covered / until the next rain?** · `38.6 TO 83.3 / BUFFER 0.950 / +1 DAY TO RAIN` | One screen answers: are we covered until the next rain? |
| 10 | 26.42 | 30.00 | End card: wave mark + wordmark, tagline, thin rule, four pressures, NASA Space Apps Challenge, credits. Fade to black. | **AquaState** · `THE WATER LEDGER` · **Water is the secret of life. This is its ledger.** · `DROUGHT · FLOOD · WILDFIRE · DESERTIFICATION` · `NASA SPACE APPS CHALLENGE` · `AQUASTATE · WORLD WATER & CLIMATE OBSERVATORY` · credits | AquaState. Water is the secret of life. This is its ledger. |

## Visual rules

- The app's palette: carbon `#080E10`, ivory `#F2F8F6`, petrol-mint
  `#5EEAD4`, amber `#F6BE5C`, coral `#FF7864`.
- Type: Instrument Sans for speech, JetBrains Mono for data and captions.
- Motion: slow pushes/pans only; text rises 14–16 px and fades over
  0.4–0.55 s. Hard cuts on sentence starts; a 0.3 s dip to black before
  the product reveal and the end card.
- Grain and vignette are applied globally to unify the app screens and the
  satellite photography.

## Data shown

WCRI-2.0 snapshot `wcri-20261115002208`, 15 Nov 2026:
249 countries scored · 70 resilient / 108 stable / 62 watch / 9 stressed /
0 critical · average 61.5 · 82,394 catalogued dams · 33 monitored ·
200 active events.

Algeria: WCRI 45.6 (Watch), rank 232/249, drought 56, flood 0, wildfire 15,
desertification 67, confidence 0.72.

Beni Haroun: DRI 81.0 (Recharging), observed 38.6, projected +14 d 83.3,
buffer bridge Φ 0.950, autonomy 27.0 d, first rain +1 d.
