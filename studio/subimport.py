"""载入字幕 / 歌词文件（2026-11-17 用户：播放页右键字幕 → 载入字幕 / 歌词）。
文件 → 播放页用的字幕句 [{'s': 开始秒, 'e': 结束秒, 'text': 文字}]。
支持 .lrc（含多个时间标签、[offset:]、逐字 <mm:ss.xx> 标签）、.srt、.vtt、.ass / .ssa，
以及 QQ 音乐 .qrc（加密的本地文件、接口返回的十六进制、已解开的 XML）和酷狗 .krc（2026-11-18，解密见 lyricdec.py，移植自 LDDC）；格式照 LRC / SubRip / WebVTT / ASS 的常见写法
（参照 pysubs2、pylrc 的解析规则，只取时间和文字，样式不要）。编码：UTF-8（含 BOM）、UTF-16（BOM）、GB18030。"""
import os, re

MAX_BYTES = 4 << 20


def decode(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16')
    for enc in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', 'replace')


def _clean(t):
    t = re.sub(r'<[^>]*>', '', t)  # HTML / VTT 标签、LRC 逐字时间
    return re.sub(r'\s+', ' ', t).strip()


def _fix_ends(sents, last_len=4.0):
    sents = [x for x in sents if x['text']]
    sents.sort(key=lambda x: x['s'])
    for i, x in enumerate(sents):
        nxt = sents[i + 1]['s'] if i + 1 < len(sents) else None
        if x.get('e') is None or x['e'] <= x['s']:
            x['e'] = nxt if nxt is not None and nxt > x['s'] else x['s'] + last_len
    return [{'s': round(x['s'], 3), 'e': round(x['e'], 3), 'text': x['text']} for x in sents]


LRC_TAG = re.compile(r'\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]')


def parse_lrc(text):
    off = 0.0
    m = re.search(r'\[offset:\s*([+-]?\d+)\s*\]', text, re.I)
    if m:
        off = int(m.group(1)) / 1000.0  # 正数 = 歌词提前
    out = []
    for line in text.splitlines():
        tags = list(LRC_TAG.finditer(line))
        if not tags or tags[0].start() != 0:
            continue
        body = _clean(line[tags[-1].end():])
        for t in tags:
            frac = t.group(3) or '0'
            s = int(t.group(1)) * 60 + int(t.group(2)) + int(frac) / (10 ** len(frac))
            out.append({'s': max(0.0, s - off), 'e': None, 'text': body})
    return _fix_ends(out)


TS = r'(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})'


def _ts(m, base):
    h, mi, s, ms = m.group(base), m.group(base + 1), m.group(base + 2), m.group(base + 3)
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / (10 ** len(ms))


CUE = re.compile(TS + r'\s*-->\s*' + TS)


def parse_srt_vtt(text):
    out, cur = [], None
    for line in text.splitlines() + ['']:
        m = CUE.search(line)
        if m:
            if cur:
                out.append(cur)
            cur = {'s': _ts(m, 1), 'e': _ts(m, 5), 'lines': []}
        elif cur is not None:
            if line.strip():
                cur['lines'].append(line)
            else:
                out.append(cur); cur = None
    return _fix_ends([{'s': c['s'], 'e': c['e'], 'text': _clean(' '.join(c['lines']))} for c in out])


def parse_ass(text):
    fmt, out = None, []
    for line in text.splitlines():
        if line.lower().startswith('format:') and fmt is None and 'start' in line.lower():
            fmt = [x.strip().lower() for x in line.split(':', 1)[1].split(',')]
        elif line.lower().startswith('dialogue:'):
            f = fmt or ['layer', 'start', 'end', 'style', 'name', 'marginl', 'marginr', 'marginv', 'effect', 'text']
            parts = line.split(':', 1)[1].split(',', len(f) - 1)
            if len(parts) < len(f):
                continue
            d = dict(zip(f, parts))

            def sec(v):
                h, m, s = v.strip().split(':')
                return int(h) * 3600 + int(m) * 60 + float(s)
            try:
                t = re.sub(r'\{[^}]*\}', '', d['text']).replace('\\N', ' ').replace('\\n', ' ').replace('\\h', ' ')
                out.append({'s': sec(d['start']), 'e': sec(d['end']), 'text': _clean(t)})
            except (KeyError, ValueError):
                continue
    return _fix_ends(out)


_QRC_XML = re.compile(r'LyricContent="(.*?)"\s*/>', re.S)
_QK_LINE = re.compile(r'^\[(\d+),(\d+)\](.*)$')


def parse_qrc_xml(xml):
    """QRC 明文：<Lyric_1 LyricContent="[开始毫秒,时长]字(开始,时长)字(开始,时长)…"> → 字幕句（只取整句的时间和文字）"""
    import html
    m = _QRC_XML.search(xml)
    body = html.unescape(m.group(1)) if m else xml
    out = []
    for line in body.splitlines():
        lm = _QK_LINE.match(line.strip())
        if not lm:
            continue
        st, du, txt = int(lm.group(1)), int(lm.group(2)), re.sub(r'\(\d+,\d+\)', '', lm.group(3))
        out.append({'s': st / 1000, 'e': (st + du) / 1000, 'text': _clean(txt)})
    return _fix_ends(out)


def parse_krc(text):
    """KRC 明文：[开始毫秒,时长]<字偏移,字时长,0>字… → 字幕句"""
    out = []
    for line in text.lstrip('\ufeff').splitlines():
        lm = _QK_LINE.match(line.strip())
        if lm:
            st, du = int(lm.group(1)), int(lm.group(2))
            out.append({'s': st / 1000, 'e': (st + du) / 1000, 'text': _clean(re.sub(r'<\d+,\d+,\d+>', '', lm.group(3)))})
    return _fix_ends(out)


def parse(name, raw):
    """文件名 + 内容（bytes）→ 字幕句。认不出 / 没有带时间的句子 → ValueError"""
    if len(raw) > MAX_BYTES:
        raise ValueError('字幕文件太大（最多 4 MB）')
    ext = os.path.splitext(name or '')[1].lower()
    import lyricdec
    if raw.startswith(lyricdec.QRC_MAGIC) or (ext == '.qrc' and b'<Lyric_1' not in raw[:4096]):  # 加密的 QRC（本地文件 / 接口的十六进制）
        sents = parse_qrc_xml(lyricdec.qrc_decrypt(raw))
        if not sents:
            raise ValueError('QRC 歌词里没有带时间的句子')
        return sents
    if raw.startswith(b'krc1'):  # 加密的 KRC
        sents = parse_krc(lyricdec.krc_decrypt(raw))
        if not sents:
            raise ValueError('KRC 歌词里没有带时间的句子')
        return sents
    text = decode(raw).replace('\r\n', '\n').replace('\r', '\n')
    if '<Lyric_1' in text:  # 已经解开的 QRC（XML）
        sents = parse_qrc_xml(text)
        if sents:
            return sents
    if ext in ('.qrc', '.krc') and _QK_LINE.search(text.lstrip('\ufeff')):  # 已经解开的逐字歌词（没有外面的 XML）
        sents = parse_krc(text) if ext == '.krc' else parse_qrc_xml(text)
        if sents:
            return sents
    if ext in ('.ass', '.ssa') or '[Events]' in text:
        sents = parse_ass(text)
    elif ext in ('.srt', '.vtt') or CUE.search(text):
        sents = parse_srt_vtt(text)
    else:
        sents = parse_lrc(text)
    if not sents:
        raise ValueError('没有找到带时间的字幕（支持 LRC、SRT、VTT、ASS、QRC、KRC）')
    return sents
