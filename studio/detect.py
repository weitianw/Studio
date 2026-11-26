"""在图里找脸、手（修脸修手 / 局部细化用），全部在 CPU 上跑 ONNX 模型，不占显卡。

- 人：YOLOX-L（DWPose 自带的人体检测）
- 脸、手：DWPose 全身 133 个关键点（脸 68 点、左右手各 21 点）→ 按点围出框；ControlNet 的姿势骨架也用它
模型放在 models/detect/，第一次用到时才载入，之后留在内存里（约 500MB）。"""
import os, threading
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）
import numpy as np
from PIL import Image

DIR = config.models('detect')
FILES = {'det': 'yolox_l.onnx', 'pose': 'dw-ll_ucoco_384.onnx'}
_s, _lock = {}, threading.Lock()


def available(kind=None):
    need = {'face': ['det', 'pose'], 'hand': ['det', 'pose'], 'pose': ['det', 'pose']}
    keys = need.get(kind, list(FILES)) if kind else list(FILES)
    import importlib.util
    if importlib.util.find_spec('onnxruntime') is None:
        return False
    return all(os.path.isfile(os.path.join(DIR, FILES[k])) for k in keys)


def _sess(k):
    with _lock:
        if k not in _s:
            import onnxruntime as ort
            o = ort.SessionOptions(); o.intra_op_num_threads = max(2, (os.cpu_count() or 8) // 2)
            _s[k] = ort.InferenceSession(os.path.join(DIR, FILES[k]), o, providers=['CPUExecutionProvider'])
        return _s[k]


def sessions(threads, kinds=('det', 'pose')):
    """单独的一组人体 / 姿势模型会话（线程数自己定；用完扔掉就释放内存）"""
    import onnxruntime as ort
    o = ort.SessionOptions(); o.intra_op_num_threads = max(1, int(threads)); o.inter_op_num_threads = 1
    return {k: ort.InferenceSession(os.path.join(DIR, FILES[k]), o, providers=['CPUExecutionProvider']) for k in kinds}


def _nms(boxes, scores, thr):
    order, keep = scores.argsort()[::-1], []
    while order.size:
        i = order[0]; keep.append(i)
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0]); yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2]); yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        a = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1]); b = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        order = order[1:][inter / (a + b - inter + 1e-9) <= thr]
    return keep


