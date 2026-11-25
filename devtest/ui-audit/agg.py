import json, sys, os, glob, re
sys.stdout.reconfigure(encoding='utf-8')
skip = set((os.environ.get('SKIP') or 'ellipsis,small').split(','))
only = set(filter(None, (os.environ.get('ONLY') or '').split(',')))
U = {}
for f in glob.glob('aud/*/res.json'):
    prof = f.split(os.sep)[-2] if os.sep in f else f.split('/')[-2]
    R = json.load(open(f, encoding='utf-8'))
    items = [(n, part, x) for n, rec in R['pages'].items() for part in ('top', 'bottom') for x in (rec.get(part) or {}).get('F', [])]
    items += [(n + '[弹窗]', 'm', x) for n, M in (R.get('modal') or {}).items() for x in (M.get('check') or {}).get('F', [])]
    for n, part, x in items:
        if x['kind'] in skip or (only and x['kind'] not in only): continue
        el = re.sub(r'“.*', '', x['el'])[:50]; k = (n, x['kind'], el)
        U.setdefault(k, {'profs': set(), 'msg': x['msg'], 'el': x['el']})['profs'].add(prof + part[0])
for (n, kind, el), v in sorted(U.items()):
    print(f"{n:12} {kind:11} {v['el'][:56]:56} | {v['msg'][:50]:50} | {len(v['profs'])}: {','.join(sorted(v['profs']))[:90]}")
