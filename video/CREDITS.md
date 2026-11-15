# Credits and source ledger

Every visual in the film is either the AquaState app itself or a credited
public-domain / NASA-ESA still. No stock video was downloaded.

## Imagery

### Blue Marble 2012
- **Frame:** opening Earth.
- **Source:** NASA/Goddard Space Flight Center, "Most Amazing High Definition
  Image of Earth — Blue Marble 2012", NASA Image ID
  `GSFC_20171208_Archive_e001386`.
- **Date:** 25 January 2012.
- **Credit:** NASA/Goddard Space Flight Center.
- **Terms:** NASA imagery; NASA does not copyright its images. Credit given.

### Nile River at night from the ISS
- **Frame:** "Every civilization grew along a river."
- **Source:** NASA/ISS photograph `iss075e0155946`, "City lights outline
  Egypt's Nile River and highlight its delta."
- **Date:** 26 September 2026.
- **Credit:** ESA / Sophie Adenot, via NASA.
- **Terms:** NASA image use policy; photographer credit given as supplied by
  NASA. The film caption reads `NASA / ESA · S. ADENOT · ISS`.

### Lake Mead, 2021
- **Frame:** drought / "A changing climate is rewriting the map" and
  "Some farmers find no water."
- **Source:** NASA/JPL-Caltech, "Lake Mead, 2021", NASA Image ID `PIA24696`.
- **Date:** 22 June 2021.
- **Credit:** NASA/JPL-Caltech.
- **Terms:** NASA/JPL imagery; credit given.

### Flooded farmland, Canton, Missouri
- **Frame:** "Elsewhere, floods take the harvest, and the city."
- **Source:** FEMA photo by Jocelyn Augustino, "Aerial of farm buildings under
  flood waters in Missouri", FEMA Photo Library #36452, via Wikimedia Commons.
- **Date:** 20 June 2008 (Mississippi River flood near Canton, MO).
- **Credit:** Jocelyn Augustino / FEMA.
- **Terms:** Public domain (U.S. Government work).
- **Note:** the on-screen caption is `MISSISSIPPI RIVER · 2008 · FEMA`. An
  earlier draft incorrectly said "Missouri River · 2011"; that was corrected
  before delivery.

## App screens

- **Source:** AquaState, WCRI-2.0 snapshot `wcri-20261115002208`,
  15 November 2026.
- **Pages:** `/` (world), `/country/DZ/` (Algeria), `/dam/beni-haroun/`.
- **Capture:** Playwright with Microsoft Edge, 1920×1080 CSS viewport at
  device scale factor 2 → 3840×2160 PNG.
- **Data shown:** 249 countries scored; global WCRI 61.5; 82,394 catalogued
  dams; 33 monitored; 200 active events; Algeria 45.6 Watch, rank 232/249;
  Beni Haroun DRI 81.0 Recharging, 38.6 observed → 83.3 projected,
  Φ 0.950, +1 day to rain.
- **Underlying data sources:** NASA POWER / MERRA-2, NASA EONET, Open-Meteo
  GloFAS and forecast, World Bank, Wikidata / Wikipedia, Natural Earth.
  These are named in the app's `/sources/` ledger and on the end card.

## Type

- **Instrument Sans** — SIL Open Font License 1.1. Bundled in the app.
- **JetBrains Mono** — SIL Open Font License 1.1. Bundled in the app.

## Voice

- Generated with **edge-tts** (Microsoft neural TTS), voice
  `en-US-AndrewNeural`, rate `+10%`, pitch `-2Hz`.
- Script is original, written for this film.

## Music

- Original 30-second cue synthesized from sine/additive/noise sources in
  NumPy and SciPy. No third-party music, samples or loops.
- Structure: D-minor drone and sparse piano → pulse on the flood → lift on the
  product reveal → D-major resolution on the end card.

## Software

- Python 3.14, Pillow, NumPy, SciPy, imageio-ffmpeg, Playwright, Microsoft Edge.
- ffmpeg / libx264 / AAC.
- Custom renderer: `assets_build/film.py`; score: `assets_build/score.py`;
  mix and publish: `assets_build/finalize.py`.

## Honesty note

AquaState is a screening decision aid, not an operational, safety or
investment tool. The film does not claim NASA endorsement. The hackathon
line on the end card is "NASA SPACE APPS CHALLENGE" — a challenge credit,
not an award claim.
