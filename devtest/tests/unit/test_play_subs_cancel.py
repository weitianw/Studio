"""播放页“正在生成字幕”的进度和取消（2026-11-18 用户）：识别换成故意慢的假函数，不用显卡、不碰真实文件。
- 开始后返回 running + 进度 p（0~1）；
- 取消：马上回到 none；那次识别做完后结果丢掉，不写字幕；
- 取消后立刻重新开始：旧的那次做完时不会顶掉 / 删掉新的结果；
- 没在识别时点取消：照实返回现在的字幕。"""
import os, sys, threading, time
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server


@pytest.fixture
def h(tmp_path):
    audio, out = str(tmp_path / 'a.wav'), str(tmp_path / 'subs' / 'x.json')
    os.makedirs(os.path.dirname(out))
    open(audio, 'wb').write(b'x')
    calls = {'n': 0}

    def fake_ffmpeg(*a):
        open(a[-1], 'wb').write(b'\0' * (44 + 32000 * 10))  # 10 秒的 16 kHz 单声道

    def slow_asr(wav, tag='', language=None):
        calls['n'] += 1; n = calls['n']
        time.sleep(0.8)
        return f'第{n}次。', [{'c': c, 's': 0.1 * i, 'e': 0.1 * i + 0.1} for i, c in enumerate(f'第{n}次')], 'zh'
    hd = object.__new__(server.Handler)
    sent = []
    hd.send_json = lambda d, code=200: sent.append(d)
    ps = [patch.object(server, 'play_subs_target', return_value=(audio, out)), patch.object(server, 'ffmpeg', fake_ffmpeg),
          patch.object(server, 'transcribe_ts', slow_asr), patch.object(server, 'act', lambda *a, **k: None), patch.object(server, 'space', return_value='n')]
    for x in ps: x.start()
    server.play_subs_state.clear(); server.play_subs_prog.clear()

    def call(method='GET', **q):
        hd.play_api(method, [], {'key': 'job:t', **q}); return sent[-1]
    yield call, out
    for x in ps: x.stop()


def wait_done(call, t=5):
    end = time.time() + t
    while time.time() < end:
        r = call()
        if r['state'] != 'running':
            return r
        time.sleep(0.05)
    return r


def test_progress_then_done(h):
    call, out = h
    r = call('POST'); assert r['state'] == 'running' and 0 < r['p'] < 1
    time.sleep(0.4); r2 = call(); assert r2['state'] == 'running' and r2['p'] >= r['p']
    r = wait_done(call); assert r['state'] == 'done' and r['sents'][0]['text'] == '第1次。'
    assert os.path.isfile(out) and not [f for f in os.listdir(os.path.dirname(out)) if '.part' in f]


def test_cancel_discards_result(h):
    call, out = h
    call('POST'); time.sleep(0.2)
    assert call('POST', cancel='1')['state'] == 'none'
    assert call()['state'] == 'none'
    time.sleep(1.2)  # 那次识别做完
    assert call()['state'] == 'none' and not os.path.exists(out)
    assert not [f for f in os.listdir(os.path.dirname(out)) if '.part' in f or '16k' in f]


def test_restart_after_cancel_keeps_new_result(h):
    call, out = h
    call('POST'); time.sleep(0.2)
    call('POST', cancel='1')
    call('POST')  # 马上重新开始（第 2 次识别）
    r = wait_done(call); assert r['state'] == 'done' and r['sents'][0]['text'] == '第2次。'
    time.sleep(0.3)
    assert call()['sents'][0]['text'] == '第2次。'  # 第 1 次做完时没有顶掉


def test_cancel_when_already_done_reports_done(h):
    call, out = h
    call('POST'); wait_done(call)
    r = call('POST', cancel='1'); assert r['state'] == 'done' and r['sents']
