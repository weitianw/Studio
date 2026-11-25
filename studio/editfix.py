r"""指令改图（Qwen 改图）出图后的两个可选后处理，默认都关（2026-11-04 第 6 轮 A/B，对比图在那次会话的 scratchpad r5/）：

1. keep_face「保留原脸 · 校正肤色」：改图会把整个人重画一遍——脸会变一点；新露出的皮肤按影棚暖光画，原图是阴天 / 冷色时人像是贴上去的。
   做法：原图和结果各找 478 个脸部关键点 → 原图的脸按关键点对齐、羽化贴回（颜色对齐到结果的脸，免得脸和身体两个色调）；
   结果里的皮肤（YCrCb 肤色范围，闭运算 + 模糊成一整片，防止花斑）按“原图的脸 / 结果的脸”的颜色比例校正 60%。背景不动
   （试过把没变的背景贴回原图：旧衣服的轮廓会在雪地上留一圈印子）。

2. face_crop / face_paste「脸部精修」：全身照里脸太小，只能像个大概。把脸连头发裁成方形、放大到 1024，再用 Qwen 改图照着脸图重画，
   缩回去羽化贴回。脸图按同样比例裁（脸占画面一样大；裁得只剩脸时模型会把脸画得特别大）。效果：眼睛、嘴、脸型更像脸图，
   偶尔会把脸图的背景色带到脸边，所以默认关。

关键点用 ComfyUI 自带的 MediaPipe（outfit2.landmarks → facelmk.py，CPU 上几秒）。找不到脸时返回 None，调用方保留原图。"""
import io, os, tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TMP = None  # server.wire_modules 接上：() → 当前空间的临时目录
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
REFINE_PROMPT = '图 1 是一张照片里女人脸部的特写。让她的长相和图 2 的女人完全一样（同一个人：同样的眼睛、眉毛、鼻子、嘴、脸型），保持图 1 的头部角度、表情、发型、光线和色调，画面构图和边缘不变。'


def _lmk(*ims):
    """[PIL 图, ...] → 每张的关键点（478, 2）或 None"""
    import outfit2
    with tempfile.TemporaryDirectory(prefix='editfix_', dir=TMP() if TMP else None) as d:  # TMP：server 接上按空间的临时目录（私密的在 .data 里，以前一律系统临时目录）
        pairs = []
        for k, im in enumerate(ims):
            p = os.path.join(d, f'{k}.png'); im.save(p)
            pairs.append((p, os.path.join(d, f'{k}.npz')))
        out = []
        for xy, _ in outfit2.landmarks(*pairs):
            xy = xy[0]
            out.append(None if np.isnan(xy).any() else xy.astype(np.float64))
        return out


def _poly(xy, size, idx=OVAL):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).polygon([tuple(xy[i]) for i in idx], fill=255)
    return m


def _umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0); a, b = src - ms, dst - md
    U, D, Vt = np.linalg.svd(b.T @ a / len(src)); S = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[1, 1] = -1
    R = U @ S @ Vt
    s = (D * np.diag(S)).sum() / (a ** 2).sum(1).mean()
    return s * R, md - s * R @ ms


