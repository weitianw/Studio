"""F13 / F14 / F19（2026-11-17 审查）：恢复历史任务时计时不重新开始；转写中断后历史还在；并发保存设置不丢字段。临时目录。"""
import json, os, sys, threading, time
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import stages, stt


SAVED = {'t0': 1000.0, 't1': 1100.0, 'now': 1100.0, 'stages': [{'name': '生成', 'sec': 80.0, 'live': False}, {'name': '拼接音频', 'sec': 20.0, 'live': False}]}


def total(e):
    return round((e['t1'] or e['now']) - e['t0'], 1)


def test_track_restore_finished_does_not_grow():
    tr = stages.Track.restore(SAVED)
    e1 = tr.export(); time.sleep(0.2); e2 = tr.export()
    assert total(e1) == total(e2) == 100.0
    assert [s['sec'] for s in e2['stages']] == [80.0, 20.0] and not any(s['live'] for s in e2['stages'])
    tr.note('完成')  # 恢复后再赋值“完成”：不再开新的一步
    assert len(tr.export()['stages']) == 2


def test_track_restore_old_record_and_interrupted():
    tr = stages.Track.restore(None, 500.0, 560.0)  # 旧记录没有计时字段
    e = tr.export(); assert total(e) == 60.0 and e['stages'] == []
    live = {'t0': 10.0, 't1': None, 'now': 40.0, 'stages': [{'name': '识别', 'sec': 30.0, 'live': True}]}
    e = stages.Track.restore(live, 10.0, 40.0).export()  # 存的时候还在跑（被关掉了）：按结束时间收尾
    assert total(e) == 30.0 and not e['stages'][0]['live']


def test_tts_job_restore_keeps_timing(tmp_path):
    import server
    d = tmp_path / 'job1'; d.mkdir()
    (d / 'job.json').write_text(json.dumps({'params': {'kind': 'tts'}, 'state': 'done', 'message': '完成', 'created': 1000.0, 'finished': 1100.0, 'segments': [], 'timing': SAVED}), encoding='utf-8')
    with patch.object(server, 'jobs', {}):
        server.load_job('n', str(tmp_path), 'job1')
        j = server.jobs['job1']
        e1 = j.timing(); time.sleep(0.2); e2 = j.timing()
    assert total(e1) == total(e2) == 100.0 and not any(s['live'] for s in e2['stages'])


def test_stt_restore_keeps_timing(tmp_path):
    d = tmp_path / 's1'; d.mkdir()
    (d / 'stt.json').write_text(json.dumps({'id': 's1', 'state': 'done', 'message': '完成', 'created': 1000.0, 'finished': 1100.0, 'timing': SAVED}), encoding='utf-8')
    (tmp_path / 's2').mkdir()  # 旧记录：没有 timing
    (tmp_path / 's2' / 'stt.json').write_text(json.dumps({'id': 's2', 'state': 'done', 'created': 500.0, 'finished': 530.0}), encoding='utf-8')
    with patch.object(stt, 'stt_jobs', {}):
        stt.load_old_stt(str(tmp_path))
        assert total(stt.stt_jobs['s1'].timing()) == 100.0
        assert total(stt.stt_jobs['s2'].timing()) == 30.0


def test_stt_interrupted_before_and_during_recognition_still_listed(tmp_path):
    src = tmp_path / 'in.wav'; src.write_bytes(b'x')
    # ① 刚开始（准备音频之前）就被关掉：线程没跑起来
    with patch.object(stt, 'stt_jobs', {}), patch.object(stt.threading, 'Thread'):
        j = stt.SttJob(str(src), 'a.wav', 'qwen', 'auto', None, root=str(tmp_path))
    with patch.object(stt, 'stt_jobs', {}):
        stt.load_old_stt(str(tmp_path))
        r = stt.stt_jobs[j.id]
        assert r.state == 'error' and '上次未完成' in r.message
    # ② 识别时被关掉
    entered = threading.Event()

    def fake_ff(*a):
        open(a[-1], 'wb').write(b'w')
    def hang(*a, **k):
        entered.set(); time.sleep(30)
    root2 = tmp_path / 'r2'; root2.mkdir()
    with patch.object(stt, 'stt_jobs', {}), patch.object(stt, 'ffmpeg', fake_ff), patch.object(stt, 'media_seconds', lambda p: 12.0), \
            patch.object(stt, 'media_fp', lambda p: 'fp'), patch.object(stt, 'act', lambda *a, **k: None):
        j2 = stt.SttJob(str(tmp_path / 'in2.wav'), 'b.wav', 'qwen', 'auto', hang, root=str(root2))
        assert entered.wait(5)
    with patch.object(stt, 'stt_jobs', {}):
        stt.load_old_stt(str(root2))
        r = stt.stt_jobs[j2.id]
        assert r.state == 'error' and '上次未完成' in r.message and r.duration == 12.0


def test_concurrent_settings_saves_keep_both(tmp_path):
    f = tmp_path / 'settings.json'
    f.write_text(json.dumps({'llm_model': 'a', 'whisper_model': 'm0'}), encoding='utf-8')
    real_load = stt.load_settings

    def slow_load():  # 让两个请求的读改写交错
        s = real_load(); time.sleep(0.2); return s
    keys = [k for k in stt.DEFAULT_SETTINGS if not k.startswith('whisper_exe')][:2]
    with patch.object(stt, 'SETTINGS', str(f)), patch.object(stt, 'load_settings', slow_load):
        ts = [threading.Thread(target=stt.save_settings, args=({keys[0]: 'X1'},)), threading.Thread(target=stt.save_settings, args=({keys[1]: 'X2'},))]
        [t.start() for t in ts]; [t.join() for t in ts]
    s = json.loads(f.read_text(encoding='utf-8'))
    assert s[keys[0]] == 'X1' and s[keys[1]] == 'X2'


def test_settings_write_failure_keeps_original(tmp_path):
    f = tmp_path / 'settings.json'
    f.write_text(json.dumps({'llm_model': 'a'}), encoding='utf-8')
    before = f.read_bytes()
    k = next(iter(stt.DEFAULT_SETTINGS))
    with patch.object(stt, 'SETTINGS', str(f)), patch.object(stt.os, 'replace', side_effect=OSError('写不进去')):
        with pytest.raises(OSError):
            stt.save_settings({k: 'zz'})
    assert f.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ['settings.json']
