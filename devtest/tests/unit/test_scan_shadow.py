"""C03（2026-11-17 审查）：scan_shadow 只报真的“import 执行前就用了”，import 之后用、嵌套函数、一行导入多个都不误报；退出码可判读。"""
import os, subprocess, sys, textwrap

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))
import scan_shadow

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools', 'scan_shadow.py')


def hits(tmp_path, src):
    p = tmp_path / 'm.py'; p.write_text('import os, json, socket\n' + textwrap.dedent(src), encoding='utf-8')
    return [(fn.name, h) for fn, hs in scan_shadow.scan_file(str(p)) for h in hs]


def test_true_positive_use_before_import(tmp_path):
    r = hits(tmp_path, '''
    def f():
        x = os.getcwd()
        import os
        return x
    ''')
    assert [(n, h[0]) for n, h in r] == [('f', 'os')]


def test_use_after_import_is_fine(tmp_path):
    assert hits(tmp_path, '''
    def f():
        import socket, json
        s = socket.socket
        if s:
            return json.dumps({})
    ''') == []


def test_conditional_import_then_use_outside(tmp_path):
    r = hits(tmp_path, '''
    def f(a):
        if a:
            import json
        return json.dumps(a)
    ''')
    assert [h[0] for _, h in r] == ['json']


def test_nested_function_scopes(tmp_path):
    assert hits(tmp_path, '''
    def outer():
        v = os.sep          # 外层用的是模块的 os：import 在里面的函数里
        def inner():
            import os
            return os.sep
        return v, inner
    ''') == []
    r = hits(tmp_path, '''
    def outer():
        def inner():
            return json.dumps(1)
        import json
        return inner
    ''')
    assert r == []  # inner 里的 json 是外层的闭包：不在本工具的范围（以前会把 inner 的用法算到外层头上）


def test_global_and_loop(tmp_path):
    assert hits(tmp_path, '''
    def f():
        global json
        json.dumps(1)
        import json
    ''') == []
    r = hits(tmp_path, '''
    def f(xs):
        for x in xs:
            os.path.join(x)
            import os
    ''')
    assert [h[0] for _, h in r] == ['os']


def test_exit_codes(tmp_path):
    ok = tmp_path / 'ok.py'; ok.write_text('import os\ndef f():\n    import os\n    return os.sep\n', encoding='utf-8')
    bad = tmp_path / 'bad.py'; bad.write_text('import os\ndef f():\n    a = os.sep\n    import os\n', encoding='utf-8')
    broken = tmp_path / 'broken.py'; broken.write_text('def f(:\n', encoding='utf-8')
    run = lambda p: subprocess.run([sys.executable, '-I', TOOL, str(p)], capture_output=True, text=True, encoding='utf-8').returncode
    assert (run(ok), run(bad), run(broken)) == (0, 1, 2)
