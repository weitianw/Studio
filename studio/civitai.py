"""Civitai：在应用里搜 LoRA、看示例图 / 视频、一键下载到对的文件夹，并记下触发词和推荐强度。

- 密钥存在 .data/civitai.json（用户同意保存）；网页上只显示有没有存，不回传密钥本身
- 下载到：Wan 2.2 / H3 → ComfyUI\\models\\loras；Z-Image Turbo → models\\Z-Image\\loras；Krea 2 → models\\Krea2\\loras
- 每个下载的 LoRA 旁边放一个同名的 .civitai.json（触发词、推荐强度、作者、模型页地址、预览图），LoRA 列表里显示
"""
import json, os, re, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_FILE = os.path.join(ROOT, '.data', 'civitai.json')
API = 'https://civitai.com/api/v1'
UA = 'Studio/1.0'
# 网页上的“用在哪个模型” → Civitai 的 baseModel 和本地 LoRA 文件夹
TARGETS = {
    # Wan 2.2 / Wan Animate / Bernini-R 的分类 2026-11-06 随 Wan 一起去掉了
    'h3': {'name': 'MiniMax H3', 'base': ['MiniMax H3'], 'dir': os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'models', 'loras')},
    'zimage': {'name': 'Z-Image Turbo', 'base': ['ZImageTurbo'], 'dir': os.path.join(ROOT, 'models', 'Z-Image', 'loras')},
    'krea': {'name': 'Krea 2', 'base': ['Krea 2', 'Flux.2 Krea'], 'dir': os.path.join(ROOT, 'models', 'Krea2', 'loras')},
    'qedit': {'name': 'Qwen 指令改图', 'base': ['Qwen', 'Qwen Image Edit'], 'dir': os.path.join(ROOT, 'models', 'QwenEdit', 'loras')},
    # Qwen-Image 2.1（文生图、指令改图、局部重画共用）：Civitai 的分类叫「Qwen 2.1」，少数作者选了「Qwen 2」
    'q21': {'name': 'Qwen 2.1', 'base': ['Qwen 2.1', 'Qwen 2'], 'dir': os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'models', 'loras', 'Qwen21')},
    # 只做文生图的两个底子（2026-11-16）：MOSS 的 LoRA 在 Civitai 叫「MOSS Image」；H3-Image 用生视频 H3 的 LoRA（同一个底子），单独放一个文件夹
    'moss': {'name': 'MOSS Image', 'base': ['MOSS Image'], 'dir': os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'models', 'loras', 'MOSS')},
    'h3img': {'name': 'H3-Image', 'base': ['MiniMax H3'], 'dir': os.path.join(ROOT, 'tools', 'ComfyUI_windows_portable', 'ComfyUI', 'models', 'loras', 'H3_Image')},
}
SORTS = {'downloads': 'Most Downloaded', 'rating': 'Highest Rated', 'new': 'Newest'}
downloads = {}
_lock = threading.Lock()


def key():
    try:
        with open(KEY_FILE, encoding='utf-8') as f:
            return (json.load(f) or {}).get('key') or ''
    except (OSError, ValueError):
        return ''


def set_key(k):
    k = str(k or '').strip()
    if k and not re.fullmatch(r'[A-Za-z0-9_\-]{16,128}', k):
        raise ValueError('密钥格式有误（请在 Civitai → 账号设置 → API Keys 中生成）')
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    tmp = KEY_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'key': k}, f)
    os.replace(tmp, KEY_FILE)


def _get(url, timeout=25):
    h = {'User-Agent': UA}
    if key():
        h['Authorization'] = 'Bearer ' + key()
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _strip(html, n=600):
    t = re.sub(r'<[^>]+>', ' ', html or ''); t = re.sub(r'\s+', ' ', t).strip()
    return t[:n]


def _weight(text):
    """从作者的说明里找推荐强度（strength / weight 0.x ~ 1.x），找不到返回 None"""
    m = re.search(r'(?:strength|weight|强度|权重)[^0-9]{0,24}([0-2](?:\.\d+)?)(?:\s*[-~–to]+\s*([0-2](?:\.\d+)?))?', text or '', re.I)
    if not m:
        return None
    a = float(m.group(1)); b = float(m.group(2)) if m.group(2) else a
    v = round((a + b) / 2, 2)
    return v if 0.1 <= v <= 2 else None


