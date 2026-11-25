"""Studio 桌面应用：用 Windows 自带的 Edge 内核（WebView2）打开一个独立窗口，界面和网页版完全一样。

- 工作室没在运行：在后台启动它（不弹黑色窗口），关闭应用窗口时一起退出工作室和推理引擎，显存随之释放。
- 工作室已经在运行（比如你正在用浏览器版）：直接连上去；关闭应用窗口时不去关它，免得打断浏览器里的使用。
- 私密空间：应用每次打开都是普通界面；关掉窗口就退出私密空间。
- 视频小窗可以拖到应用外面：变成一个没有标题栏的独立小窗口，放在桌面任何地方，可以选“始终在最前面”。
- 播放页的全屏：网页进入全屏时，应用窗口本身也切成全屏（WebView2 自己只会铺满窗口，不会盖住任务栏）。

启动：Studio.exe -I studio/app.py   （桌面上的“Studio”快捷方式；Studio.exe = Conda 里改了名字和图标的 pythonw，见 studioexe.py，
      任务管理器里显示“Studio”而不是“Python”。没有 Studio.exe 时照旧用 pythonw -I studio/app.py）
"""
import ctypes, ctypes.wintypes, json, os, subprocess, sys, threading, time, urllib.parse, urllib.request

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
sys.path.insert(0, os.path.join(STUDIO, 'pylib'))
sys.path.insert(0, STUDIO)  # winchrome.py 等同目录的模块（pythonw -I 启动时不会自动把脚本所在目录加进来）
import webview  # noqa: E402

URL = 'http://127.0.0.1:7860'
ICON = os.path.join(STUDIO, 'web', 'app.ico')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

LOADING = '''<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:#1e1e1e;color:#f2f2f2;font:14px -apple-system,"Segoe UI","Microsoft YaHei UI",sans-serif;display:grid;place-items:center;-webkit-user-select:none;user-select:none}
.b{display:flex;flex-direction:column;align-items:center;gap:18px}.w{display:flex;align-items:center;gap:9px;font-size:30px;font-weight:700;letter-spacing:-.035em}
svg{width:32px;height:32px}.s{width:22px;height:22px;border:2.5px solid rgba(255,255,255,.18);border-top-color:#fff;border-radius:50%;animation:r .8s linear infinite}
.t{color:#8a8a8a;font-size:13px}@keyframes r{to{transform:rotate(360deg)}}
@media (prefers-color-scheme: light){html,body{background:#f5f5f7;color:#1d1d1f}.s{border-color:rgba(0,0,0,.12);border-top-color:#1d1d1f}}
</style></head><body><div class="b"><div class="w"><svg viewBox="0 0 24 24"><path fill="currentColor" d="M19.2 2.2 9.4 4.4c-.6.1-1 .6-1 1.2v10.2a3.4 3.4 0 1 0 1.6 2.9V9.2l8.6-1.9v6.6a3.4 3.4 0 1 0 1.6 2.9V3.4c0-.8-.7-1.3-1-1.2z"/></svg>Studio</div>
<div class="s"></div><div class="t" id="t">正在启动推理引擎…</div></div></body></html>'''


import hashlib, secrets, socket  # noqa: E402
# 2026-11-17 审查 F04：实例归属。应用启动后台时给一个随机口令（环境变量传过去；设置里“重启 Studio”时新进程继承），
# 后台的 /api/boot 只回口令的摘要。关窗口时只关“摘要对得上”的后台——以前已有的 Studio 响应慢（超过 1.5 秒）就被当成没在运行，
# 另起的后台抢不到端口，关窗口时却向固定端口发关闭、按安装目录结束引擎，把别人正在用的 Studio 关掉了
TOKEN = secrets.token_hex(16)
TAG = hashlib.sha256(TOKEN.encode()).hexdigest()[:16]
PORT = int(urllib.parse.urlsplit(URL).port or 80)


def probe(timeout=3):
    """后台的 /api/boot（很轻，不查引擎）：{'boot', 'owner', 'pid'}；连不上 / 不像 Studio → None"""
    try:
        d = json.loads(urllib.request.urlopen(URL + '/api/boot', timeout=timeout).read().decode('utf-8'))
        return d if isinstance(d, dict) and 'boot' in d else None
    except Exception:
        return None


def alive():
    return probe(1.5) is not None


def port_taken():
    """端口上有没有程序在听（不管它回得快不快）：有就不再另起一个后台去抢"""
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(('127.0.0.1', PORT)); return True
    except OSError:
        return False
    finally:
        s.close()


