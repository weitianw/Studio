"""Studio 的 MCP 服务（2026-11-14）：让 Claude Code / Codex / 其他支持 MCP 的 Agent 用 Studio 干活，但看不到任何文件、标题、画面。

它只是把工具调用转给正在运行的 Studio 的 /api/agent/*（agentapi.py：只收 / 只回代号和数字），本身不读任何文件；
Studio 没开就报错（不会替你启动 Studio）。用官方 MCP Python SDK（modelcontextprotocol/python-sdk，装在 tools/mcp_lib）。

用法：
  python -I agent_mcp.py                 MCP 服务（stdio），由 Agent 启动
  python -I agent_mcp.py --set-key       私密空间：输入一次密钥，用 Windows DPAPI 加密存到 %LOCALAPPDATA%\\StudioAgent（只有你的 Windows 账户能解开）
  python -I agent_mcp.py --clear-key     删掉存的密钥
环境变量：STUDIO_URL（默认 http://127.0.0.1:7860）、STUDIO_SPACE（normal / private，默认 normal）"""
import asyncio, ctypes, ctypes.wintypes as wt, json, os, sys, time, urllib.request, http.cookiejar
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'mcp_lib'))
URL = os.environ.get('STUDIO_URL', 'http://127.0.0.1:7860').rstrip('/')
SPACE = 'private' if os.environ.get('STUDIO_SPACE', 'normal').lower() in ('private', 'v', 'vault') else 'normal'
KEY_FILE = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'StudioAgent', 'vault.dpapi')


# ------------------------------------------------------------------ Windows DPAPI（本机、本账户才能解开）
class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wt.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, enc):
    src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char))); out = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if enc else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):  # 0x1 = 不弹界面
        raise OSError('DPAPI 失败')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# ------------------------------------------------------------------ 连 Studio
_jar = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(_jar))
_unlocked = [False]


