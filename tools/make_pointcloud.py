#!/usr/bin/env python3
"""Build the coloured 3D point cloud used in the hero of adembtr.github.io.

Pipeline:  portrait photo
           -> person matte: BRIA RMBG-1.4 if available offline, else MediaPipe multiclass selfie
              segmenter, else a depth threshold; every matte is refined with GrabCut at full resolution
           -> monocular depth (Depth Anything V2; the cached checkpoint is used)
           -> nose-safe depth shaping (percentile clamp, soft knee, normalised smoothing)
           -> N coloured points -> compact binary for Three.js.

Binary format "ABPC":
    char[4]  magic "ABPC"
    uint32   point count
    float32  depth range used (informational)
    int16    x, y, z  * count      (divide by 32767 -> [-1, 1])
    uint8    r, g, b  * count

usage: make_pointcloud.py <photo> <out_dir> [preview_dir]
env:   DEPTH_MODEL (default depth-anything/Depth-Anything-V2-Metric-Outdoor-Large-hf)
       MP_MODEL    (path to selfie_multiclass_256x256.tflite)
"""
import os
import struct
import sys

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

SRC, OUT_DIR = sys.argv[1], sys.argv[2]
PREVIEW_DIR = sys.argv[3] if len(sys.argv) > 3 else OUT_DIR
DEPTH_MODEL = os.environ.get("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Metric-Outdoor-Large-hf")
MP_MODEL = os.environ.get("MP_MODEL", "")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(PREVIEW_DIR, exist_ok=True)
torch.manual_seed(7)
rng = np.random.default_rng(7)

img = Image.open(SRC).convert("RGB")
W, H = img.size
rgb_np = np.asarray(img)
bgr_np = cv2.cvtColor(rgb_np, cv2.COLOR_RGB2BGR)
print("image", W, H, flush=True)


# ----------------------------------------------------------------------------- depth (first: it is cached)
def run_depth(im):
    from transformers import pipeline

    pipe = pipeline("depth-estimation", model=DEPTH_MODEL, device=0, model_kwargs={"local_files_only": True})
    out = pipe(im)
    pd = out["predicted_depth"]
    if pd.ndim == 2:
        pd = pd[None, None]
    elif pd.ndim == 3:
        pd = pd[None]
    dep = F.interpolate(pd.float(), size=(H, W), mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
    metric = "Metric" in DEPTH_MODEL
    # make "near" large for both model families
    near = -dep if metric else dep
    return near, dep, metric


near, depth_raw, is_metric = run_depth(img)
print("depth:", DEPTH_MODEL, "metric" if is_metric else "relative", float(depth_raw.min()), float(depth_raw.max()), flush=True)
torch.cuda.empty_cache()


# ----------------------------------------------------------------------------- person matte
def seg_rmbg(im):
    from transformers import AutoModelForImageSegmentation

    m = AutoModelForImageSegmentation.from_pretrained("briaai/RMBG-1.4", trust_remote_code=True, local_files_only=True).cuda().eval()
    a = np.asarray(im.resize((1024, 1024), Image.BILINEAR), dtype=np.float32) / 255.0
    t = torch.from_numpy(a).permute(2, 0, 1)[None]
    t = (t - 0.5) / 1.0
    with torch.no_grad():
        r = m(t.cuda())
    mk = r[0][0] if isinstance(r, (list, tuple)) else r
    mk = F.interpolate(mk, size=(H, W), mode="bilinear", align_corners=False)[0, 0]
    mk = (mk - mk.min()) / (mk.max() - mk.min() + 1e-8)
    return mk.cpu().numpy()


def seg_mediapipe(im):
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    base = mp_python.BaseOptions(model_asset_path=MP_MODEL)
    opts = vision.ImageSegmenterOptions(base_options=base, running_mode=vision.RunningMode.IMAGE,
                                        output_category_mask=False, output_confidence_masks=True)
    with vision.ImageSegmenter.create_from_options(opts) as seg:
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb_np))
        res = seg.segment(mp_img)
        conf = [c.numpy_view().copy() for c in res.confidence_masks]
    bg = conf[0]  # 0 background, 1 hair, 2 body skin, 3 face skin, 4 clothes, 5 accessories
    person = 1.0 - bg
    if person.shape != (H, W):
        person = cv2.resize(person, (W, H), interpolation=cv2.INTER_LINEAR)
    return person.astype(np.float32)


