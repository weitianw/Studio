"""F16（2026-11-17 审查）：改视频按任务和底模判断真正要的文件；模拟文件矩阵下界面状态（status）和后台提交（parse）一致。不碰真实模型。"""
import os, sys
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import videoedit as ve
import videogen as V

VAE = [f for f in V.MODELS['h3']['files'] if f.startswith('vae/')]
GEN = list(V.MODELS['h3']['files']) + list(V.MODELS['h3']['diffusion'])  # 生视频的官方原版（FL2VA / Ref2VA 完整版）
OFFICIAL = VAE + [ve.FULL, ve.FULL_TE, ve.LITE, ve.LITE_TE]
LORAS = [ve.FILES[k] for k in ve.FILES]  # 各做法的 LoRA / 节点文件都在
MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 2000


def run(files):
    have = set(files)
    with patch.object(V, '_have', lambda f: f in have), patch.object(ve.V, '_have', lambda f: f in have), patch.object(ve, 'qedit_ok', lambda: True), \
            patch.object(ve.os.path, 'isfile', lambda p: True if p == V.COMFY_PY else os.path.isfile(p)), patch.object(ve, 'RMBG', ve.FILES.get('cs11', 'x')):
        st = ve.status()
        res = {}
        for task in ve.TASKS:
            b = {'edit': {'task': task}, 'prompt': '白色连衣裙'}
            try:
                ve.parse(b, MP4, b'\x89PNG' + b'\x00' * 2000)
                res[task] = True
            except RuntimeError:
                res[task] = False
            except ValueError as e:  # 参数类的问题（不是缺文件）
                res[task] = 'value:' + str(e)
        return st, res


@pytest.mark.parametrize('name,files', [
    ('只有官方完整版 / 精简版', OFFICIAL + LORAS),
    ('只有生视频的官方完整版', GEN + LORAS),
    ('两样都有', GEN + OFFICIAL + LORAS),
])
def test_status_matches_submit(name, files):
    st, res = run(files)
    for task, avail in st['tasks'].items():
        assert res[task] is avail, (name, task, avail, res[task], st.get('missing'))


def test_official_only_enables_official_paths():
    st, res = run(OFFICIAL + LORAS)
    assert st['official'] and st['ok'] and all(st['tasks'].values())
    assert st['swap_by'] == ['v11', 'ref'] and st['head_by'] == ['fs']


def test_nothing_installed():
    st, res = run([])
    assert not st['ok'] and not any(st['tasks'].values()) and not any(res.values())
