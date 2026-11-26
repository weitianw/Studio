"""模型目录（开源泛化 ②）：模型从代码挪进 json，用户可以自己加模型。

三层，后面的覆盖前面的（同一个 id）：
  1. studio/catalog/<类>.json          程序自带（进 git）
  2. studio/packs/<包>/catalog/<类>.json 功能包带的（包在才有）
  3. studio/user-models.json            用户自己加的 / 改的（不进 git），格式 {"image": [ {...}, ... ], "llm": [...], "tts": [...]}

每一类里分 families（怎么跑：工作流 / 引擎，写在代码里，json 只给默认文件和设置）和 models（用哪些文件）。
用户条目可以：加新模型（选一个已有的 family、给出文件）；改已有模型的某几项；"hidden": true 藏起来。
没写 settings 的用户模型，用同一 family 第一个模型的设置（family 自己写了 settings 的用 family 的）。
"""
import copy, glob, json, os, threading

STUDIO = os.path.dirname(os.path.abspath(__file__))
CAT_DIR = os.path.join(STUDIO, 'catalog')
PACKS_DIR = os.path.join(STUDIO, 'packs')
USER_FILE = os.path.join(STUDIO, 'user-models.json')
_lock = threading.RLock()


def _read(p):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def packs():
    """装着的功能包（studio/packs/<名字>/，有 pack.json 的）"""
    out = []
    for d in sorted(glob.glob(os.path.join(PACKS_DIR, '*', 'pack.json'))):
        meta = _read(d) or {}
        out.append({'id': os.path.basename(os.path.dirname(d)), **meta})
    return out


def has_pack(name):
    return os.path.isfile(os.path.join(PACKS_DIR, name, 'pack.json'))


def user_entries(kind):
    d = _read(USER_FILE) or {}
    v = d.get(kind) if isinstance(d, dict) else None
    return [x for x in v if isinstance(x, dict) and x.get('id')] if isinstance(v, list) else []


def _merge(base, extra, source):
    fams, models = base['families'], base['models']
    for f, meta in (extra.get('families') or {}).items():
        fams[f] = {**fams.get(f, {}), **meta}
    for e in extra.get('models') or []:
        if not isinstance(e, dict) or not e.get('id'):
            continue
        k = e['id']
        if k in models:
            models[k] = {**models[k], **e}
        else:
            models[k] = {**e, 'source': source}
    return base


def load(kind):
    """合好的目录：{'families': {...}, 'models': {id: {...}}}（models 保持顺序：自带的在前，功能包的、用户的接在后面）"""
    with _lock:
        base = _read(os.path.join(CAT_DIR, kind + '.json')) or {}
        out = {'families': copy.deepcopy(base.get('families') or {}), 'models': {}}
        for e in base.get('models') or []:
            out['models'][e['id']] = {**copy.deepcopy(e), 'source': 'builtin'}
        for p in packs():
            extra = _read(os.path.join(PACKS_DIR, p['id'], 'catalog', kind + '.json'))
            if extra:
                _merge(out, extra, 'pack:' + p['id'])
        _merge(out, {'models': user_entries(kind)}, 'user')
        for k in [k for k, m in out['models'].items() if m.get('hidden')]:
            out['models'].pop(k)
        fam_first = {}
        for k, m in out['models'].items():
            fam_first.setdefault(m.get('family'), m)
        for k, m in out['models'].items():
            f = out['families'].get(m.get('family')) or {}
            if 'settings' not in m:
                m['settings'] = copy.deepcopy(f.get('settings') or (fam_first.get(m.get('family')) or {}).get('settings') or {})
            if 'modes' not in m:
                m['modes'] = list(f.get('modes') or list(m['settings']) or ['txt'])
            if 'defaults' not in m and 'txt' in m['settings']:
                s = m['settings']['txt']
                m['defaults'] = {x: s.get(x, 1.0 if x == 'cfg' else None) for x in ('steps', 'cfg', 'sampler', 'scheduler')}
        return out


def save_user(kind, entries):
    """写回 user-models.json 里这一类（别的类不动）"""
    with _lock:
        d = _read(USER_FILE) or {}
        if not isinstance(d, dict):
            d = {}
        d[kind] = entries
        tmp = USER_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, USER_FILE)
