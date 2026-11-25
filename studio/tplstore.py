"""模板套（2026-11-09 用户）：程序在用户写的内容外面套的那些固定文字，集中在这里管理。

- 一套 = 全部页面用到的全部模板。内置两套只读：正向写法（默认）和 11-08 写法。
- 用户可以基于任意一套新建（复制那一套的全部文字）、改名、改文字、删除，自己定默认用哪套；普通空间和私密空间各存各的。
- 各模块用 register() 登记自己的模板（页面、名称、内置文字、占位符），用 T(名字) 取当前这套里的文字，用 flag() 取这套的写法开关。
- 当前空间放在线程局部变量里：网页请求由 server 设，后台任务开始时由任务自己设（videogen / imagegen）。
"""
import json
import os
import re
import threading
import uuid

_tl = threading.local()
FILE = lambda sp: None  # 由 server 换成真正的路径（普通空间 outputs/，私密空间 .data/）
BUILTIN = {'pos': {'name': '正向写法', 'flags': {'pos': True}, 't': {}},
           'v1108': {'name': '11-08 写法', 'flags': {'pos': False}, 't': {}}}
VERS = {}  # 模板 key → [(版本 id, 名字, {模板名: 文字} 或 None)]，第一个是默认（= 各套内置的文字）；别的版本在网页「系统指令」里选，按空间存在 pick（2026-11-16）
STALE = {}  # 模板名 → 以前的内置文字：自己建的套里照抄的旧内置文字不算“改过”（跟着现在的内置走）
KINDS = []  # 网页上一项一项列出来：{key, pages, label, names: [{name, lang}], slots: {占位符: 说明}}
PROVIDERS = ['videoedit', 'outfit2', 'h3extra', 'ptrans', 'editfix', 'q21', 'audioedit', 'stt']  # 登记了模板的模块：列出全部模板前先导入（有的模块平时用到才导入）
_lock = threading.Lock()
_cache = {}


def register(pages, key, label, names, builtin, slots=None, group=None, sys=False, versions=None, stale=None):
    """pages：用到它的页面（一个或几个）；group：属于哪个功能（网页上先选功能、再选这一份，2026-11-09 用户：一次全列出来太多）；label：功能里的这一份；names：[(模板名, 'zh' / 'en' / '')]；builtin：{套 id: {模板名: 文字}}（没给的套用正向写法那份）
    sys：给 AI 模型的系统指令（网页上和“模板”分开放）；versions：[(版本 id, 名字, {模板名: 文字})]，第一个的文字给 None = 内置那份；stale：{模板名: [以前的内置文字]}"""
    if versions:
        VERS[key] = versions
        for v in versions:  # 别的版本的文字也不算“自己改过”（选了某个版本时新建的套会照抄它）
            for n, x in (v[2] or {}).items():
                STALE.setdefault(n, set()).add(x)
    for n, olds in (stale or {}).items():
        STALE.setdefault(n, set()).update(olds)
    for n, *_ in names:
        for sid in BUILTIN:
            BUILTIN[sid]['t'][n] = (builtin.get(sid) or builtin['pos'])[n]
    KINDS[:] = [k for k in KINDS if k['key'] != key] + [{'key': key, 'pages': [pages] if isinstance(pages, str) else list(pages), 'group': group or label, 'label': label, 'names': [{'name': x[0], 'lang': x[1], **({'pic': x[2]} if len(x) > 2 else {})} for x in names],  # pic：有参考图 / 无参考图（没有这项 = 只有一种）
                'slots': slots or {}, 'sys': bool(sys), **({'versions': [{'id': v[0], 'label': v[1]} for v in versions]} if versions else {})}]


def fmt(t, **kw):
    """只换认识的占位符 {名字}：自己改的模板里写了别的花括号也不会报错"""
    return re.sub(r'\{(\w+)\}', lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), t)


SPACE = None  # 由 server 换成它自己的 space()（网页请求和后台任务线程都已按空间设好）


def space():
    return SPACE() if SPACE else getattr(_tl, 'sp', 'n')


def set_space(sp):
    _tl.sp = sp if sp in ('n', 'v') else 'n'


def store(sp):
    f = FILE(sp)
    if not f or not os.path.isfile(f):
        return {'default': 'pos', 'sets': [], 'pick': {}}
    try:
        mt = os.path.getmtime(f)
        if _cache.get(f, (None,))[0] != mt:
            with open(f, encoding='utf-8') as fh:
                d = json.load(fh)
            sets = [x for x in (d.get('sets') or []) if isinstance(x, dict) and isinstance(x.get('id'), str) and isinstance(x.get('t'), dict)]
            pick = {k: v for k, v in (d.get('pick') or {}).items() if isinstance(k, str) and isinstance(v, str)} if isinstance(d.get('pick'), dict) else {}
            _cache[f] = (mt, {'default': d.get('default') if isinstance(d.get('default'), str) else 'pos', 'sets': sets, 'pick': pick})
        return _cache[f][1]
    except (OSError, ValueError):
        return {'default': 'pos', 'sets': [], 'pick': {}}


def _own(x, base, n):
    """自己建的这套里，这一份是不是自己改过的（照抄的内置文字 / 以前的内置文字不算）"""
    v = x['t'].get(n) if x else None
    return isinstance(v, str) and v != base['t'].get(n) and v not in STALE.get(n, ())


