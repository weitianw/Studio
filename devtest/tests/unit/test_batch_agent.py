"""F02 / F21 / F10 / P03 / F09 / F11（2026-11-17 审查）：批量的结果计数、私密推送、活动索引与锁、Agent 的对账和重启后的旧代号。
假的视频模块（不跑引擎、不碰真实数据），临时目录。"""
import json, os, sys, threading, time, types
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import batch, agentapi


class FakeVG:
    def __init__(self):
        self.jobs, self.gal, self.spliced, self.splice_fail = {}, {'n': [], 'v': []}, [], False

    def gallery(self, sp):
        return list(self.gal[sp])

    def gallery_get(self, gid, sp):
        return next((x for x in self.gal[sp] if x['id'] == gid), None)

    def vfile(self, sp, f):
        return f

    def _probe(self, p):
        return {'duration': 10}

    def splice(self, first, sp, rest):
        if self.splice_fail:
            raise RuntimeError('拼接失败（模拟）')
        self.spliced.append([first] + rest)
        return {'id': 'sp_' + first, 'file': 'sp.mp4'}

    def qc_run(self, sp, iid):
        return {'m': {'face_sim': 0.9, 'face_dL': 1, 'bg_dL': 1, 'drift': 0.01}, 'flags': []}

    def list_jobs(self, sp, limit=30):
        return [j for j in self.jobs.values() if j.get('space') == sp]


@pytest.fixture
def env(tmp_path, monkeypatch):
    vg = FakeVG()
    notes, acts = [], []
    d = {sp: (str(tmp_path / sp / 'recipes.json'), str(tmp_path / sp / 'batches')) for sp in ('n', 'v')}
    video = tmp_path / 'v.mp4'; video.write_bytes(b'x')
    monkeypatch.setattr(batch, '_ctx', {'videogen': vg, 'dirs': lambda sp: d[sp], 'act': lambda *a, **k: acts.append(a), 'notify': lambda *a: notes.append(a),
                                        'set_space': lambda sp: None, 'mats_path': lambda rel: str(video), 'submit': lambda body, sp: {'id': 'J' + str(len(vg.jobs))},
                                        'split_for': lambda *a: [[0, 5], [5, 10]], '_th': True})
    monkeypatch.setattr(batch, '_active', {}); monkeypatch.setattr(batch, '_claimed', set()); monkeypatch.setattr(batch, '_ops', {})
    monkeypatch.setattr(batch, '_cancel_req', set())
    monkeypatch.setattr(agentapi, '_ctx', {'videogen': vg, 'key_file': str(tmp_path / 'agent.key'), 'act': lambda *a, **k: None, 'ffmpeg': None})
    monkeypatch.setattr(agentapi, '_map', {})
    return types.SimpleNamespace(vg=vg, notes=notes, acts=acts, tmp=tmp_path)


def make(sp, segs, splice=True, bid=None):
    r = {'id': 'default', **batch._clean_recipe({'name': '测试配方', 'instruction': '换成白色连衣裙', 'splice': splice})}
    b = {'id': bid or time.strftime('%Y%m%d-%H%M%S-') + os.urandom(2).hex(), 'space': sp, 'created': time.time(), 'recipe': r, 'state': 'running', 'note': '',
         'items': [{'video': {'mats': 'a.mp4'}, 'label': '', 'dur': 10, 'state': 'run', 'splice': None, 'error': '', 'segs': segs}]}
    batch._put(sp, b)
    batch._mark_active(sp, b['id'])
    return b


def seg(a, z, state, ok=True, result='g'):
    tries = [{'job': 'J', 'state': 'done', 'result': result, 'ok': ok, 'score': 0.5}] if state == 'done' else [{'job': None, 'state': 'error', 'error': '生成失败'}]
    return {'a': a, 'b': z, 'tries': tries, 'best': 0 if state == 'done' else None, 'state': state}


# ---------------- F02 / F21
def test_all_success(env):
    b = make('n', [seg(0, 5, 'done', result='g1'), seg(5, 10, 'done', result='g2')])
    batch.tick('n', b['id'])
    b = batch.get('n', b['id'])
    assert b['state'] == 'done' and b['items'][0]['state'] == 'done'
    assert b['counts']['complete'] == 1 and b['counts']['seg_pass'] == 2 and b['note'].startswith('1/1 个视频完整做好')
    assert env.notes[-1] == ('批量做完了', b['note'], '/batch')


