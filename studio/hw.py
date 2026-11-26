"""显卡 / 内存概况，和“这个模型放不放得下”的估计（开源泛化 ②）。

估法参照 LM Studio 的“能不能完全放进显卡”：按模型文件的大小加一点余量算，不实际载入。
  ok     全部放得进显存
  tight  显存放不下全部，但必须留在显卡上的部分放得下、其余能放进内存（引擎会分到内存里跑，慢一些）
  no     连这样也放不下
没有 NVIDIA 显卡 / 读不到时 gpu() 返回 []，fit() 返回 'unknown'。"""
import ctypes, os, subprocess, threading, time

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
_cache = {'t': 0.0, 'gpu': None}
_lock = threading.Lock()
OVERHEAD_GB = 1.5  # 激活值、CUDA 上下文这些：生图 / 视频按 1.5 GB 留


def gpu(max_age=10.0):
    """[{name, total_gb, used_gb}]（每张 NVIDIA 显卡一项）"""
    with _lock:
        if _cache['gpu'] is not None and time.time() - _cache['t'] < max_age:
            return _cache['gpu']
        out = []
        try:
            r = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used', '--format=csv,noheader,nounits'],
                               capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
            for line in r.stdout.strip().splitlines():
                name, tot, used = [x.strip() for x in line.rsplit(',', 2)]
                out.append({'name': name, 'total_gb': round(int(tot) / 1024, 1), 'used_gb': round(int(used) / 1024, 1)})
        except (OSError, ValueError, subprocess.SubprocessError):
            out = []
        _cache.update(t=time.time(), gpu=out)
        return out


def ram():
    """{total_gb, avail_gb}"""
    try:
        import psutil
        v = psutil.virtual_memory()
        return {'total_gb': round(v.total / 2 ** 30, 1), 'avail_gb': round(v.available / 2 ** 30, 1)}
    except Exception:
        pass
    if os.name == 'nt':
        class MS(ctypes.Structure):
            _fields_ = [('len', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong), ('avail', ctypes.c_ulonglong),
                        ('tp', ctypes.c_ulonglong), ('ap', ctypes.c_ulonglong), ('tv', ctypes.c_ulonglong), ('av', ctypes.c_ulonglong), ('ae', ctypes.c_ulonglong)]
        m = MS(); m.len = ctypes.sizeof(MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return {'total_gb': round(m.total / 2 ** 30, 1), 'avail_gb': round(m.avail / 2 ** 30, 1)}
    return {'total_gb': None, 'avail_gb': None}


def fit(need_gb, offload_gb=0.0, vram_gb=None, ram_gb=None):
    """need_gb = 全部放进显卡要多少；offload_gb = 其中引擎可以挪到内存里的部分（文本编码器、分层放的模型层）。"""
    if need_gb is None:
        return 'unknown'
    if vram_gb is None:
        g = gpu()
        vram_gb = g[0]['total_gb'] if g else None
    if ram_gb is None:
        ram_gb = ram()['total_gb']
    if not vram_gb:
        return 'unknown'
    if need_gb <= vram_gb * 0.95:
        return 'ok'
    on_gpu = need_gb - offload_gb
    if on_gpu <= vram_gb * 0.95 and offload_gb <= (ram_gb or 0) * 0.85:
        return 'tight'
    return 'no'


def summary():
    g = gpu()
    return {'gpu': g, 'ram': ram(), 'vram_gb': g[0]['total_gb'] if g else None}
