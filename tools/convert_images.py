#!/usr/bin/env python3
"""Convert the selected source images to WebP (<= 300 KB each). Sources are never modified."""
import os
import shutil
from PIL import Image

SITE = "/home/adem/Desktop/adem_batur_site"
IMG = f"{SITE}/public/assets/img"
VID = f"{SITE}/public/assets/video"
os.makedirs(IMG, exist_ok=True)

TEK = "/home/adem/Desktop/teknofest/havacılıkta yapay zeka"
REPO = "/home/adem/Desktop/teknofest/nuron-teknofest-2026"
PLAY = "/home/adem/Desktop/Dotnote_Play_Yukle"
SCR = "/tmp/claude-1000/-home-adem/b3309163-9d43-4e1f-806d-95f370bc55e7/scratchpad"

JOBS = [  # (src, dst name, max width)
    (f"{PLAY}/5_tablet10_ekranlari/01_pdf_handwriting.png", "dotnote_pdf_handwriting", 1400),
    (f"{PLAY}/5_tablet10_ekranlari/03_audio_on_page.png", "dotnote_audio_on_page", 1400),
    (f"{PLAY}/5_tablet10_ekranlari/05_split_view.png", "dotnote_split_view", 1400),
    (f"{PLAY}/5_tablet10_ekranlari/08_dark_mode.png", "dotnote_dark_mode", 1400),
    (f"{PLAY}/2_one_cikan_grafik/feature_graphic_1024x500.png", "dotnote_feature", 1024),
    (f"{PLAY}/1_uygulama_simgesi/icon_512.png", "dotnote_icon", 512),
    (f"{REPO}/assets/session4_poster.jpg", "nuron_poster", 1600),
    (f"{REPO}/results/session4/trajectory_xy.png", "nuron_traj_xy", 1400),
    (f"{REPO}/results/session4/trajectory_3d.png", "nuron_traj_3d", 1400),
    (f"{TEK}/COMPTETITION/SUNUM_NURON_V2/sekil/sekil_g2_hata.png", "nuron_gps_error", 1600),
    (f"{TEK}/COMPTETITION/SUNUM_NURON_V2/sekil/d1_uctanuca.png", "nuron_pipeline", 1800),
    (f"{SCR}/gh_imgs/plate_sample_result.jpg", "plate_sample", 800),
    (f"{SCR}/gh_imgs/lp85_frame.png", "arc_lp85", 1200),
    ("/home/adem/Desktop/linkedin_profil/linkedin_kapak_1584x396.png", "banner", 1584),
    ("/home/adem/Desktop/linkedin_profil/profil_fotografi.jpg", "portrait", 720),
    (f"{VID}/dotnote_write.poster.png", "poster_dotnote_write", 1280),
    (f"{VID}/dotnote_logo.poster.png", "poster_dotnote_logo", 1280),
    (f"{VID}/nuron_session4.poster.png", "poster_nuron_session4", 1280),
]


def to_webp(src, name, max_w, limit=300_000):
    im = Image.open(src)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    dst = f"{IMG}/{name}.webp"
    for q in (86, 80, 74, 68, 60, 52, 45):
        im.save(dst, "WEBP", quality=q, method=6)
        if os.path.getsize(dst) <= limit:
            break
    print(f"{name}.webp  {im.width}x{im.height}  q={q}  {os.path.getsize(dst)//1024} KB")


for src, name, mw in JOBS:
    if os.path.exists(src):
        to_webp(src, name, mw)
    else:
        print("MISSING", src)

# vector assets are copied as they are (tiny)
shutil.copy("/home/adem/Desktop/dark_mode.svg", f"{IMG}/github_card.svg")
shutil.copy(
    "/home/adem/Desktop/Apps/Dotnote_Logolar/1_simdiki_logo_I2_Parilti/store/icon_parilti_crisp.svg",
    f"{IMG}/dotnote_logo.svg",
)
# posters are kept only as webp
for p in ("dotnote_write", "dotnote_logo", "nuron_session4"):
    pp = f"{VID}/{p}.poster.png"
    if os.path.exists(pp):
        os.remove(pp)
print("done")