def test_missing_segment_is_partial_not_done(env):
    b = make('n', [seg(0, 5, 'done', result='g1'), seg(5, 10, 'fail')])
    batch.tick('n', b['id'])
    b = batch.get('n', b['id'])
    it = b['items'][0]
    assert it['state'] == 'partial' and it['splice']['state'] == 'done' and env.vg.spliced == [['g1']]  # 做好的部分保留
    c = b['counts']
    assert c['complete'] == 0 and c['partial'] == 1 and c['seg_gen_fail'] == 1 and c['seg_pass'] == 1
    assert '0/1 个视频完整做好' in b['note'] and '缺 5.0 秒–10.0 秒' in b['note'] and '生成失败' in b['note']
    assert env.notes[-1][0] == '批量做完了（有缺的）'
    batch.redo('n', b['id'], 0, 1)  # 缺的段可以重做
    b = batch.get('n', b['id'])
    assert b['state'] == 'running' and b['items'][0]['segs'][1]['state'] == 'wait' and b['id'] in batch.active_ids('n')


def test_qc_fail_and_splice_fail_counted_separately(env):
    b = make('n', [seg(0, 5, 'done', ok=False, result='g1'), seg(5, 10, 'done', result='g2')])
    batch.tick('n', b['id'])
    b = batch.get('n', b['id'])
    assert b['items'][0]['state'] == 'done' and b['counts']['seg_qc_fail'] == 1 and '1 段没过质检' in b['note']
    env.vg.splice_fail = True
    b2 = make('n', [seg(0, 5, 'done', result='g1')])
    batch.tick('n', b2['id'])
    b2 = batch.get('n', b2['id'])
    assert b2['items'][0]['state'] == 'partial' and b2['counts']['splice_failed'] == 1 and '1 个拼接失败' in b2['note']


def test_private_batch_push_hides_details(env):
    b = make('v', [seg(0, 5, 'done', result='g1'), seg(5, 10, 'fail')])
    batch.tick('v', b['id'])
    b = batch.get('v', b['id'])
    assert env.notes[-1] == ('Studio', '有任务已完成', '/batch')  # 和别的私密任务一样：不说是什么、不报数字
    assert '缺' in b['note'] and b['counts']['partial'] == 1  # 解锁后的界面里照样有详情
    assert all('缺' not in str(a) and '个视频' not in str(a) for a in env.acts)
    b2 = make('v', [seg(0, 5, 'fail')])
    batch.tick('v', b2['id'])
    assert env.notes[-1] == ('Studio', '有任务失败', '/batch')


def test_agent_batch_status_uses_same_counts(env):
    b = make('n', [seg(0, 5, 'done', result='g1'), seg(5, 10, 'fail')])
    batch.tick('n', b['id'])
    r = agentapi.batch_status('n', 'b_' + b['id'])
    assert r['counts'] == batch.get('n', b['id'])['counts']
    assert r['videos'][0]['state'] == 'partial' and r['videos'][0]['outcome']['missing'] == [[5, 10]]


# ---------------- F10 / P03
def test_old_active_batch_beyond_300_is_advanced(env):
    old = make('n', [seg(0, 5, 'done', result='g0')], bid='20000101-000000-0001')
    for k in range(320):  # 更新的 320 条历史
        b = {'id': f'20260101-{k:06d}-ffff', 'space': 'n', 'created': 1, 'recipe': old['recipe'], 'items': [], 'state': 'done', 'note': ''}
        batch._put('n', b)
    batch._active.clear()  # 模拟重启：活动索引重新扫一遍
    assert old['id'] in batch.active_ids('n')
    lst = batch.listing('n')
    assert lst[0]['id'] == old['id'] and len(lst) == 31  # 正在跑的排最前，后面一页历史
    reads = []
    real_get = batch.get
    with patch.object(batch, 'get', side_effect=lambda sp, bid: reads.append(bid) or real_get(sp, bid)):
        for sp in ('n', 'v'):
            for bid in sorted(batch.active_ids(sp)):
                batch.tick(sp, bid)
    assert len(reads) <= 2  # 只读正在跑的那一份（以前每轮最多读 600 份）
    assert batch.get('n', old['id'])['state'] == 'done' and old['id'] not in batch.active_ids('n')


