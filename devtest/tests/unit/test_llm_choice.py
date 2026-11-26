"""开源泛化 ②：AI 助手的模型能换。目录里的默认模型照旧排第一；models/llm/ 下自己放的 .gguf 自动列出来
（同文件夹的 mmproj-*.gguf 当识图部分），按显存自动放（gpu = fit），不开 MTP；选了不存在的模型时退回默认的。"""
import os, sys

STUDIO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
sys.path.insert(0, STUDIO)
import config, promptgen  # noqa: E402


def test_default_and_folder_models(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'MODELS_DIR', str(tmp_path))
    d = tmp_path / 'llm' / 'Small-8B'
    d.mkdir(parents=True)
    (d / 'small-8b-q4_k_m.gguf').write_bytes(b'0' * 10)
    (d / 'mmproj-small.gguf').write_bytes(b'0')
    ms = promptgen.llm_models()
    assert list(ms)[0] == 'qwen38-27b' and ms['qwen38-27b']['mtp'] is True
    k = 'gguf:llm/Small-8B/small-8b-q4_k_m.gguf'
    assert k in ms and ms[k]['mmproj'] == 'mmproj-small.gguf' and ms[k]['gpu'] == 'fit' and not ms[k].get('mtp')
    assert promptgen.available(k) == os.path.isfile(promptgen.LLAMA)
    assert promptgen.vision(k) is True
    assert promptgen.clamp_engine({'model': k})['model'] == k
    assert promptgen.clamp_engine({'model': 'nope'})['model'] == 'qwen38-27b'
    assert promptgen.model_info('nope')['file'] == promptgen.MODEL_FILE
    assert [m['id'] for m in promptgen.model_list()] == ['qwen38-27b', k]