def search(q='', target='h3', sort='downloads', cursor=''):
    t = TARGETS.get(target) or TARGETS['h3']
    params = [('types', 'LORA'), ('limit', '24'), ('sort', SORTS.get(sort, SORTS['downloads'])), ('nsfw', 'false')]
    params += [('baseModels', b) for b in t['base']]
    if q:
        params.append(('query', q[:100]))
    if cursor:
        params.append(('cursor', cursor[:200]))
    d = _get(API + '/models?' + urllib.parse.urlencode(params))
    out = []
    for m in d.get('items') or []:
        it = _item(m, target)
        if it:
            out.append(it)
    md = d.get('metadata') or {}
    return {'items': out, 'cursor': md.get('nextCursor') or '', 'key': bool(key())}


def _item(m, target, keep=None):
    """Civitai 的一个模型 → 商店卡片 / 详情用的格式。keep：一定要留下的版本 id（我的下载：版本的底模不在这一栏时也要显示自己下的那个）"""
    t = TARGETS.get(target) or TARGETS['h3']
    if True:
        vs = []
        for v in m.get('modelVersions') or []:  # 版本按作者排的顺序（和模型页一致）；只留这个模型能用的，最多 8 个
            if v.get('baseModel') not in t['base'] and v.get('id') != keep:
                continue
            if len(vs) >= 8:
                break
            vs.append({'id': v.get('id'), 'name': v.get('name'), 'base': v.get('baseModel'), 'words': v.get('trainedWords') or [],
                       'files': [{'name': f.get('name'), 'kb': f.get('sizeKB'), 'primary': bool(f.get('primary'))} for f in (v.get('files') or []) if (f.get('name') or '').lower().endswith(('.safetensors', '.gguf'))],
                       # 示例图：就是模型页上这个版本的那一组（作者发的、同样的顺序），最多 20 张；只留 PG / PG-13 的
                       'media': [{'url': i.get('url'), 'type': i.get('type')} for i in (v.get('images') or []) if i.get('url') and _safe(i)][:20]})
        if not vs or m.get('nsfw'):
            return None
        desc = _strip(m.get('description'), 1500)
        st = m.get('stats') or {}
        return {'id': m.get('id'), 'name': m.get('name'), 'creator': (m.get('creator') or {}).get('username'),
                'downloads': st.get('downloadCount'), 'likes': st.get('thumbsUpCount'), 'desc': desc[:600], 'weight': _weight(desc), 'versions': vs,
                'html': (m.get('description') or '')[:60000],  # 作者的完整说明（HTML，网页上清理后按原格式显示）
                'url': f"https://civitai.com/models/{m.get('id')}"}


def model(mid, target, version=None):
    """我的下载 → 详情：按模型 id 取 Civitai 上的这一个模型（格式和搜索结果一样）"""
    m = _get(f'{API}/models/{int(mid)}')
    it = _item(m, target, keep=int(version) if version else None)
    if not it:
        raise ValueError('Civitai 上这个模型已没有可用的版本')
    return it


LORA_EXT = ('.safetensors', '.gguf')


def _ids(url):
    """模型页地址里的模型 id、版本 id"""
    a = re.search(r'/models/(\d+)', url or ''); b = re.search(r'modelVersionId=(\d+)', url or '')
    return (int(a.group(1)) if a else None), (int(b.group(1)) if b else None)


def mine(target):
    """我的下载：这个模型的 LoRA 文件夹里的全部 LoRA。Wan / Animate / Bernini / H3 共用一个文件夹：有记录的按记录里的底模分到对应的那一栏；
    没有记录的（自己放进来的）每一栏都列出，标“未识别”，可以按文件指纹去 Civitai 查"""
    t = TARGETS.get(target)
    if not t:
        raise ValueError('未知的模型')
    d = t['dir']
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    meta = meta_for(d)
    shared = sum(1 for x in TARGETS.values() if os.path.normcase(x['dir']) == os.path.normcase(d)) > 1
    out = []
    for n in names:
        if not n.lower().endswith(LORA_EXT):
            continue
        p = os.path.join(d, n)
        try:
            st = os.stat(p)
        except OSError:
            continue
        mt = meta.get(n)
        if mt and mt.get('base') and mt['base'] not in t['base']:
            continue  # 记录里写着是别的底模（同一个文件夹里别的模型的 LoRA）
        if not (mt and mt.get('base')) and shared and _guess(n) != target:
            continue  # 没有记录：按文件名猜是哪个模型的，只放在那一栏
        mid, vid = _ids((mt or {}).get('url'))
        out.append({'file': n, 'size': st.st_size, 'mtime': st.st_mtime, 'meta': mt, 'model_id': mid, 'version_id': vid})
    out.sort(key=lambda x: -x['mtime'])
    return out


