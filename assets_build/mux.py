import imageio_ffmpeg
import subprocess
import os

ff = imageio_ffmpeg.get_ffmpeg_exe()
sil = "assets_build/out/aquastate_silent.mp4"
mix = "assets_build/audio/mix.wav"
out = "assets_build/out/aquastate_30s.mp4"

cmd = [
    ff, "-y", "-hide_banner", "-i", sil, "-i", mix,
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
    "-movflags", "+faststart",
    "-metadata", "title=AquaState - The Water Ledger",
    "-metadata", "comment=NASA Space Apps Challenge 2026 - AquaState",
    "-metadata", "artist=AquaState",
    out,
]
p = subprocess.run(cmd, capture_output=True, text=True)
print("mux return", p.returncode)
print(p.stderr[-1200:])
print("size MB", round(os.path.getsize(out) / 1024 / 1024, 2))

p = subprocess.run([ff, "-hide_banner", "-i", out], capture_output=True, text=True)
print(p.stderr[:1600])

for t in [1.5, 11.45, 16.1, 21.85, 23.51, 26.42]:
    subprocess.run(
        [ff, "-y", "-hide_banner", "-ss", str(t), "-i", out, "-frames:v", "1",
         f"assets_build/out/frame_{t}.png"],
        capture_output=True,
    )
print("frames done")