def owned():
    d = probe(3)
    return bool(d and d.get('owner') and d.get('owner') == TAG)


def start_server():
    """在后台启动工作室（它会自己再启动推理引擎），输出写进日志，不弹黑色窗口。带上这次的口令（归属）"""
    py = sys.executable
    if os.path.basename(py).lower() in ('pythonw.exe', 'studio.exe'):
        try:
            import studioexe
            py = studioexe.server_exe()  # 后台用 StudioServer.exe（任务管理器里显示“Studio 后台”），没做好就用 python.exe
        except Exception:
            py = os.path.join(os.path.dirname(py), 'python.exe')
    log = open(os.path.join(STUDIO, 'app-server.log'), 'w', encoding='utf-8', errors='replace')
    return subprocess.Popen([py, '-I', os.path.join(STUDIO, 'server.py'), '--no-browser'], cwd=ROOT,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW, env={**os.environ, 'STUDIO_OWNER_TOKEN': TOKEN})


def stop_server(proc):
    """关闭窗口时：只结束这个应用启动的后台（口令摘要对得上；应用里重启过也算）和它的推理引擎。不是自己的一概不动"""
    mine = owned()
    if mine:
        try:  # 先请它自己退出：在设置里一键重启过的话，现在的后台已经不是 proc 了
            urllib.request.urlopen(urllib.request.Request(URL + '/api/shutdown', data=b'{}', method='POST',
                                                          headers={'Content-Type': 'application/json', 'X-Studio-Owner': TOKEN}), timeout=3).read()
            time.sleep(1.5)
        except Exception:
            pass
    if proc and proc.poll() is None:  # 自己的子进程还在（没抢到端口的那个也在这里收掉）：连同它启动的子进程一起结束
        subprocess.run(['taskkill', '/f', '/t', '/pid', str(proc.pid)], capture_output=True, creationflags=NO_WINDOW)
        try:
            proc.terminate(); proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if mine:  # 推理引擎、本地翻译 / 提示词模型、生图引擎（强行结束工作室时它们自己收不到退出信号）——只在关的是自己的后台时
        kill_ours(('audiocpp_server.exe', 'llama-server.exe', 'sd-server.exe'))


def kill_ours(names):
    """2026-11-14 审查：以前 taskkill /im 按名字全杀，会连别的程序、测试实例的同名进程一起结束。现在只结束程序文件在本项目里的那些"""
    try:
        import psutil
    except ImportError:
        return
    root = os.path.normcase(os.path.abspath(ROOT)) + os.sep
    # 测试实例（devtest/run.py）和正式 Studio 共用同一份程序文件：只看路径会连测试实例的引擎一起结束（审查 7）。
    # 再加一条：只结束在正式 Studio 的引擎端口上监听的那个（配音 8080、生图 8091、本地翻译 8093、提示词 8097）
    formal = {8080, 8091, 8093, 8097}
    for p in psutil.process_iter(['name', 'exe']):
        try:
            if (p.info['name'] or '').lower() in names and os.path.normcase(p.info['exe'] or '').startswith(root):
                ports = {c.laddr.port for c in (getattr(p, 'net_connections', None) or p.connections)(kind='inet') if c.status == psutil.CONN_LISTEN and c.laddr}  # psutil 5.x 叫 connections
                if ports & formal:
                    p.kill()
        except (psutil.Error, OSError, AttributeError):
            pass


def set_icon(window):
    """任务栏和标题栏用 Studio 自己的图标，而不是 Python 的。"""
    try:
        hwnd = int(window.native.Handle.ToInt64())
        u32 = ctypes.windll.user32
        for size, which in ((16, 0), (32, 1)):
            h = u32.LoadImageW(None, ICON, 1, size * 2 if which else size, size * 2 if which else size, 0x10)
            if h:
                u32.SendMessageW(hwnd, 0x80, which, h)  # WM_SETICON
    except Exception:
        pass


FIX = {'nw': ('SOUTH', 'EAST'), 'ne': ('SOUTH', 'WEST'), 'sw': ('NORTH', 'EAST'), 'se': ('NORTH', 'WEST')}  # 拖哪个角 → 对角不动


def round_corners(window):
    """Windows 11：没有标题栏的小窗口也用系统的圆角。"""
    try:
        hwnd = int(window.native.Handle.ToInt64())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)  # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND
    except Exception:
        pass