def _guess(name):
    """共用 LoRA 文件夹里没有记录的文件：按名字猜是哪个模型的"""
    n = name.lower()
    return 'h3'  # 这个文件夹里现在只有 H3 的（Wan 去掉了）


def _meta(v, info=None, name=''):
    """下载 / 识别后存进 .civitai.json 的那份记录"""
    info = info or {}
    return {'name': info.get('model') or (v.get('model') or {}).get('name') or name, 'version': v.get('name'), 'words': v.get('trainedWords') or [],
            'weight': info.get('weight'), 'url': f"https://civitai.com/models/{v.get('modelId')}?modelVersionId={v.get('id')}",
            'creator': info.get('creator'), 'base': v.get('baseModel'),
            **_preview(v)}


def _safe(i):
    """Civitai 的级别：1 PG、2 PG-13，4 及以上不显示。只留 PG / PG-13（没标级别的不留）"""
    return 1 <= (i.get('nsfwLevel') or 99) <= 2


def _preview(v):
    """预览：第一张示例图；没有图（示例全是视频）就用第一个视频（都只取 PG / PG-13 的）"""
    ims = [i for i in (v.get('images') or []) if i.get('url') and _safe(i)]
    i = next((x for x in ims if x.get('type') == 'image'), None) or next((x for x in ims if x.get('type') == 'video'), None)
    return {'preview': i.get('url'), 'preview_type': i.get('type')} if i else {'preview': None}


def identify(target, file):
    """没有记录的 LoRA：算文件的 SHA256，去 Civitai 按指纹查是哪个模型、哪个版本，查到就写 .civitai.json（以后显示模型名、能看详情）"""
    import hashlib
    t = TARGETS.get(target)
    if not t:
        raise ValueError('未知的模型')
    name = os.path.basename(str(file or ''))
    p = os.path.join(t['dir'], name)
    if not name.lower().endswith(LORA_EXT) or not os.path.isfile(p):
        raise ValueError('找不到这个 LoRA 文件')
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    try:
        v = _get(f'{API}/model-versions/by-hash/{h.hexdigest()}')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError('Civitai 上没有找到这个文件（可能不是从 Civitai 下载的，或作者改过文件）') from None
        raise
    creator = None
    try:  # 作者名在模型那一层
        creator = ((_get(f"{API}/models/{int(v.get('modelId'))}").get('creator')) or {}).get('username')
    except Exception:
        pass
    m = _meta(v, {'creator': creator}, name)
    with open(p + '.civitai.json', 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False)
    return m


def installed(target):
    d = (TARGETS.get(target) or {}).get('dir')
    if not d or not os.path.isdir(d):
        return set()
    return set(os.listdir(d))


def meta_for(dirpath):
    """LoRA 文件夹里每个 LoRA 的 .civitai.json（触发词、推荐强度…）：{文件名: {...}}"""
    out = {}
    try:
        names = os.listdir(dirpath)
    except OSError:
        return out
    for n in names:
        if n.endswith('.civitai.json'):
            try:
                with open(os.path.join(dirpath, n), encoding='utf-8') as f:
                    out[n[:-len('.civitai.json')]] = json.load(f)
            except (OSError, ValueError):
                pass
    return out


