"""F05 / F06（2026-11-17 审查）：测试实例不碰正式目录、不启停共用的配音引擎；--reset 只删经过核实的生成目录。
全部在一次性目录里；启动器那项起一个真的测试 Studio（独立端口、临时状态目录），只记录写入，不看任何文件内容。"""
import os, sys, json, subprocess, time, socket, textwrap
from unittest.mock import patch
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DEVTEST = os.path.normpath(os.path.join(HERE, '..', '..'))
REPO = os.path.dirname(DEVTEST)
sys.path.insert(0, DEVTEST)
sys.path.insert(0, os.path.join(REPO, 'studio'))
from statecheck import reset_refusal  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    r = tmp_path / 'repo'
    for d in ('devtest/fixtures/pub', 'devtest/tests/unit', 'devtest/tools', 'devtest/ui-audit', 'devtest/gpu-tests', 'devtest/states/gpu', 'studio'):
        (r / d).mkdir(parents=True)
    return r


def refuse(st, r, known=()):
    return reset_refusal(str(st), str(r), str(r / 'devtest'), [str(k) for k in known])


def test_valid_states_can_be_reset(tree):
    s = tree / 'devtest' / 'states' / 'mine'; s.mkdir(); (s / '.devtest-state').touch()
    assert refuse(s, tree) is None
    k = tree / 'devtest' / 'states' / 'gpu'  # profile 默认目录（老的没有标记）
    assert refuse(k, tree, [k]) is None
    out = tree.parent / 'elsewhere'; out.mkdir(); (out / '.devtest-state').touch()  # 别处的、带标记的
    assert refuse(out, tree) is None


@pytest.mark.parametrize('rel', ['devtest/fixtures', 'devtest/fixtures/pub', 'devtest/tests', 'devtest', '.', 'studio', 'devtest/tools'])
def test_source_and_fixtures_refused(tree, rel):
    d = tree / rel
    (d / '.devtest-state').touch()  # 就算有人放了标记也不行
    assert refuse(d, tree) is not None


def test_unmarked_dir_refused(tree):
    d = tree / 'devtest' / 'states' / 'x'; d.mkdir()
    assert '标记' in refuse(d, tree)


def test_junction_refused(tree):
    if os.name != 'nt':
        pytest.skip('Windows 联接点')
    import _winapi
    target = tree / 'studio'
    j = tree / 'devtest' / 'states' / 'jn'
    _winapi.CreateJunction(str(target), str(j))
    (target / '.devtest-state').touch()
    try:
        assert refuse(j, tree) is not None
    finally:
        os.rmdir(j)


def test_real_repo_tracked_files_refused():
    assert reset_refusal(os.path.join(DEVTEST, 'fixtures'), REPO, DEVTEST) is not None


# ---- 共用的配音引擎（8080）：借用的不重启、不关 ----
def test_shared_engine_not_restarted_or_killed():
    import server
    with patch.object(server, 'ENGINE_SHARED', True), patch.object(server, 'ENGINE_OWNED', False), \
            patch.object(server, 'engine_alive', return_value=True), patch.object(server, 'engine_config_matches', return_value=False), \
            patch.object(server, 'kill_ours') as kill, patch.object(server.subprocess, 'Popen') as popen:
        assert server.start_engine() is None
        kill.assert_not_called(); popen.assert_not_called()
    with patch.object(server, 'ENGINE_SHARED', True), patch.object(server, 'ENGINE_OWNED', False), patch.object(server, 'jobs', {}), \
            patch.object(server, 'stop_all_engines'), patch.object(server.videogen.Engine, 'shutdown'), patch.object(server.time, 'sleep'), \
            patch.object(server, 'kill_ours') as kill, patch.object(server.os, '_exit', side_effect=SystemExit):
        with pytest.raises(SystemExit):
            server.shutdown_self()
        kill.assert_not_called()


def test_formal_studio_still_stops_its_engine():
    import server
    with patch.object(server, 'ENGINE_SHARED', False), patch.object(server, 'jobs', {}), patch.object(server, 'stop_all_engines'), \
            patch.object(server.videogen.Engine, 'shutdown'), patch.object(server.time, 'sleep'), \
            patch.object(server, 'kill_ours') as kill, patch.object(server.os, '_exit', side_effect=SystemExit):
        with pytest.raises(SystemExit):
            server.shutdown_self()
        kill.assert_called_once()


