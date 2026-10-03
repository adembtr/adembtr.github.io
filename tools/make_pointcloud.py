#!/usr/bin/env python3
"""Build the full-3D coloured point cloud used in the hero of adembtr.github.io.

Pipeline:  portrait photo
           -> person matte + part masks (MediaPipe multiclass selfie segmenter; RMBG-1.4 if cached),
              refined with GrabCut at full resolution
           -> monocular depth (Depth Anything V2) -> nose-safe relief shaping
           -> closed volume: every silhouette row becomes an elliptical cross-section whose depth
              follows the part (head ~1.1 x half-width, neck ~0.95, torso ~0.5); the front sheet is
              modulated by the depth relief (nose, lips, eye sockets), the back sheet is the mirrored
              ellipse; side/back colours are propagated from the silhouette rim (hair, clothes, skin)
              and darkened
           -> points sampled evenly over the surface (ellipse arc length x row perimeter), with
              outward normals for back-face culling and shading in the shader
           -> compact binary for Three.js.

Binary format "ABP2":
    char[4]  magic "ABP2"
    uint32   point count
    uint32   front-sheet point count (points are ordered front first)
    float32  depth range (informational)
    int16    x, y, z  * count      (divide by 32767 -> [-1, 1])
    uint8    r, g, b  * count
    int8     nx, ny, nz * count    (divide by 127)

usage: make_pointcloud.py <photo> <out_dir> [preview_dir]
env:   DEPTH_MODEL (default depth-anything/Depth-Anything-V2-Base-hf)
       MP_MODEL    (path to selfie_multiclass_256x256.tflite)
       N_FRONT / N_BACK (desktop), N_FRONT_M / N_BACK_M (mobile LOD)
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
DEPTH_MODEL = os.environ.get("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Base-hf")
MP_MODEL = os.environ.get("MP_MODEL", "")
N_FRONT, N_BACK = int(os.environ.get("N_FRONT", 140_000)), int(os.environ.get("N_BACK", 60_000))
N_FRONT_M, N_BACK_M = int(os.environ.get("N_FRONT_M", 84_000)), int(os.environ.get("N_BACK_M", 36_000))
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(PREVIEW_DIR, exist_ok=True)
torch.manual_seed(7)
rng = np.random.default_rng(7)

img = Image.open(SRC).convert("RGB")
W, H = img.size
rgb_np = np.asarray(img)
bgr_np = cv2.cvtColor(rgb_np, cv2.COLOR_RGB2BGR)
UPP = 2.0 / (W - 1)  # units per pixel (the image spans x in [-1, 1])
print("image", W, H, flush=True)


# ----------------------------------------------------------------------------- depth
def run_depth(im):
    from transformers import pipeline

    pipe = pipeline("depth-estimation", model=DEPTH_MODEL, device=0, model_kwargs={"local_files_only": True})
    pd = pipe(im)["predicted_depth"]
    if pd.ndim == 2:
        pd = pd[None, None]
    elif pd.ndim == 3:
        pd = pd[None]
    dep = F.interpolate(pd.float(), size=(H, W), mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
    metric = "Metric" in DEPTH_MODEL
    return (-dep if metric else dep), dep, metric  # "near" is large for both families


near, depth_raw, is_metric = run_depth(img)
print("depth:", DEPTH_MODEL, "metric" if is_metric else "relative", flush=True)
torch.cuda.empty_cache()


# ----------------------------------------------------------------------------- person matte + parts
CLASS_CONF = None  # 6 x H x W: 0 bg, 1 hair, 2 body skin, 3 face skin, 4 clothes, 5 accessories


def seg_rmbg(im):
    from transformers import AutoModelForImageSegmentation

    m = AutoModelForImageSegmentation.from_pretrained("briaai/RMBG-1.4", trust_remote_code=True, local_files_only=True).cuda().eval()
    a = np.asarray(im.resize((1024, 1024), Image.BILINEAR), dtype=np.float32) / 255.0
    t = (torch.from_numpy(a).permute(2, 0, 1)[None] - 0.5) / 1.0
    with torch.no_grad():
        r = m(t.cuda())
    mk = r[0][0] if isinstance(r, (list, tuple)) else r
    mk = F.interpolate(mk, size=(H, W), mode="bilinear", align_corners=False)[0, 0]
    mk = (mk - mk.min()) / (mk.max() - mk.min() + 1e-8)
    return mk.cpu().numpy()


def seg_mediapipe():
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
    conf = [cv2.resize(c, (W, H), interpolation=cv2.INTER_LINEAR) if c.shape != (H, W) else c for c in conf]
    return np.stack(conf).astype(np.float32)


def grabcut_refine(alpha_coarse, work=1100, iters=4):
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
    n, lab, stats, _ = cv2.connectedComponentsWithStats(out.astype(np.uint8), 8)
    if n > 2:
        big = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        out = (lab == big).astype(np.float32)
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    out = cv2.resize(out, (W, H), interpolation=cv2.INTER_LINEAR)
    return np.clip(cv2.GaussianBlur(out, (0, 0), 1.6), 0, 1)


alpha = None
if MP_MODEL and os.path.exists(MP_MODEL):
    try:
        CLASS_CONF = seg_mediapipe()
        alpha = 1.0 - CLASS_CONF[0]
        print("matte source: MediaPipe selfie multiclass", flush=True)
    except Exception as e:  # noqa: BLE001
        print("MediaPipe failed:", repr(e)[:160], flush=True)
if alpha is None:
    try:
        alpha = seg_rmbg(img)
        print("matte source: RMBG-1.4", flush=True)
    except Exception as e:  # noqa: BLE001
        print("RMBG unavailable:", repr(e)[:120], flush=True)
        v = (near - near.min()) / (near.max() - near.min() + 1e-8)
        thr, _ = cv2.threshold((v * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        alpha = (v * 255 > thr).astype(np.float32)
        print("matte source: depth threshold", flush=True)
alpha = grabcut_refine(alpha)
sil = alpha > 0.5
print("matte refined, coverage", float(sil.mean()), flush=True)
cv2.imwrite(os.path.join(PREVIEW_DIR, "mask.png"), (alpha * 255).astype(np.uint8))

# ----------------------------------------------------------------------------- relief shaping (nose-safe)
yy = np.repeat(np.arange(H, dtype=np.float64)[:, None], W, axis=1)
A = np.stack([yy[sil], np.ones(int(sil.sum()))], axis=1)
coef, *_ = np.linalg.lstsq(A, near[sil].astype(np.float64), rcond=None)
near = near - (coef[0] * yy + coef[1]).astype(np.float32) * 0.8  # remove most of the camera lean
p2, p98 = np.percentile(near[sil], [2, 98])
r = np.clip((near - p2) / (p98 - p2 + 1e-8), 0, 1)
p_top = np.percentile(r[sil], 94)
r = np.minimum(r, p_top) / max(p_top, 1e-6)      # clamp the nearest few percent (nose tip, chin)
knee = 0.62
nm = r > knee
r[nm] = knee + (r[nm] - knee) * 0.45               # soft knee on the near range
sigma = W / 110.0
num = cv2.GaussianBlur(r * alpha, (0, 0), sigma)
den = cv2.GaussianBlur(alpha, (0, 0), sigma) + 1e-6
r = np.clip(0.55 * (num / den) + 0.45 * r, 0, 1)
dep_vis = cv2.applyColorMap((r * 255).astype(np.uint8), cv2.COLORMAP_MAGMA)
dep_vis[~sil] = 0
cv2.imwrite(os.path.join(PREVIEW_DIR, "depth.png"), dep_vis)

# ----------------------------------------------------------------------------- per-row cross-sections
K_HEAD, K_SKIN, K_CLOTH, K_OTHER = 1.10, 0.95, 0.50, 0.70
rows_main = {}   # y -> (xl, xr) of the widest run
runs = []        # (y, xl, xr, is_main)
for y in range(H):
    row = sil[y]
    if not row.any():
        continue
    d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
    starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
    widths = ends - starts + 1
    main = int(np.argmax(widths))
    for i, (s, e) in enumerate(zip(starts, ends)):
        if e - s + 1 < 2:
            continue
        runs.append((y, int(s), int(e), i == main))
    rows_main[y] = (int(starts[main]), int(ends[main]))

ys_main = np.array(sorted(rows_main))
y0, y1 = ys_main.min(), ys_main.max()
hw_y = np.zeros(H)
xc_y = np.zeros(H)
for y, (xl, xr) in rows_main.items():
    hw_y[y] = (xr - xl + 1) / 2.0
    xc_y[y] = (xl + xr) / 2.0
# fill gaps so derivatives are defined
for arr in (hw_y, xc_y):
    arr[:] = np.interp(np.arange(H), ys_main, arr[ys_main])
hw_s = cv2.GaussianBlur(hw_y.reshape(-1, 1), (0, 0), 2.0).ravel()
xc_s = cv2.GaussianBlur(xc_y.reshape(-1, 1), (0, 0), 2.0).ravel()
dhw = np.gradient(hw_s)
dxc = np.gradient(xc_s)
# per-row part fractions -> depth factor k(y), back fullness bk(y), head weight
if CLASS_CONF is not None:
    cc = CLASS_CONF * sil[None]
    tot = cc[1:].sum(axis=(0, 2)) + 1e-6
    head_y = (cc[1] + cc[3] + cc[5]).sum(axis=1) / tot
    skin_y = cc[2].sum(axis=1) / tot
    cloth_y = cc[4].sum(axis=1) / tot
    other_y = np.clip(1 - head_y - skin_y - cloth_y, 0, 1)
    k_y = K_HEAD * head_y + K_SKIN * skin_y + K_CLOTH * cloth_y + K_OTHER * other_y
    bk_y = 1.0 * head_y + 1.0 * skin_y + 0.9 * cloth_y + 1.0 * other_y
else:  # no parts: head = top 45% of the silhouette height
    head_y = (np.arange(H) < y0 + 0.45 * (y1 - y0)).astype(np.float64)
    k_y = np.where(head_y > 0.5, K_HEAD, K_CLOTH).astype(np.float64)
    bk_y = np.ones(H)
valid = np.zeros(H, bool)
valid[ys_main] = True
for arr in (k_y, bk_y, head_y):
    arr[~valid] = np.interp(np.nonzero(~valid)[0], ys_main, arr[ys_main])
k_y = cv2.GaussianBlur(k_y.reshape(-1, 1), (0, 0), H / 70.0).ravel()
bk_y = cv2.GaussianBlur(bk_y.reshape(-1, 1), (0, 0), H / 70.0).ravel()
head_y = cv2.GaussianBlur(head_y.reshape(-1, 1), (0, 0), H / 120.0).ravel()

# skull half-width: on head rows the ears and hair tufts that stick out sideways are not part of the
# round cross-section; they become thin flaps at the equator. A running median removes those bumps.
from scipy.ndimage import median_filter
win = max(9, int((y1 - y0) * 0.10)) | 1
hw_med = np.minimum(hw_s, median_filter(hw_s, size=win, mode='nearest'))
hb = np.clip((head_y - 0.35) / 0.30, 0, 1)
hb = hb * hb * (3 - 2 * hb)
hw_sk = hw_s * (1 - hb) + hw_med * hb
hw_sk = cv2.GaussianBlur(hw_sk.reshape(-1, 1), (0, 0), 4.0).ravel()
dhw_sk = np.gradient(cv2.GaussianBlur(hw_sk.reshape(-1, 1), (0, 0), 2.0).ravel())

# per-row depth offset z0(y) from the relief's row median (torso sits behind the head)
z0r = np.zeros(H)
for y, (xl, xr) in rows_main.items():
    z0r[y] = np.median(r[y, xl:xr + 1])
z0r[~valid] = np.interp(np.nonzero(~valid)[0], ys_main, z0r[ys_main])
z0r = cv2.GaussianBlur(z0r.reshape(-1, 1), (0, 0), H / 40.0).ravel()
Z_SCALE = 0.7
z0_units = np.maximum(Z_SCALE * (z0r - z0r[ys_main].max()), -0.32)
z0_px = z0_units / UPP
dz0 = np.gradient(z0_px)
print(f"k(y) head rows ~{k_y[y0 + (y1 - y0) // 5]:.2f}, torso rows ~{k_y[y1 - (y1 - y0) // 8]:.2f}; z0 range {z0_units.min():.2f}..{z0_units.max():.2f}", flush=True)

# relief residual within the row (nose, lips, eye sockets): modulates the front sheet
r_row = np.zeros(H)
for y, (xl, xr) in rows_main.items():
    r_row[y] = np.median(r[y, xl:xr + 1])
r_res = np.clip(r - r_row[:, None], -0.25, 0.25).astype(np.float32)
BETA = 0.8  # +20% bulge at the nose, -20% in the sockets, relative to the local ellipse depth

# hair colour per row (median of confident hair pixels) and hair fraction per row
hair_col_y = np.full((H, 3), np.nan)
hair_frac_y = np.zeros(H)
if CLASS_CONF is not None:
    hair_m = (CLASS_CONF[1] > 0.5) & (alpha > 0.9)
    tot_row = (CLASS_CONF[1:] * sil[None]).sum(axis=(0, 2)) + 1e-6
    hair_frac_y = (CLASS_CONF[1] * sil).sum(axis=1) / tot_row
    for y in ys_main:
        px = rgb_np[y][hair_m[y]]
        if len(px) >= 20:
            hair_col_y[y] = np.median(px, axis=0)
    good = ~np.isnan(hair_col_y[:, 0])
    if good.sum() >= 3:
        gy = np.nonzero(good)[0]
        for ch in range(3):
            hair_col_y[:, ch] = np.interp(np.arange(H), gy, hair_col_y[gy, ch])
        hair_col_y = cv2.GaussianBlur(hair_col_y.astype(np.float32), (0, 0), sigmaX=0.1, sigmaY=H / 80.0)
    else:
        hair_col_y[:] = 40.0
    hair_frac_y = cv2.GaussianBlur(hair_frac_y.reshape(-1, 1).astype(np.float32), (0, 0), H / 90.0).ravel()
else:
    hair_col_y[:] = 40.0
w_hair_y = np.clip((hair_frac_y - 0.08) / 0.22, 0, 1)
w_hair_y = w_hair_y * w_hair_y * (3 - 2 * w_hair_y)
# the back of the head is hair down to about the ear lobes (~2/3 of the face height), then neck skin
if CLASS_CONF is not None:
    face_rows = np.nonzero((CLASS_CONF[3] * sil).sum(axis=1) / (sil.sum(axis=1) + 1e-6) > 0.2)[0]
    if len(face_rows) > 10:
        yf0, yf1 = face_rows.min(), face_rows.max()
        yy1 = np.arange(H)
        t_nape = np.clip((yy1 - (yf0 + 0.68 * (yf1 - yf0))) / (0.32 * (yf1 - yf0) + 1e-6), 0, 1)
        hair_back = (1 - t_nape * t_nape * (3 - 2 * t_nape)) * (yy1 <= yf1)
        w_hair_y = np.maximum(w_hair_y, hair_back * np.clip((head_y - 0.35) / 0.3, 0, 1))

# rim colours per row for the back sheet (sampled a few px inside the silhouette, box-averaged)
blur_rgb = cv2.blur(rgb_np.astype(np.float32) * alpha[..., None], (9, 7))
blur_a = cv2.blur(alpha, (9, 7))[..., None] + 1e-6
rim_src = np.clip(blur_rgb / blur_a, 0, 255)

# per-row rim colours, smoothed along y, and whether the rim pixel is skin (ear / cheek)
rim_l = np.zeros((H, 3), np.float32)
rim_r = np.zeros((H, 3), np.float32)
inner_l = np.zeros((H, 3), np.float32)
inner_r = np.zeros((H, 3), np.float32)
skin_l = np.zeros(H, np.float32)
skin_r = np.zeros(H, np.float32)
for y, (xl, xr) in rows_main.items():
    hwp = (xr - xl + 1) / 2.0
    ins = int(min(8, max(1, hwp * 0.6)))
    xa, xb = min(xl + ins, W - 1), max(xr - ins, 0)
    rim_l[y], rim_r[y] = rim_src[y, xa], rim_src[y, xb]
    xc_ = (xl + xr) / 2.0
    inner_l[y] = rim_src[y, int(np.clip(xc_ - 0.68 * hwp, 0, W - 1))]
    inner_r[y] = rim_src[y, int(np.clip(xc_ + 0.68 * hwp, 0, W - 1))]
    if CLASS_CONF is not None:
        skin_l[y] = CLASS_CONF[2, y, xa] + CLASS_CONF[3, y, xa]
        skin_r[y] = CLASS_CONF[2, y, xb] + CLASS_CONF[3, y, xb]
for arr in (rim_l, rim_r, inner_l, inner_r):
    for ch in range(3):
        arr[~valid, ch] = np.interp(np.nonzero(~valid)[0], ys_main, arr[ys_main, ch])
    arr[:] = cv2.GaussianBlur(arr, (0, 0), sigmaX=0.1, sigmaY=H / 150.0)
for arr in (skin_l, skin_r):
    arr[~valid] = np.interp(np.nonzero(~valid)[0], ys_main, arr[ys_main])
    arr[:] = cv2.GaussianBlur(arr.reshape(-1, 1), (0, 0), H / 150.0).ravel()
# skin at the rim on head rows = ear / cheek edge: blend it toward the cheek colour further in
ear_w_l = np.clip((skin_l - 0.35) / 0.3, 0, 1) * hb
ear_w_r = np.clip((skin_r - 0.35) / 0.3, 0, 1) * hb

# ----------------------------------------------------------------------------- sampling
run_arr = np.array(runs, dtype=np.int64)
ry, rxl, rxr, rmain = run_arr[:, 0], run_arr[:, 1], run_arr[:, 2], run_arr[:, 3].astype(bool)
rhw = (rxr - rxl + 1) / 2.0                                  # true silhouette half-width
rxc = (rxl + rxr) / 2.0
rhw_x = np.where(rmain, hw_sk[ry], rhw)                      # round cross-section half-width (smoothed)
rflap = np.maximum(rhw - rhw_x, 0.0)                         # flap width per side (ears, tufts)
rdhw = np.where(rmain, dhw_sk[ry], 0.0)
rdxc = np.where(rmain, dxc[ry], 0.0)
rk = k_y[ry]
rbk = bk_y[ry]
slope = np.where(rmain, np.sqrt(1 + rdhw ** 2), 1.0)
yn = ry / (H - 1)
fade = np.clip((0.985 - yn) / 0.16, 0, 1)
fade = fade * fade * (3 - 2 * fade)
w_row = rhw_x * slope * (1 + rk) / 2 * fade                  # ~ perimeter of the half ellipse
w_row /= w_row.sum()
w_flap = rflap * fade
flap_share = float(w_flap.sum() * 2 / (np.pi / 2 * (rhw_x * (1 + rk) / 2 * fade).sum() + w_flap.sum() * 2))
w_flap /= max(w_flap.sum(), 1e-9)
print(f"flap share of the front area: {flap_share:.3f}", flush=True)


def lift(col):
    lum = col @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    col = np.clip(lum[:, None] + (col - lum[:, None]) * 1.12, 0, 1)
    return np.clip((col - 0.5) * 1.06 + 0.5, 0, 1)


def finish(x, y, z_px, nrm, col):
    nrm = nrm / (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9)
    nrm[:, 1] *= -1  # image y points down, world y points up
    X = x / (W - 1) * 2 - 1
    Y = -(y / (H - 1) * 2 - 1)
    Z = z_px * UPP + rng.normal(0, 0.0015, len(x))
    return np.stack([X, Y, Z], axis=1).astype(np.float32), (col * 255).round().astype(np.uint8), nrm.astype(np.float32)


def sample_flaps(n):
    """Ears and side tufts: thin sheets just in front of the equator, photo colours."""
    ridx = rng.choice(len(runs), size=n, p=w_flap)
    side = np.where(rng.uniform(0, 1, n) < 0.5, -1.0, 1.0)
    y = ry[ridx] + rng.uniform(-0.5, 0.5, n)
    u = rng.uniform(0, 1, n)
    x = rxc[ridx] + side * (rhw_x[ridx] + u * rflap[ridx])
    yi = np.clip(np.round(y).astype(int), 0, H - 1)
    xi = np.clip(np.round(x).astype(int), rxl[ridx] + 1, rxr[ridx] - 1)
    xi = np.clip(xi, 0, W - 1)
    z_px = z0_px[yi] + rng.uniform(0.0, 0.05, n) * rk[ridx] * rhw_x[ridx]
    nrm = np.stack([side * 0.45, np.zeros(n), np.full(n, 0.9)], axis=1)
    col = lift(rgb_np[yi, xi].astype(np.float32) / 255.0)
    return finish(x, y, z_px, nrm, col)


def sample_sheet(n, front):
    """Even surface sampling: rows by perimeter, angle by ellipse arc length."""
    out_rows, out_th = [], []
    got = 0
    while got < n:
        m = int((n - got) * 1.6) + 1000
        ridx = rng.choice(len(runs), size=m, p=w_row)
        th = rng.uniform(1e-4, np.pi - 1e-4, m)
        kk = rk[ridx]
        acc = rng.uniform(0, 1, m) < np.sqrt(np.sin(th) ** 2 + (kk * np.cos(th)) ** 2) / np.maximum(1.0, kk)
        out_rows.append(ridx[acc])
        out_th.append(th[acc])
        got += int(acc.sum())
    ridx = np.concatenate(out_rows)[:n]
    th = np.concatenate(out_th)[:n]
    y = ry[ridx] + rng.uniform(-0.5, 0.5, n)
    hw, xc, kk, bk = rhw_x[ridx], rxc[ridx], rk[ridx], rbk[ridx]
    dhw_r, dxc_r = rdhw[ridx], rdxc[ridx]
    s, c = np.sin(th), np.cos(th)
    x = xc + hw * c
    yi = np.clip(np.round(y).astype(int), 0, H - 1)
    xi = np.clip(np.round(x).astype(int), rxl[ridx] + 3, rxr[ridx] - 3)
    xi = np.clip(xi, 0, W - 1)
    t_px = kk * hw * s
    if front:
        z_px = z0_px[yi] + t_px * (1 + BETA * r_res[yi, xi])
        nrm = np.stack([kk * c, -(dz0[yi] * s + kk * dhw_r + kk * dxc_r * c), s], axis=1)
        col = rgb_np[yi, xi].astype(np.float32) / 255.0
        graze = np.clip((0.58 - s) / 0.5, 0, 1)                    # 1 at the rim, 0 past ~35 deg
        graze = graze * graze * (3 - 2 * graze)
        ear_w = np.where(c < 0, ear_w_l[yi], ear_w_r[yi]) * graze * 0.8
        inner = np.where((c < 0)[:, None], inner_l[yi], inner_r[yi]) / 255.0
        col = lift(np.clip(col * (1 - ear_w[:, None]) + inner * ear_w[:, None], 0, 1))
    else:
        z_px = z0_px[yi] - bk * t_px
        nrm = np.stack([bk * kk * c, dz0[yi] * s - bk * (kk * dhw_r + kk * dxc_r * c), -s], axis=1)
        if True:
            left = (rim_l[yi] * (1 - ear_w_l[yi][:, None] * 0.8) + inner_l[yi] * ear_w_l[yi][:, None] * 0.8) / 255.0
            right = (rim_r[yi] * (1 - ear_w_r[yi][:, None] * 0.8) + inner_r[yi] * ear_w_r[yi][:, None] * 0.8) / 255.0
            small = ~rmain[ridx]                                     # tufts: their own rim colour
            if small.any():
                ins2 = np.clip(rxl[ridx[small]] + 2, 0, W - 1)
                left[small] = rim_src[yi[small], ins2] / 255.0
                right[small] = rim_src[yi[small], np.clip(rxr[ridx[small]] - 2, 0, W - 1)] / 255.0
        mix = ((c + 1) / 2)[:, None]
        rim_col = left * (1 - mix) + right * mix
        # behind the head: hair; behind the neck/torso: the rim colour (skin, clothes)
        back_col = rim_col * (1 - w_hair_y[yi][:, None]) + (hair_col_y[yi] / 255.0) * w_hair_y[yi][:, None]
        tb = np.clip(s / 0.35, 0, 1)[:, None]
        tb = tb * tb * (3 - 2 * tb)
        col = rim_col * (1 - tb) + back_col * tb
        dark = np.where(w_hair_y[yi] > 0.5, 0.86 - 0.30 * s, 0.90 - 0.24 * s)[:, None]
        col = np.clip(col * dark * (1 + rng.normal(0, 0.025, (n, 1))), 0, 1)
    return finish(x, y, z_px, nrm, col)


def build(n_front, n_back):
    n_fl = int(n_front * flap_share)
    pf, cf, nf = sample_sheet(n_front - n_fl, True)
    pl, cl, nl = sample_flaps(n_fl)
    pb, cb, nb = sample_sheet(n_back, False)
    of, ob = rng.permutation(n_front), rng.permutation(n_back)
    pf, cf, nf = np.concatenate([pf, pl]), np.concatenate([cf, cl]), np.concatenate([nf, nl])
    return (np.concatenate([pf[of], pb[ob]]), np.concatenate([cf[of], cb[ob]]), np.concatenate([nf[of], nb[ob]]), n_front)


def write_bin(path, pos, col, nrm, n_front):
    n = len(pos)
    with open(path, "wb") as f:
        f.write(b"ABP2")
        f.write(struct.pack("<II", n, n_front))
        f.write(struct.pack("<f", float(pos[:, 2].max() - pos[:, 2].min())))
        f.write(np.clip(pos * 32767, -32767, 32767).astype("<i2").tobytes())
        f.write(col.tobytes())
        f.write(np.clip(nrm * 127, -127, 127).astype(np.int8).tobytes())
    print("wrote", path, os.path.getsize(path), "bytes", n, "points", flush=True)


P, C, Nr, NF = build(N_FRONT, N_BACK)
write_bin(os.path.join(OUT_DIR, "portrait_3d_hi.bin"), P, C, Nr, NF)
Pm, Cm, Nm, NFm = build(N_FRONT_M, N_BACK_M)
write_bin(os.path.join(OUT_DIR, "portrait_3d_lo.bin"), Pm, Cm, Nm, NFm)
print(f"z range {P[:, 2].min():.2f}..{P[:, 2].max():.2f}", flush=True)


# ----------------------------------------------------------------------------- turntable preview
def render(angle_deg, size=560):
    th = np.deg2rad(angle_deg)
    cth, sth = np.cos(th), np.sin(th)
    xr = P[:, 0] * cth + P[:, 2] * sth
    zr = -P[:, 0] * sth + P[:, 2] * cth
    nz = -Nr[:, 0] * sth + Nr[:, 2] * cth           # view-space normal z (orthographic, camera at +z)
    keep = nz > -0.05
    bright = 0.68 + 0.32 * np.sqrt(np.clip(nz, 0, 1))
    canvas = np.full((size, size, 3), (18, 14, 11), np.uint8)
    idx = np.nonzero(keep)[0]
    idx = idx[np.argsort(zr[idx])]                    # far first
    px = ((xr[idx] * 0.78 + 1) * 0.5 * (size - 1)).astype(int)
    py = ((-P[idx, 1] * 0.78 + 1) * 0.5 * (size - 1) - size * 0.04).astype(int)
    ok = (px >= 1) & (px < size - 1) & (py >= 1) & (py < size - 1)
    col = np.clip(C[idx].astype(np.float32) * bright[idx, None], 0, 255).astype(np.uint8)
    for i in np.nonzero(ok)[0]:
        c = col[i]
        cv2.circle(canvas, (int(px[i]), int(py[i])), 1, (int(c[2]), int(c[1]), int(c[0])), -1)
    cv2.putText(canvas, f"{angle_deg:+d} deg", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA)
    return canvas


sheet = np.concatenate([render(a) for a in (-60, -30, 0, 30, 60)], axis=1)
cv2.imwrite(os.path.join(PREVIEW_DIR, "turntable.png"), sheet)
print("turntable written", flush=True)
