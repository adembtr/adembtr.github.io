#!/usr/bin/env python3
"""favicon.png (64) and apple-touch-icon.png (180): dark rounded square with the AB monogram."""
from PIL import Image, ImageDraw, ImageFont

OUT = "/home/adem/Desktop/adem_batur_site/public"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def icon(size, radius_ratio=0.24, out="favicon.png"):
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * radius_ratio), fill=(14, 18, 32, 255))
    font = ImageFont.truetype(FONT, int(s * 0.40))
    txt = "AB"
    bbox = d.textbbox((0, 0), txt, font=font)
    w, hh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (s - w) / 2 - bbox[0], (s - hh) / 2 - bbox[1]
    # gradient text: draw into a mask and paste gradient through it
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).text((x, y), txt, font=font, fill=255)
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for i in range(s):
        k = i / (s - 1)
        gd.line([(0, i), (s, i)], fill=(int(246 - 19 * k), int(203 - 49 * k), int(106 - 63 * k), 255))
    im.paste(grad, (0, 0), mask)
    im = im.resize((size, size), Image.LANCZOS)
    im.save(f"{OUT}/{out}")
    print("wrote", out)


icon(64, out="favicon.png")
icon(180, radius_ratio=0.2, out="apple-touch-icon.png")
