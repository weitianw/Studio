import json, sys
sys.stdout.reconfigure(encoding='utf-8')
for tag in sys.argv[1:]:
    R = json.load(open(f'click_{tag}/res.json', encoding='utf-8'))
    print('#####', tag, 'errs:', R.get('_errs', [])[:6])
    for pg, items in R.items():
        if pg.startswith('_'): continue
        n = len(items); bad = []
        for it in items:
            if it.get('skip') or it.get('gone'): continue
            prob = []
            if it.get('hit') not in (None, 'ok'): prob.append('点不到:' + str(it['hit']))
            if it.get('err'): prob.append('报错:' + str(it['err'])[:120])
            if it.get('stuck'): prob.append('关不掉:' + str(it['stuck']))
            if it.get('ovx'): prob.append('横向溢出')
            if any(p.get('out') for p in it.get('pops', [])): prob.append('弹出层出屏')
            for s in it.get('sub', []):
                if s.get('hit') not in (None, 'ok'): prob.append(f"子项点不到[{s['t']}]:{s['hit']}")
                if s.get('err'): prob.append(f"子项报错[{s['t']}]:" + str(s['err'])[:100])
                if s.get('out'): prob.append(f"子项出屏[{s['t']}]")
            if prob: bad.append((it['t'], prob))
        print(f'== {pg}: {n} 项', '' if bad else '没问题')
        for t, p in bad: print('   ', t, '|', '; '.join(p)[:300])
