"""提示词翻成英文（“提示词语言 = 英文”时用，2026-11-04 用户要求）。
用本地提示词模型（AI 助手那个，约 23 GB 显存）翻；翻完把显存让出来再跑视频。
锁住的内容（翻译前后必须一字不差，不一样就报错，调用方回退成中文）：
- <d>…</d> 里的对白、引号里的画面文字（“…”、"…"、「…」）
- 标签：<Subject N> <Picture N> <Video N> <Audio N> [Shot N] (S1)，‹…› 占位
- 标记词和段落名：fully_preserved 这类、[video editing] 这类任务类型、subject_definitions: 这类字段名
做法：先把锁住的内容换成 ⟦0⟧ ⟦1⟧ …，让模型只翻其余部分并原样保留这些记号，翻完再换回去、逐个核对。
结果按“原文 + 语言”缓存（内存 + 一个 JSON 文件），同一段不重复翻。"""
import hashlib, json, os, re, threading

CHAT = None      # 由 server.py 换成 local_chat(system, user)
RELEASE = None   # 由 server.py 换成“提示词模型退出、让出显存”
CACHE = None     # 由 server.py 设成缓存文件的路径；也可以是函数 CACHE() → 当前空间的缓存文件（2026-11-14：私密空间的翻译不再写进普通空间的缓存）
_lock = threading.Lock()
_mems = {}       # 缓存文件 → {键: 译文}


def _path():
    return CACHE() if callable(CACHE) else CACHE


def _m():
    return _mems.setdefault(_path() or '', {})

MARKS = ('fully_preserved', 'partially_preserved', 'attribute_transfer', 'weak_reference', 'fully_copy', 'partially_copy')
FIELDS = ('subject_definitions', 'summary', 'retention_analysis', 'detailed_description', 'overall_soundscape', 'non_diegetic_music', 'integrated_multimodal_description')
LOCK_RE = re.compile(
    r'<d>.*?</d>'                                   # 对白
    r'|“[^”]*”|"[^"\n]*"|「[^」]*」'               # 引号里的画面文字
    r'|<(?:Subject|Picture|Video|Audio) \d+>'       # 标签
    r'|\[Shot \d+\]|\((?:S\d+(?:,\s*S\d+)*)\)'
    r'|‹[^›]*›'                                     # 模板占位
    r'|\[(?:[a-z][a-z +]*)\]'                       # [video editing] 这类任务类型
    r'|\b(?:' + '|'.join(MARKS) + r')\b'
    r'|^\s*(?:' + '|'.join(FIELDS) + r')\s*:',      # 段落名（行首）
    re.S | re.M)
SYSTEM = ('You are a professional translator for AI video-generation prompts. Translate the user text from Chinese into natural, precise English. '
          'Rules: 1) Every token of the form ⟦number⟧ must appear in your output exactly once, unchanged, at the matching place. '
          '2) Keep the line breaks and the order of the lines. 3) Translate faithfully and completely; do not add, remove, soften or explain anything. '
          '4) Output only the translation.')
CJK = re.compile(r'[一-鿿]')


def needs(text):
    return bool(CJK.search(text or ''))


def _key(text, lang):
    return hashlib.sha1(f'{lang}\n{text}'.encode('utf-8') + (b'' if tplstore.T('PT_SYS') == SYSTEM else b'\n' + tplstore.T('PT_SYS').encode('utf-8'))).hexdigest()


def _load():
    c, m = _path(), _m()
    if m or not c or not os.path.isfile(c):
        return
    try:
        with open(c, encoding='utf-8') as f:
            m.update(json.load(f))
    except (OSError, ValueError):
        pass


def _save():
    c = _path()
    if not c:
        return
    try:
        items = dict(list(_m().items())[-500:])  # 最多留 500 条
        os.makedirs(os.path.dirname(c), exist_ok=True)
        with open(c + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False)
        os.replace(c + '.tmp', c)
    except OSError:
        pass


def locked(text):
    """锁住的内容（按出现顺序）"""
    return [m.group(0) for m in LOCK_RE.finditer(text or '')]


def check(src, out):
    """翻译前后锁住的内容是不是一样（顺序可以变，数量和内容不能变）→ 不一样的那些；空 = 没问题"""
    a, b = sorted(locked(src)), sorted(locked(out))
    if a == b:
        return []
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    return sorted((ca - cb).elements()) + sorted((cb - ca).elements())


def translate(text, lang='en'):
    """→ (译文, 是否来自缓存)。锁住的内容对不上时抛 ValueError（带上对不上的内容）"""
    text = (text or '').strip()
    if lang != 'en' or not needs(text):
        return text, False
    with _lock:
        _load()
        k = _key(text, lang)
        if k in _m():
            return _m()[k], True
    spans = []

    def sub(m):
        spans.append(m.group(0))
        return f'⟦{len(spans) - 1}⟧'
    masked = LOCK_RE.sub(sub, text)
    if CHAT is None:
        raise RuntimeError('本地提示词模型不可用，无法翻译')
    try:
        out = (CHAT(tplstore.T('PT_SYS'), masked) or '').strip()
    finally:
        if RELEASE:
            try:
                RELEASE()  # 翻完让出显存，再跑视频
            except Exception:
                pass
    out = re.sub(r'^```\w*\n|\n```$', '', out).strip()
    marks = re.findall(r'⟦(\d+)⟧', out)
    if sorted(map(int, marks)) != list(range(len(spans))):
        raise ValueError('翻译结果中受保护的内容（对白、画面文字、标签或标记词）不完整，已改用中文')
    res = re.sub(r'⟦(\d+)⟧', lambda m: spans[int(m.group(1))], out)
    bad = check(text, res)
    if bad:
        raise ValueError('翻译前后受保护的内容不一致：' + '、'.join(bad[:5]))
    if needs(re.sub(LOCK_RE, '', res)):  # 锁住的部分以外还留着中文：没翻完
        raise ValueError('翻译结果中仍有未翻译的中文，已改用中文')
    with _lock:
        _m()[_key(text, lang)] = res
        _save()
    return res, False


# 2026-11-09 模板套：翻译用的系统指令登记到 tplstore
import tplstore
tplstore.register(['vgen', 'vedit'], 'pt_sys', '系统指令', [('PT_SYS', 'en')], {'pos': {'PT_SYS': SYSTEM}}, group='翻译成英文', sys=True)
