"""P03（2026-11-17 审查）：批量 runner 每一轮读多少份记录、处理一条时别的批量 / 取消要等多久。
同一场景（300 条历史 + 1 条正在跑；处理一条要 2 秒）分别跑修复前（c400ee5 的 batch.py，命令行给路径）和现在的 batch.py。临时目录、假的视频模块。
用法：python -I bench_p03.py [旧 batch.py 路径]"""
import importlib.util, json, os, sys, tempfile, threading, time, types
STUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'studio')
sys.path.insert(0, STUDIO)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def bench(mod, label, newest=False):
    d = tempfile.mkdtemp()
    reads = [0]
    vg = types.SimpleNamespace(jobs={}, gallery=lambda sp: [], _probe=lambda p: {'duration': 10}, qc_run=lambda *a: {}, splice=lambda *a: {})
    mod._ctx.update({'videogen': vg, 'dirs': lambda sp: (os.path.join(d, sp, 'r.json'), os.path.join(d, sp, 'b')), 'act': lambda *a, **k: None,
                     'notify': lambda *a: None, 'set_space': lambda sp: None, 'mats_path': lambda r: __file__, '_th': True})
    r = {'id': 'x', **mod._clean_recipe({'name': 't', 'instruction': '白色连衣裙'})}
    for k in range(300):
        mod._put('n', {'id': f'20260101-{k:06d}-ffff', 'space': 'n', 'created': 1, 'recipe': r, 'items': [], 'state': 'done', 'note': ''})
    act = {'id': '29990101-000000-0001' if newest else '20000101-000000-0001', 'space': 'n', 'created': 1, 'recipe': r, 'state': 'running', 'note': '',
           'items': [{'video': {'mats': 'a'}, 'label': '', 'dur': 10, 'state': 'run', 'splice': None, 'error': '', 'segs': [{'a': 0, 'b': 5, 'tries': [], 'best': None, 'state': 'wait'}]}]}
    other = dict(act, id='29990101-000000-0000' if newest else '20000101-000000-0002')
    mod._put('n', act); mod._put('n', other)
    real_get = mod.get
    mod.get = lambda sp, bid: (reads.__setitem__(0, reads[0] + 1), real_get(sp, bid))[1]
    slow = threading.Event()

    def step(sp, b):  # 处理一条要 2 秒（质检 / 拼接）
        if b['id'] == act['id']:
            slow.wait(2)
        return False
    mod._step = step
    if hasattr(mod, 'active_ids'):
        mod._active.clear()
    # 一轮 runner 读了几份（不含第一次建活动索引那次全扫）
    if hasattr(mod, 'active_ids'):
        mod.active_ids('n'); mod.active_ids('v')
    reads[0] = 0
    t = threading.Thread(target=lambda: (mod._wake.set(), None)); t.start(); t.join()

    def one_pass():
        if hasattr(mod, 'tick'):
            for sp in ('n', 'v'):
                for bid in sorted(mod.active_ids(sp)):
                    mod.tick(sp, bid)
        else:  # 旧 runner 的一轮
            for sp in ('n', 'v'):
                for bid in mod._all_ids(sp)[:300]:
                    with mod._lock:
                        b = mod.get(sp, bid)
                        if not b or b.get('state') != 'running':
                            continue
                        mod._step(sp, b)
    th = threading.Thread(target=one_pass); th.start(); time.sleep(0.3)
    t0 = time.time(); mod.cancel('n', other['id']); wait_cancel = time.time() - t0  # 处理 act 时取消另一条
    th.join()
    return {'version': label, 'scenario': 'active newest' if newest else 'active older than 300 history', 'reads_per_pass': reads[0], 'cancel_wait_s': round(wait_cancel, 2),
            'active_processed': slow.is_set() or wait_cancel > 0.5 or label == 'now'}


if __name__ == '__main__':
    out = []
    if len(sys.argv) > 1:
        out.append(bench(load(sys.argv[1], 'batch_old'), 'before c400ee5'))
        out.append(bench(load(sys.argv[1], 'batch_old2'), 'before c400ee5', newest=True))
    out.append(bench(load(os.path.join(STUDIO, 'batch.py'), 'batch_new'), 'now'))
    out.append(bench(load(os.path.join(STUDIO, 'batch.py'), 'batch_new2'), 'now', newest=True))
    for x in out:
        print(json.dumps(x, ensure_ascii=False))
