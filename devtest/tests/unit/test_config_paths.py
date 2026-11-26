"""开源泛化 ①：路径配置（studio/config.py）和 server.json 的相对路径。
- 没设环境变量 / settings.json 时，路径和以前写死的完全一样（程序文件夹里的 models、tools……）
- server.json 写成相对路径以后，交给引擎的配置展开回完整路径，和以前写死的 D:/AI-TTS/... 一字不差（换成这台电脑的程序文件夹）
- 设了 STUDIO_MODELS_DIR 时，models/ 开头的路径跟着走"""
import importlib, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'studio'))
ROOT = os.path.dirname(STUDIO)
sys.path.insert(0, STUDIO)
import config  # noqa: E402


def test_defaults_are_inside_program_folder():
    assert config.ROOT == ROOT
    assert config.MODELS_DIR == os.path.join(ROOT, 'models') or os.environ.get('STUDIO_MODELS_DIR')
    assert config.COMFY_DIR == os.path.join(config.COMFY_PORTABLE, 'ComfyUI')
    assert config.LLAMA_SERVER.endswith(os.path.join('llama.cpp', 'llama-server.exe')) or os.environ.get('STUDIO_LLAMA_DIR')
    assert config.models('a', 'b.gguf') == os.path.join(config.MODELS_DIR, 'a', 'b.gguf')


def test_resolve():
    assert config.resolve('models/X/y.gguf') == os.path.join(config.MODELS_DIR, 'X', 'y.gguf')
    assert config.resolve('voice-library') == os.path.join(ROOT, 'voice-library')
    assert config.resolve(r'D:\abs\x.gguf') == r'D:\abs\x.gguf'
    assert config.resolve('') == '' and config.resolve(None) is None


def test_server_json_resolves_to_full_paths(monkeypatch):
    import server
    monkeypatch.setattr(server, 'SERVER_CFG', os.path.join(ROOT, 'server.json'))
    monkeypatch.setattr(server, '_cfg_local', lambda: {})
    raw = json.load(open(os.path.join(ROOT, 'server.json'), encoding='utf-8'))
    cfg = server.server_cfg()
    root = ROOT.replace('\\', '/')
    assert cfg['voice_dir'] == root + '/voice-library'
    for a, b in zip(raw['models'], cfg['models']):
        assert a['id'] == b['id']
        assert b['path'] == (config.MODELS_DIR.replace('\\', '/') + a['path'][6:] if a['path'].startswith('models/') else a['path'])
        for k, v in (b.get('session_options') or {}).items():
            if k.endswith('_path'):
                assert os.path.isabs(v), (k, v)


def test_models_dir_env(tmp_path):
    code = 'import config, json; print(json.dumps([config.MODELS_DIR, config.resolve("models/a/b")]))'
    env = {**os.environ, 'STUDIO_MODELS_DIR': str(tmp_path)}
    out = subprocess.run([sys.executable, '-c', code], cwd=STUDIO, env=env, capture_output=True, text=True, check=True).stdout
    md, rb = json.loads(out)
    assert md == str(tmp_path) and rb == os.path.join(str(tmp_path), 'a', 'b')


def test_entry_scripts_import_config_under_isolated_mode():
    """python -I 启动时脚本所在文件夹不在搜索路径里：几个能直接运行的脚本也要能 import config"""
    for f in ('studioexe.py', 'agent_mcp.py'):
        src = open(os.path.join(STUDIO, f), encoding='utf-8').read()
        i, j = src.index('_sys.path.insert'), src.index('import config')
        assert i < j, f
