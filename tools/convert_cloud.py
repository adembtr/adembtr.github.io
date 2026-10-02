#!/usr/bin/env python3
"""tools/portrait_cloud.png (transparent screenshot of the WebGL cloud) -> public/assets/img/portrait_cloud.webp"""
import os
from PIL import Image

SRC = "/home/adem/Desktop/adem_batur_site/tools/portrait_cloud.png"
DST = "/home/adem/Desktop/adem_batur_site/public/assets/img/portrait_cloud.webp"
im = Image.open(SRC).convert("RGBA")
bbox = im.getbbox()
if bbox:
    im = im.crop(bbox)
side = max(im.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
done = False
for size in (1200, 1000, 880, 760):
    small = canvas.resize((size, size), Image.LANCZOS)
    for q in (78, 68, 58):
        small.save(DST, "WEBP", quality=q, method=6)
        if os.path.getsize(DST) <= 300_000:
            done = True
            break
    if done:
        break
print("portrait_cloud.webp", small.size, "q", q, os.path.getsize(DST) // 1024, "KB")
os.remove(SRC)
