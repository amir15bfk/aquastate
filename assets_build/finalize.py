import imageio_ffmpeg
import subprocess
import os
import shutil

ff = imageio_ffmpeg.get_ffmpeg_exe()
outdir = "assets_build/out"
sil = os.path.join(outdir, "aquastate_silent.mp4")
mix = "assets_build/audio/mix.wav"
master = os.path.join(outdir, "AquaState_30s_1080p.mp4")
web = os.path.join(outdir, "AquaState_30s_1080p_web.mp4")
small = os.path.join(outdir, "AquaState_30s_720p.mp4")

# 1. mux master
cmd = [
    ff, "-y", "-hide_banner", "-i", sil, "-i", mix,
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
    "-movflags", "+faststart",
    "-metadata", "title=AquaState - The Water Ledger",
    "-metadata", "comment=NASA Space Apps Challenge 2026 - AquaState",
    "-metadata", "artist=AquaState",
    master,
]
p = subprocess.run(cmd, capture_output=True, text=True)
print("master", p.returncode, round(os.path.getsize(master) / 1048576, 1), "MB")

# 2. web 1080p
p = subprocess.run([
    ff, "-y", "-hide_banner", "-i", master,
    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
    "-c:a", "copy", "-movflags", "+faststart",
    "-metadata", "title=AquaState - The Water Ledger", web,
], capture_output=True, text=True)
print("web", p.returncode, round(os.path.getsize(web) / 1048576, 1), "MB")

# 3. 720p
p = subprocess.run([
    ff, "-y", "-hide_banner", "-i", master,
    "-vf", "scale=1280:720:flags=lanczos",
    "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-pix_fmt", "yuv420p",
    "-c:a", "copy", "-movflags", "+faststart",
    "-metadata", "title=AquaState - The Water Ledger", small,
], capture_output=True, text=True)
print("720", p.returncode, round(os.path.getsize(small) / 1048576, 1), "MB")

# 4. poster + key frame
for t, name in [(28.9, "AquaState_poster.jpg"), (13.8, "AquaState_index.jpg"), (0.9, "AquaState_earth.jpg")]:
    subprocess.run([ff, "-y", "-hide_banner", "-ss", str(t), "-i", master, "-frames:v", "1", "-q:v", "2", os.path.join(outdir, name)], capture_output=True)

# 5. publish folder
pub = "video"
os.makedirs(pub, exist_ok=True)
for f in [master, web, small, os.path.join(outdir, "AquaState_poster.jpg")]:
    shutil.copy2(f, os.path.join(pub, os.path.basename(f)))

print("\nPUBLISHED")
for f in sorted(os.listdir(pub)):
    print(" ", f, round(os.path.getsize(os.path.join(pub, f)) / 1048576, 2), "MB")

# probe master
p = subprocess.run([ff, "-hide_banner", "-i", master], capture_output=True, text=True)
for line in p.stderr.splitlines():
    if "Duration" in line or "Stream #" in line:
        print(line.strip())