def persons(img, thr=0.35, S=None):  # S：自己的一组模型会话（找换装点用，限制线程数）
    """人体框 [[x1,y1,x2,y2,score], …]（原图坐标）"""
    a = np.asarray(img.convert('RGB'))
    h, w = a.shape[:2]; r = min(640 / h, 640 / w)
    pad = np.full((640, 640, 3), 114, np.uint8)
    pad[:int(h * r), :int(w * r)] = np.asarray(img.convert('RGB').resize((int(w * r), int(h * r)), Image.BILINEAR))
    out = (S['det'] if S else _sess('det')).run(None, {'images': pad.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    grids, strides = [], []
    for st in (8, 16, 32):
        n = 640 // st; xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2)); strides.append(np.full((n * n, 1), st))
    g, s = np.concatenate(grids), np.concatenate(strides)
    xy = (out[:, :2] + g) * s; wh = np.exp(out[:, 2:4]) * s
    sc = out[:, 4] * out[:, 5]  # 第 0 类 = 人
    m = sc > thr
    if not m.any():
        return []
    b = np.concatenate([xy[m] - wh[m] / 2, xy[m] + wh[m] / 2], 1) / r
    keep = _nms(b, sc[m], 0.45)
    return [[*np.clip(b[i], 0, [w, h, w, h]).tolist(), float(sc[m][i])] for i in keep]


def kp_pre(img, box):
    """姿势模型的输入：按人体框裁出 288×384 的图并归一化 → (3×384×288 数组, 换回原图坐标用的参数)"""
    x1, y1, x2, y2 = box[:4]
    cx, cy, bw, bh = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) * 1.25, (y2 - y1) * 1.25
    if bw / bh > 288 / 384:
        bh = bw * 384 / 288
    else:
        bw = bh * 288 / 384
    crop = img.convert('RGB').crop((int(cx - bw / 2), int(cy - bh / 2), int(cx + bw / 2), int(cy + bh / 2))).resize((288, 384), Image.BILINEAR)
    a = (np.asarray(crop, np.float32) - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
    return a.transpose(2, 0, 1).astype(np.float32), (cx, cy, bw, bh)


def kp_post(sx, sy, g):
    """姿势模型的输出（一个人）→ 133 个关键点 [[x,y,score], …]"""
    cx, cy, bw, bh = g
    xl, yl = sx.argmax(1) / 2.0, sy.argmax(1) / 2.0
    v = np.minimum(sx.max(1), sy.max(1))
    kx = xl / 288 * bw + cx - bw / 2; ky = yl / 384 * bh + cy - bh / 2
    return np.stack([kx, ky, v], 1)


def keypoints(img, box, S=None):
    """一个人的 133 个关键点 [[x,y,score], …]（DWPose，COCO-WholeBody 顺序）"""
    a, g = kp_pre(img, box)
    sx, sy = (S['pose'] if S else _sess('pose')).run(None, {'input': a[None]})
    return kp_post(sx[0], sy[0], g)


def _kbox(k, idx, thr, n_min):
    p = k[idx]; p = p[p[:, 2] > thr]
    if len(p) < n_min:
        return None
    return [float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max()), float(p[:, 2].mean())]


def faces_hands(img, persons_=None):
    """脸框、手框：按 DWPose 关键点围出来（脸往上补额头，手四周放大一点）"""
    W, H = img.size
    faces, hands = [], []
    for pb in (persons_ if persons_ is not None else persons(img)):
        k = keypoints(img, pb)
        f = _kbox(k, slice(23, 91), 0.3, 12)
        if f:
            fw, fh = f[2] - f[0], f[3] - f[1]
            faces.append([max(0, f[0] - fw * .1), max(0, f[1] - fh * .45), min(W, f[2] + fw * .1), min(H, f[3] + fh * .08), f[4]])
        for sl in (slice(91, 112), slice(112, 133)):
            hb = _kbox(k, sl, 0.3, 8)
            if hb:
                hw, hh = hb[2] - hb[0], hb[3] - hb[1]; e = max(hw, hh) * .25 + 4
                hands.append([max(0, hb[0] - e), max(0, hb[1] - e), min(W, hb[2] + e), min(H, hb[3] + e), hb[4]])
    return faces, hands


def pose_map(img):
    """ControlNet 用的姿势骨架图（OpenPose 配色，黑底），和原图一样大"""
    from PIL import ImageDraw
    W, H = img.size
    out = Image.new('RGB', (W, H)); d = ImageDraw.Draw(out)
    limbs = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11), (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]
    cols = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
            (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]
    sw = max(2, round(min(W, H) / 160))
    for pb in persons(img):
        k = keypoints(img, pb)
        c = k[:17]  # COCO 17 点 → OpenPose 18 点（加脖子 = 两肩中点）
        neck = np.array([(c[5, 0] + c[6, 0]) / 2, (c[5, 1] + c[6, 1]) / 2, min(c[5, 2], c[6, 2])])
        op = np.stack([c[0], neck, c[6], c[8], c[10], c[5], c[7], c[9], c[12], c[14], c[16], c[11], c[13], c[15], c[2], c[1], c[4], c[3]])
        for n, (i, j) in enumerate(limbs):
            if op[i, 2] > .3 and op[j, 2] > .3:
                d.line([tuple(op[i, :2]), tuple(op[j, :2])], fill=tuple(int(v * .6) for v in cols[n % 18]), width=sw * 2)
        for n, p in enumerate(op):
            if p[2] > .3:
                d.ellipse([p[0] - sw * 1.5, p[1] - sw * 1.5, p[0] + sw * 1.5, p[1] + sw * 1.5], fill=cols[n % 18])
        for sl in (slice(91, 112), slice(112, 133)):  # 手指
            hk = k[sl]
            for a_, b_ in [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (0, 9), (9, 10), (10, 11), (11, 12), (0, 13), (13, 14), (14, 15), (15, 16), (0, 17), (17, 18), (18, 19), (19, 20)]:
                if hk[a_, 2] > .3 and hk[b_, 2] > .3:
                    d.line([tuple(hk[a_, :2]), tuple(hk[b_, :2])], fill=(0, 120, 255), width=max(1, sw // 2 + 1))
        for p in k[23:91]:  # 脸上的点
            if p[2] > .3:
                d.ellipse([p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5], fill=(255, 255, 255))
    return out
