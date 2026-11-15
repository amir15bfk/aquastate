import asyncio, json, sys, os
import edge_tts

TEXT = (
    "Water shaped the world. "
    "Every civilization grew along a river. "
    "A changing climate is rewriting the map. "
    "Some farmers search for water that never comes. "
    "Elsewhere, floods take the harvest, and the city. "
    "AquaState turns NASA's Earth data into one Water-Climate Resilience Index. "
    "249 countries. Four live pressures. 82,394 dams. "
    "Your country. Your number. "
    "One screen answers: are we covered until the next rain? "
    "AquaState. Water is the secret of life. This is its ledger."
)

VOICE = sys.argv[1] if len(sys.argv) > 1 else "en-US-AndrewNeural"
RATE = sys.argv[2] if len(sys.argv) > 2 else "+0%"
OUT = sys.argv[3] if len(sys.argv) > 3 else "assets_build/audio/vo"
PITCH = sys.argv[4] if len(sys.argv) > 4 else "+0Hz"

async def attempt():
    communicate = edge_tts.Communicate(
        TEXT, VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary"
    )
    words = []
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append({
                "text": chunk["text"],
                "offset_ms": chunk["offset"] / 10000.0,
                "duration_ms": chunk["duration"] / 10000.0,
            })
    return bytes(audio), words

async def main():
    last = None
    for i in range(6):
        try:
            audio, words = await attempt()
            if len(audio) > 50000 and words:
                os.makedirs(os.path.dirname(OUT), exist_ok=True)
                with open(OUT + ".mp3", "wb") as f:
                    f.write(audio)
                with open(OUT + "_words.json", "w", encoding="utf-8") as f:
                    json.dump(words, f, indent=1)
                print("voice", VOICE, "rate", RATE, "pitch", PITCH, "words", len(words), "bytes", len(audio))
                print("last end ms", round(words[-1]["offset_ms"] + words[-1]["duration_ms"], 1))
                print("first", words[0])
                print("last", words[-1])
                return
        except Exception as e:
            last = e
            print("attempt", i + 1, "failed:", type(e).__name__, str(e)[:120])
            await asyncio.sleep(1.5)
    raise SystemExit(f"failed: {last}")

asyncio.run(main())
