"""开发测试用的 Studio：和真实数据完全隔开。2026-11-14：几个测试 Studio（原来散在各次会话的临时文件夹里）合成这一个，按用途选 --profile。
- 数据（作品、音色、生图、私密空间、临时文件、手机配对……）都在测试数据目录里；音源库从 devtest/fixtures 复制过去。私密空间的密钥是 testky。
- 电脑端口 / 手机端口（进来的请求一律当成手机 = Tailscale 地址）、生图 / 翻译 / 提示词引擎、视频引擎 ComfyUI 都用单独的端口，不和正在用的 Studio 打架。

  profile   用途                               端口（电脑 / 手机）  ComfyUI   测试数据               素材库
  dev       日常开发（默认，原 run.py）        7865 / 7866          8189      devtest/state          真实素材库
  gpu       显卡 A/B 测试（原 run_gpu_batch）  7897 / 7898          8199      devtest/states/gpu     真实素材库
  chk       全面检查（原 run_chk）             7897 / 7898          8199      devtest/states/gpu     测试数据里的 mats（隔开）
  ui        界面预览（原 run_ui）              7899 / 7900          8299      devtest/states/ui      真实素材库

用法：python -I devtest/run.py [--profile gpu] [--port 7897] [--phone-port 7898] [--comfy-port 8199] [--state 目录] [--reset]
端口也能用环境变量改：STUDIO_TEST_PORT、STUDIO_TEST_PHONE_PORT、STUDIO_TEST_COMFY_PORT（命令行参数优先）；STUDIO_TEST_STATE 改测试数据目录。
只改电脑端口时，其余端口跟着挪同样多（例：gpu 用 --port 7917 → 手机 7918、ComfyUI 8219、生图 8125…）。
同时开几个会话各自测试时，给每个会话不同的端口和测试数据目录就不会撞。"""
import hashlib, os, shutil, sys, threading, types

HERE = os.path.dirname(os.path.abspath(__file__))
ARGV0 = sys.argv[1:]  # 设置里“重启 Studio”时原样带上


def _arg(name, env=None, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return os.environ.get(env) if env and os.environ.get(env) else default


PROFILES = {  # 端口：电脑、手机、生图、翻译、提示词、ComfyUI；mats：None = 真实素材库，'state' = 测试数据里的 mats，其他 = 那个目录
    'dev': {'ports': (7865, 7866, 8095, 8096, 8098, 8189), 'state': os.path.join(HERE, 'state'), 'mats': None},  # 日常开发：用真实素材库
    'gpu': {'ports': (7897, 7898, 8105, 8106, 8108, 8199), 'state': os.path.join(HERE, 'states', 'gpu'), 'mats': r'D:\AI-TTS\素材库'},  # 显卡测试：用真实素材库（用户说这些都可以用）
    'chk': {'ports': (7897, 7898, 8105, 8106, 8108, 8199), 'state': os.path.join(HERE, 'states', 'gpu'), 'mats': 'state'},
    'ui': {'ports': (7899, 7900, 8115, 8116, 8118, 8299), 'state': os.path.join(HERE, 'states', 'ui'), 'mats': r'D:\AI-TTS\素材库'},
}
PF = _arg('--profile', 'STUDIO_TEST_PROFILE', 'dev')
if PF not in PROFILES:
    sys.exit(f'没有这个 profile：{PF}（可选：{"、".join(PROFILES)}）')
P = PROFILES[PF]
PORT = int(_arg('--port', 'STUDIO_TEST_PORT', P['ports'][0]))
DP = PORT - P['ports'][0]  # 只改了电脑端口：其余端口（手机、生图 / 翻译 / 提示词引擎、ComfyUI）跟着挪同样多，两个会话用同一个 profile 也不会撞
PHONE = int(_arg('--phone-port', 'STUDIO_TEST_PHONE_PORT', P['ports'][1] + DP))
COMFY = int(_arg('--comfy-port', 'STUDIO_TEST_COMFY_PORT', P['ports'][5] + DP))
ENG = tuple(x + DP for x in P['ports'][2:5])  # 生图、翻译、提示词
ST, FX = os.path.normpath(os.path.abspath(_arg('--state', 'STUDIO_TEST_STATE', P['state']))), os.path.join(HERE, 'fixtures')
if P['mats']:
    os.environ['STUDIO_MATERIALS'] = os.path.join(ST, 'mats') if P['mats'] == 'state' else P['mats']
MARK = os.path.join(ST, '.devtest-state')  # 这个文件夹是测试启动器建的（--reset 只删经过核实的生成目录）
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)  # -I 运行时脚本目录不在 sys.path 里
from statecheck import reset_refusal  # noqa: E402

