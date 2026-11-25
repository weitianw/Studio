"""F18（2026-11-17 审查）：同一个目标的并发下载只放行一个；模型已落盘而说明信息没写成时，重试能补写。假的 Civitai 接口，临时目录。"""
import io, json, os, sys, threading, time, types
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import civitai

VER = {'files': [{'name': 'x.safetensors', 'primary': True, 'sizeKB': 100, 'downloadUrl': 'https://example.invalid/x'}], 'model': {'name': 'm'}, 'name': 'v1'}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(civitai, 'TARGETS', {'h3': {'dir': str(tmp_path / 'loras')}})
    monkeypatch.setattr(civitai, 'downloads', {})
    monkeypatch.setattr(civitai, '_get', lambda url: VER)
    monkeypatch.setattr(civitai, '_meta', lambda v, info, name: {'name': 'm', 'version': 'v1'})
    monkeypatch.setattr(civitai, 'key', lambda: '')
    return tmp_path / 'loras'


class Resp(io.BytesIO):
    headers = {'Content-Type': 'application/octet-stream', 'Content-Length': str(200 * 1024)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_concurrent_same_target_only_one(env):
    started = []
    barrier = threading.Barrier(2)
    res = []

    def go():
        barrier.wait()
        try:
            res.append(civitai.download(1, 'h3'))
        except ValueError as e:
            res.append(str(e))
    with patch.object(civitai, 'threading', types.SimpleNamespace(Thread=lambda target, args, daemon: type('T', (), {'start': lambda s: started.append(args)})())):
        ts = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
    assert len(started) == 1 and sum(isinstance(r, str) and '正在下载' in r for r in res) == 1


def test_meta_failure_then_retry_rewrites_meta(env):
    with patch.object(civitai, 'threading', types.SimpleNamespace(Thread=lambda target, args, daemon: type('T', (), {'start': lambda s: None})())):
        d = civitai.download(1, 'h3')
    did, dst = d['id'], civitai.downloads[d['id']]['_dst']
    opener = type('O', (), {'open': lambda s, req, timeout=60: Resp(b'\x01' * (200 * 1024))})()
    with patch.object(civitai.urllib.request, 'build_opener', lambda *a: opener), patch.object(civitai, '_write_meta', side_effect=OSError('写不进去')):
        civitai._fetch(did, 'https://example.invalid/x', dst, {'name': 'm'})
    st = civitai.downloads[did]
    assert st['state'] == 'done' and '说明信息' in st['error'] and os.path.getsize(dst) == 200 * 1024
    assert not [f for f in os.listdir(env) if f.endswith('.part')]
    r = civitai.download(1, 'h3')  # 重试：不重新下载，补写说明信息
    assert r['state'] == 'done' and r.get('note') and json.load(open(dst + '.civitai.json', encoding='utf-8'))['name'] == 'm'
    with pytest.raises(ValueError, match='此前已下载'):
        civitai.download(1, 'h3')
