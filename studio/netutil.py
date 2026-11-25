"""本机端口有没有程序在监听（2026-11-08 性能检查）。

这台电脑上连一个没人监听的本机端口，不会马上被拒绝，而是要等到超时：socket 0.3 秒、urllib 2 秒。
各个引擎的“在不在”检查以前都是直接去连，引擎没开时，每 5 秒一次的状态请求就要白等 2 秒。
现在先用 psutil 看一眼正在监听的端口（约 1 毫秒，结果复用 0.5 秒）：没人在听就直接判定“没开”；
有人在听才照原来的方式去问（判断结果和以前完全一样，只是没开的时候不再等超时）。"""
import threading, time

_lock = threading.Lock()
_cache = {'t': 0.0, 'ports': None}


def listening(port):
    """True = 有程序在这个端口监听；False = 确定没有；None = 查不了（照原来的方式去连）"""
    try:
        import psutil
    except Exception:
        return None
    with _lock:
        now = time.time()
        if _cache['ports'] is None or now - _cache['t'] > 0.5:
            try:
                _cache['ports'] = {c.laddr.port for c in psutil.net_connections('tcp') if c.status == psutil.CONN_LISTEN and c.laddr}
            except Exception:
                _cache['ports'] = None
                return None
            _cache['t'] = now
        return int(port) in _cache['ports']


def maybe_up(port):
    """False 只在确定没人监听时返回；查不了也当成“可能在”（交给原来的检查）"""
    return listening(port) is not False
