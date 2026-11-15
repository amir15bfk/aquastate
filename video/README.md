# AquaState — 30-second hackathon film

**"Water is the secret of life. This is its ledger."**

A 30.00-second, 1920×1080, 30 fps film for the AquaState / NASA Space Apps
Challenge pitch. It opens on the idea that water shaped civilization, turns
through drought and flood, then lands on the app and its WCRI-2.0 index —
down to one country and one dam — before the end card.

## Files

| File | Use | Size |
|---|---|---|
| `AquaState_30s_1080p.mp4` | master, 1080p, high bitrate | ~99 MB |
| `AquaState_30s_1080p_web.mp4` | upload / share, 1080p | ~33 MB |
| `AquaState_30s_720p.mp4` | social / low-bandwidth | ~5 MB |
| `AquaState_poster.jpg` | thumbnail / cover frame | ~0.14 MB |

All versions are 30.00 s, H.264 High, yuv420p, AAC 48 kHz stereo.

## The cut

| Time | Picture | Voiceover |
|---|---|---|
| 0.00–1.49 | NASA Blue Marble, slow push. "Water shaped the world." | Water shaped the world. |
| 1.49–3.73 | Nile at night from the ISS; city lights trace the river. | Every civilization grew along a river. |
| 3.73–6.15 | Lake Mead 2021, receding shoreline. | A changing climate is rewriting the map. |
| 6.15–8.61 | Same shot, second thought. | Some farmers find no water. |
| 8.61–11.44 | FEMA aerial of flooded farmland, Mississippi 2008. | Elsewhere, floods take the harvest, and the city. |
| 11.44–16.10 | Brand reveal and WCRI ring counting to 61.5. | AquaState turns NASA's Earth data into one Water-Climate Resilience Index. |
| 16.10–21.85 | The world dashboard: 249 countries, 4 pressures, 82,394 dams. | 249 countries. Four live pressures. 82,394 dams. |
| 21.85–23.51 | Algeria country sheet, WCRI 45.6, Watch. | Your country. Your number. |
| 23.51–26.42 | Beni Haroun dam, DRI 81.0, Recharging — then the question. | One screen answers: are we covered until the next rain? |
| 26.42–30.00 | End card: wordmark, tagline, NASA Space Apps Challenge, credits. | AquaState. Water is the secret of life. This is its ledger. |

The edit is cut to the voiceover's word-boundary timings, so each picture
change lands on the first word of its sentence.

## Voiceover

See `VOICEOVER.txt` for the full script and exact timings.

## How it was made

- **App screens:** real 4K captures of the running app (`world`, `country/DZ`,
  `dam/beni-haroun`) at 3840×2160, captured with Playwright + Microsoft Edge.
- **Typography:** the app's own Instrument Sans and JetBrains Mono, converted
  from the bundled woff2 files. No substitute fonts.
- **Palette:** sampled from the app's dark world sheet and light country sheet.
- **Imagery:** NASA/ESA and FEMA public-domain stills (see `CREDITS.md`).
  Motion is applied as slow pushes/pans (Ken Burns), not third-party video
  clips. This is deliberate: it keeps every visual traceable and
  license-clean.
- **Voice:** edge-tts, `en-US-AndrewNeural`, rate +10%, pitch −2 Hz. The
  narration ends at 29.81 s.
- **Score:** original 30 s cue, synthesized in NumPy/SciPy (D minor tension
  resolving to D major). No library music.
- **Renderer:** custom Python/Pillow compositor, piped raw frames to ffmpeg,
  encoded with libx264 at CRF 16 for the master.
- **Data snapshot:** WCRI-2.0, 15 Nov 2026 — 249 countries scored, 82,394
  catalogued dams, 33 monitored, 200 active events, global average 61.5;
  Algeria 45.6 Watch; Beni Haroun 81.0 Recharging.

## Regenerating

From the `aquastate-world/` directory:

```powershell
# 1. (optional) re-capture the app screens
python manage.py runserver 127.0.0.1:8010
# then run the Playwright capture script in assets_build/ (shots are included)

# 2. render the picture
python assets_build/film.py --render --out assets_build/out/aquastate_silent.mp4

# 3. render the score
python assets_build/score.py

# 4. mix, mux and publish all three sizes
python assets_build/finalize.py
```

`assets_build/film.py --stills 0.9,13.8,28.6` renders individual frames for
quick checks.

## A note on claims

The film says "NASA's Earth data" because NASA POWER / MERRA-2 and NASA
EONET are core inputs. The app also uses Open-Meteo GloFAS, the World Bank
and Wikidata; the end card names them. The film does not claim NASA
endorsement, and the app is a screening decision aid, not an operational
warning system.