def native_drag(window, done=None):
    """必须在窗口自己的界面线程里调用（从别的线程发消息系统不认）。"""
    try:
        from System import Action
        hwnd = int(window.native.Handle.ToInt64())
        u32 = ctypes.windll.user32

        def run():
            u32.ReleaseCapture()
            u32.SendMessageW(hwnd, 0xA1, 2, 0)  # WM_NCLBUTTONDOWN + HTCAPTION：系统开始拖动窗口，松开鼠标结束
            if done:  # 松手了（不能在界面线程里等网页回话，换个线程通知）
                threading.Thread(target=done, daemon=True).start()
        window.native.BeginInvoke(Action(run))
    except Exception:
        pass


class Bridge:
    """主窗口和应用外的视频小窗之间传话。两个窗口里的页面都通过 window.pywebview.api 调这里。"""

    def __init__(self):
        self.main = None
        self.mini = None
        self.fs = False
        self.compact = None  # 精简模式时：原来的窗口位置大小
        self.chrome = None   # 自绘标题栏（winchrome.Chrome）
        self.tray = None
        self.thumbs = None   # 任务栏缩略图上的 上一首 / 播放 / 下一首（taskbar.ThumbBar）
        self.last = {}
        self.lock = threading.Lock()
        self.close_mode = close_mode_get()  # 点 × 时：'tray' 收进托盘（默认）/ 'quit' 退出（设置页里选，2026-11-06 用户）
        self.quitting = False                # 托盘菜单“退出”等：真的要退出，不再拦
        self.tray_hinted = False

    def hide_to_tray(self):
        """收进托盘：窗口藏起来，程序和后台都还在（音乐可以接着放）。在界面线程里调用。"""
        wlog('tray-hide', self.main.native)
        self.tray_show()
        self.main.native.Hide()
        # 2026-11-08 用户：收进托盘时，正在私密空间就退出私密空间。这里在界面线程上，直接 evaluate_js 会等它自己而卡住——另开一个线程去通知页面
        threading.Thread(target=self.to_main, args=('trayHidden', None), daemon=True).start()
        if not self.tray_hinted and self.tray:  # 第一次收起来：提示一下在哪里
            self.tray_hinted = True
            try:
                self.tray.ShowBalloonTip(2500, 'Studio 仍在运行', '点右下角的 Studio 图标打开；右键可以退出。可在设置里改为点 × 直接退出', 0)
            except Exception:
                pass

    def quit(self):
        self.quitting = True
        self.main.destroy()

    def tray_show(self):
        """右下角托盘图标：单击 / 双击打开窗口；右键菜单可以退出。在界面线程里调用。"""
        if self.tray:
            self.tray.Visible = True
            return
        from System.Drawing import Icon
        from System.Windows.Forms import NotifyIcon, ContextMenuStrip, MouseButtons
        t = NotifyIcon()
        t.Icon = Icon(ICON); t.Text = 'Studio'
        menu = ContextMenuStrip()
        menu.Items.Add('显示 Studio').Click += lambda s, e: self.show_main()
        menu.Items.Add('退出').Click += lambda s, e: self.quit()
        t.ContextMenuStrip = menu
        t.MouseClick += lambda s, e: self.show_main() if e.Button == MouseButtons.Left else None
        t.Visible = True
        self.tray = t

    def show_main(self):
        f = self.main.native
        f.Show(); f.Activate()
        ctypes.windll.user32.SetForegroundWindow(int(f.Handle.ToInt64()))
        wlog('tray-show', f)

    def boss(self):
        """一键隐藏（Ctrl + Alt + H）：窗口在 → 让页面暂停、关小窗、退出私密空间，窗口收进托盘；窗口已藏起来 → 拿出来。"""
        from System import Action
        f = self.main.native
        st = {}
        f.Invoke(Action(lambda: st.update(v=bool(f.Visible))))
        if not st.get('v'):
            f.Invoke(Action(self.show_main))
            return
        self.to_main('bossKey', None)
        f.Invoke(Action(lambda: (self.tray_show(), f.Hide())))

    def to_main(self, fn, arg):
        try:
            self.main.evaluate_js(f'window.{fn} && window.{fn}({json.dumps(arg)})')
        except Exception:
            pass

    def to_mini(self, fn, arg):
        w = self.mini
        if w:
            try:
                w.evaluate_js(f'window.{fn} && window.{fn}({json.dumps(arg)})')
            except Exception:
                pass

    def open_mini(self, st):
        with self.lock:
            if self.mini:
                return
            self.last = {'t': st.get('t', 0), 'paused': st.get('paused', True), 'w': st.get('w'), 'top': st.get('top', True)}
            url = URL + '/static/mini.html#' + urllib.parse.quote(json.dumps(st))
            w = webview.create_window(st.get('title') or 'Studio 小窗', url, js_api=MiniApi(self), width=int(st.get('w', 360)), height=int(st.get('h', 252)),
                                      x=int(st.get('x', 100)), y=int(st.get('y', 100)), frameless=True, easy_drag=False, on_top=bool(st.get('top', True)),
                                      min_size=(170, 150), background_color='#000000', shadow=True)
            self.mini = w
            w.events.shown += lambda: (set_icon(w), round_corners(w), st.get('drag') and native_drag(w, lambda: self.to_main('miniDragDone', None)))
            w.events.closed += lambda: self.mini_gone(w)
            w.events.loaded += lambda: self.to_mini('miniStart', None)  # 由这里开始播放（算作应用发起的，不受自动播放限制）

    def mini_gone(self, w):
        """小窗口被系统关掉（比如 Alt+F4）：主窗口当作“关闭并暂停”。"""
        if self.mini is w:
            self.mini = None
            self.to_main('miniReturn', {**self.last, 'mode': 'close'})

    def close_mini(self, st):
        with self.lock:
            w, self.mini = self.mini, None
        if not w:
            return
        try:
            w.destroy()
        except Exception:
            pass
        self.to_main('miniReturn', st)


