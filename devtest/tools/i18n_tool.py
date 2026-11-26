"""英文界面词典（studio/web/i18n-en.js）的维护（开源泛化 ④）。

  python -I devtest/tools/i18n_tool.py missing [输出.json]
      找出前端源码里现在的词典翻不全的中文（和 i18n.js 同样的规则：整段有词条，或者用片段拼完以后没有中文），写成待翻译的列表。
  python -I devtest/tools/i18n_tool.py add 译文.json
      把 {中文: English} 合进词典（同一个中文以新的为准），按键排好写回 i18n-en.js。
  界面上实际剩下的：devtest/ui-audit/t_i18n.py（测试 Studio 里每页切成英文，列出还剩的中文）。
翻译要求：简洁、正式的产品界面英文（句首大写，按钮短）；保留数字、型号、文件名；片段前后的标点照原来的作用写（，→ , ：→ : ）。"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(ROOT, 'studio', 'web')
DICT = os.path.join(WEB, 'i18n-en.js')
HAN = re.compile('[一-鿿]')
RUN = re.compile(r'[一-鿿　-〿＀-￯“”‘’…·—][一-鿿　-〿＀-￯“”‘’…·—0-9A-Za-z \-/.%+×~]*'
                 r'[一-鿿　-〿＀-￯“”‘’…]|[一-鿿]')


def load():
    t = open(DICT, encoding='utf-8').read()
    return json.loads(t[t.index('{'):t.rindex('}') + 1])


def save(d):
    js = ('/* English UI dictionary (Chinese source fragment -> English), extracted from the UI source and translated; used by i18n.js. */\n'
          'window.I18N_EN = ' + json.dumps(d, ensure_ascii=False, sort_keys=True, indent=0) + ';\n')
    open(DICT, 'w', encoding='utf-8', newline='\n').write(js)


def covered(s, D, rx):
    t = s.strip()
    if t in D:
        return True

    def rep(m):
        a, b = m.start(), m.end()
        p, n = s[a - 1] if a else '', s[b] if b < len(s) else ''
        if len(m.group(0)) == 1 and (HAN.search(p or ' ') or HAN.search(n or ' ')):
            return m.group(0)
        return D[m.group(0)]
    return not HAN.search(rx.sub(rep, s))


def missing():
    D = load()
    rx = re.compile('|'.join(re.escape(k) for k in sorted((k for k in D if k), key=len, reverse=True)))
    todo = set()
    for f in glob.glob(os.path.join(WEB, '*.js')) + glob.glob(os.path.join(WEB, '*.html')):
        if f.endswith('i18n-en.js'):
            continue
        t = open(f, encoding='utf-8').read()
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
        t = re.sub(r'(?m)^\s*//.*$', '', t)
        t = re.sub(r'(?m)\s//\s.*$', '', t)
        for m in RUN.finditer(t):
            s = m.group(0).strip()
            if HAN.search(s) and not covered(s, D, rx):
                todo.add(s)
    return sorted(todo)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a[:1] == ['missing']:
        m = missing()
        if len(a) > 1:
            json.dump(m, open(a[1], 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        print(f'翻不全的 {len(m)} 段'); [print(' ', x) for x in m[:40]]
    elif a[:1] == ['add'] and len(a) > 1:
        d = load(); new = json.load(open(a[1], encoding='utf-8'))
        bad = [k for k, v in new.items() if not isinstance(v, str) or not v.strip() or HAN.search(v)]
        d.update({k: v for k, v in new.items() if k not in bad})
        save(d); print(f'加了 {len(new) - len(bad)} 条，跳过 {len(bad)} 条（空的或者还有中文），词典共 {len(d)} 条')
    else:
        sys.exit(__doc__)
