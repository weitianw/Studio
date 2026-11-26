"""模型页（开源泛化 ② / ⑤）的后台：按类列出模型（文件在不在、多大、估计要多少显存、放不放得下），
列出 ComfyUI 各文件夹里的模型文件（加模型时选），加 / 改 / 删 / 藏用户自己的模型。

用到的模块由 server.py 交进来（init），这里不自己 import 那些大模块，单元测试可以换成假的。"""
import glob, json, os, re

import catalog, config, hw

M = {}  # init() 填：imagegen / q21 / promptgen / videogen / server_cfg / specs_dir / restart_tts
EXTS = ('.safetensors', '.gguf', '.ckpt', '.pt', '.pth', '.bin', '.sft')
FOLDERS = ('diffusion_models', 'unet', 'checkpoints', 'text_encoders', 'clip', 'vae', 'loras')
KINDS = ('image', 'llm', 'tts')


def init(**kw):
    M.update(kw)


def _gb(p):
    try:
        return round(os.path.getsize(p) / 1e9, 2) if p and os.path.isfile(p) else None
    except OSError:
        return None


def _sum(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs), 1) if xs else None


def _row(id_, name, source, missing, sizes, need, offload, extra=None):
    return {'id': id_, 'name': name, 'source': source or 'builtin', 'have': not missing, 'missing': missing,
            'gb': _sum(sizes), 'need_gb': need, 'fit': hw.fit(need, offload) if not missing else 'unknown', **(extra or {})}


def image_rows():
    q21, ig = M['q21'], M['imagegen']
    rows = []
    for k, m in q21.MODELS.items():
        fam = q21.FAMILY[k]
        if fam == 'ckpt':
            sizes = [_gb(q21._path('checkpoints', q21.UNET[k]))] + ([_gb(q21._path('vae', q21.MODEL_TXT[k]['vae']))] if q21.MODEL_TXT.get(k, {}).get('vae') else [])
            unet, te = sizes[0], 0.0
        else:
            tf = q21.txt_files(k)
            unet, te, vae = _gb(q21._path('diffusion_models', q21.UNET[k])), _gb(q21._path('text_encoders', tf['te'])), _gb(q21._path('vae', tf['vae']))
            sizes = [unet, te, vae]
        need = round(_sum(sizes) + hw.OVERHEAD_GB, 1) if None not in sizes else None
        offload = (te or 0) + (sizes[-1] or 0 if fam != 'ckpt' else 0) + 0.5 * (unet or 0)  # ComfyUI 用完就把文本编码器、VAE 挪走；放不下时主模型也能部分放在内存里
        rows.append(_row(k, m.get('name') or k, m.get('source'), q21.missing(k), sizes, need, offload,
                         {'family': fam, 'family_name': (q21.FAMILIES.get(fam) or {}).get('name') or fam, 'modes': m.get('modes')}))
    for k, m in ig.MODELS.items():  # sd.cpp 跑的（指令改图）
        if m.get('backend') == 'comfy':
            continue
        try:
            files = [os.path.join(ig.model_dir(k), f) for f in ig.model_files(k) if f]
            miss = ig.missing_files(k)
        except Exception:
            files, miss = [], ['?']
        sizes = [_gb(p) for p in files]
        need = round(_sum(sizes) + hw.OVERHEAD_GB, 1) if sizes and None not in sizes else None
        off = (_sum(sizes[1:]) or 0) + 0.5 * (sizes[0] or 0) if sizes else 0  # --offload-to-cpu：文本编码器、VAE 和一部分主模型放在内存
        rows.append(_row(k, m.get('name') or k, 'builtin', miss, sizes, need, off, {'family': 'sdcpp', 'family_name': 'stable-diffusion.cpp'}))
    return rows


def llm_rows():
    pg = M['promptgen']
    out = []
    for x in pg.model_list():
        need = round(x['gb'] + 1.5, 1) if x['gb'] else None  # 加上 8K 上下文的 KV 缓存
        out.append(_row(x['id'], x['name'], x.get('source'), [] if x['have'] else [x['id']], [x['gb']], need, x['gb'] or 0, {'vision': x['vision']}))
    return out


def video_rows():
    vg = M['videogen']
    out = []
    for k, m in vg.MODELS.items():
        files = list(m.get('files') or []) + ([vg.h3_diffusion()] if k == 'h3' and vg.h3_diffusion() else list(m.get('diffusion') or [])[:1])
        sizes = [_gb(os.path.join(vg.MODELS_DIR, f)) for f in files if f]
        need = round(_sum(sizes) + 3.0, 1) if sizes and None not in sizes else None
        te = sizes[0] if sizes else 0
        out.append(_row(k, m.get('name') or k, 'builtin', vg.missing(k), sizes, need, (te or 0) + 0.6 * ((_sum(sizes[1:]) or 0)), {'family': 'h3'}))
    return out


def tts_rows():
    cfg = M['server_cfg']()
    user = {e['id'] for e in catalog.user_entries('tts')}
    out = []
    for m in cfg.get('models', []):
        p = m.get('path')
        g = _gb(p) if p and os.path.isfile(p) else None
        miss = [] if (p and os.path.exists(p)) else [p]
        out.append(_row(m['id'], m['id'], 'user' if m['id'] in user else 'builtin', miss, [g], round(g * 1.3 + 1.0, 1) if g else None, 0,
                        {'family': m.get('family'), 'task': m.get('task')}))
    return out


