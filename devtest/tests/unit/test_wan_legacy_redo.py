"""C02（2026-11-17 审查）：Wan 的生成分支删掉后，旧记录（model = wan、改衣做法 = animate / bernini）重新生成照样能排上，按 H3 / 参考生成做。
临时目录，不起引擎、不用显卡（缺文件检查、排队都换成假的）。"""
import os, sys, threading
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import videogen, videoedit


def queued(b, img=None, vid=None):
    q = []
    with patch.object(videogen, 'missing', lambda key: []), patch.object(videogen, 'official_ok', lambda: {'fl2va': True, 'ref2va': True}), patch.object(videogen, '_q', q), patch.object(videogen, '_qcv', threading.Condition()), \
            patch.object(videogen, 'jobs', {}):
        j = videogen.submit(b, img, 'ffmpeg', None, vid)
    return j, q


def test_old_wan_generation_redo_runs_as_h3():
    old = {'model': 'wan', 'prompt': '一个人在海边散步', 'seconds': 5, 'size': '480p', 'steps': 4, 'split': 2, 'seed': -1}
    j, q = queued(old, b'')
    assert j['model'] == 'h3' and q and q[0]['model'] == 'h3'
    assert j['seconds'] <= videogen.MAX_SECONDS['h3']


def test_redo_input_from_old_record(tmp_path):
    sp = 'n'
    rd = tmp_path / 'redo'; rd.mkdir()
    (rd / 'v1.mp4').write_bytes(b'\x00' * 2000)
    item = {'id': 'g1', 'redo': {'b': {'model': 'wan', 'prompt': '旧提示词', 'edit': {'task': 'outfit', 'method': 'animate'}}, 'vid': 'v1.mp4', 'img': None}}
    with patch.object(videogen, 'gallery_get', lambda iid, s: item), patch.object(videogen, 'videos_dir', lambda s: str(tmp_path)):
        b, img, vid = videogen.redo_input('g1', sp)
    assert b['model'] == 'wan' and b['seed'] == -1 and vid == b'\x00' * 2000 and img is None


def test_old_outfit_method_migrates_to_ref():
    st = {'ok': True, 'tasks': {t: True for t in videoedit.TASKS}, 'missing': [], 'swap_by': ['v11', 'ref'], 'outfit_ref': True, 'full': True, 'official': True,
          'lite': False, 'head_by': ['fs']}
    with patch.object(videoedit, 'status', lambda: st), patch.object(videoedit, 'video_kind', lambda v: 'mp4'):
        for old in ('animate', 'bernini'):
            try:
                e = videoedit.parse({'prompt': '换成红裙子', 'edit': {'task': 'outfit', 'method': old}}, b'\x00' * 2000, b'img')
            except (RuntimeError, ValueError) as x:  # 后面的步骤要真文件：只要不是因为“做法不存在”报错
                assert 'animate' not in str(x) and 'bernini' not in str(x)
                continue
            assert e['method'] == 'ref'


def test_old_wan_record_workflow(tmp_path):
    """旧 Wan 记录（带尾帧、自选 LoRA、不要声音）拼出来的是 H3 工作流：17k+5 帧、尾帧接 last_frame、LoRA 只接一份、声音节点去掉。
    （审查时另用同样三种任务比对过改动前后的工作流 JSON，逐字节一致）"""
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (640, 480), (120, 80, 60)).save(buf, 'PNG'); png = buf.getvalue()
    j, q = queued({'model': 'wan', 'prompt': '海边', 'seconds': 5, 'size': '480p', 'audio': False}, png)
    j = q[0]; j['_end'] = png; j['loras'] = [{'name': 'my.safetensors', 'w': 0.6, 'on': 'both'}]  # 尾帧；旧 Wan 的“两者都接”
    (tmp_path / 'in').mkdir(); (tmp_path / 'out').mkdir()
    with patch.object(videogen, '_have', lambda f: True), patch.object(videogen.Engine, 'ensure', lambda *a, **k: None), \
            patch.object(videogen, 'sampler_options', lambda: None), patch.dict(videogen.WORK, {'n': str(tmp_path)}):
        wf = videogen._prep_job(j).wf
    assert [n['inputs'].get('length') for n in wf.values() if n['class_type'].startswith('MiniMaxH3')] == [124]
    assert wf['7']['inputs']['last_frame'] == ['40', 0] and wf['40']['class_type'] == 'LoadImage'
    assert [n['inputs']['lora_name'] for n in wf.values() if n['class_type'] == 'LoraLoaderModelOnly' and n['inputs']['lora_name'] == 'my.safetensors'] == ['my.safetensors']
    assert '14' not in wf and not any(n['class_type'].startswith('Wan') for n in wf.values())
