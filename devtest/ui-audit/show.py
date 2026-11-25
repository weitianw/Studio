import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
skip = set((os.environ.get('SKIP') or 'ellipsis').split(','))
for prof in sys.argv[1:]:
    R = json.load(open(f'aud/{prof}/res.json', encoding='utf-8'))
    print('#####', prof, 'errs', R['errs'][:5], 'bad', R['bad'][:5])
    for n, rec in R['pages'].items():
        fs = [(part, f) for part in ('top', 'bottom') for f in (rec.get(part) or {}).get('F', []) if f['kind'] not in skip]
        sw = {k: v for k, v in (rec.get('swipe') or {}).items() if v.get('moved') and k[0] in 'LR'}
        le = rec.get('lastEl') or {}
        if fs or sw or rec.get('crash') or le.get('coveredBy') or 'go()' in (rec.get('nav') or []):
            print('==', n, rec.get('nav'), 'crash' if rec.get('crash') else '', 'lastCovered:' + str(le.get('coveredBy')) if le.get('coveredBy') else '', 'SWIPE' + str(list(sw)) if sw else '')
            seen = set()
            for part, f in fs:
                k = (f['kind'], f['el'][:40], f['msg'][:30])
                if k in seen: continue
                seen.add(k); print('  ', part[0], f['kind'], f['el'][:58], '|', f['msg'][:64], f['r'])
    for pn, M in (R.get('modal') or {}).items():
        print('MODAL', pn, M.get('open'), {k: v.get('moved') for k, v in (M.get('swipe') or {}).items()}, [f['kind'] + ' ' + f['el'][:40] for f in (M.get('check') or {}).get('F', []) if f['kind'] not in skip][:8], M.get('crash', ''))