class MainApi:
    """主窗口的页面用的接口。"""

    def __init__(self, b):
        self._b = b

    def _ui(self, fn):
        """在主窗口的界面线程里执行（窗口消息相关的操作必须这样）。"""
        from System import Action
        f = self._b.main.native
        f.Invoke(Action(fn))

    def fullscreen(self, on):
        """网页进入全屏：窗口盖住整个屏幕（连任务栏）。用 WinForms 自己的属性改（直接改窗口位置会被 WinForms 记的状态改回去）。"""
        b = self._b
        if not b.chrome or bool(on) == b.chrome.fullscreen:
            return
        b.fs = bool(on)
        f = b.main.native
        from System.Windows.Forms import FormWindowState, Screen

        def run():
            c = b.chrome
            wlog('fullscreen-on' if on else 'fullscreen-off', f)
            if on:
                from System.Drawing import Rectangle
                mx = f.WindowState == FormWindowState.Maximized
                n = normal_rect(int(f.Handle.ToInt64()))
                c.fs_saved = (mx, Rectangle(n.X, n.Y, n.Width, n.Height) if mx else f.Bounds, None)
                c.fullscreen = True
                f.WindowState = FormWindowState.Normal
                f.TopMost = True
                f.Bounds = Screen.FromControl(f).Bounds
            else:
                c.fullscreen = False
                was_max, r, _ = c.fs_saved or (False, None, None)
                f.TopMost = False
                if r is not None:
                    f.Bounds = r
                if was_max:
                    f.WindowState = FormWindowState.Maximized
            ctypes.windll.user32.SetWindowPos(int(f.Handle.ToInt64()), 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)  # 重新算边框
        self._ui(run)

    # ---- 自绘标题栏：按钮画在网页里，操作交给系统 ----
    def win_drag(self):
        if self._b.chrome:
            from System import Action
            self._b.main.native.BeginInvoke(Action(self._b.chrome.drag))

    def win_edge(self, edge):
        if self._b.chrome:
            from System import Action
            self._b.main.native.BeginInvoke(Action(lambda: self._b.chrome.resize_edge(edge)))

    def win_max(self):
        if self._b.chrome:
            self._ui(self._b.chrome.toggle_max)

    def win_min(self):
        if self._b.chrome:
            self._ui(self._b.chrome.minimize)

    def win_close(self):  # 标题栏的 ×：按设置收进托盘或退出
        b = self._b
        if b.close_mode == 'quit':
            b.quit()
        else:
            self._ui(b.hide_to_tray)

    def set_close_mode(self, mode):  # 设置页改了“点 × 时”：记下来（下次打开也照这个）
        self._b.close_mode = 'quit' if mode == 'quit' else 'tray'
        close_mode_set(self._b.close_mode)
        return self._b.close_mode

    def get_close_mode(self):
        return self._b.close_mode

    def win_state(self):
        return self._b.chrome.state() if self._b.chrome else {}

    # ---- 精简模式：整个主窗口缩成一条小播放器（浮在最前面），只能左右拖改宽度；再点一下恢复原来的大小和位置 ----
    def compact(self, on, w=340, h=64, top=True):
        b = self._b
        f = b.main.native
        scale = getattr(f, '_scale', 1) or 1
        u32 = ctypes.windll.user32

        def run():
            hwnd = int(f.Handle.ToInt64())
            c = b.chrome
            wlog('compact-on' if on else 'compact-off', f, had=bool(b.compact))
            if on and not b.compact:
                if c.fullscreen:
                    if c.fs_saved and c.fs_saved[2] is None:  # 网页全屏（用 WinForms 属性进的）：按同样的方式退出
                        from System.Windows.Forms import FormWindowState
                        c.fullscreen = False
                        was_max, r, _ = c.fs_saved
                        f.TopMost = False
                        if r is not None:
                            f.Bounds = r
                        if was_max:
                            f.WindowState = FormWindowState.Maximized
                    else:
                        c.set_fullscreen(False)
                    b.fs = False
                b.compact = {'max': bool(u32.IsZoomed(hwnd)), 'top': f.TopMost, 'min': f.MinimumSize}
                if b.compact['max']:
                    u32.ShowWindow(hwnd, 9)
                r = ctypes.wintypes.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
                b.compact['bounds'] = (r.left, r.top, r.right - r.left, r.bottom - r.top)
                from System.Drawing import Size
                f.MinimumSize = Size(0, 0)
                fr = c.frame()  # 左右下各有一圈看不见的改大小边框：w、h 是网页内容的大小，窗口要再加上边框
                W, H = int(w * scale) + 2 * fr, int(h * scale) + fr
                c.compact = {'min_w': int(280 * scale) + 2 * fr, 'max_w': int(560 * scale) + 2 * fr, 'min_h': H, 'max_h': H, 'drawer': False, 'h': H}
                u32.SetWindowPos(hwnd, 0, r.right - W - int(24 * scale), r.top + int(24 * scale), W, H, 0x0004)  # 放在原窗口右上角
                f.TopMost = bool(top)
            elif not on and b.compact:
                k, b.compact = b.compact, None
                c.compact = None
                f.TopMost = k['top']
                f.MinimumSize = k['min']
                L, T, W, H = k['bounds']
                u32.SetWindowPos(hwnd, 0, L, T, W, H, 0x0004)
                if k['max']:
                    u32.ShowWindow(hwnd, 3)
        self._ui(run)

    def compact_size(self, w, h, drawer=False):
        """展开 / 收起字幕区：高度变化，左上角不动。展开后可以往下拖改字幕区高度。"""
        b = self._b
        if not b.compact or not b.chrome:
            return
        f = b.main.native
        scale = getattr(f, '_scale', 1) or 1

        def run():
            c = b.chrome.compact
            fr = b.chrome.frame()
            H = int(h * scale) + fr
            c['drawer'] = bool(drawer)
            c['min_h'], c['max_h'] = (int(60 * scale) + int(160 * scale) + fr, int(60 * scale) + int(800 * scale) + fr) if drawer else (H, H)
            hwnd = int(f.Handle.ToInt64())
            r = ctypes.wintypes.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, r.right - r.left, H, 0x0002 | 0x0004)
        self._ui(run)

    def compact_pin(self, on):
        f = self._b.main.native
        self._ui(lambda: setattr(f, 'TopMost', bool(on)))

    def compact_hide(self):
        """精简模式里点 ×：窗口藏起来，只留右下角托盘里的图标（音乐照常放）；点托盘图标再出来。"""
        b = self._b
        self._ui(lambda: (b.tray_show(), b.main.native.Hide()))

    def boss(self):  # 页面里按了 Ctrl + Alt + H（全局快捷键没注册上时的后备）
        threading.Thread(target=self._b.boss, daemon=True).start()

    def tb_state(self, playing, enabled):  # 任务栏缩略图按钮跟着播放状态变（播放 ↔ 暂停图标；没在播放时变灰）
        t = self._b.thumbs
        if t:
            self._ui(lambda: t.update(playing, enabled))

    def compact_drag(self):
        self.win_drag()

    def mini_open(self, st):
        self._b.open_mini(st)

    def mini_move(self, x, y):
        if self._b.mini:
            self._b.mini.move(int(x), int(y))

    def mini_cmd(self, c):
        self._b.to_mini('miniCmd', c)

    def mini_close(self, mode):
        b = self._b
        st = dict(b.last)
        if b.mini:
            try:
                st.update(b.mini.evaluate_js('window.miniState()') or {})
            except Exception:
                pass
        st['mode'] = mode
        b.close_mini(st)


