"""生成视频的自动调色（2026-11-09 用户：生成出来背景和皮肤偏暗；希望能按原视频 / 按自己给的图 / 冷白风格调色）。

做法：在 Lab 色彩空间里算一个全局的颜色变换（亮度 L 的均值和对比度、a / b 的均值），做成 3D 调色表（.cube），
再用 ffmpeg 的 lut3d 套到整段视频上——只改颜色，不改画面内容，声音原样保留。
- match：照原视频调（第五版）。背景（画面上方和左右两边）按 MKL 对齐，皮肤按脸部实测差值单独修正；人身上的衣服变了也不会带偏。
- ref：照一张参考图的整体色调调（图里的颜色分布 → 视频）。
- preset：预设风格（cold_white 冷白：提亮、偏冷、压一点暖黄）。
strength 0~1：调多少（1 = 完全对齐）。
"""
import io
import os
import subprocess
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)  # 不弹黑窗

import numpy as np
from PIL import Image

PRESETS = {  # 在 Lab 里的目标调整：dL 亮度、ka 红绿、kb 黄蓝（负数 = 更冷）、contrast 对比度倍数、sat 饱和度倍数
    'cold_white': {'name': '冷白', 'dL': 9.0, 'da': 0.0, 'db': -4.0, 'contrast': 1.0, 'sat': 0.94},  # 11-09 第二版：第一版（dL 5、对比 0.95）发灰发闷
}
_M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_W = np.array([0.9505, 1.0, 1.089])


