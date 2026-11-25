"""视频截一帧 → 素材库（2026-11-19 用户）。

在放大看视频的地方（素材库里打开的视频、生视频 / 改视频的成品）按 S 截下当前这一帧，存进素材库；
同一个视频截的图默认放进一个图集（文件夹里有 .post.json，素材库里显示成一格），图集放在成对的图片文件夹里（例如 clips → clips image）。
播放页不截（用户：播放页有书签就够了）。

- 取帧：后台用 ffmpeg 从原文件按准确时间取（播放时看的可能是转码过的预览），对齐到帧（和浏览器画面上那一帧是同一帧），PNG。
- 记录：素材库根目录的 .frames.json：{videos: {key: {src, size, dur, fps, album, items: [{rel, t}]}}}；
  key = 'm:' + 素材库相对路径 / 'g:' + 视频库 id。图集的 .post.json 里也写了来源（{kind: 'frames', video: src, name}）。
- 素材库里移动视频 / 图集时同步更新记录（on_move）；文件没了的条目在读的时候顺手清掉。
参考：PotPlayer / mpv / VLC 的单键截图、逐帧；DaVinci Resolve 的 Grab Still（静帧记着来源时间码、能跳回去）。"""
import hashlib, json, math, os, re, subprocess, threading, time

NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
INDEX = '.frames.json'
POST = '.post.json'
CONF = {'root': '', 'ffmpeg': 'ffmpeg', 'ffprobe': 'ffprobe'}
_lock = threading.RLock()
_probe_cache = {}


def init(root, ffmpeg, ffprobe):
    CONF.update(root=root, ffmpeg=ffmpeg, ffprobe=ffprobe)


# ---------- 记录 ----------
def _ipath():
    return os.path.join(CONF['root'], INDEX)


def load():
    try:
        with open(_ipath(), encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('videos'), dict):
            return d
    except (OSError, ValueError):
        pass
    return {'v': 1, 'videos': {}}


def save(d):
    p = _ipath(); tmp = p + '.tmp'
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def key_of(src):
    if src.get('mats'):
        return 'm:' + str(src['mats']).replace('\\', '/').strip('/')
    if src.get('gallery'):
        return 'g:' + str(src['gallery'])
    raise ValueError('不知道是哪个视频')


def _exists(rel):
    return os.path.isfile(os.path.join(CONF['root'], *rel.split('/')))


def items(key, prune=True):
    """这个视频截过的图（按时间排）；文件已经不在的顺手从记录里去掉"""
    with _lock:
        d = load(); e = d['videos'].get(key)
        if not e:
            return None
        keep = [x for x in e.get('items') or [] if _exists(x['rel'])]
        if prune and len(keep) != len(e.get('items') or []):
            if keep:
                e['items'] = keep
            else:
                d['videos'].pop(key, None)
            save(d)
        e = dict(e, items=sorted(keep, key=lambda x: x['t']))
        return e if keep else None


def by_image():
    """{图片相对路径: (key, t, src)}：素材库列表里给截图标上“来自哪个视频、第几秒”"""
    out = {}
    for k, e in load()['videos'].items():
        for x in e.get('items') or []:
            out[x['rel']] = (k, x['t'], e.get('src'))
    return out


def counts():
    """{视频 key: 张数}（只数文件还在的）：素材库视频格子上的小角标"""
    return {k: n for k, e in load()['videos'].items() if (n := sum(1 for x in e.get('items') or [] if _exists(x['rel'])))}


def add(src, info, rel, t, album):
    with _lock:
        d = load(); k = key_of(src)
        e = d['videos'].setdefault(k, {'src': src, 'items': []})
        e.update(src=src, size=info.get('size'), dur=info.get('dur'), fps=info.get('fps'), name=info.get('name'))
        if album:
            e['album'] = album
        e['items'] = [x for x in e['items'] if x['rel'] != rel] + [{'rel': rel, 't': t}]
        save(d)


def remove_image(rel):
    with _lock:
        d = load(); hit = False
        for k in list(d['videos']):
            e = d['videos'][k]; n0 = len(e.get('items') or [])
            e['items'] = [x for x in e.get('items') or [] if x['rel'] != rel]
            if len(e['items']) != n0:
                hit = True
                if not e['items']:
                    d['videos'].pop(k)
        if hit:
            save(d)
        return hit