def _post(path, body, timeout=900):
    # X-Space：说清楚要在哪个空间做；Studio 重启过、私密登录没了会回 409（以前不带，服务端按普通空间悄悄做了，2026-11-16 审查）
    r = urllib.request.Request(URL + path, json.dumps(body or {}).encode(), {'Content-Type': 'application/json', 'X-Space': 'v' if SPACE == 'private' else 'n'}, method='POST')
    try:
        return json.loads(_op.open(r, timeout=timeout).read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except Exception:
            return {'error': f'Studio 返回 {e.code}'}
    except (urllib.error.URLError, OSError):
        return {'error': 'Studio 没有在运行（请先打开 Studio；这个服务不会替你启动）'}


def _call(tool, body=None, again=True):
    if SPACE == 'private' and not _unlocked[0]:
        if not os.path.isfile(KEY_FILE):
            return {'error': '私密空间还没设置密钥：请在终端运行 python -I agent_mcp.py --set-key'}
        with open(KEY_FILE, 'rb') as f:
            key = _dpapi(f.read(), False).decode('utf-8')
        r = _post('/api/vault/unlock', {'key': key}, 30)
        if not r.get('vault'):
            return {'error': '私密空间密钥不对或被暂时锁定'}
        _unlocked[0] = True
    r = _post('/api/agent/' + tool, body)
    if isinstance(r, dict) and r.get('error') == 'vault expired' and SPACE == 'private':  # 登录过期：重新登录再试一次
        _unlocked[0] = False
        return _call(tool, body, False) if again else {'error': '私密空间登录失效，重新登录也没成功'}
    return r


# ------------------------------------------------------------------ MCP 工具
def build():
    from mcp.server.mcpserver import MCPServer
    s = MCPServer('studio', instructions=(
        'Studio video tools. You never see file names, titles or pixels: videos are opaque ids (v_… = source material, w_… = generated result), jobs are j_…. '
        'Preferred flow: list_videos → list_recipes → run_recipe (the batch engine segments, generates, quality-checks, retries and splices by itself) → batch_status(wait_min=…) → report. '
        'Low-level flow for special cases: recommend_segments → edit_outfit → wait_jobs → check_quality → retry. Do not invent ids. Generating takes ~8–30 min per segment.'))

    @s.tool()
    def whoami() -> dict:
        """Which Studio space this server works in (normal / private)."""
        return _call('whoami')

    @s.tool()
    def list_videos(source: str = 'materials', limit: int = 50, offset: int = 0) -> dict:
        """List videos as opaque ids with duration (s), width, height, has-audio and day. source = 'materials' (source library) or 'results' (generated videos; 'source' = the id it was made from)."""
        return _call('list_videos', {'source': source, 'limit': limit, 'offset': offset})

    @s.tool()
    def cutpoints(video: str) -> dict:
        """Music beats + motion points for a video id (good moments to switch outfit): points [{t, kind: beat|hit|swing|turn, score 0–1, on_beat, downbeat}], bpm, music sections. First call may take ~10–60 s."""
        return _call('cutpoints', {'video': video})

    @s.tool()
    def recommend_segments(video: str) -> dict:
        """Recommended segments to edit [[start, end], …] (s), using the user's learned preference when there is enough history ('by': learned | rule)."""
        return _call('recommend_segments', {'video': video})

    @s.tool()
    def edit_outfit(video: str, instruction: str = '', segments: list[list[float]] | None = None, viggle: bool | None = None, seed: int = -1, size: str = '720p') -> dict:
        """Change the clothes of the person in a video. instruction = the change in Chinese or English (e.g. '衣服换成白色连衣裙'), required.
        segments = [[start, end], …] in seconds (one job each; default = whole video, Viggle max 14 s per segment). viggle = None uses the app default (off).
        Returns job ids. Uses the same defaults as the app's 生成 button."""
        return _call('edit_outfit', {'video': video, 'instruction': instruction, 'segments': segments, 'viggle': viggle, 'seed': seed, 'size': size})

    @s.tool()
    def job_status(jobs: list[str] | None = None) -> dict:
        """State of jobs (queued / running / done / error / cancelled), progress %, current stage, seconds elapsed, result id when done, per-stage seconds."""
        return _call('job_status', {'jobs': jobs})

    @s.tool()
    async def wait_jobs(jobs: list[str], timeout_min: int = 60) -> dict:
        """Wait until all given jobs finish (or timeout, max 120 min), then return their status. Prefer this over repeated job_status calls.
        Ids that cannot be found come back with state 'missing' (also listed in 'missing') — they are not treated as finished successfully."""
        end = time.time() + 60 * max(1, min(120, timeout_min))
        while True:
            r = _call('job_status', {'jobs': jobs})
            js = r.get('jobs') if isinstance(r, dict) else None
            # 按请求的代号对账（F09）：每个都要有一行；missing 也算结束（不会再变），但单独报出来
            if js is not None and len(js) >= len(set(jobs or [])) and (all(j.get('state') in ('done', 'error', 'cancelled', 'missing') for j in js) or time.time() > end):
                return {**r, 'timed_out': time.time() > end, 'all_done': all(j.get('state') == 'done' for j in js) and bool(js)}
            if js is None and r.get('error'):
                return r
            await asyncio.sleep(20)

    @s.tool()
    def check_quality(job: str) -> dict:
        """Automatic quality check of a finished job (or result id): pass/fail, reasons, metrics (face_sim vs source, face/background brightness difference, motion drift). Takes ~10–30 s on CPU."""
        return _call('check_quality', {'job': job})

    @s.tool()
    def list_recipes() -> dict:
        """Saved batch recipes (complete settings sets). Prefer run_recipe over edit_outfit: the batch engine itself segments, generates, quality-checks, retries with new seeds, keeps the best take and splices it back."""
        return _call('list_recipes')

    @s.tool()
    def run_recipe(videos: list[str], recipe: str, instruction: str = '') -> dict:
        """Run a recipe on several video ids in the background. instruction is required for clothing-change recipes without a saved one. Returns a batch id (b_…)."""
        return _call('run_recipe', {'videos': videos, 'recipe': recipe, 'instruction': instruction or None})

    @s.tool()
    async def batch_status(batch: str, wait_min: int = 0) -> dict:
        """Progress of a batch: per video, its segments (state, tries, pass, metrics, result id) and the spliced result id. wait_min > 0 waits until it finishes (max 600)."""
        end = time.time() + 60 * max(0, min(600, wait_min))
        while True:
            r = _call('batch_status', {'batch': batch})
            if not isinstance(r, dict) or r.get('error') or r.get('state') != 'running' or time.time() >= end:
                return r
            await asyncio.sleep(30)

    @s.tool()
    def retry(job: str, seed: int = -1) -> dict:
        """Run the same job again with another seed (-1 = random). Returns the new job id."""
        return _call('retry', {'job': job, 'seed': seed})
    return s


if __name__ == '__main__':
    if '--set-key' in sys.argv:
        import getpass
        k = getpass.getpass('私密空间密钥（输入时不显示）：')
        os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
        with open(KEY_FILE, 'wb') as f:
            f.write(_dpapi(k.encode('utf-8'), True))
        print('已加密保存到', KEY_FILE)
    elif '--clear-key' in sys.argv:
        if os.path.isfile(KEY_FILE):
            os.remove(KEY_FILE)
        print('已删除')
    else:
        build().run()