class MiniApi:
    """应用外的视频小窗的页面用的接口。"""

    def __init__(self, b):
        self._b = b

    def move(self, x, y):
        if self._b.mini:
            self._b.mini.move(int(x), int(y))

    def resize(self, w, h, corner):
        from webview.window import FixPoint
        if self._b.mini:
            a, c = FIX.get(corner, FIX['se'])
            self._b.mini.resize(int(w), int(h), getattr(FixPoint, a) | getattr(FixPoint, c))

    def start_drag(self):
        """按住画面拖动：交给 Windows 自己的“拖标题栏”来移动窗口（和拖普通窗口一样跟手，不会一顿一顿）。"""
        w = self._b.mini
        if w:
            native_drag(w)

    def pin(self, on):
        if self._b.mini:
            self._b.mini.on_top = bool(on)
            self._b.last['top'] = bool(on)

    def state(self, st):
        self._b.last.update(st or {})
        self._b.to_main('miniExt', st)

    def ended(self):
        self._b.to_main('miniExtEnded', None)

    def done(self, st):
        self._b.last.update(st or {})
        self._b.close_mini(st)


WINDOW_FILE = os.path.join(STUDIO, 'app-data', 'window.json')
WINDOW_LOG = os.path.join(STUDIO, 'app-data', 'window-log.jsonl')


