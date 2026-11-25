"""F07（2026-11-17 审查）：单段重做时合并、导出 MP3、最后写记录任何一步失败，原文字、声音、成品、记录都保持一致；重试能成功。
合成的音频、临时目录，不碰真实作品。"""
import json, math, os, struct, sys, wave
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server


def tone(path, hz, sec=0.6, sr=24000):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(2 * math.pi * hz * i / sr))) for i in range(int(sr * sec))))


@pytest.fixture
def job(tmp_path):
    j = object.__new__(server.Job)
    j.id, j.dir = 'tjob', str(tmp_path)
    (tmp_path / 'seg').mkdir()
    j.params = {'model': 'm', 'voice': '', 'check': False, 'pause': 0.1, 'pause_para': 0.2}
    j.segments = []
    for i, hz in enumerate((300, 400)):
        tone(j.seg_path(i), hz)
        j.segments.append({'index': i, 'text': f'第{i}段原文', 'direction': '', 'status': 'done', 'cer': 0.0, 'asr': '', 'attempts': 1,
                           'seconds': 0.6, 'mode': '', 'end': 'sent', 'para_end': False})
    j.state, j.message, j.error, j.title = 'done', '完成', '', 't'
    j.created, j.finished, j.duration, j.cancel, j.saved = 1.0, 2.0, None, False, False
    j.log = lambda *a, **k: None
    j.merge()  # 原成品
    j.save()
    (tmp_path / 'subs_play.json').write_text('{"sents": []}', encoding='utf-8')  # 原字幕
    return j


def snap(j):
    d = j.dir
    rd = lambda n: open(os.path.join(d, n), 'rb').read()
    return {'seg1': rd('seg/0001.wav'), 'wav': rd('output.wav'), 'mp3': rd('output.mp3'), 'job': rd('job.json'), 'text': j.segments[1]['text'],
            'subs': os.path.exists(os.path.join(d, 'subs_play.json'))}


def fake_render(j):
    def render(i, attempt, model, voice):  # 模拟生成：这一段换成新的声音
        s = j.segments[i]
        tone(j.seg_path(i), 800)
        s.update(status='done', seconds=0.6, attempts=s['attempts'] + 1)
    return render


def redo(j):
    with patch.object(server, 'model_info', return_value={}), patch.object(server, 'get_voice', return_value=None), \
            patch.object(j, 'render', fake_render(j), create=True):
        j.redo(1, text='第1段新文字')


@pytest.mark.parametrize('where', ['merge', 'mp3', 'save'])
def test_failure_keeps_everything_consistent_then_retry_works(job, where):
    before = snap(job)
    real_ffmpeg, real_write, real_merge = server.ffmpeg, server.write_json, server.merge_segments
    boom = RuntimeError('注入的失败：' + where)
    ff = (lambda *a: (_ for _ in ()).throw(boom)) if where == 'mp3' else real_ffmpeg
    mg = (lambda *a, **k: (_ for _ in ()).throw(boom)) if where == 'merge' else real_merge
    n = {'k': 0}

    def wj(path, obj, **kw):
        if where == 'save' and str(path).endswith('job.json'):
            n['k'] += 1
            if n['k'] == 1:  # 第一次（发布成品时那次）失败；回滚时那次照常写
                raise OSError('注入的写入失败')
        return real_write(path, obj, **kw)
    with patch.object(server, 'ffmpeg', ff), patch.object(server, 'merge_segments', mg), patch.object(server, 'write_json', wj):
        with pytest.raises((RuntimeError, OSError)):
            redo(job)
    after = snap(job)
    assert after['seg1'] == before['seg1'], '这一段的声音被换掉了'
    assert after['wav'] == before['wav'] and after['mp3'] == before['mp3'], '旧成品被改了'
    assert after['text'] == before['text'] == '第1段原文'
    assert json.loads(after['job'])['segments'][1]['text'] == '第1段原文'
    assert after['subs'], '旧字幕在失败时被删了'
    assert not [f for f in os.listdir(job.dir) if '.new.' in f or f.endswith(('.redo-old', '.redo-bak'))], os.listdir(job.dir)
    assert not [f for f in os.listdir(os.path.join(job.dir, 'seg')) if f.endswith('.redo-bak')]
    with wave.open(os.path.join(job.dir, 'output.wav')) as w:  # 旧成品能正常读
        assert w.getnframes() > 0
    redo(job)  # 重试：成功
    ok = snap(job)
    assert ok['seg1'] != before['seg1'] and ok['wav'] != before['wav'] and ok['mp3'] != before['mp3']
    assert ok['text'] == '第1段新文字' and json.loads(ok['job'])['segments'][1]['text'] == '第1段新文字'
    assert not ok['subs']  # 成品换了：旧字幕作废


def test_normal_merge_is_atomic_on_export_failure(job):
    before = snap(job)
    with patch.object(server, 'ffmpeg', side_effect=RuntimeError('导出失败')):
        with pytest.raises(RuntimeError):
            job.merge()
    after = snap(job)
    assert after['wav'] == before['wav'] and after['mp3'] == before['mp3']
