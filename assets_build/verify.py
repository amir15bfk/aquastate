import imageio_ffmpeg
import subprocess
import os
import re
from PIL import Image, ImageDraw, ImageFont

ff = imageio_ffmpeg.get_ffmpeg_exe()
master = "video/AquaState_30s_1080p.mp4"

p = subprocess.run([ff, "-hide_banner", "-i", master], capture_output=True, text=True)
print(p.stderr[:1200])

p = subprocess.run(
    [ff, "-hide_banner", "-i", master, "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
    capture_output=True, text=True,
)
txt = p.stderr
for pat, label in [(r"I:\s+(-?[\d.]+) LUFS", "integrated"), (r"Peak:\s+(-?[\d.]+) dBFS", "true peak"), (r"LRA:\s+(-?[\d.]+) LU", "LRA")]:
    m = re.findall(pat, txt)
    print(label, m[-1] if m else "?")

# contact sheet from the encoded master
times = [0.8, 2.4, 4.8, 7.2, 9.8, 12.8, 14.8, 17.4, 19.8, 22.8, 25.6, 28.8]
os.makedirs("assets_build/verify", exist_ok=True)
for t in times:
    subprocess.run(
        [ff, "-y", "-hide_banner", "-ss", str(t), "-i", master, "-frames:v", "1",
         f"assets_build/verify/v_{t}.png"],
        capture_output=True,
    )

cols, rows = 3, 4
tw, th = 560, 315
sheet = Image.new("RGB", (cols * tw, rows * th), (12, 16, 18))
d = ImageDraw.Draw(sheet)
font = ImageFont.truetype("assets_build/fonts/jetbrains-mono-400.ttf", 16)
for i, t in enumerate(times):
    im = Image.open(f"assets_build/verify/v_{t}.png").resize((tw, th), Image.LANCZOS)
    x, y = (i % cols) * tw, (i // cols) * th
    sheet.paste(im, (x, y))
    d.text((x + 12, y + th - 28), f"{t:.1f}s", font=font, fill=(94, 234, 212))
sheet.save("assets_build/verify/contact_sheet_final.jpg", quality=90)
print("wrote assets_build/verify/contact_sheet_final.jpg")
