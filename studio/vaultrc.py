"""私密空间里用电脑控制手机正在播放的内容（2026-11-16 用户：手机放在口袋里、正好在用电脑时，可以从电脑操控）。

做法参照 Jellyfin 的远程控制 / Spotify Connect：播放的设备（手机）把“在放什么、放到哪”报给后台，控制的设备（电脑）把命令交给后台，
后台转给手机；两台设备之间不直接连。手机一直挂着一个等命令的请求（长轮询），命令一到马上回。

2026-11-16 在 iPhone（iOS 27，主屏幕应用）上实测（devtest/tools/ios_lock_probe.py）：锁屏时只要还在出声，网页照常运行，命令当秒执行；
真的暂停十几秒后网页就被系统挂起、再也收不到命令——所以手机上暂停时改放一段无声音频（silence_wav），让网页保持运行。

第二版（同日，用户）：手机不在私密空间也能被控制——
- 电脑（在私密空间里）先“开启控制”（arm），手机不管在哪个空间，只要在放东西、等命令时看到电脑开着，就听电脑的；
- 电脑点的私密内容，发给不在私密空间的手机时换成一次性的播放地址（token）：只对那台手机、只在电脑开着控制时有效；
  标题 / 封面 / 文件名都不给，手机上只显示“电脑控制播放”，视频也只当声音放（不出画面）；
- 手机在私密空间里放着、电脑开着控制时退出私密空间：先把正在放的换成一次性地址（hand），退出后接着放。
- 电脑关掉控制 / 退出私密空间 / 3 分钟没动静（页面关了）：一次性地址全部作废。

所有东西都只放在内存里：不写硬盘、不写日志、不打印。"""
import hashlib, os, secrets, threading, time

FRESH = 15  # 手机多少秒没报状态就算断开了（锁屏后网页的计时器大约 2 秒一次）
CMD_TTL = 15  # 命令多久没送到就作废：手机醒来时不要把很久以前的命令一口气执行一遍
WAIT = 20  # 手机等命令的请求最长挂多久
ARM_TTL = 180  # 电脑开着控制、但这么久没来问过（页面关了 / 睡了）：当成关掉了
MAX_ITEMS = 500
RC_TITLE = '电脑控制播放'  # 不在私密空间的手机上显示的名字（不露出私密内容的名字）
MEDIA_PREFIX = ('/media/lib/', '/media/job/', '/media/video/', '/media/conv/')  # 一次性地址只能指向这几种播放用的文件

_cv = threading.Condition()
_st = {'dev': None, 'state': None, 'at': 0.0, 'cmds': [], 'seq': 0, 'arm': None, 'arm_at': 0.0, 'tok': {}, 'names': [], 'queue': [], 'seen': None}  # seen：最近一次有手机在放、来等命令（不记放的是什么）  # names：换成一次性地址的那一串的名字（只给电脑看）

_STATE_KEYS = {'title': str, 'sub': str, 't': float, 'd': float, 'paused': bool, 'video': bool, 'rate': float,
               'i': int, 'n': int, 'soft': bool, 'gone': bool, 'cover': str, 'orb': str, 'rc': bool,
               'key': str, 'subsKey': str, 'qv': int, 'kerr': str}  # key / subsKey：私密空间里放的那首（电脑收藏、看字幕用）；qv：播放列表变了就加一；kerr：暂停时无声音频没放出来的原因
_ITEM_KEYS = ('key', 'title', 'sub', 'orb', 'cover', 'url', 'convUrl', 'conv', 'pos', 'video', 'subsKey', 'dur', 'resume')  # resume：电脑记着的上次放到哪（秒）
CMDS = {'toggle', 'play', 'pause', 'seek', 'seekBy', 'next', 'prev', 'rate', 'queue', 'jump'}


def key_of(secret):
    return hashlib.sha256(('rc:' + (secret or '')).encode()).hexdigest()[:16] if secret else ''