if '--reset' in sys.argv and os.path.isdir(ST):
    why = reset_refusal(ST, REPO, HERE, [v['state'] for v in PROFILES.values()])
    if why:
        sys.exit(f'--reset 拒绝删除 {ST}：{why}。请手动处理')
    shutil.rmtree(ST)
if not os.path.isdir(ST):
    shutil.copytree(os.path.join(FX, 'pub'), os.path.join(ST, 'pub'))
    shutil.copytree(os.path.join(FX, 'vault'), os.path.join(ST, 'data', 'library'))
    open(MARK, 'w').close()
sys.argv = ['server.py', '--port', str(PORT), '--library', os.path.join(ST, 'data', 'library'), '--publib', os.path.join(ST, 'pub'), '--no-browser']
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'studio'))
os.environ['STUDIO_DEFER_DIRS'] = '1'  # 导入时不在正式目录里建文件夹，下面改好路径后在测试目录里建（F05）
import server as S, imagegen, remote, stt, translate, videogen  # noqa: E402
S.ENGINE_SHARED = True  # 8080 的配音引擎是借正式 Studio 的：不重启、关闭时不结束（F05）
try:
    import promptgen  # noqa: E402  提示词助手（有的话）
except ImportError:
    promptgen = None

R = S.ROOT
MAP = {os.path.join(R, 'outputs'): os.path.join(ST, 'outputs'), os.path.join(R, 'voice-library'): os.path.join(ST, 'voice-library'),
       os.path.join(R, '.data'): os.path.join(ST, 'data'), os.path.join(R, '音源库'): os.path.join(ST, 'pub'),
       os.path.join(R, 'studio', 'tmp'): os.path.join(ST, 'tmp')}
os.makedirs(os.path.join(ST, 'voice-library'), exist_ok=True)  # 空的测试音色库（以前整份复制用户的 voice-library，2026-11-15 审查）
# 设置文件和配音引擎配置：用测试目录里的（以前直接改用户真实的 studio/settings.json、server.json）
stt.SETTINGS = os.path.join(ST, 'settings.json')
if not os.path.isfile(os.path.join(ST, 'server.json')) and os.path.isfile(S.SERVER_CFG):
    shutil.copy2(S.SERVER_CFG, os.path.join(ST, 'server.json'))
S.SERVER_CFG = os.path.join(ST, 'server.json')
def _no_engine_opts(b):  # 配音引擎（8080）是和用户的 Studio 共用的：测试 Studio 不许改它的设置、也不许重启它
    raise RuntimeError('测试 Studio 不修改配音引擎设置（引擎和正式 Studio 共用）')
S.set_tts_engine_opts = _no_engine_opts


def fix(v):
    if isinstance(v, str):
        for a, b in MAP.items():
            if v == a or v.startswith(a + os.sep):
                return b + v[len(a):]
    return v


# 2026-11-14 审查：以前只改这 7 个模块，push / passkey / civitai / audioedit 等的路径还指着正式数据。现在 studio 里已经载入的模块全部改
_SD = os.path.normcase(os.path.join(os.path.dirname(HERE), 'studio'))
_MODS = [m for m in list(sys.modules.values()) if getattr(m, '__file__', None) and os.path.normcase(os.path.dirname(os.path.abspath(m.__file__))) == _SD]
for mod in _MODS:
    for k, v in list(vars(mod).items()):
        if isinstance(v, str) and fix(v) != v:
            setattr(mod, k, fix(v))
        elif isinstance(v, dict) and k in ('DIRS', 'WORK'):
            setattr(mod, k, {a: fix(b) for a, b in v.items()})
        elif isinstance(v, types.FunctionType) and v.__defaults__:
            v.__defaults__ = tuple(fix(x) for x in v.__defaults__)