def rgb2lab(a):
    a = np.where(a > 0.04045, ((a + 0.055) / 1.055) ** 2.4, a / 12.92)
    xyz = a @ _M.T / _W
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def lab2rgb(l):
    fy = (l[..., 0] + 16) / 116
    fx, fz = fy + l[..., 1] / 500, fy - l[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * _W
    rgb = xyz @ np.linalg.inv(_M).T
    rgb = np.where(rgb > 0.0031308, 1.055 * np.clip(rgb, 0, None) ** (1 / 2.4) - 0.055, 12.92 * rgb)
    return np.clip(rgb, 0, 1)


def _times(n, dur, ranges=None):
    """均匀取 n 个时间点；ranges=[[a, b], ...] 时只在这几段里取（按长度分配）"""
    rg = [(float(a), float(b)) for a, b in (ranges or []) if float(b) - float(a) > 0.05]
    if not rg:
        return [(k + 0.5) * dur / n if dur else 0 for k in range(n)]
    tot, out = sum(b - a for a, b in rg), []
    for k in range(n):
        u = (k + 0.5) * tot / n
        for a, b in rg:
            if u <= b - a:
                out.append(a + u)
                break
            u -= b - a
    return out


_dur_cache = {}  # (路径, 修改时间, 大小) → 时长


def _duration(ffmpeg, path):
    try:
        st = os.stat(path); key = (os.path.normcase(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return 0.0
    if key not in _dur_cache:
        try:
            _dur_cache[key] = float(subprocess.run([ffmpeg.replace('ffmpeg.exe', 'ffprobe.exe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                                   capture_output=True, text=True, creationflags=NW).stdout.strip() or 0)
        except ValueError:
            _dur_cache[key] = 0.0
    return _dur_cache[key]


def _split_png(raw):
    """image2pipe 出来的一串 PNG 拆开"""
    sig, out, i = b'\x89PNG\r\n\x1a\n', [], raw.find(b'\x89PNG\r\n\x1a\n')
    while i >= 0:
        j = raw.find(sig, i + 8)
        out.append(raw[i:j if j >= 0 else len(raw)])
        i = j
    return out


def frames(ffmpeg, path, n=12, width=360, ranges=None):
    """均匀取 n 帧（RGB 0~1）；ranges：只在这几段时间里取。
    2026-11-17 审查 P04：以前每一帧起一个 ffmpeg（加一次 ffprobe），照原视频调色要起约 26 个进程；
    现在一个 ffmpeg 一次取完（每帧一个输入、各自快速而准确地跳过去，取到的帧和以前一样），时长按文件版本缓存"""
    ts = _times(n, _duration(ffmpeg, path), ranges)
    if not ts:
        return []
    args = [ffmpeg, '-v', 'error']
    for t in ts:
        args += ['-ss', f'{t:.3f}', '-i', path]
    fc = ';'.join(f'[{k}:v]trim=end_frame=1,setpts=PTS-STARTPTS,scale={width}:-2,format=rgb24[v{k}]' for k in range(len(ts)))
    fc += ';' + ''.join(f'[v{k}]' for k in range(len(ts))) + f'concat=n={len(ts)}:v=1:a=0[o]'
    r = subprocess.run(args + ['-filter_complex', fc, '-map', '[o]', '-fps_mode', 'passthrough', '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, creationflags=NW)
    out = [np.asarray(Image.open(io.BytesIO(b)).convert('RGB'), dtype=np.float64) / 255 for b in _split_png(r.stdout)]
    if len(out) == len(ts):
        return out
    out = []  # 一次取不出来（个别容器 / 很老的 ffmpeg）：照以前一帧一个进程
    for t in ts:
        o = subprocess.run([ffmpeg, '-v', 'error', '-ss', f'{t:.3f}', '-i', path, '-frames:v', '1', '-vf', f'scale={width}:-2', '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, creationflags=NW).stdout
        if o:
            out.append(np.asarray(Image.open(io.BytesIO(o)).convert('RGB'), dtype=np.float64) / 255)
    return out


def _bg(a):
    """背景：画面上方 22% + 左右两边各 12%（人通常在中间）"""
    h, w = a.shape[:2]
    m = np.zeros((h, w), bool)
    m[:int(h * .22)] = True
    m[:, :int(w * .12)] = True
    m[:, -int(w * .12):] = True
    return a[m]


def _stats(labs):
    x = np.concatenate([p.reshape(-1, 3) for p in labs])
    return x.mean(0), x.std(0) + 1e-6


def transform(kind, src_labs=None, gen_labs=None, ref_lab=None, preset=None, strength=1.0):
    """返回 f(lab) -> lab"""
    s = float(np.clip(strength, 0, 1))
    if kind == 'preset':
        p = PRESETS[preset]

        def f(l):
            o = l.copy()
            o[..., 0] = 50 + (l[..., 0] - 50) * (1 + (p['contrast'] - 1) * s) + p['dL'] * s * np.sin(np.pi * np.clip(l[..., 0], 0, 100) / 100)  # 主要提中间调（皮肤），最暗和最亮的地方几乎不动
            o[..., 1] = l[..., 1] * (1 + (p['sat'] - 1) * s) + p['da'] * s
            o[..., 2] = l[..., 2] * (1 + (p['sat'] - 1) * s) + p['db'] * s
            return o
        return f
    if kind == 'match':  # 第五版（2026-11-10）：背景按 MKL 对齐原视频，皮肤只按脸实测的差值修正；第三、四版按背景一起提亮，脸本来不暗也被提亮，用户说惨白
        return _match5(src_labs, gen_labs, s)
    # 2026-11-09 第二版：肤色和背景分开对齐（第一版只按背景算，脸跟着走，用户觉得脸还是暗）。
    # 参考图同样只学它的肤色和白墙这类无彩色的地方，图里的衣服颜色（比如蓝格子裙）不会把整段视频带偏
    want = [rgb2lab_px(x) for x in (src_labs if kind == 'match' else [ref_lab])]
    have = gen_labs
    ws, wn = _parts(want), _parts(have)
    d_skin = (ws[0] - wn[0]) if ws[0] is not None and wn[0] is not None else np.zeros(3)
    d_neu = (ws[1] - wn[1]) if ws[1] is not None and wn[1] is not None else np.zeros(3)
    d_neu[0] = np.clip(d_neu[0], -12, 12); d_skin[0] = np.clip(d_skin[0], -12, 12)

    def f(l):
        w = skin_w(l)[..., None]
        return l + s * (w * d_skin + (1 - w) * d_neu)
    return f


def _face(a):
    """脸附近（画面上方 45%、中间 60%）的皮肤像素"""
    h, w = a.shape[:2]
    x = a[:int(h * .45), int(w * .2):int(w * .8)].reshape(-1, 3)
    return x[skin_w(x) > 0.6]


def _bgm(h, w):
    m = np.zeros((h, w), bool)
    m[:int(h * .22)] = True
    m[:, :int(w * .12)] = True
    m[:, -int(w * .12):] = True
    return m


def _mkl(A, B):
    """Monge–Kantorovich 线性颜色迁移（color_matcher / ComfyUI Color Match 常用的 mkl）：把协方差 A 的分布变成 B 的"""
    da, ua = np.linalg.eigh(A); da = np.sqrt(np.clip(da, 1e-6, None))
    dc, uc = np.linalg.eigh((da[:, None] * (ua.T @ B @ ua)) * da[None, :]); dc = np.sqrt(np.clip(dc, 1e-6, None))
    return ua @ np.diag(1 / da) @ uc @ np.diag(dc) @ uc.T @ np.diag(1 / da) @ ua.T


def _match5(src_labs, gen_labs, s, skin_clip=6.0):
    """照原视频调（2026-11-10 第五版）。量出来的：成品的背景每次都暗 3~4（L），脸却不一定——有的片段脸本来就比原视频亮，
    第三、四版照背景一起提亮，脸就白了（用户说“惨白”）。所以分开：
    1. 不是皮肤的地方：背景（上方 + 两边，原视频和成品是同一个场景）的颜色分布用 MKL 整体对齐（亮度、对比、色偏、饱和度一起）；
    2. 皮肤：同一时刻、同一位置两边都是皮肤的脸部像素，按中位差修正（最多 ±6），脸本来不暗就几乎不动。
    6 段测试（docs/AB测试/调色_1109/报告.md）：脸的亮度差都在 ±0.5 以内（第四版最多 +4.9），背景亮度差基本归零"""
    xs, xg, ps, pg = [], [], [], []
    for a, g in zip(src_labs, gen_labs):
        if a.shape != g.shape:
            continue
        m = _bgm(*a.shape[:2]); xs.append(a[m]); xg.append(g[m])
        h, w = a.shape[:2]; mf = np.zeros((h, w), bool); mf[:int(h * .45), int(w * .2):int(w * .8)] = True
        mf &= (skin_w(a) > .6) & (skin_w(g) > .6); ps.append(a[mf]); pg.append(g[mf])
    if not xs:  # 尺寸对不上（不该发生）：退回只按背景对亮度
        return _match4(src_labs, gen_labs, s)
    xs, xg = np.concatenate(xs), np.concatenate(xg); ms, mg = xs.mean(0), xg.mean(0)
    T = _mkl(np.cov((xg - mg).T), np.cov((xs - ms).T))
    ps, pg = np.concatenate(ps), np.concatenate(pg)
    d = np.clip(np.median(ps - pg, 0), -skin_clip, skin_clip) if len(ps) > 300 else np.zeros(3)

    def f(l):
        w = skin_w(l)[..., None]
        o = (1 - w) * ((l - mg) @ T + ms) + w * (l + d)
        return l + s * (o - l)
    return f


def _match4(src_labs, gen_labs, s, chroma=False):
    """照原视频调（2026-11-10 第四版）：第三版把肤色的红也对齐了，用户说“惨白、还不如原本的”——
    这版只对亮度：背景的明暗曲线按分位数对齐（成品整体偏暗 8–12% 是背景量出来最稳的那部分），颜色不动；
    chroma=True 时背景的 a / b 也对齐（皮肤不动）"""
    qs = np.linspace(1, 99, 25)
    bs = np.concatenate([_bg(x) for x in src_labs]); bg = np.concatenate([_bg(x) for x in gen_labs])
    qg = np.maximum.accumulate(np.percentile(bg[:, 0], qs) + np.arange(len(qs)) * 1e-6)
    ys = np.maximum.accumulate(np.percentile(bs[:, 0], qs))
    xg, ys = np.concatenate([[0], qg, [100]]), np.concatenate([[0], ys, [100]])
    dab = bs[:, 1:].mean(0) - bg[:, 1:].mean(0)

    def f(l):
        o = l.copy()
        o[..., 0] = l[..., 0] + s * (np.interp(l[..., 0], xg, ys) - l[..., 0])
        if chroma:
            o[..., 1:] = l[..., 1:] + s * dab * (1 - skin_w(l))[..., None]
        return o
    return f


def rgb2lab_px(x):
    return x  # 传进来的已经是 Lab（名字留着，读起来清楚：要对齐的那一边）


def skin_w(l):
    """一个颜色有多像皮肤（0~1）：色相 15°~75°、饱和度 6~40、亮度 30 以上；边缘平滑过渡"""
    a, b, L = l[..., 1], l[..., 2], l[..., 0]
    C = np.hypot(a, b); h = np.degrees(np.arctan2(b, a))
    ramp = lambda x, lo, hi: np.clip((x - lo) / (hi - lo), 0, 1)
    return ramp(h, 5, 20) * (1 - ramp(h, 70, 85)) * ramp(C, 4, 9) * (1 - ramp(C, 40, 50)) * ramp(L, 25, 40)


def _parts(labs):
    """(皮肤的平均 Lab, 无彩色背景的平均 Lab)；找不到的那一项是 None"""
    x = np.concatenate([p.reshape(-1, 3) for p in labs])
    w = skin_w(x)
    sk = x[w > 0.8]
    C = np.hypot(x[:, 1], x[:, 2])
    nu = x[(C < 8) & (x[:, 0] > 45)]
    return (sk.mean(0) if len(sk) > 200 else None), (nu.mean(0) if len(nu) > 200 else None)


def write_cube(path, f, n=33):
    g = np.linspace(0, 1, n)
    b, gg, r = np.meshgrid(g, g, g, indexing='ij')  # .cube：红色变化最快
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = lab2rgb(f(rgb2lab(rgb)))
    with open(path, 'w', encoding='ascii') as fh:
        fh.write(f'LUT_3D_SIZE {n}\n')
        fh.writelines(f'{x[0]:.6f} {x[1]:.6f} {x[2]:.6f}\n' for x in out)


def apply(ffmpeg, src, dst, cube, crf=16, ranges=None):
    """用 lut3d 套到整段视频上（声音原样复制）；ranges：只套在这几段时间上（拼好的视频：原视频的部分不动）"""
    cube_arg = cube.replace('\\', '/').replace(':', '\\:')
    r = subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', src, '-vf', f"lut3d='{cube_arg}'" + (":enable='" + '+'.join(f'between(t,{float(a):.3f},{float(b):.3f})' for a, b in ranges) + "'" if ranges else ''), '-c:v', 'libx264', '-g', '12', '-keyint_min', '1', '-crf', str(crf), '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', dst], capture_output=True, text=True, creationflags=NW)  # 和其它成品一样：拖动跳得准、边下边播（2026-11-16 审查）
    if r.returncode:
        raise RuntimeError('调色失败：' + (r.stderr or '')[-300:])
    return dst


def fix(ffmpeg, gen, dst, mode, src=None, ref_image=None, preset='cold_white', strength=1.0, work=None, ranges=None):
    """mode：'match'（照原视频）/ 'ref'（照参考图）/ 'preset'。返回 dst
    ranges（只对 match）：拼好的视频里生成的那几段 [[开始秒, 结束秒], ...]。2026-11-10 用户：拼好的视频调色后看不出变化、生成的那段还是偏——
    以前整段一起量，大部分画面就是原视频本身，算出来几乎不用调，调色表又套到了整段上。现在只量、只调生成的那几段"""
    rg = ranges if mode == 'match' and ranges else None
    gl = [rgb2lab(x) for x in frames(ffmpeg, gen, ranges=rg)]
    if mode == 'match':
        f = transform('match', [rgb2lab(x) for x in frames(ffmpeg, src, ranges=rg)], gl, strength=strength)
    elif mode == 'ref':
        im = np.asarray(Image.open(ref_image).convert('RGB').resize((360, 360)), dtype=np.float64) / 255
        f = transform('ref', gen_labs=gl, ref_lab=rgb2lab(im), strength=strength)
    else:
        f = transform('preset', preset=preset, strength=strength)
    cube = os.path.join(work or os.path.dirname(dst), os.path.splitext(os.path.basename(dst))[0] + '.cube')
    write_cube(cube, f)
    try:
        return apply(ffmpeg, gen, dst, cube, ranges=rg)
    finally:
        try:
            os.remove(cube)
        except OSError:
            pass