def _clean(d, keys):
    out = {}
    for k, typ in keys.items():
        v = d.get(k)
        if v is None:
            continue
        try:
            if typ is str:
                v = str(v)[:300]
            elif typ is bool:
                v = bool(v)
            elif typ is float:
                v = float(v)
                if v != v or v in (float('inf'), float('-inf')):
                    continue
            else:
                v = int(v)
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out


def _own(u):
    return isinstance(u, str) and u.startswith('/') and not u.startswith('//')


def _item(x):
    """电脑点的那一首（播放列表里的一项）：只留播放要用的字段；地址必须是 Studio 自己的（以 / 开头）"""
    if not isinstance(x, dict):
        return None
    o = {}
    for k in _ITEM_KEYS:
        v = x.get(k)
        if v is None:
            continue
        o[k] = v if isinstance(v, (bool, int, float)) else str(v)[:2000]
    for k in ('url', 'convUrl', 'cover'):
        if k in o and not _own(o[k]):
            o.pop(k)
    if 'resume' in o and not (isinstance(o['resume'], (int, float)) and not isinstance(o['resume'], bool) and 0 < o['resume'] < 1e7):
        o.pop('resume')
    return o if o.get('url') or o.get('conv') else None


def _items(raw, i):
    items = [y for y in (_item(x) for x in (raw or [])[:MAX_ITEMS]) if y]
    try:
        i = int(i or 0)
    except (TypeError, ValueError):
        i = 0
    return items, max(0, min(len(items) - 1, i)) if items else 0


def _armed(now=None):
    return bool(_st['arm']) and (now or time.time()) - _st['arm_at'] < ARM_TTL


def _mint(path, dev):
    """一次性播放地址：后台记下它指向哪个文件、给哪台手机；电脑关掉控制就全部作废"""
    p = path.split('?', 1)[0]
    if not any(p.startswith(x) for x in MEDIA_PREFIX) or '..' in p:
        return None
    t = secrets.token_urlsafe(18)
    _st['tok'][t] = {'path': path, 'dev': dev}
    if len(_st['tok']) > 5000:  # 只留最近的
        for k in list(_st['tok'])[:-5000]:
            _st['tok'].pop(k, None)
    return f'/api/rc/m/{t}/a{os.path.splitext(p)[1].lower()[:6]}'


def _tokenize(items, i, dev):
    """给不在私密空间的手机：每一首换成一次性地址，名字 / 封面 / 路径都不给；要先转换才能放的（还没转好）跳过。
    名字记在后台（names），电脑看手机在放第几首时用"""
    out, ni, names = [], 0, []
    for k, x in enumerate(items):
        src = x.get('convUrl') or (x.get('url') if not x.get('conv') else None)
        u = _mint(src, dev) if src else None
        if not u:
            continue
        if k <= i:
            ni = len(out)
        o = {'key': f'rc:{len(out)}', 'url': u, 'title': RC_TITLE, 'sub': '', 'rc': True}
        if x.get('dur'):
            o['dur'] = x['dur']
        if x.get('resume'):
            o['resume'] = x['resume']  # 上次放到哪（只是秒数）
        out.append(o)
        names.append({k: x[k] for k in ('title', 'sub', 'cover', 'orb', 'key', 'subsKey') if x.get(k)})
    _st['names'] = names
    return out, ni


# ---------------------------------------------------------------- 电脑这边（都在私密空间里调）
def arm(owner, on):
    """电脑开启 / 关掉控制。关掉时一次性地址全部作废，等着的手机马上知道"""
    with _cv:
        if on:
            if _st['arm'] != owner:
                _st['cmds'] = []
            if _st['state'] and time.time() - _st['at'] > FRESH * 4:  # 早就没动静的旧状态（上一次的手机）：不显示成“休眠”，当成还没有手机
                _st.update(dev=None, state=None, at=0.0, queue=[])
            _st.update(arm=owner, arm_at=time.time())
        elif _st['arm'] == owner:
            _st.update(arm=None, arm_at=0.0, cmds=[], tok={}, names=[])
            if _st['state'] and _st['state'].get('rc'):  # 手机在放电脑发过去的：关掉控制它就停了，这个状态也不要了
                _st.update(dev=None, state=None, at=0.0, queue=[])
        _cv.notify_all()
        return {'armed': _st['arm'] == owner}