OUT = os.path.join(ST, 'outputs')
S.recent_file = lambda: os.path.join(S.DATA if S.space() == 'v' else OUT, 'recent.json')
S.tags_file = lambda: os.path.join(S.DATA if S.space() == 'v' else OUT, 'tags.json')
S.order_file = lambda: os.path.join(S.DATA if S.space() == 'v' else OUT, 'src-order.json')
for d in (S.TMP, S.JOBS, S.LIB, S.DATA, S.VJOBS, S.VLIB, S.VSTT, S.VTMP, S.COVERS, S.PSUBS, S.PUBLIB, S.PCOVERS, S.PPSUBS, S.LIBRARY, stt.STT_DIR):
    os.makedirs(d, exist_ok=True)
S.VAULT_KEY_SHA = ''  # 测试实例不用旧的源码哈希（F08）：密钥 testky 写成测试数据里自己的本机记录
if not os.path.isfile(S.VAULT_REC):
    import vaultkey  # noqa: E402
    vaultkey.save(S.VAULT_REC, vaultkey.make('testky'))
imagegen.PORT, translate.LOCAL_PORT = ENG[0], ENG[1]
if promptgen:
    promptgen.PORT = ENG[2]
    promptgen.LOG = os.path.join(ST, 'prompt-engine.log')
remote.CONF = os.path.join(OUT, 'remote.json')
if not os.path.isfile(remote.CONF):
    remote.save({'enabled': True, 'devices': []})
videogen.LOG = os.path.join(ST, 'comfy-engine.log')
videogen.PORT = COMFY  # 不和正在用的 Studio 的视频引擎（8188）撞
videogen.EXTRA_ARGS = ['--database-url', 'sqlite:///' + os.path.join(ST, 'comfyui.db').replace(os.sep, '/')]
S.wire_modules()  # 和正式启动时一样把各模块接好
S.RESTART_CMD = [sys.executable, '-I', os.path.abspath(__file__), *[x for x in ARGV0 if x != '--reset']]  # 重启时不再带 --reset（审查 23：以前每次点重启都把测试数据重建一遍）  # 设置里“重启 Studio”：用同样的参数重新跑这个测试脚本
S.RESTART_LOG = os.path.join(ST, 'restart.log')
S.DIAG_LOG = os.path.join(ST, 'play-diag.log')  # 播放诊断日志也别写进真实的 outputs
bad = [p for p in (S.JOBS, S.LIB, S.TMP, S.DATA, S.PUBLIB, imagegen.DIRS['n'], imagegen.DIRS['v'], videogen.DIRS['n'], videogen.DIRS['v'], videogen.WORK['n'], stt.STT_DIR, remote.CONF, S.VAULT_REC) if not os.path.abspath(p).startswith(ST)]
_REAL = tuple(os.path.normcase(a) for a in MAP)  # 改完以后还有哪个模块的路径指着正式数据（outputs / .data / 音源库 / voice-library / studio	mp）：启动时说出来
_left = [f'{m.__name__}.{k}' for m in _MODS for k, v in vars(m).items() if isinstance(v, str) and os.path.normcase(v).startswith(_REAL)]
if _left:
    print('注意：这些路径还指着正式数据：' + '、'.join(_left), flush=True)
if P['mats'] == 'state' and not os.path.abspath(S.MATS_DIR).startswith(ST):
    bad.append('MATS_DIR')
if bad:
    sys.exit('测试数据目录没有全部隔开：' + ', '.join(bad))
S.load_old_jobs()
stt.load_old_stt()
stt.load_old_stt(S.VSTT, 'v')
threading.Thread(target=S.job_worker, daemon=True).start()


class PhoneHandler(S.Handler):  # 手机端口进来的当成手机
    def setup(self):
        super().setup()
        self.client_address = ('100.64.0.99', self.client_address[1])


threading.Thread(target=S.Server(('127.0.0.1', PHONE), PhoneHandler).serve_forever, daemon=True).start()
print(f'测试 Studio（{PF}）：电脑 http://127.0.0.1:{PORT}  手机 http://127.0.0.1:{PHONE}  ComfyUI {COMFY}  生图 / 翻译 / 提示词 {ENG}  数据 {ST}', flush=True)
S.Server(('127.0.0.1', PORT), S.Handler).serve_forever()