def get(sp, sid=None):
    """某一套（不给 id = 默认那套）：{id, name, builtin, flags, t, vers}；找不到就是内置的正向写法。
    vers：有几个版本的系统指令现在用的是哪个 {key: {id, label, own}}（own = 这套里自己改过这一份，用的是改过的文字）"""
    st = store(sp)
    sid = sid or st['default']
    x = None if sid in BUILTIN else next((x for x in st['sets'] if x['id'] == sid), None)
    if sid not in BUILTIN and not x:
        return get(sp, 'pos')
    base = BUILTIN[sid] if x is None else (BUILTIN.get(x.get('root')) or BUILTIN['pos'])  # 后来新加的模板：这套里没有的，用它最初基于的那套内置的
    t = {n: (x['t'][n] if _own(x, base, n) else v) for n, v in base['t'].items()}
    vers = {}
    for key, vs in VERS.items():
        v = next((v for v in vs if v[0] == st['pick'].get(key)), vs[0])
        own = any(_own(x, base, n) for n in {n for vv in vs for n in (vv[2] or {})})
        if v[2] and not own:
            t.update(v[2])
        vers[key] = {'id': v[0], 'label': v[1], 'own': own}
    if x is None:
        b = BUILTIN[sid]
        return {'id': sid, 'name': b['name'], 'builtin': True, 'flags': dict(b['flags']), 't': t, 'vers': vers}
    return {'id': x['id'], 'name': str(x.get('name') or '未命名'), 'builtin': False, 'flags': {**base['flags'], **(x.get('flags') or {})}, 'base': x.get('base'), 't': t, 'vers': vers}


def T(name):
    u = getattr(_tl, 'used', None)
    if u is not None and name not in u:  # 预览时记下用到了哪几份（网页的“模板”里直接定位到正在用的那份）
        u.append(name)
    return get(space())['t'][name]


class track:
    """with tplstore.track() as used: …  ——这段代码里用到的模板名按顺序收进 used"""
    def __enter__(self):
        self.prev, _tl.used = getattr(_tl, 'used', None), []
        return _tl.used

    def __exit__(self, *a):
        _tl.used = self.prev


def flag(name):
    return get(space())['flags'].get(name)


def listing(sp):
    import importlib
    for m in PROVIDERS:
        try:
            importlib.import_module(m)
        except Exception:  # 某个模块导入失败：其余照常列出
            pass
    st = store(sp)
    sets = [{'id': k, 'name': b['name'], 'builtin': True} for k, b in BUILTIN.items()] + [{'id': x['id'], 'name': str(x.get('name') or '未命名'), 'builtin': False, 'base': x.get('base')} for x in st['sets']]
    d = st['default'] if any(x['id'] == st['default'] for x in sets) else 'pos'
    order = ['ve_', 'vg_', 'img_', 'qe_', 'pt_', 'ae_', 'stt_']  # 网页上的顺序：同一页里先主要的，再 Qwen 改图那句、翻译
    kinds = sorted(KINDS, key=lambda k: next((i for i, x in enumerate(order) if k['key'].startswith(x)), 99))
    return {'sets': sets, 'default': d, 'kinds': kinds, 'pick': dict(st.get('pick') or {})}


def op(sp, b, write_json):
    """网页的操作：create（基于某一套新建）/ save（改名字或文字）/ delete / default / pick（系统指令选哪个版本：key + ver）"""
    f = FILE(sp)
    if not f:
        raise ValueError('模板存放位置不可用')
    with _lock:
        cur = store(sp)
        st = {'default': cur['default'], 'sets': [json.loads(json.dumps(x)) for x in cur['sets']], 'pick': dict(cur.get('pick') or {})}
        kind, sid = b.get('op'), str(b.get('id') or '')
        if kind == 'create':
            src = get(sp, str(b.get('base') or 'pos'))
            name = str(b.get('name') or '').strip()[:40] or (src['name'] + ' 副本')
            sid = 'u' + uuid.uuid4().hex[:8]
            root = src['id'] if src['builtin'] else next((x.get('root') for x in st['sets'] if x['id'] == src['id']), 'pos')
            st['sets'].append({'id': sid, 'name': name, 'base': src['id'], 'root': root, 'flags': src['flags'], 't': src['t']})
        elif kind in ('save', 'delete'):
            x = next((x for x in st['sets'] if x['id'] == sid), None)
            if not x:
                raise ValueError('内置模板不可修改，请先基于它新建一套' if sid in BUILTIN else '找不到这套模板')
            if kind == 'delete':
                st['sets'].remove(x)
                if st['default'] == sid:
                    st['default'] = 'pos'
            else:
                if isinstance(b.get('name'), str) and b['name'].strip():
                    x['name'] = b['name'].strip()[:40]
                known = BUILTIN['pos']['t']
                for n, v in (b.get('t') or {}).items():
                    if n in known and isinstance(v, str):
                        x['t'][n] = v[:20000]
        elif kind == 'pick':
            key, ver = str(b.get('key') or ''), str(b.get('ver') or '')
            vs = VERS.get(key)
            if not vs or not any(v[0] == ver for v in vs):
                raise ValueError('找不到这个版本')
            if ver == vs[0][0]:
                st['pick'].pop(key, None)
            else:
                st['pick'][key] = ver
        elif kind == 'default':
            if sid not in BUILTIN and not any(x['id'] == sid for x in st['sets']):
                raise ValueError('找不到这套模板')
            st['default'] = sid
        else:
            raise ValueError('未知操作')
        os.makedirs(os.path.dirname(f), exist_ok=True)
        write_json(f, st, indent=1)
        _cache.pop(f, None)
    return {**listing(sp), 'id': sid}
