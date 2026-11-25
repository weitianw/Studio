"""C05（2026-11-17 审查）：网页上改配音引擎的会话参数，写进 server.local.json（本机覆盖），受跟踪的 server.json 一个字节都不变；
引擎拿到的是合成后的配置；改回默认时覆盖清掉；默认里本来就开着的参数关掉时记成 null。临时目录。"""
import json, os, sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import server

BASE = {'host': '127.0.0.1', 'models': [
    {'id': 'breeze', 'family': 'breeze_tts', 'session_options': {'breeze_tts.perf_mode': 'cuda_perf'}},
    {'id': 'qwen3-base', 'family': 'qwen3_tts'}, {'id': 'qwen3-design', 'family': 'qwen3_tts'}, {'id': 'qwen3-custom', 'family': 'qwen3_tts'}]}


def setup(tmp_path):
    p = tmp_path / 'server.json'
    p.write_text(json.dumps(BASE, ensure_ascii=False, indent=2), encoding='utf-8')
    return p, p.read_bytes()


def test_writes_local_override_only(tmp_path):
    p, raw = setup(tmp_path)
    with patch.object(server, 'SERVER_CFG', str(p)):
        assert server.tts_engine_opts()['breeze_perf'] == 'cuda_perf'
        assert server.server_cfg_file() == str(p)  # 没有本机覆盖：引擎照旧直接读 server.json
        assert server.set_tts_engine_opts({'qwen3_perf': 'flash_attention', 'breeze_perf': 'off'}) is True
        assert p.read_bytes() == raw  # 受跟踪的默认文件没动
        loc = json.loads((tmp_path / 'server.local.json').read_text(encoding='utf-8'))
        assert loc == {'models': {'breeze': {'session_options': {'breeze_tts.perf_mode': None}},
                                  **{m: {'session_options': {'qwen3_tts.perf_mode': 'flash_attention'}} for m in ('qwen3-base', 'qwen3-design', 'qwen3-custom')}}}
        o = server.tts_engine_opts()  # “重启后”：重新读文件
        assert o['qwen3_perf'] == 'flash_attention' and o['breeze_perf'] == 'off'
        eff = server.server_cfg_file()  # 引擎启动时拿到合成的那份
        assert eff.endswith('server.effective.json')
        e = {m['id']: m for m in json.load(open(eff, encoding='utf-8'))['models']}
        assert 'session_options' not in e['breeze'] and e['qwen3-base']['session_options'] == {'qwen3_tts.perf_mode': 'flash_attention'}
        assert server.set_tts_engine_opts({'qwen3_perf': 'flash_attention'}) is False  # 没变：不写
        assert server.set_tts_engine_opts({'qwen3_perf': 'off', 'breeze_perf': 'cuda_perf'}) is True  # 都改回默认：覆盖清掉
        assert not (tmp_path / 'server.local.json').exists() and server.server_cfg_file() == str(p)
        assert p.read_bytes() == raw


def test_bad_local_file_ignored(tmp_path):
    p, raw = setup(tmp_path)
    (tmp_path / 'server.local.json').write_text('{不是 JSON', encoding='utf-8')
    with patch.object(server, 'SERVER_CFG', str(p)):
        assert server.tts_engine_opts()['breeze_perf'] == 'cuda_perf'
        assert server.server_cfg_file() == str(p)