def test_video_job_list_keeps_all_active(env):
    import videogen
    jobs = {f'q{k}': {'id': f'q{k}', 'space': 'n', 'state': 'queued', 'created': k} for k in range(40)}
    jobs.update({f'd{k}': {'id': f'd{k}', 'space': 'n', 'state': 'done', 'created': 100 + k} for k in range(10)})
    with patch.object(videogen, 'jobs', jobs), patch.object(videogen, 'public', lambda j: dict(j)):
        ids = {j['id'] for j in videogen.list_jobs('n')}
        assert {f'q{k}' for k in range(40)} <= ids  # 最早排的也在
        assert videogen.get_job('q0', 'n')['id'] == 'q0' and videogen.get_job('q0', 'v') is None


def test_lock_not_held_while_processing_and_ops_applied(env):
    a = make('n', [seg(0, 5, 'done', result='g1')])
    other = make('n', [seg(0, 5, 'done', ok=False, result='o1'), seg(5, 10, 'done', result='o2')])
    other['items'][0]['segs'][0]['tries'].append({'job': 'J2', 'state': 'done', 'result': 'o3', 'ok': True, 'score': 0.9})
    batch._put('n', other)
    gate = threading.Event()
    real_step = batch._step

    def slow(sp, b):  # 处理一条要很久（质检 / 拼接）
        gate.wait(3)
        return real_step(sp, b)
    with patch.object(batch, '_step', slow):
        t = threading.Thread(target=batch.tick, args=('n', a['id'])); t.start()
        time.sleep(0.2)
        t0 = time.time()
        batch.pick('n', other['id'], 0, 0, 1)  # 别的批量：不用等
        waited = time.time() - t0
        batch.redo('n', a['id'], 0, 0)  # 正在处理的这条：排队，提交前应用
        gate.set(); t.join(5)
    assert waited < 0.5
    assert batch.get('n', other['id'])['items'][0]['segs'][0]['best'] == 1
    a2 = batch.get('n', a['id'])
    assert a2['state'] == 'running' and a2['items'][0]['segs'][0]['state'] == 'wait'  # 重做没丢


def test_cancel_during_processing(env):
    a = make('n', [seg(0, 5, 'done', result='g1'), seg(5, 10, 'done', result='g2')])
    gate = threading.Event()
    real_step = batch._step
    with patch.object(batch, '_step', lambda sp, b: (gate.wait(3), real_step(sp, b))[1]):
        t = threading.Thread(target=batch.tick, args=('n', a['id'])); t.start()
        time.sleep(0.2)
        t0 = time.time(); batch.cancel('n', a['id']); assert time.time() - t0 < 0.5
        gate.set(); t.join(5)
    assert batch.get('n', a['id'])['state'] == 'cancelled'


# ---------------- F09 / F11
def test_job_status_reconciles_missing(env):
    env.vg.jobs = {'J1': {'id': 'J1', 'space': 'n', 'state': 'running', 'created': time.time()},
                   'J2': {'id': 'J2', 'space': 'n', 'state': 'done', 'created': time.time()}}
    h1, h2 = agentapi.handle('job', 'J1', 'n'), agentapi.handle('job', 'J2', 'n')
    r = agentapi.job_status('n', ['j_nothere00'])
    assert r['jobs'][0]['state'] == 'missing' and r['missing'] == ['j_nothere00']  # 全部缺失
    r = agentapi.job_status('n', [h1, 'j_nothere00'])
    assert [j['state'] for j in r['jobs']] == ['running', 'missing'] and r['missing'] == ['j_nothere00']  # 部分缺失
    r = agentapi.job_status('n', [h2])
    assert r['jobs'][0]['state'] == 'done' and r['missing'] == []


def test_old_job_handle_after_restart_can_redo(env):
    env.vg.gal['n'] = [{'id': 'G1', 'job': 'J9', 'file': 'a.mp4'}]
    h = agentapi.handle('job', 'J9', 'n')
    agentapi._map.clear(); env.vg.jobs = {}  # 模拟重启：内存里的代号表、任务都没了
    got = {}
    env.vg.redo_input = lambda iid, sp: ({'model': 'h3'}, None, None)
    env.vg.submit = lambda b, img, ff, x, vid: got.setdefault('b', b) and {'id': 'J10'}
    r = agentapi.retry('n', h)
    assert got['b']['model'] == 'h3' and r['job'].startswith('j_')
    st = agentapi.job_status('n', [h])
    assert st['jobs'][0]['state'] == 'done' and st['jobs'][0]['result'].startswith('w_')  # 重启前做完的：从视频库对上
    agentapi._map.clear()
    with pytest.raises(ValueError):  # 空间隔离：私密空间里解析不出普通空间的代号
        agentapi.retry('v', h)