def wlog(evt, f=None, **kw):
    """窗口大小的诊断记录（2026-11-16 用户：窗口大小经常自己变回默认大小，查是哪一步变的）。
    记事件（打开、精简模式、全屏、收进托盘、拿出来）和每次大小变化：时间、窗口位置大小（物理像素）、状态、所在屏幕。最多留约 400 行。
    f = 窗口的 WinForms 对象（要在界面线程里调）"""
    try:
        rec = {'t': time.strftime('%m-%d %H:%M:%S'), 'e': evt, **kw}
        if f is not None:
            from System.Windows.Forms import Screen
            b, s = f.Bounds, Screen.FromControl(f).Bounds
            rec.update(b=[b.X, b.Y, b.Width, b.Height], st=str(f.WindowState), vis=bool(f.Visible), scale=getattr(f, '_scale', None), scr=[s.X, s.Y, s.Width, s.Height])
        os.makedirs(os.path.dirname(WINDOW_LOG), exist_ok=True)
        with open(WINDOW_LOG, 'a', encoding='utf-8') as fp:
            fp.write(json.dumps(rec, ensure_ascii=False) + '\n')
        if os.path.getsize(WINDOW_LOG) > 120_000:
            with open(WINDOW_LOG, encoding='utf-8') as fp:
                keep = fp.readlines()[-400:]
            with open(WINDOW_LOG, 'w', encoding='utf-8') as fp:
                fp.writelines(keep)
    except Exception:
        pass


def hotkey_loop(bridge):
    """全局快捷键 Ctrl + Alt + H（一键隐藏）：不管当前在用哪个程序都能按。被别的程序占用了就算了（页面里按还是有效）。"""
    u32 = ctypes.windll.user32
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, WM_HOTKEY = 0x1, 0x2, 0x4000, 0x0312
    if not u32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL | MOD_NOREPEAT, ord('H')):
        return
    msg = ctypes.wintypes.MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == WM_HOTKEY and bridge.main:
            threading.Thread(target=bridge.boss, daemon=True).start()


CLOSE_F = os.path.join(STUDIO, 'app-close.json')  # 点 × 时怎么做（设置页改）


def close_mode_get():
    try:
        with open(CLOSE_F, encoding='utf-8') as f:
            return 'quit' if json.load(f).get('mode') == 'quit' else 'tray'
    except (OSError, ValueError, AttributeError):
        return 'tray'


def close_mode_set(mode):
    try:
        with open(CLOSE_F, 'w', encoding='utf-8') as f:
            json.dump({'mode': mode}, f)
    except OSError:
        pass


def already_running():
    """只开一个：已经开着就把那个窗口调到最前面，这次不再打开新的。"""
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.CreateMutexW(None, False, 'AITTS.Studio.App')
    if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    h = u32.FindWindowW(None, 'Studio')
    if h:
        u32.ShowWindow(h, 5)  # SW_SHOW：收进托盘（藏起来）的也拿出来
        u32.ShowWindow(h, 9)  # SW_RESTORE（最小化了也还原）
        u32.SetForegroundWindow(h)
    return True