def download(version_id, target, file_name=None, info=None):
    t = TARGETS.get(target)
    if not t:
        raise ValueError('无法确定应放入哪个模型的 LoRA 文件夹')
    v = _get(f'{API}/model-versions/{int(version_id)}')
    files = [f for f in (v.get('files') or []) if (f.get('name') or '').lower().endswith(('.safetensors', '.gguf'))]
    f = next((x for x in files if x.get('name') == file_name), None) or next((x for x in files if x.get('primary')), None) or (files[0] if files else None)
    if not f:
        raise ValueError('该版本没有可下载的 LoRA 文件')
    name = os.path.basename(f['name'])
    if not re.fullmatch(r'[^\\/:*?"<>|]{1,200}', name):
        raise ValueError('文件名有误')
    os.makedirs(t['dir'], exist_ok=True)
    dst = os.path.join(t['dir'], name)
    meta = _meta(v, info, name)
    did = uuid.uuid4().hex[:8]
    # 2026-11-17 审查 F18：查重和登记在同一把锁里（以前登记目标文件在锁外，两个请求能同时通过、写同一个 .part）
    with _lock:
        if any(x.get('state') == 'running' and x.get('_dst') == dst for x in downloads.values()):
            raise ValueError('这个文件正在下载中：' + name)
        if os.path.exists(dst):
            if not os.path.exists(dst + '.civitai.json'):  # 模型已经下好、说明信息上次没写成：补写，不重新下载（以前重试会被“此前已下载”挡住）
                _write_meta(dst, meta)
                return {'id': did, 'name': name, 'target': target, 'state': 'done', 'got': os.path.getsize(dst), 'total': os.path.getsize(dst), 'error': '', 'note': '已补写说明信息'}
            raise ValueError('此前已下载：' + name)
        downloads[did] = {'id': did, 'name': name, 'target': target, 'got': 0, 'total': int((f.get('sizeKB') or 0) * 1024), 'state': 'running', 'error': '', 't': time.time(),
                          '_dst': dst, '_sha': str((f.get('hashes') or {}).get('SHA256') or '').lower()}  # 下完核对（Civitai 给了的话）
    downloads[did]['title'] = ' · '.join(x for x in (meta.get('name'), meta.get('version')) if x)  # 进度里显示模型名 · 版本（文件名放在提示里）
    threading.Thread(target=_fetch, args=(did, f.get('downloadUrl') or f'https://civitai.com/api/download/models/{int(version_id)}', dst, meta), daemon=True).start()
    return {k: v for k, v in downloads[did].items() if not k.startswith('_')}