def seg_depth(near_map):
    v = near_map.astype(np.float32)
    v = (v - v.min()) / (v.max() - v.min() + 1e-8)
    thr, _ = cv2.threshold((v * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (v * 255 > thr).astype(np.float32)


def grabcut_refine(alpha_coarse, work=1100, iters=4):
    """Refine a coarse matte with GrabCut on a downscaled image, then upsample."""
    scale = work / max(H, W)
    small = cv2.resize(bgr_np, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    a = cv2.resize(alpha_coarse, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_LINEAR)
    k = max(3, int(work * 0.035)) | 1
    fg = (a > 0.5).astype(np.uint8)
    sure_fg = cv2.erode(fg, np.ones((k, k), np.uint8))
    sure_bg = cv2.erode(1 - fg, np.ones((k, k), np.uint8))
    mask = np.full(a.shape, cv2.GC_PR_BGD, np.uint8)
    mask[fg == 1] = cv2.GC_PR_FGD
    mask[sure_fg == 1] = cv2.GC_FGD
    mask[sure_bg == 1] = cv2.GC_BGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(small, mask, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    out = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.float32)
    # keep only the biggest component (the bust) and fill holes
    n, lab, stats, _ = cv2.connectedComponentsWithStats(out.astype(np.uint8), 8)
    if n > 2:
        big = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        out = (lab == big).astype(np.float32)
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    out = cv2.resize(out, (W, H), interpolation=cv2.INTER_LINEAR)
    return np.clip(cv2.GaussianBlur(out, (0, 0), 1.6), 0, 1)


alpha_src = None
alpha = None
try:
    alpha = seg_rmbg(img)
    alpha_src = "RMBG-1.4"
except Exception as e:  # noqa: BLE001
    print("RMBG unavailable:", repr(e)[:160], flush=True)
if alpha is None and MP_MODEL and os.path.exists(MP_MODEL):
    try:
        alpha = seg_mediapipe(img)
        alpha_src = "MediaPipe selfie multiclass"
    except Exception as e:  # noqa: BLE001
        print("MediaPipe failed:", repr(e)[:160], flush=True)
if alpha is None:
    alpha = seg_depth(near)
    alpha_src = "depth threshold"
print("matte source:", alpha_src, "coverage", float((alpha > 0.5).mean()), flush=True)
# every matte gets the same colour-based refinement so hair edges are crisp
alpha = grabcut_refine(alpha)
print("matte refined, coverage", float((alpha > 0.5).mean()), flush=True)
cv2.imwrite(os.path.join(PREVIEW_DIR, "mask.png"), (alpha * 255).astype(np.uint8))

# ----------------------------------------------------------------------------- depth shaping
inside = alpha > 0.5
# remove most of the global lean (depth trend along y: chest near, crown far) so the relief
# describes the shape of the head and shoulders rather than the camera angle
yy = np.repeat(np.arange(H, dtype=np.float64)[:, None], W, axis=1)
A = np.stack([yy[inside], np.ones(int(inside.sum()))], axis=1)
coef, *_ = np.linalg.lstsq(A, near[inside].astype(np.float64), rcond=None)
near = near - (coef[0] * yy + coef[1]).astype(np.float32) * 0.8
print("lean removed: slope per px", float(coef[0]), flush=True)
p2, p98 = np.percentile(near[inside], [2, 98])
d = np.clip((near - p2) / (p98 - p2 + 1e-8), 0, 1)

# nose-safe shaping:
# 1) clamp the closest few percent (nose tip / chin) so nothing sticks out
p_top = np.percentile(d[inside], 94)
d = np.minimum(d, p_top) / max(p_top, 1e-6)
# 2) soft knee: compress the near range (face front) even further
knee = 0.62
near_mask = d > knee
d[near_mask] = knee + (d[near_mask] - knee) * 0.45
# 3) smooth the relief with a normalised convolution (background never bleeds in)
sigma = W / 110.0
num = cv2.GaussianBlur(d * alpha, (0, 0), sigma)
den = cv2.GaussianBlur(alpha, (0, 0), sigma) + 1e-6
d_smooth = num / den
d = np.clip(0.55 * d_smooth + 0.45 * d, 0, 1)

dep_vis = cv2.applyColorMap((d * 255).astype(np.uint8), cv2.COLORMAP_MAGMA)
dep_vis[~inside] = 0
cv2.imwrite(os.path.join(PREVIEW_DIR, "depth.png"), dep_vis)

# ----------------------------------------------------------------------------- sampling
DEPTH_RANGE = 0.50  # total z extent in units where the bust is 2 wide ("moderate depth")
ys, xs = np.nonzero(alpha > 0.35)
a = alpha[ys, xs]
yn = ys / (H - 1)
fade = np.clip((0.985 - yn) / 0.16, 0, 1)          # dissolve the hard bottom cut of the photo
fade = fade * fade * (3 - 2 * fade)
w = a * fade
w /= w.sum()

N_MAIN, N_MOBILE = 100_000, 30_000
idx = rng.choice(len(xs), size=N_MAIN, replace=False, p=w)
sx = xs[idx].astype(np.float32) + rng.uniform(-0.5, 0.5, N_MAIN)
sy = ys[idx].astype(np.float32) + rng.uniform(-0.5, 0.5, N_MAIN)
cx = np.clip(sx.round().astype(int), 0, W - 1)
cy = np.clip(sy.round().astype(int), 0, H - 1)

X = sx / (W - 1) * 2 - 1
Y = -(sy / (H - 1) * 2 - 1)
Z = (d[cy, cx] - 0.5) * DEPTH_RANGE

rgb = rgb_np.astype(np.float32)[cy, cx] / 255.0
lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
rgb = np.clip(lum[:, None] + (rgb - lum[:, None]) * 1.12, 0, 1)   # gentle saturation
rgb = np.clip((rgb - 0.5) * 1.06 + 0.5, 0, 1)                      # gentle contrast
rgb_u8 = (rgb * 255).round().astype(np.uint8)

order = rng.permutation(N_MAIN)  # the mobile LOD is simply the first 30k of a shuffled set
X, Y, Z, rgb_u8 = X[order], Y[order], Z[order], rgb_u8[order]


def write_bin(path, n):
    pos = np.stack([X[:n], Y[:n], Z[:n]], axis=1)
    pos_i16 = np.clip(pos * 32767, -32767, 32767).astype("<i2")
    with open(path, "wb") as f:
        f.write(b"ABPC")
        f.write(struct.pack("<I", n))
        f.write(struct.pack("<f", DEPTH_RANGE))
        f.write(pos_i16.tobytes())
        f.write(rgb_u8[:n].tobytes())
    print("wrote", path, os.path.getsize(path), "bytes", flush=True)


write_bin(os.path.join(OUT_DIR, "portrait_100k.bin"), N_MAIN)
write_bin(os.path.join(OUT_DIR, "portrait_30k.bin"), N_MOBILE)


# ----------------------------------------------------------------------------- preview render
def render(angle_deg, size=700):
    th = np.deg2rad(angle_deg)
    xr = X * np.cos(th) + Z * np.sin(th)
    zr = -X * np.sin(th) + Z * np.cos(th)
    canvas = np.zeros((size, size, 3), np.uint8)
    canvas[:] = (14, 12, 10)
    order_ = np.argsort(zr)
    px = ((xr * 0.92 + 1) * 0.5 * (size - 1)).astype(int)
    py = ((-Y * 0.92 + 1) * 0.5 * (size - 1)).astype(int)
    ok = (px >= 0) & (px < size) & (py >= 0) & (py < size)
    for i in order_[ok[order_]]:
        c = rgb_u8[i]
        cv2.circle(canvas, (int(px[i]), int(py[i])), 1, (int(c[2]), int(c[1]), int(c[0])), -1)
    return canvas


sheet = np.concatenate([render(-22), render(0), render(22)], axis=1)
cv2.imwrite(os.path.join(PREVIEW_DIR, "preview_views.png"), sheet)
print("preview written", flush=True)