def dup(key, t, tol=0.1):
    e = items(key, prune=False)
    return next((x for x in (e or {}).get('items') or [] if abs(x['t'] - t) < tol and _exists(x['rel'])), None)


def on_move(old, new):
    """素材库里把 old（文件或文件夹，相对路径）移到了 new：记录里的视频、截图、图集路径跟着改"""
    old, new = old.strip('/'), new.strip('/')
    fix = lambda r: new + r[len(old):] if r == old or r.startswith(old + '/') else r
    with _lock:
        d = load(); ch = False; out = {}
        for k, e in d['videos'].items():
            if k.startswith('m:') and fix(k[2:]) != k[2:]:
                k = 'm:' + fix(k[2:]); e['src'] = {'mats': k[2:]}; ch = True
            for x in e.get('items') or []:
                r = fix(x['rel'])
                if r != x['rel']:
                    x['rel'] = r; ch = True
            if e.get('album') and fix(e['album']) != e['album']:
                e['album'] = fix(e['album']); ch = True
            out[k] = e
        if ch:
            d['videos'] = out; save(d)
            for e in out.values():  # 图集里的 .post.json 也写着来源视频
                a = e.get('album'); src = e.get('src') or {}
                if a and src.get('mats'):
                    p = os.path.join(CONF['root'], *a.split('/'), POST)
                    try:
                        info = json.load(open(p, encoding='utf-8'))
                        if info.get('kind') == 'frames' and info.get('video') != src:
                            info['video'] = src
                            with open(p, 'w', encoding='utf-8') as f:
                                json.dump(info, f, ensure_ascii=False, indent=1)
                    except (OSError, ValueError):
                        pass


# ---------- 取帧 ----------
def probe(path):
    """→ {dur, fps, w, h, size}（按路径 + 大小 + 修改时间缓存）"""
    st = os.stat(path); ck = (path, st.st_size, st.st_mtime)
    if ck in _probe_cache:
        return _probe_cache[ck]
    out = {'dur': 0.0, 'fps': 0.0, 'w': 0, 'h': 0, 'size': st.st_size}
    try:
        r = subprocess.run([CONF['ffprobe'], '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate,avg_frame_rate,width,height:format=duration',
                            '-of', 'json', path], capture_output=True, timeout=30, creationflags=NO_WINDOW)
        j = json.loads(r.stdout.decode('utf-8', 'replace') or '{}')
        s = (j.get('streams') or [{}])[0]
        def rate(x):
            try:
                a, b = str(x).split('/'); return float(a) / float(b) if float(b) else 0.0
            except (ValueError, ZeroDivisionError):
                return 0.0
        fps = rate(s.get('avg_frame_rate')) or rate(s.get('r_frame_rate'))
        out.update(dur=float((j.get('format') or {}).get('duration') or 0), fps=fps if 1 <= fps <= 240 else 0.0, w=int(s.get('width') or 0), h=int(s.get('height') or 0))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    _probe_cache[ck] = out
    return out


def snap(t, fps, dur=0):
    """浏览器画面上的那一帧 = 时间戳不超过 t 的最后一帧：对齐到帧号（没有帧率就原样）"""
    t = max(0.0, float(t))
    if dur:
        t = min(t, max(0.0, dur - (1 / fps if fps else 0.05)))
    if not fps:
        return round(t, 3)
    return round(math.floor(t * fps + 0.003) / fps, 6)  # 留 6 位小数：对齐过的时间再对齐一次还是同一帧（第二轮审查 7：以前取 3 位，30 fps 的 0.033 秒再对齐会退到 0）


