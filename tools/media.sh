#!/usr/bin/env bash
# Copies and compresses the real media used on the site. Sources are read-only; nothing is moved.
set -euo pipefail
SITE=/home/adem/Desktop/adem_batur_site
IMG=$SITE/public/assets/img
VID=$SITE/public/assets/video
mkdir -p "$IMG" "$VID"

DOT=/home/adem/Desktop/Dotnote_Tanitim_Videosu/Dotnote_Tanitim_v4.mp4
NUR="/home/adem/Desktop/teknofest/havacılıkta yapay zeka/results/oturum4/nuron_sonuc_rgb_OTURUM4_2026-09-20.mp4"

clip () { # src start dur name crf_h264 crf_vp9
  local src=$1 ss=$2 t=$3 name=$4 crf=$5 vcrf=$6
  ffmpeg -v error -y -ss "$ss" -t "$t" -i "$src" -an \
    -vf "scale=1280:-2:flags=lanczos,fps=30" -c:v libx264 -preset slow -crf "$crf" -pix_fmt yuv420p \
    -profile:v high -level 4.0 -movflags +faststart "$VID/$name.mp4"
  ffmpeg -v error -y -ss "$ss" -t "$t" -i "$src" -an \
    -vf "scale=1280:-2:flags=lanczos,fps=30" -c:v libvpx-vp9 -b:v 0 -crf "$vcrf" -row-mt 1 -deadline good -cpu-used 2 \
    "$VID/$name.webm"
  ffmpeg -v error -y -ss "$ss" -i "$src" -frames:v 1 -vf "scale=1280:-2:flags=lanczos" "$VID/$name.poster.png"
}

clip "$DOT" 9   14 dotnote_write 27 36
clip "$DOT" 202 14 dotnote_logo  27 36
clip "$NUR" 28  12 nuron_session4 29 37

ls -la "$VID"