# ---- 真的起一个测试 Studio：记录所有写入，正式目录里一次都不能有 ----
WRAP = textwrap.dedent(r'''
    import os, sys, json, runpy
    LOG, FORMAL, ST = sys.argv[1], json.loads(sys.argv[2]), os.path.normcase(sys.argv[3])
    FORMAL = [os.path.normcase(p) for p in FORMAL]
    hits = open(LOG, 'w', encoding='utf-8')
    def bad(p):
        try:
            p = os.path.normcase(os.path.abspath(os.fsdecode(p)))
        except Exception:
            return False
        return not p.startswith(ST) and any(p == f or p.startswith(f + os.sep) for f in FORMAL)
    def hook(ev, args):
        if ev == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            mode = args[1] if len(args) > 1 and isinstance(args[1], str) else 'r'
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if (any(c in mode for c in 'wax+') or (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))) and bad(args[0]):
                hits.write(ev + ' ' + os.fsdecode(args[0]) + '\n'); hits.flush()
        elif ev in ('os.mkdir', 'os.rename', 'os.remove', 'os.rmdir', 'shutil.rmtree', 'shutil.copyfile', 'shutil.move') and args:
            for a in (args[:2] if ev in ('os.rename', 'shutil.copyfile', 'shutil.move') else args[:1]):
                if isinstance(a, (str, bytes, os.PathLike)) and bad(a) and not (ev == 'shutil.copyfile' and a is args[0]):
                    hits.write(ev + ' ' + os.fsdecode(a) + '\n'); hits.flush()
    sys.addaudithook(hook)
    sys.argv = [sys.argv[4]] + sys.argv[5:]
    runpy.run_path(sys.argv[0], run_name='__main__')
''')


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


def test_launcher_writes_nothing_formal(tmp_path):
    st = tmp_path / 'state'
    formal = [os.path.join(REPO, x) for x in ('outputs', '.data', '音源库', 'voice-library', 'studio/tmp', 'studio/settings.json', 'studio/server.json')]
    log, wrap = tmp_path / 'writes.log', tmp_path / 'wrap.py'
    wrap.write_text(WRAP, encoding='utf-8')
    port = free_port()
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    p = subprocess.Popen([sys.executable, '-I', str(wrap), str(log), json.dumps(formal), str(st), os.path.join(DEVTEST, 'run.py'),
                          '--profile', 'chk', '--port', str(port), '--phone-port', str(free_port()), '--comfy-port', str(free_port()), '--state', str(st)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(240):
            if p.poll() is not None:
                break
            try:
                socket.create_connection(('127.0.0.1', port), timeout=.5).close(); ok = True; break
            except OSError:
                time.sleep(.5)
        out = '' if ok else p.stdout.read().decode('utf-8', 'replace')[-2000:]
        assert ok, out
        time.sleep(3)  # 让启动后的后台线程跑一会
    finally:
        p.kill(); p.wait(10)  # 自己起的子进程，按句柄结束
    hits = log.read_text(encoding='utf-8').strip()
    assert hits == '', '测试实例写了正式目录：\n' + hits[:2000]
    assert (st / '.devtest-state').exists()


def test_audit_hook_positive_control(tmp_path):
    """对照：真往“正式目录”写，钩子能抓到（证明上面那项不是因为钩子没生效才通过）"""
    formal = tmp_path / 'formal'; formal.mkdir()
    target = tmp_path / 'writer.py'
    target.write_text(f"import os\nopen(r'{formal / 'x.json'}', 'w').write('1')\nos.mkdir(r'{formal / 'sub'}')\n", encoding='utf-8')
    log, wrap = tmp_path / 'writes.log', tmp_path / 'wrap.py'
    wrap.write_text(WRAP, encoding='utf-8')
    subprocess.run([sys.executable, '-I', str(wrap), str(log), json.dumps([str(formal)]), str(tmp_path / 'state'), str(target)], timeout=60, check=True)
    hits = log.read_text(encoding='utf-8')
    assert 'x.json' in hits and 'sub' in hits