def load_bounds():
    """上次关闭时窗口的位置和大小；那块屏幕不在了（换了显示器）就居中打开。"""
    try:
        b = json.load(open(WINDOW_FILE, encoding='utf-8'))
        w, h = max(1100, int(b['w'])), max(700, int(b['h']))
        x, y = int(b['x']), int(b['y'])
        pt = ctypes.wintypes.POINT(int((x + w / 2) * b.get('scale', 1)), int((y + 20) * b.get('scale', 1)))
        on_screen = ctypes.windll.user32.MonitorFromPoint(pt, 0)  # MONITOR_DEFAULTTONULL
        return {'width': w, 'height': h, **({'x': x, 'y': y} if on_screen else {})}  # 总是以窗口模式打开：上次最大化 / 全屏的话，用最大化之前的窗口大小
    except Exception:
        return {'width': 1480, 'height': 940}


def normal_rect(hwnd):
    """窗口“还原”后的位置大小（系统记的；WinForms 的 RestoreBounds 会多算一个标题栏的高度）。"""
    import winchrome
    wp = winchrome.WINDOWPLACEMENT(); wp.length = ctypes.sizeof(winchrome.WINDOWPLACEMENT)
    ctypes.windll.user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    r = wp.rcNormalPosition
    return type('R', (), {'X': r.left, 'Y': r.top, 'Width': r.right - r.left, 'Height': r.bottom - r.top})()


def get_zoom(f):
    """窗口里网页现在的缩放（WebView2 的 ZoomFactor，要在界面线程里读）。"""
    try:
        from System import Action
        out = []
        f.Invoke(Action(lambda: out.append(float(f.webview.ZoomFactor))))
        z = out[0] if out else None
        return round(z, 3) if z and 0.25 <= z <= 5 else None
    except Exception:
        return None


def set_zoom(window, z):
    try:
        from System import Action
        f = window.native
        f.Invoke(Action(lambda: setattr(f.webview, 'ZoomFactor', float(z))))
    except Exception:
        pass


def saved_zoom():
    try:
        z = float(json.load(open(WINDOW_FILE, encoding='utf-8')).get('zoom') or 0)
        return z if 0.25 <= z <= 5 and abs(z - 1) > 0.001 else None
    except Exception:
        return None


def save_bounds(window, bridge):
    try:
        f = window.native
        scale = getattr(f, '_scale', 1) or 1
        r = normal_rect(int(f.Handle.ToInt64())) if str(f.WindowState) == 'Maximized' else f.Bounds  # 最大化时记“还原后”的大小
        maxed = str(f.WindowState) == 'Maximized' and not bridge.fs
        if bridge.compact:  # 精简模式下关掉：记的是原来的大窗口
            L, T, W, H = bridge.compact['bounds']
            r = type('R', (), {'X': L, 'Y': T, 'Width': W, 'Height': H})()
            maxed = bridge.compact['max']
        if bridge.chrome and bridge.chrome.fullscreen and bridge.chrome.fs_saved:
            r = bridge.chrome.fs_saved[1]
            maxed = bridge.chrome.fs_saved[0]
        b = {'x': round(r.X / scale), 'y': round(r.Y / scale), 'w': round(r.Width / scale), 'h': round(r.Height / scale),
             'max': maxed, 'scale': scale}
        z = get_zoom(f)
        if z:
            b['zoom'] = z  # 页面缩放（Ctrl + 滚轮 / Ctrl + 加减号）：下次打开还是这个大小
        if b == getattr(save_bounds, 'last', None):
            return
        wlog('size', f, saved=b, compact=bool(bridge.compact), fs=bool(bridge.fs))  # 诊断：每次大小 / 位置变化
        os.makedirs(os.path.dirname(WINDOW_FILE), exist_ok=True)
        tmp = WINDOW_FILE + '.tmp'
        json.dump(b, open(tmp, 'w', encoding='utf-8')); os.replace(tmp, WINDOW_FILE)
        save_bounds.last = b
    except Exception:
        pass


