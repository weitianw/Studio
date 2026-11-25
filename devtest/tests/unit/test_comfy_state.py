"""F17（2026-11-17 审查）：ComfyUI 状态分清 就绪 / 启动中 / 无响应 / 别的程序占着端口；启动慢时不另起一个去抢。
本机随机端口上的假服务，不启动 ComfyUI。"""
import json, os, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import videogen as V


def serve(body=None, delay=0, code=200):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            time.sleep(delay)
            raw = json.dumps(body).encode() if body is not None else b'<html>not comfy</html>'
            self.send_response(code); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    s = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def state_on(srv, owner=(True, 10), quick=False):
    import netutil
    with patch.object(V, 'PORT', srv.server_address[1]), patch.object(netutil, 'maybe_up', lambda p: True), patch.object(V.Engine, '_owner', classmethod(lambda c: owner)):
        return V.Engine.state(quick=quick)


def test_ready_and_foreign():
    s = serve({'system': {'os': 'nt'}}); assert state_on(s) == 'ready'; s.shutdown()
    s = serve(None); assert state_on(s) == 'foreign'; s.shutdown()  # 回了话但不是 ComfyUI
    s = serve({'x': 1}, code=404); assert state_on(s) == 'foreign'; s.shutdown()


def test_silent_listener_states():
    s = serve({'system': {}}, delay=3)  # 端口在听、2 秒内不回话
    try:
        assert state_on(s, owner=(True, 30)) == 'starting'  # 我们的、刚起来：启动中
        assert state_on(s, owner=(False, 0)) == 'foreign'  # 别的程序
        with patch.object(V.Engine, 'STARTING_GRACE', 1):
            assert state_on(s, owner=(True, 999)) == 'ready'  # 起来很久：再等一次长的（这次 3 秒回了）
    finally:
        s.shutdown()


def test_unresponsive_and_down():
    s = serve({'system': {}}, delay=30)
    try:
        with patch.object(V.Engine, 'STARTING_GRACE', 1), patch.object(V, '_http', side_effect=TimeoutError('超时')):
            assert state_on(s, owner=(True, 999)) == 'unresponsive'
    finally:
        s.shutdown()
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
    with patch.object(V, 'PORT', port):
        assert V.Engine.state() == 'down'


def test_ensure_waits_for_slow_start_without_spawning():
    seq = iter(['starting', 'starting', 'ready'])
    with patch.object(V.Engine, 'state', classmethod(lambda c, quick=False: next(seq))), patch.object(V.time, 'sleep', lambda s: None), \
            patch.object(V.subprocess, 'Popen') as popen:
        V.Engine.ensure()
        popen.assert_not_called()  # 不另起一个去抢端口


@pytest.mark.parametrize('st,msg', [('foreign', '别的程序'), ('unresponsive', '没有响应')])
def test_ensure_errors_clearly(st, msg):
    with patch.object(V.Engine, 'state', classmethod(lambda c, quick=False: st)), patch.object(V.subprocess, 'Popen') as popen:
        with pytest.raises(RuntimeError, match=msg):
            V.Engine.ensure()
        popen.assert_not_called()
