"""把 StudioLogo.png（深色底 + 两块蓝色渐变）描成无背景的 SVG：两块形状的轮廓 + 各自的线性渐变（按原图取色）。
用法：python logo_vectorize.py <StudioLogo.png> [输出 svg，默认 studio/web/logo.svg]"""
import os, sys
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure

if len(sys.argv) < 2:
    sys.exit(__doc__)
SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio', 'web', 'logo.svg')
im = np.asarray(Image.open(SRC).convert('RGB')).astype(float)
H, W, _ = im.shape
bg = np.median(np.concatenate([im[:20].reshape(-1, 3), im[-20:].reshape(-1, 3)]), axis=0)
dist = np.sqrt(((im - bg) ** 2).sum(-1))
blue = im[..., 2] - im[..., 0]
mask = (dist > 28) & (blue > 8)
mask = ndimage.binary_opening(mask, iterations=2)
lab, n = ndimage.label(mask)
sizes = ndimage.sum(mask, lab, range(1, n + 1))
keep = [i + 1 for i in np.argsort(sizes)[::-1][:2]]
print('bg', bg, 'shapes', n, sorted(sizes)[-3:])

# 视图框：两块形状的外接框 + 一点边距，正方形
ys, xs = np.nonzero(np.isin(lab, keep))
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
side = max(x1 - x0, y1 - y0) * 1.04
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
vx, vy = cx - side / 2, cy - side / 2
S = 100 / side  # 归一化到 100×100


def P(x, y):
    return (x - vx) * S, (y - vy) * S


def bezier_path(pts):
    """闭合的 Catmull-Rom 曲线 → 三次贝塞尔"""
    n = len(pts)
    d = []
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = p1 + (p2 - p0) / 6
        c2 = p2 - (p3 - p1) / 6
        if i == 0:
            d.append(f'M{p1[0]:.2f} {p1[1]:.2f}')
        d.append(f'C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}')
    return ''.join(d) + 'Z'


paths, grads = [], []
for k, li in enumerate(sorted(keep, key=lambda l: ndimage.center_of_mass(mask, lab, l)[0])):
    m = lab == li
    sm = ndimage.gaussian_filter(m.astype(float), 2.6)
    c = max(measure.find_contours(sm, 0.5), key=len)[:-1]  # (row, col)
    # 沿轮廓等距重新取点（不等距的点用 Catmull-Rom 会在长直边两头冒尖）
    seg = np.sqrt((np.diff(np.vstack([c, c[:1]]), axis=0) ** 2).sum(1)); L = np.concatenate([[0], np.cumsum(seg)])
    N = 84; u = np.linspace(0, L[-1], N, endpoint=False); cc = np.vstack([c, c[:1]])
    c = np.stack([np.interp(u, L, cc[:, 0]), np.interp(u, L, cc[:, 1])], 1)
    pts = np.array([P(x, y) for y, x in c])
    paths.append(bezier_path(pts))
    # 渐变：试各个方向，按方向分段取平均色，选分段内颜色最一致的方向
    yy, xx = np.nonzero(ndimage.binary_erosion(m, iterations=6))
    col = im[yy, xx]
    best = None
    for ang in range(0, 180, 3):
        a = np.deg2rad(ang); t = xx * np.cos(a) + yy * np.sin(a)
        t = (t - t.min()) / (t.max() - t.min() + 1e-9)
        b = np.minimum((t * 10).astype(int), 9)
        err = sum(col[b == i].var(0).sum() * (b == i).sum() for i in range(10) if (b == i).any())
        if best is None or err < best[0]:
            best = (err, ang)
    a = np.deg2rad(best[1]); t = xx * np.cos(a) + yy * np.sin(a); tmin, tmax = t.min(), t.max()
    t = (t - tmin) / (tmax - tmin)
    stops = []
    for i in range(6):
        lo, hi = i / 6, (i + 1) / 6
        s = (t >= lo) & (t <= hi)
        if s.any():
            cc = np.median(col[s], 0); stops.append(((lo + hi) / 2, '#%02x%02x%02x' % tuple(int(round(v)) for v in cc)))
    # 渐变线的两端（用户空间坐标）
    cxs, cys = xx.mean(), yy.mean()
    # 投影 t=0 和 t=1 的点：沿方向从中心移动
    tc = cxs * np.cos(a) + cys * np.sin(a)
    p0 = np.array([cxs, cys]) + (tmin - tc) * np.array([np.cos(a), np.sin(a)])
    p1 = np.array([cxs, cys]) + (tmax - tc) * np.array([np.cos(a), np.sin(a)])
    (gx1, gy1), (gx2, gy2) = P(*p0), P(*p1)
    grads.append((f'sg{k}', gx1, gy1, gx2, gy2, stops))
    print('shape', k, 'angle', best[1], stops)

defs = ''.join(f'<linearGradient id="{g}" gradientUnits="userSpaceOnUse" x1="{a:.2f}" y1="{b:.2f}" x2="{c:.2f}" y2="{d:.2f}">' + ''.join(f'<stop offset="{o:.3f}" stop-color="{col}"/>' for o, col in st) + '</linearGradient>' for g, a, b, c, d, st in grads)
svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs>{defs}</defs>' + ''.join(f'<path fill="url(#sg{k})" d="{d}"/>' for k, d in enumerate(paths)) + '</svg>\n'
open(OUT, 'w', encoding='utf-8', newline='\n').write(svg)
print(len(svg), 'bytes', 'viewbox side px', side)