def main():
    # 让 Windows 把它当成一个独立的应用（任务栏单独一组、用自己的图标），而不是“Python”
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AITTS.Studio')
    except Exception:
        pass
    if already_running():
        return
    try:  # Conda 升级 Python 后 Studio.exe / StudioServer.exe 会过时：先把后台用的那份重做好（窗口用的那份正在运行，改名让开，下次打开生效）
        import studioexe
        if studioexe.stale():
            studioexe.build()
    except Exception:
        pass
    proc = None if (alive() or port_taken()) else start_server()  # 端口已经有人在听（哪怕回得慢）：连上它，不另起一个去抢

    bridge = Bridge()
    lb = load_bounds()
    wlog('open', loaded=lb)  # 诊断：这次打开用的大小（读不到上次的会是 1480×940）
    window = webview.create_window('Studio', html=LOADING, min_size=(1100, 700), background_color='#1e1e1e', js_api=MainApi(bridge), **lb)
    bridge.main = window
    window.events.closing += lambda: save_bounds(window, bridge)  # 记住窗口位置和大小，下次在原处打开

    def on_closing():  # Alt + F4、任务栏右键“关闭窗口”也按设置：默认收进托盘（返回 False = 不关）
        if bridge.quitting or bridge.close_mode == 'quit' or bridge.main is not window:
            return None
        if ctypes.windll.user32.GetSystemMetrics(0x2000):  # SM_SHUTTINGDOWN：电脑在关机 / 注销，不拦
            return None
        try:
            bridge.hide_to_tray()
        except Exception:
            return None
        return False
    window.events.closing += on_closing

    window.events.shown += lambda: set_icon(window)  # 窗口真正出现后才有句柄，这时再换图标

    def keep_bounds():  # 每隔几秒把窗口的位置 / 大小记一次（有变化才写）：关机、重启电脑、应用被结束时也不会丢
        from System import Action
        last_st = None
        while bridge.main is window:
            time.sleep(4)
            try:
                f = window.native
                if f is not None and str(f.WindowState) != last_st:  # 诊断：最小化 / 还原 / 最大化
                    last_st = str(f.WindowState)
                    f.Invoke(Action(lambda: wlog('state', window.native)))
                if f is not None and str(f.WindowState) != 'Minimized':
                    f.Invoke(Action(lambda: save_bounds(window, bridge)))
            except Exception:
                pass
    window.events.shown += lambda: threading.Thread(target=keep_bounds, daemon=True).start()

    def chrome_on():  # 自绘标题栏（winchrome.py）+ 托盘图标
        from System import Action
        f = window.native

        def run():
            import winchrome
            bridge.chrome = winchrome.Chrome(int(f.Handle.ToInt64()))
            bridge.tray_show()
            try:  # 任务栏缩略图按钮；点了交给网页（不能在界面线程里等网页，另开线程）
                import taskbar
                bridge.thumbs = taskbar.ThumbBar(int(f.Handle.ToInt64()), lambda c: threading.Thread(target=bridge.to_main, args=('tbCmd', c), daemon=True).start())
                bridge.chrome.on_msg = bridge.thumbs.on_msg
            except Exception:
                bridge.thumbs = None
        f.Invoke(Action(run))
        threading.Thread(target=hotkey_loop, args=(bridge,), daemon=True).start()
    window.events.shown += chrome_on

    def main_closed():  # 主窗口关了：小窗口也一起关，托盘图标收起
        if bridge.tray:
            try:
                bridge.tray.Visible = False; bridge.tray.Dispose()
            except Exception:
                pass
        w, bridge.mini = bridge.mini, None
        if w:
            try:
                w.destroy()
            except Exception:
                pass
    window.events.closed += main_closed

    def boot():
        for _ in range(600):  # 最多等 5 分钟（第一次加载引擎会慢一些）
            if alive():
                window.load_url(URL + '/play?launch=' + str(int(time.time() * 1000)))  # 每次打开应用一个新编号：网页据此知道是关掉重开（WebView2 的 sessionStorage 关掉后还在）
                z = saved_zoom()
                if z:  # 上次关掉时的页面缩放：载入后恢复（页面刚换地址时设一次、稍后再设一次保险）
                    for t in (0.8, 2.5):
                        threading.Timer(t, set_zoom, args=(window, z)).start()
                return
            if proc and proc.poll() is not None:
                window.evaluate_js("document.getElementById('t').textContent='启动失败，请查看 studio/app-server.log'")
                return
            time.sleep(0.5)
        window.evaluate_js("document.getElementById('t').textContent='启动超时，请查看 studio/app-server.log'")

    try:
        # storage_path：设置（音量、主题、收藏的展开状态等）保存在 studio/app-data，下次打开还在
        webview.start(boot, private_mode=False, storage_path=os.path.join(STUDIO, 'app-data'))
    finally:
        if proc:  # 这次是应用自己起的后台（应用里重启过也是自己的）：stop_server 会再核对口令，不是自己的不关
            stop_server(proc)


if __name__ == '__main__':
    main()
