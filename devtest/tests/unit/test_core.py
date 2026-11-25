"""纯 Python 的单元测试（不起服务、不用显卡）：2026-11-14 审查修的几处 + 推荐分段 / Agent 接口的关键规则。
跑：cd devtest && python -m pytest"""
import json, os, sys, tempfile, time
import numpy as np
import pytest

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)


def test_timing_stops_after_finish():
    import stages
    t = stages.Track(); t.note('正在生成'); t.finish(); t.note('完成')
    time.sleep(0.05)
    e = t.export()
    assert [s['name'] for s in e['stages']] == ['正在生成']  # 结束以后不再开新的一步（以前“完成”那一步会一直涨）


def test_media_fp_reads_second_half_of_small_files(tmp_path):
    import stt
    a, b = tmp_path / 'a.bin', tmp_path / 'b.bin'
    head = os.urandom(1 << 20)
    a.write_bytes(head + b'\x00' * 500_000); b.write_bytes(head + b'\x01' * 500_000)
    assert stt.media_fp(str(a)) != stt.media_fp(str(b))


def test_stt_load_skips_broken_records(tmp_path):
    import stt
    (tmp_path / 'x').mkdir(); (tmp_path / 'x' / 'stt.json').write_text('{}', encoding='utf-8')
    stt.load_old_stt(str(tmp_path), 'n')  # 以前 KeyError: 'id'


def test_translate_cache_is_per_space(tmp_path):
    import ptrans
    cur = {'sp': 'n'}
    ptrans.CACHE = lambda: str(tmp_path / cur['sp'] / 'c.json')
    ptrans._m()['k'] = 'normal'; ptrans._save()
    cur['sp'] = 'v'
    assert 'k' not in ptrans._m()
    ptrans._m()['k'] = 'private'; ptrans._save()
    assert json.load(open(tmp_path / 'n' / 'c.json', encoding='utf-8')) == {'k': 'normal'}
    assert json.load(open(tmp_path / 'v' / 'c.json', encoding='utf-8')) == {'k': 'private'}
    ptrans.CACHE = None


def test_autocorr_lags_match_full_correlation():
    on = np.random.default_rng(1).random(3000)
    full = np.correlate(on, on, 'full')[on.size - 1:]
    for L in (20, 45, 80):
        assert np.isclose(full[L], np.dot(on[:-L], on[L:]))


def test_segpref_split_matches_web_rule():
    import segpref  # 十一酱那段的候选点 → 和以前网页上的规则一样的三段
    pts = [(0.733, 'hit', 0.669, 0, 0), (2.467, 'beat', 0.7, 0, 0), (3.067, 'swing', 0.725, 0, 0), (3.367, 'swing', 0.68, 1, 1), (4.667, 'hit', 0.62, 0, 0),
           (5.1, 'swing', 0.561, 1, 1), (5.533, 'hit', 0.585, 0, 0), (6.267, 'hit', 0.7, 0, 0), (6.867, 'swing', 0.84, 1, 1), (7.3, 'beat', 0.7, 0, 0),
           (7.733, 'swing', 0.66, 0, 0), (8.167, 'beat', 0.7, 0, 0), (8.633, 'swing', 0.739, 1, 1), (9.5, 'hit', 0.817, 0, 0), (10.367, 'swing', 0.567, 1, 1),
           (10.8, 'hit', 0.721, 0, 0), (11.233, 'swing', 0.63, 0, 0), (11.667, 'beat', 0.7, 0, 0), (12.133, 'swing', 0.734, 1, 1), (12.567, 'swing', 0.67, 0, 0),
           (13.0, 'swing', 0.744, 0, 0), (13.267, 'hit', 0.6, 0, 0), (14.767, 'hit', 0.56, 0, 0)]
    cp = {'dur': 15.0, 'points': [{'t': t, 'kind': k, 'score': s, **({'sync': True} if y else {}), **({'db': True} if d else {})} for t, k, s, y, d in pts]}
    assert segpref.split(cp) == [[0.733, 5.1], [6.867, 10.367], [12.133, 15.0]]


def test_segpref_needs_enough_history(tmp_path):
    import segpref
    fn = str(tmp_path / 'p.jsonl')
    cp = {'dur': 10.0, 'points': [{'t': 1.0, 'kind': 'hit', 'score': 0.8}, {'t': 5.0, 'kind': 'hit', 'score': 0.8}]}
    for k in range(3):
        segpref.record(fn, {**cp, '_key': f'v{k}'}, [[1.0, 5.0]])
    st = segpref.status(fn)
    assert st['videos'] == 3 and st['use'] == 'rule'


def test_agent_scrub_removes_names_and_paths():
    import agentapi
    for raw in ('素材库中找不到该文件：clips/@某人_20240127_标题.mp4', r'No such file: D:\Studio\private\library\a b.mp4', '读不出「我的视频」'):
        out = agentapi.scrub(raw)
        assert '.mp4' not in out and '@' not in out and 'clips' not in out and '我的视频' not in out and 'library' not in out
    assert agentapi.scrub('正在生成 · 第 3/6 步') == '正在生成 · 第 3/6 步'


def test_agent_handles_are_opaque(tmp_path):
    import agentapi
    agentapi.setup(key_file=str(tmp_path / 'k'))
    h = agentapi.handle('mats', 'clips/秘密.mp4', 'v')
    assert h.startswith('v_') and len(h) == 12 and '秘密' not in h
    assert agentapi.handle('mats', 'clips/秘密.mp4', 'n') != h  # 两个空间的代号不一样
