"""开源泛化 ②⑤：放不放得下的估计（hw.fit）和模型页的“自己加模型”（modelsinfo.save_user / delete_user）。"""
import json, os, sys
import pytest

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)
import catalog, hw, modelsinfo  # noqa: E402


def test_fit_rules():
    assert hw.fit(20, 10, vram_gb=24, ram_gb=64) == 'ok'
    assert hw.fit(30, 10, vram_gb=24, ram_gb=64) == 'tight'     # 文本编码器挪到内存后放得下
    assert hw.fit(30, 2, vram_gb=24, ram_gb=64) == 'no'         # 挪不走那么多
    assert hw.fit(30, 28, vram_gb=24, ram_gb=16) == 'no'        # 内存也不够
    assert hw.fit(None) == 'unknown' and hw.fit(5, vram_gb=0) == 'unknown'


class FakeQ21:
    FAMILIES = {'zimg': {'name': 'Z-Image Turbo'}, 'ckpt': {'name': 'Checkpoint'}}


class FakeIG:
    reloads = 0

    def reload_models(self):
        FakeIG.reloads += 1


@pytest.fixture
def mi(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, 'USER_FILE', str(tmp_path / 'user-models.json'))
    spec = tmp_path / 'specs'
    spec.mkdir()
    (spec / 'kokoro.json').write_text(json.dumps({'display_name': 'Kokoro', 'tasks': ['tts']}), encoding='utf-8')
    restarted = []
    monkeypatch.setattr(modelsinfo, 'M', {'q21': FakeQ21, 'imagegen': FakeIG(), 'specs_dir': str(spec), 'restart_tts': lambda: restarted.append(1)})
    yield restarted


def test_add_image_model_and_reload(mi):
    e = modelsinfo.save_user('image', {'name': 'My SDXL', 'family': 'ckpt', 'unet': 'sdxl\\x.safetensors', 'evil': 1})
    assert e == {'id': 'u-my-sdxl', 'name': 'My SDXL', 'family': 'ckpt', 'unet': 'sdxl\\x.safetensors'}
    assert catalog.user_entries('image') == [e] and FakeIG.reloads >= 1
    modelsinfo.save_user('image', {'id': 'u-my-sdxl', 'name': 'Renamed', 'family': 'ckpt', 'unet': 'sdxl\\x.safetensors'})
    assert [x['name'] for x in catalog.user_entries('image')] == ['Renamed']   # 同 id 覆盖
    with pytest.raises(ValueError):
        modelsinfo.save_user('image', {'name': 'bad', 'family': 'nope', 'unet': 'a'})
    with pytest.raises(ValueError):
        modelsinfo.save_user('image', {'name': 'no file', 'family': 'zimg'})
    modelsinfo.delete_user('image', 'u-my-sdxl')
    assert catalog.user_entries('image') == []
    with pytest.raises(KeyError):
        modelsinfo.delete_user('image', 'u-my-sdxl')


def test_hide_builtin_and_llm_and_tts(mi):
    assert modelsinfo.save_user('image', {'id': 'zit-diving', 'hidden': True}) == {'id': 'zit-diving', 'hidden': True}
    e = modelsinfo.save_user('llm', {'file': 'llm/Small/small-q4.gguf'})
    assert e['dir'] == 'llm/Small' and e['file'] == 'small-q4.gguf' and e['gpu'] == 'fit'
    with pytest.raises(ValueError):
        modelsinfo.save_user('llm', {'file': 'x.bin'})
    t = modelsinfo.save_user('tts', {'name': 'Kokoro', 'family': 'kokoro', 'path': 'models\\kokoro\\k.gguf'})
    assert t == {'id': 'kokoro', 'family': 'kokoro', 'path': 'models/kokoro/k.gguf', 'task': 'tts', 'mode': 'offline'} and mi == [1]
    with pytest.raises(ValueError):
        modelsinfo.save_user('tts', {'family': 'unknown', 'path': 'a.gguf'})
    with pytest.raises(ValueError):
        modelsinfo.save_user('video', {})


def test_user_tts_models_reach_engine_config(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(catalog, 'USER_FILE', str(tmp_path / 'u.json'))
    catalog.save_user('tts', [{'id': 'kokoro', 'family': 'kokoro', 'path': 'models/kokoro/k.gguf', 'task': 'tts', 'mode': 'offline'},
                              {'id': 'breeze', 'hidden': True}])
    monkeypatch.setattr(server, '_cfg_local', lambda: {})
    cfg = server.server_cfg()
    ids = [m['id'] for m in cfg['models']]
    assert 'kokoro' in ids and 'breeze' not in ids
    k = next(m for m in cfg['models'] if m['id'] == 'kokoro')
    assert os.path.isabs(k['path']) and k['path'].endswith('kokoro/k.gguf')