def grab(path, t, out, fps=0.0):
    """取第 t 秒那一帧（原分辨率）存成 out（扩展名决定格式）。-ss 放在 -i 前面：先跳到前面的关键帧再解码到准确位置"""
    seek = max(0.0, t - (0.25 / fps if fps else 0.0))  # 退四分之一帧：取到的“第一帧 ≥ seek”正好是 t 那一帧
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + f'.{os.getpid()}.{threading.get_ident()}.part' + os.path.splitext(out)[1]  # 同上（审查 26）
    cmd = [CONF['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-ss', f'{seek:.4f}', '-i', path, '-frames:v', '1', '-an', '-sn', '-y']
    if out.lower().endswith(('.jpg', '.jpeg')):
        cmd += ['-q:v', '2']
    r = subprocess.run(cmd + [tmp], capture_output=True, timeout=120, creationflags=NO_WINDOW)
    if not os.path.isfile(tmp) or not os.path.getsize(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError('没能取到这一帧' + (('：' + r.stderr.decode('utf-8', 'replace').strip().splitlines()[-1][:120]) if r.stderr.strip() else ''))
    os.replace(tmp, out)
    return out


def thumb(path, t, out, h=160):
    """缩略图条上的一小张（不求准到帧：-noaccurate_seek 取附近的关键帧，快）"""
    if os.path.isfile(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + f'.{os.getpid()}.{threading.get_ident()}.part.jpg'  # 每个请求自己的临时文件（同一张同时被要两次时不互相抢，审查 26）
    subprocess.run([CONF['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-noaccurate_seek', '-ss', f'{max(0.0, t):.3f}', '-i', path, '-frames:v', '1', '-an', '-sn',
                    '-vf', f'scale=-2:{h}', '-q:v', '5', '-y', tmp], capture_output=True, timeout=60, creationflags=NO_WINDOW)
    if os.path.isfile(tmp) and os.path.getsize(tmp):
        try:
            os.replace(tmp, out)
        except OSError:  # 另一个请求刚把同一张放好
            try:
                os.remove(tmp)
            except OSError:
                pass
        if os.path.isfile(out):
            return out
    raise RuntimeError('没能取到缩略图')


def thumb_key(path, t):
    st = os.stat(path)
    return hashlib.sha1(f'{path}|{st.st_size}|{st.st_mtime}|{round(t, 2)}'.encode()).hexdigest()[:20]


# ---------- 存进素材库 ----------
def stamp(t):
    return f'{int(t // 60)}m{t % 60:05.2f}s'


def safe_name(s, n=80):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', str(s or '')).strip().strip('.')
    return s[:n].rstrip(' ._') or '视频'


def default_dest(src, private_space):
    """截图默认放哪（素材库相对路径）：素材库里 a/b/x.mp4 → 同一层的「b image」（例如 clips → clips image）；
    根目录的视频 / 生成的视频 → 「视频截图/…」"""
    if src.get('mats'):
        parent = os.path.dirname(str(src['mats']).replace('\\', '/').strip('/')).replace('\\', '/')
        return parent + ' image' if parent else '视频截图'
    return '视频截图/私密空间' if private_space else '视频截图/生成的视频'


def album_dir(parent_abs, name, src=None):
    """这个视频的图集文件夹：和视频同名。那里已经是别的图集（同名的另一个图集）、或是另一个同名视频的截图图集（审查 12）时，
    依次试「… 截图」「… 截图 2」…，直到空着的、或就是这个视频自己的那个"""
    base = safe_name(name, 70)
    for i in range(0, 50):
        d = os.path.join(parent_abs, safe_name(name) if i == 0 else base + (' 截图' if i == 1 else f' 截图 {i}'))
        p = os.path.join(d, POST)
        if not os.path.isfile(p):
            if not os.path.isdir(d) or i > 0 or not os.listdir(d):
                return d
            continue  # 同名的普通文件夹（里面有东西）：不往里放
        try:
            info = json.load(open(p, encoding='utf-8'))
        except (OSError, ValueError):
            info = {}
        if info.get('kind') == 'frames' and (src is None or not info.get('video') or info.get('video') == src):
            return d
    return os.path.join(parent_abs, base + ' 截图 ' + uuid_short())


def uuid_short():
    import uuid
    return uuid.uuid4().hex[:6]


def write_album(album_abs, src, name):
    p = os.path.join(album_abs, POST)
    if os.path.isfile(p):
        try:
            info = json.load(open(p, encoding='utf-8'))
        except (OSError, ValueError):
            info = {}
        if info.get('kind') != 'frames':
            return  # 别的图集：不动（album_dir 已经让开了）
    else:
        info = {}
    info.update(kind='frames', video=src or info.get('video') or {}, name=name, desc=info.get('desc') or f'来自视频：{name}')  # 网页取帧（src 空）不盖掉原来的来源
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=1)


def free_path(d, name):
    stem, ext = os.path.splitext(name); out, k = name, 2
    while os.path.exists(os.path.join(d, out)):
        out, k = f'{stem} ({k}){ext}', k + 1
    return os.path.join(d, out)