class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Civitai 的下载会 307 跳到 Cloudflare R2 的签名地址；urllib 跳转时会把 Authorization 头也带过去，R2 就回 400。跳转时去掉它"""
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        r = super().redirect_request(req, fp, code, msg, hdrs, newurl)
        if r is not None:
            r.remove_header('Authorization')
        return r


def _write_meta(dst, meta):
    tmp = f'{dst}.civitai.json.{uuid.uuid4().hex[:6]}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, dst + '.civitai.json')


def _fetch(did, url, dst, meta):
    d, part = downloads[did], f'{dst}.{did}.part'  # 每次下载自己的临时文件
    try:
        if key():  # 下载用 ?token=（Civitai 文档里的下载方式），不用 Authorization 头
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode({'token': key()})
        try:
            r = urllib.request.build_opener(_NoAuthRedirect).open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError('该 LoRA 的作者要求登录后才能下载：请先在上方填写 Civitai API 密钥' if not key() else 'Civitai 无法识别该 API 密钥：请在 Civitai → 账号设置 → API Keys 重新生成并填写') from None
            if e.code == 403:
                raise RuntimeError('没有下载权限：该 LoRA 可能为抢先体验（Early Access）或需付费，请先在 Civitai 网页上解锁') from None
            raise RuntimeError(f'Civitai 返回错误 {e.code}，请稍后再试') from None
        with r:
            if 'text/html' in (r.headers.get('Content-Type') or ''):
                raise RuntimeError('Civitai 要求登录：请先在上方填写 API 密钥')
            clen = int(r.headers.get('Content-Length') or 0)
            d['total'] = clen or d['total'] or 0
            import hashlib
            hs = hashlib.sha256()
            with open(part, 'wb') as out:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    out.write(b); hs.update(b); d['got'] += len(b)
        if d['got'] < 1 << 16:
            raise RuntimeError('下载的文件过小，可能不是 LoRA')
        if clen and d['got'] != clen:  # 2026-11-14 审查：以前只看是不是大于 64 KB，网断了截一半也当成功
            raise RuntimeError(f'下载不完整（{d["got"] >> 20} / {clen >> 20} MB），请重试')
        if d.get('_sha') and hs.hexdigest() != d['_sha']:
            raise RuntimeError('下载的文件和 Civitai 上的校验值对不上（可能损坏），请重试')
        os.replace(part, dst)
        try:
            _write_meta(dst, meta)
        except Exception as e:  # 模型已经落盘：算下载完成，说明信息没写成的话再点一次下载会补写
            d['error'] = f'LoRA 已下载，但说明信息没写成（{e}）：再点一次下载会补写'[:300]
        d['state'] = 'done'
    except Exception as e:
        d['state'], d['error'] = 'error', str(e)[:300]
        try:
            os.remove(part)
        except OSError:
            pass


_tr_cache = {}
_TR_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'


def _gtx(text):
    """Google 翻译的免费网页接口（不用密钥，约 0.5 秒）；多段用换行拼成一次请求"""
    body = urllib.parse.urlencode({'q': text}).encode()
    u = 'https://translate.googleapis.com/translate_a/single?' + urllib.parse.urlencode({'client': 'gtx', 'sl': 'auto', 'tl': 'zh-CN', 'dt': 't'})
    with urllib.request.urlopen(urllib.request.Request(u, data=body, headers={'User-Agent': _TR_UA, 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'}), timeout=12) as r:
        d = json.loads(r.read().decode('utf-8'))
    return ''.join(s[0] or '' for s in (d[0] or []))


def translate(texts):
    """LoRA 商店的“翻译”：把名字、说明翻成中文。触发词、文件名不翻（它们是要原样用的）。结果记在内存里，同\u4e00段不重复请求"""
    texts = [re.sub(r'\s+', ' ', str(t or '')).strip()[:1600] for t in (texts or [])[:80]]
    han = lambda t: len(re.findall(r'[\u4e00-\u9fff]', t))
    need = [t for t in dict.fromkeys(texts) if t and t not in _tr_cache and not (han(t) and han(t) >= len(re.findall(r'[A-Za-z]', t)) / 4 and not re.search(r'[\u3040-\u30ff]', t))]  # 本来就主要是中文的不翻
    # Google \u4e00次请求只认\u4e00种源语言：混着中文 / 日文的那段会让整批英文原样返回。所以只有纯拉丁字母的拼成\u4e00批，其他的单独翻
    plain = [t for t in need if not re.search(r'[^\x00-\u024f\u2000-\u2bff\ufe0f\U0001f000-\U0001ffff]', t)]
    alone = [t for t in need if t not in plain]
    batch, n = [], 0
    for t in plain + [None]:  # 每次请求不超过约 4500 字
        if t is None or (batch and n + len(t) > 4500):
            if batch:
                out = _gtx('\n'.join(batch)).split('\n')
                if len(out) != len(batch):  # 换行对不上：\u4e00段\u4e00段翻
                    alone += batch
                else:
                    for a, b in zip(batch, out):
                        if b.strip() and b.strip() != a:
                            _tr_cache[a] = b.strip()
                        elif re.search(r'[A-Za-z]{3,}\W+[A-Za-z]{3,}', a):  # 原样回来了：单独再翻\u4e00次
                            alone.append(a)
                        else:
                            _tr_cache[a] = a
            batch, n = [], 0
        if t is not None:
            batch.append(t); n += len(t) + 1
    if alone:
        with ThreadPoolExecutor(6) as ex:
            for a, f in [(a, ex.submit(_gtx, a)) for a in alone]:
                try:
                    _tr_cache[a] = f.result().strip() or a
                except Exception:  # 单独\u4e00段失败：这段先显示原文（不记缓存，下次再试）；全都失败才报错
                    if not any(x in _tr_cache for x in alone):
                        raise
    if len(_tr_cache) > 5000:
        _tr_cache.clear()
    return [_tr_cache.get(t, t) for t in texts]


def list_downloads():
    with _lock:
        for k in [k for k, v in downloads.items() if v['state'] != 'running' and time.time() - v['t'] > 3600]:
            downloads.pop(k, None)
        return [{k: v for k, v in x.items() if not k.startswith('_')} for x in sorted(downloads.values(), key=lambda x: -x['t'])]  # _dst / _sha 只在后台用
