"""F04（2026-11-17 审查）：桌面应用只关自己启动的后台。用假的后台（本机随机端口上的小 HTTP 服务）模拟，不碰正式 Studio。"""
import json, os, sys, threading, time, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, Mock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))


@pytest.fixture(scope='module')
def app():
    try:
        import app as a
    except Exception as e:
        pytest.skip(f'载入 app.py 失败（webview）：{e}')
    return a


class Fake:
    """假后台：/api/boot 回 owner；/api/shutdown 记下来（只有口令对才算）"""
    def __init__(self, owner='', delay=0, token=''):
        self.owner, self.delay, self.token, self.shutdowns, self.refused = owner, delay, token, 0, 0
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                time.sleep(me.delay)
                body = json.dumps({'boot': '1', 'owner': me.owner, 'pid': 1}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length') or 0))
                ok = bool(me.token) and self.headers.get('X-Studio-Owner') == me.token
                me.shutdowns += ok; me.refused += not ok
                self.send_response(200 if ok else 403); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


def use(app, fake):
    return patch.multiple(app, URL=f'http://127.0.0.1:{fake.port}', PORT=fake.port)


def test_slow_existing_server_is_not_competed(app):
    f = Fake(owner='', delay=2.5)  # 已有的 Studio 回得很慢（超过 1.5 秒）
    try:
        with use(app, f), patch.object(app, 'start_server') as st:
            proc = None if (app.alive() or app.port_taken()) else app.start_server()
            assert proc is None and not st.called  # 不另起一个去抢端口
    finally:
        f.close()


def test_failed_child_does_not_close_other_instance(app):
    f = Fake(owner='', token='')  # 别人启动的 Studio（没有口令）
    dead = Mock(); dead.poll.return_value = 1; dead.pid = 999999  # 自己起的后台没抢到端口，已经退出
    try:
        with use(app, f), patch.object(app, 'kill_ours') as kill, patch.object(app.subprocess, 'run') as run:
            app.stop_server(dead)
        assert f.shutdowns == 0 and f.refused == 0 and not kill.called and not run.called
    finally:
        f.close()


def test_normal_close_shuts_own_server(app):
    f = Fake(owner=app.TAG, token=app.TOKEN)
    child = Mock(); child.poll.side_effect = [None, 0]; child.pid = 999999
    try:
        with use(app, f), patch.object(app, 'kill_ours') as kill, patch.object(app.subprocess, 'run') as run, patch.object(app.time, 'sleep'):
            app.stop_server(child)
        assert f.shutdowns == 1 and kill.called and run.called  # 关了自己的后台和它的子进程、引擎
    finally:
        f.close()


def test_after_in_app_restart_ownership_carries(app):
    f = Fake(owner=app.TAG, token=app.TOKEN)  # 应用里重启过：后台换了进程，但继承了口令
    old = Mock(); old.poll.return_value = 0; old.pid = 999999  # 最初的子进程早退出了
    try:
        with use(app, f), patch.object(app, 'kill_ours') as kill, patch.object(app.subprocess, 'run') as run, patch.object(app.time, 'sleep'):
            app.stop_server(old)
        assert f.shutdowns == 1 and kill.called and not run.called
    finally:
        f.close()


def test_child_gets_token_env(app):
    with patch.object(app.subprocess, 'Popen') as popen, patch('builtins.open', Mock()):
        app.start_server()
    assert popen.call_args.kwargs['env']['STUDIO_OWNER_TOKEN'] == app.TOKEN


def test_server_shutdown_requires_owner_token():
    import server
    def call(token, header):
        h = object.__new__(server.Handler)
        h.remote = False
        h.headers = {'X-Studio-Owner': header} if header is not None else {}
        h.send_json = Mock(side_effect=lambda d, *a, **k: (d, a[0] if a else 200))
        h.jbody = lambda: {}
        with patch.object(server, 'OWNER_TOKEN', token), patch.object(server.threading, 'Thread') as th:
            r = h.dispatch('POST', ['api', 'shutdown'], {})
            return h.send_json.call_args.args, th.called
    assert call('', None)[1] is False  # 不是应用启动的：谁叫都不关
    assert call('', 'abc')[1] is False
    assert call('tok', 'wrong')[1] is False
    assert call('tok', 'tok')[1] is True