def view(owner, ctl=False):
    """电脑看手机在放什么；ctl = 电脑正在控制（顺便续上“开着”）"""
    now = time.time()
    with _cv:
        mine = _st['arm'] == owner and _armed(now)
        if ctl and mine:
            _st['arm_at'] = now
        p = {**_st['state'], 'age': round(now - _st['at'], 1)} if _st['state'] else None
        if p and p.get('rc') and mine and 0 <= p.get('i', -1) < len(_st['names']):
            p.update(_st['names'][p['i']])  # 手机在普通空间里放电脑发过去的：名字从后台记着的取（手机那边没有）
        seen = _st['seen']
        near = bool(seen) and now - seen['at'] < WAIT + 5  # 有手机在放（两个空间都算；普通空间的手机这时还没报放的是什么）
        return {'phone': p, 'armed': mine, 'near': near}


def send(owner, cmd):
    """电脑发命令。电脑没开着控制 / 没有手机在报状态时返回 None"""
    c = str((cmd or {}).get('c') or '')
    if c not in CMDS:
        raise ValueError('未知的命令')
    e = {'c': c}
    if c == 'jump':  # 电脑在手机的播放列表里点了第几首
        try:
            e['v'] = int(cmd.get('v'))
        except (TypeError, ValueError):
            raise ValueError('缺少数值')
        if not 0 <= e['v'] < MAX_ITEMS * 2:
            raise ValueError('数值不对')
    if c in ('seek', 'seekBy', 'rate'):
        try:
            e['v'] = float(cmd.get('v'))
        except (TypeError, ValueError):
            raise ValueError('缺少数值')
        if e['v'] != e['v'] or abs(e['v']) > 1e7:
            raise ValueError('数值不对')
    if c == 'queue':
        e['items'], e['i'] = _items(cmd.get('items'), cmd.get('i'))
        if not e['items']:
            raise ValueError('没有可以播放的内容')
    now = time.time()
    with _cv:
        if _st['arm'] != owner or not _armed(now) or not _st['state'] or now - _st['at'] > FRESH * 4:
            return None
        _st['seq'] += 1
        e.update(seq=_st['seq'], at=now)
        _st['cmds'] = [x for x in _st['cmds'] if now - x['at'] < CMD_TTL][-50:] + [e]
        _st['arm_at'] = now
        _cv.notify_all()
        return e['seq']


def queue(owner):
    """电脑看手机的播放列表（只要名字）。手机在普通空间里放电脑发过去的：名字从后台记着的取"""
    with _cv:
        if _st['arm'] != owner or not _armed() or not _st['state']:
            return {'items': []}
        if _st['state'].get('rc'):
            return {'items': [{k: x[k] for k in ('title', 'sub') if x.get(k)} for x in _st['names']]}
        return {'items': list(_st['queue'])}


def disarm_owner(owner):
    """这台电脑退出了私密空间：它开着的控制一起关掉"""
    if owner:
        arm(owner, False)


# ---------------------------------------------------------------- 手机这边（两个空间都能调；space = 这次请求在哪个空间）
def report(dev, body, space):
    """手机报状态。不在私密空间的手机：电脑开着控制时才收（平时普通空间里放什么，后台不管）"""
    st = _clean(body or {}, _STATE_KEYS)
    with _cv:
        armed = _armed()
        if st.get('gone'):
            if _st['dev'] == dev:
                _st.update(state=None, at=0.0)
        elif space == 'v' or armed:
            if _st['dev'] != dev:
                _st.update(cmds=[], queue=[])  # 换了一台手机：给上一台的命令作废
            _st.update(dev=dev, state={**st, 'space': space}, at=time.time())
            q = (body or {}).get('queue')
            if isinstance(q, list):  # 播放列表变了才带：只留名字（电脑上显示手机的播放列表用）
                _st['queue'] = [_clean(x, {'title': str, 'sub': str}) for x in q[:MAX_ITEMS] if isinstance(x, dict)]
        _cv.notify_all()
        return {'armed': armed, 'seq': _st['seq']}