def _skin(im, W):
    """肤色范围（YCrCb），软边；闭运算 + 模糊连成一整片（只按像素判断会在阴影处留花斑）"""
    ycc = np.asarray(im.convert('YCbCr'), np.float32); cb, cr = ycc[..., 1], ycc[..., 2]
    sk = np.clip((cr - 133) / 8, 0, 1) * np.clip((173 - cr) / 8, 0, 1) * np.clip((cb - 77) / 8, 0, 1) * np.clip((127 - cb) / 8, 0, 1)
    cl = (int(W * 0.03) // 2) * 2 + 1
    m = Image.fromarray((sk * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.MaxFilter(cl)).filter(ImageFilter.MinFilter(cl))
    return np.asarray(m.filter(ImageFilter.GaussianBlur(W * 0.01)), np.float32)[..., None] / 255


def keep_face(src_bytes, out_bytes, strength=0.6):
    """原图 + 改图结果 → 新的 PNG 字节（原脸贴回 + 皮肤校色）；任何一张找不到脸返回 None"""
    s_im = Image.open(io.BytesIO(src_bytes)).convert('RGB')
    g_im = Image.open(io.BytesIO(out_bytes)).convert('RGB')
    W, H = g_im.size
    s_im = s_im.resize((W, round(s_im.height * W / s_im.width)), Image.LANCZOS) if s_im.width != W else s_im
    xs, xg = _lmk(s_im, g_im)
    if xs is None or xg is None:
        return None
    s = np.asarray(s_im, np.float32); g = np.asarray(g_im, np.float32)
    shrink = lambda m: np.asarray(m.filter(ImageFilter.MinFilter(9)), np.float32) > 127
    fg, fs = shrink(_poly(xg, (W, H))), shrink(_poly(xs, s_im.size))
    if fg.sum() < 200 or fs.sum() < 200:
        return None
    gain = 1 + strength * (s[fs].mean(0) / np.maximum(g[fg].mean(0), 1) - 1)
    gain = np.clip(gain, 0.6, 1.4)
    sk = _skin(g_im, W)
    out = np.clip(g * (1 + (gain - 1) * sk), 0, 255)
    # 原脸：按关键点相似变换对齐到结果的脸，羽化贴回；颜色对齐到校过色的结果的脸
    A, t = _umeyama(xs, xg); Ai = np.linalg.inv(A); ti = -Ai @ t
    ws = np.asarray(s_im.transform((W, H), Image.AFFINE, (Ai[0, 0], Ai[0, 1], ti[0], Ai[1, 0], Ai[1, 1], ti[1]), Image.BICUBIC), np.float32)
    bw = float(np.ptp(xg[:, 0]))
    pm = _poly(xg, (W, H)).filter(ImageFilter.MinFilter(int(bw * 0.06) | 1)).filter(ImageFilter.GaussianBlur(bw * 0.05))
    P = np.asarray(pm, np.float32)[..., None] / 255
    fz = P[..., 0] > 0.5
    if fz.sum() > 200:
        mw, sw = ws[fz].mean(0), ws[fz].std(0) + 1e-6
        mo, so = out[fz].mean(0), out[fz].std(0) + 1e-6
        ws = np.clip((ws - mw) * (so / sw) + mo, 0, 255)
        out = ws * P + out * (1 - P)
    b = io.BytesIO(); Image.fromarray(out.astype(np.uint8)).save(b, 'PNG')
    return b.getvalue()


def face_crop(img_bytes, side=1024, scale=2.2):
    """结果图 → (裁剪图 PNG 字节, 信息)；没找到脸、或脸本来就够大（放大不到 1.5 倍）返回 (None, None)"""
    g = Image.open(io.BytesIO(img_bytes)).convert('RGB'); W, H = g.size
    xy, = _lmk(g)
    if xy is None:
        return None, None
    x0, y0 = xy.min(0); x1, y1 = xy.max(0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.08 * (y1 - y0)
    s = int(min(max(x1 - x0, y1 - y0) * scale, W, H))
    if s <= 0 or side / s < 1.5:
        return None, None
    L = int(round(min(max(cx - s / 2, 0), W - s))); T = int(round(min(max(cy - s / 2, 0), H - s)))
    b = io.BytesIO(); g.crop((L, T, L + s, T + s)).resize((side, side), Image.LANCZOS).save(b, 'PNG')
    return b.getvalue(), {'box': (L, T, s), 'xy': xy}


def ref_face(ref_bytes, side=1024, scale=2.2):
    """脸图 → 和 face_crop 同样比例的方形裁剪（脸占画面的大小一样）。
    测过：裁得只剩脸（1.45 倍）时，模型照着参考图的大小画脸，全身照里贴回去是一张特别大的脸；本来就是大头照的脸图基本不裁。找不到脸时原样返回"""
    im = Image.open(io.BytesIO(ref_bytes)).convert('RGB'); W, H = im.size
    xy, = _lmk(im)
    if xy is None:
        return ref_bytes
    x0, y0 = xy.min(0); x1, y1 = xy.max(0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.08 * (y1 - y0)
    s = int(min(max(x1 - x0, y1 - y0) * scale, W, H))
    L = int(round(min(max(cx - s / 2, 0), W - s))); T = int(round(min(max(cy - s / 2, 0), H - s)))
    b = io.BytesIO(); im.crop((L, T, L + s, T + s)).resize((side, side), Image.LANCZOS).save(b, 'PNG')
    return b.getvalue()


def face_paste(img_bytes, refined_bytes, info):
    """把重画好的脸部裁剪缩回原大小，只取脸（椭圆、羽化），颜色对齐原图那一块后贴回；返回 PNG 字节"""
    g = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    L, T, s = info['box']; xy = info['xy']
    r = Image.open(io.BytesIO(refined_bytes)).convert('RGB').resize((s, s), Image.LANCZOS)
    x0, y0 = xy.min(0) - (L, T); x1, y1 = xy.max(0) - (L, T)
    ex, ey = (x1 - x0) * 0.18, (y1 - y0) * 0.22
    m = Image.new('L', (s, s), 0)
    ImageDraw.Draw(m).ellipse((x0 - ex, y0 - ey * 1.6, x1 + ex, y1 + ey * 0.6), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(s * 0.035))
    a = np.asarray(r, np.float32); b = np.asarray(g.crop((L, T, L + s, T + s)), np.float32); mk = np.asarray(m, np.float32)[..., None] / 255
    w = mk.sum() + 1e-6
    ma, mb = (a * mk).sum((0, 1)) / w, (b * mk).sum((0, 1)) / w
    sa = np.sqrt(((a - ma) ** 2 * mk).sum((0, 1)) / w) + 1e-6; sb = np.sqrt(((b - mb) ** 2 * mk).sum((0, 1)) / w) + 1e-6
    a = np.clip((a - ma) * (sb / sa) + mb, 0, 255)
    o = g.copy(); o.paste(Image.fromarray((a * mk + b * (1 - mk)).astype(np.uint8)), (L, T))
    buf = io.BytesIO(); o.save(buf, 'PNG')
    return buf.getvalue()


# 2026-11-09 模板套：脸部精修那句登记到 tplstore（imagegen 用 tplstore.T('IMG_REFINE')）
import tplstore
tplstore.register('img', 'img_refine', '指令', [('IMG_REFINE', 'zh')], {'pos': {'IMG_REFINE': REFINE_PROMPT}}, group='脸部精修')