def tts_families():
    d = M.get('specs_dir') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'specs')
    out = []
    for p in sorted(glob.glob(os.path.join(d, '*.json'))):
        try:
            s = json.load(open(p, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        tasks = s.get('tasks') or []
        if any(t in tasks for t in ('tts', 'clone', 'design', 'vc', 'asr')):
            out.append({'id': os.path.splitext(os.path.basename(p))[0], 'name': s.get('display_name') or os.path.basename(p), 'tasks': tasks})
    return out


def report():
    q21 = M['q21']
    fams = [{'id': f, 'name': v.get('name') or f, 'folder': v.get('folder') or 'diffusion_models', 'modes': v.get('modes'),
             'te': v.get('te'), 'vae': v.get('vae')} for f, v in q21.FAMILIES.items()]
    return {'hardware': hw.summary(), 'paths': config.summary(), 'packs': catalog.packs(),
            'kinds': {'image': image_rows(), 'llm': llm_rows(), 'video': video_rows(), 'tts': tts_rows()},
            'families': {'image': fams, 'tts': tts_families()}, 'user': {k: catalog.user_entries(k) for k in KINDS}}


def list_files(folder):
    """ComfyUI/models/<folder> 下的模型文件（相对路径、大小），加模型时的下拉框用；llm = models/ 下的 .gguf"""
    if folder == 'llm':
        root, exts = config.MODELS_DIR, ('.gguf',)
    elif folder in FOLDERS:
        root, exts = os.path.join(config.COMFY_MODELS, folder), EXTS
    else:
        raise ValueError('不支持的文件夹')
    out = []
    for p in glob.glob(os.path.join(root, '**', '*'), recursive=True):
        if p.lower().endswith(exts) and os.path.isfile(p) and not os.path.basename(p).lower().startswith('mmproj'):
            out.append({'file': os.path.relpath(p, root), 'gb': _gb(p)})
    return sorted(out, key=lambda x: x['file'].lower())[:2000]


def _slug(s):
    s = re.sub(r'[^0-9A-Za-z]+', '-', s or '').strip('-').lower()
    return s[:40] or 'model'


def save_user(kind, entry):
    """加 / 改一个用户模型（同 id 覆盖）。entry 里只留认识的键；返回存好的那条"""
    if kind not in KINDS or not isinstance(entry, dict):
        raise ValueError('参数不对')
    e = {}
    name = str(entry.get('name') or '').strip()[:80]
    if entry.get('hidden') is True and entry.get('id'):  # 藏起一个模型（自带的也行）
        e = {'id': str(entry['id'])[:120], 'hidden': True}
    elif kind == 'image':
        q21 = M['q21']
        fam = entry.get('family')
        if fam not in q21.FAMILIES:
            raise ValueError('不认识的模型类型')
        unet = str(entry.get('unet') or '').strip()
        if not unet:
            raise ValueError('请选择主模型文件')
        e = {'id': str(entry.get('id') or 'u-' + _slug(name or os.path.splitext(os.path.basename(unet))[0])), 'name': name or os.path.basename(unet), 'family': fam, 'unet': unet}
        for x in ('te', 'vae'):
            if entry.get(x):
                e[x] = str(entry[x]).strip()
        if entry.get('tag'):
            e['tag'] = str(entry['tag'])[:40]
    elif kind == 'llm':
        f = str(entry.get('file') or '').strip().replace('\\', '/')
        if not f.lower().endswith('.gguf'):
            raise ValueError('请选择 .gguf 文件')
        e = {'id': str(entry.get('id') or 'u-' + _slug(name or os.path.splitext(os.path.basename(f))[0])), 'family': 'llama', 'name': name or os.path.basename(f),
             'dir': os.path.dirname(f), 'file': os.path.basename(f), 'gpu': 'fit'}
        if entry.get('mmproj'):
            e['mmproj'] = os.path.basename(str(entry['mmproj']))
    elif kind == 'tts':
        fam = entry.get('family')
        if fam not in {x['id'] for x in tts_families()}:
            raise ValueError('不认识的模型类型')
        p = str(entry.get('path') or '').strip().replace('\\', '/')
        if not p:
            raise ValueError('请填写模型文件')
        e = {'id': str(entry.get('id') or _slug(name or os.path.splitext(os.path.basename(p))[0])), 'family': fam, 'path': p,
             'task': entry.get('task') if entry.get('task') in ('tts', 'vc', 'asr') else 'tts', 'mode': 'offline'}
    cur = [x for x in catalog.user_entries(kind) if x.get('id') != e['id']]
    catalog.save_user(kind, cur + [e])
    _reload(kind)
    return e


def delete_user(kind, id_):
    cur = catalog.user_entries(kind)
    new = [x for x in cur if x.get('id') != id_]
    if len(new) == len(cur):
        raise KeyError(id_)
    catalog.save_user(kind, new)
    _reload(kind)


def _reload(kind):
    if kind == 'image':
        M['imagegen'].reload_models()
    elif kind == 'tts' and M.get('restart_tts'):
        M['restart_tts']()