def _deliver(x, space, dev):
    o = {k: v for k, v in x.items() if k != 'at'}
    if o['c'] == 'queue' and space != 'v':
        o['items'], o['i'] = _tokenize(x['items'], x['i'], dev)
        if not o['items']:
            return None
    return o


def wait(dev, since, space, armed_seen=None, timeout=WAIT, playing=False, vok=None):
    """手机等命令：有比 since 新的命令、或者电脑开 / 关了控制（和 armed_seen 不一样）就马上回，否则最多等 timeout 秒。
    since < 0 = 刚开始等：只告诉它现在的序号，旧命令不给。不在私密空间的手机：电脑没开着控制时什么命令都不给。
    playing = 手机正在放：记下“有手机在放”（不记放的是什么），电脑据此自动开启控制。
    vok：这次请求的私密空间凭证现在还有没有效。请求挂着的时候手机可能已经退出了私密空间（2026-11-17：退出前发出的请求
    把私密文件的原地址发给了已经退出的手机，放不出来）——发命令的那一刻再看一次，已经退出的按普通空间算（换成一次性地址）"""
    end = time.time() + timeout
    with _cv:
        if playing:
            _st['seen'] = {'dev': dev, 'at': time.time()}
            _cv.notify_all()
        while True:
            now = time.time()
            armed = _armed(now)
            mine = _st['dev'] == dev
            if since < 0:
                return {'cmds': [], 'seq': _st['seq'], 'armed': armed}
            sp = space if space != 'v' or vok is None or vok() else 'n'
            ok = mine and (sp == 'v' or armed)
            out = [y for y in (_deliver(x, sp, dev) for x in _st['cmds'] if ok and x['seq'] > since and now - x['at'] < CMD_TTL) if y]
            if out or now >= end or (armed_seen is not None and armed != armed_seen):
                return {'cmds': out, 'seq': _st['seq'] if mine else since, 'armed': armed}
            _cv.wait(min(1.0, end - now))


def hand(dev, items, i):
    """手机在私密空间里放着、电脑开着控制，手机要退出私密空间：正在放的这一串换成一次性地址，退出后接着放"""
    items, i = _items(items, i)
    with _cv:
        if not _armed() or not items:
            return None
        out, ni = _tokenize(items, i, dev)
        return {'items': out, 'i': ni} if out else None


def media(tok, dev):
    """一次性地址 → 原来的播放地址（私密空间里的）；不是给这台手机的 / 电脑已经关掉控制：None"""
    with _cv:
        x = _st['tok'].get(tok)
        if not x or x['dev'] != dev or not _armed():
            return None
        return x['path']


def drop(dev=None):
    """这台手机（不指定 = 全部）的状态和命令都清掉"""
    with _cv:
        if dev is None:
            _st.update(dev=None, state=None, at=0.0, cmds=[], arm=None, arm_at=0.0, tok={}, names=[], queue=[], seen=None)
        elif _st['dev'] == dev:
            _st.update(dev=None, state=None, at=0.0, cmds=[], queue=[])
        _cv.notify_all()


_SIL = {}


def silence_wav(secs=10, rate=8000):
    """手机暂停时循环放的无声音频（8 kHz 8 位单声道 WAV，10 秒约 80 KB），现做、只做一次"""
    if 'b' not in _SIL:
        import struct
        n = secs * rate
        hdr = b'RIFF' + struct.pack('<I', 36 + n) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate, 1, 8) + b'data' + struct.pack('<I', n)
        _SIL['b'] = hdr + b'\x80' * n  # 8 位 PCM 的静音是 128
    return _SIL['b']
