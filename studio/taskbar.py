"""任务栏缩略图上的“上一首 / 播放·暂停 / 下一首”三个按钮（像 Spotify、PotPlayer 那样）：
鼠标停在任务栏的 Studio 图标上，预览图下面出现这三个按钮，不用切回窗口就能控制播放。

用 Windows 的 ITaskbarList3 接口（直接用 ctypes 调 COM，不需要额外安装东西）。按钮被点时 Windows 给主窗口发
WM_COMMAND（高 16 位 = THBN_CLICKED），由 winchrome.py 接管窗口消息时转给这里。资源管理器重启后任务栏按钮会丢，
收到 “TaskbarButtonCreated” 消息时重新加一次。图标用 System.Drawing 现画，按系统浅色 / 深色主题选颜色。"""
import ctypes
from ctypes import wintypes

ole32, u32 = ctypes.windll.ole32, ctypes.windll.user32
WM_COMMAND, THBN_CLICKED = 0x0111, 0x1800
THB_ICON, THB_TOOLTIP, THB_FLAGS = 0x2, 0x4, 0x8
THBF_ENABLED, THBF_DISABLED = 0x0, 0x1
IDS = (1, 2, 3)  # 上一首 / 播放·暂停 / 下一首
WM_TASKBAR_CREATED = u32.RegisterWindowMessageW('TaskbarButtonCreated')


class GUID(ctypes.Structure):
    _fields_ = [('a', ctypes.c_ulong), ('b', ctypes.c_ushort), ('c', ctypes.c_ushort), ('d', ctypes.c_ubyte * 8)]


def guid(s):
    g = GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


class THUMBBUTTON(ctypes.Structure):
    _fields_ = [('dwMask', wintypes.DWORD), ('iId', wintypes.UINT), ('iBitmap', wintypes.UINT), ('hIcon', ctypes.c_void_p),
                ('szTip', ctypes.c_wchar * 260), ('dwFlags', wintypes.DWORD)]


def light_theme():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as k:
            return bool(winreg.QueryValueEx(k, 'SystemUsesLightTheme')[0])
    except OSError:
        return False


def make_icons(n):
    """画四个图标（n×n 像素）：上一首、播放、暂停、下一首。返回 HICON。"""
    from System import Array
    from System.Drawing import Bitmap, Graphics, SolidBrush, Color, PointF, RectangleF
    from System.Drawing.Drawing2D import SmoothingMode
    col = Color.FromArgb(255, 32, 32, 32) if light_theme() else Color.FromArgb(255, 255, 255, 255)
    u = n / 16.0

    def draw(fn):
        bmp = Bitmap(n, n)
        g = Graphics.FromImage(bmp)
        g.SmoothingMode = SmoothingMode.AntiAlias
        g.Clear(Color.Transparent)
        fn(g, SolidBrush(col))
        g.Dispose()
        return int(bmp.GetHicon().ToInt64())

    poly = lambda g, b, pts: g.FillPolygon(b, Array[PointF]([PointF(x * u, y * u) for x, y in pts]))
    rect = lambda g, b, x, y, w, h: g.FillRectangle(b, RectangleF(x * u, y * u, w * u, h * u))
    return {
        'prev': draw(lambda g, b: (rect(g, b, 3, 3.5, 1.8, 9), poly(g, b, [(13, 3.5), (13, 12.5), (5.5, 8)]))),
        'play': draw(lambda g, b: poly(g, b, [(4.5, 2.5), (4.5, 13.5), (13.5, 8)])),
        'pause': draw(lambda g, b: (rect(g, b, 4, 3, 3, 10), rect(g, b, 9, 3, 3, 10))),
        'next': draw(lambda g, b: (rect(g, b, 11.2, 3.5, 1.8, 9), poly(g, b, [(3, 3.5), (3, 12.5), (10.5, 8)]))),
    }


class ThumbBar:
    def __init__(self, hwnd, on_click):
        self.hwnd, self.on_click = hwnd, on_click
        self.playing, self.enabled, self.added = False, False, False
        self.tb = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(guid('{56FDF344-FD6D-11d0-958A-006097C9A090}')), None, 1,
                                    ctypes.byref(guid('{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}')), ctypes.byref(self.tb))
        if hr or not self.tb:
            raise OSError(f'ITaskbarList3 不可用（{hr:#x}）')
        self._call(3, ())  # HrInit
        dpi = u32.GetDpiForWindow(hwnd) or 96
        self.icons = make_icons(u32.GetSystemMetricsForDpi(49, dpi) or 16)  # SM_CXSMICON
        self.add()

    def _call(self, idx, args, argtypes=()):
        vt = ctypes.cast(self.tb, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vt[idx])
        return fn(self.tb, *args)

    def _buttons(self):
        arr = (THUMBBUTTON * 3)()
        spec = [('prev', '上一首'), ('pause' if self.playing else 'play', '暂停' if self.playing else '播放'), ('next', '下一首')]
        for b, i, (ic, tip) in zip(arr, IDS, spec):
            b.dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
            b.iId, b.hIcon, b.szTip = i, self.icons[ic], tip
            b.dwFlags = THBF_ENABLED if self.enabled else THBF_DISABLED
        return arr

    def add(self):
        try:  # ThumbBarAddButtons：每个任务栏按钮只能加一次
            self._call(15, (wintypes.HWND(self.hwnd), 3, self._buttons()), (wintypes.HWND, wintypes.UINT, ctypes.c_void_p))
            self.added = True
        except OSError:
            self.added = False

    def update(self, playing, enabled):
        self.playing, self.enabled = bool(playing), bool(enabled)
        if not self.added:
            return self.add()
        try:  # ThumbBarUpdateButtons
            self._call(16, (wintypes.HWND(self.hwnd), 3, self._buttons()), (wintypes.HWND, wintypes.UINT, ctypes.c_void_p))
        except OSError:
            pass

    def on_msg(self, msg, wp, lp):
        """winchrome 转来的窗口消息。返回 None = 不是这里的，交给原来的处理。"""
        if msg == WM_COMMAND and (wp >> 16) & 0xFFFF == THBN_CLICKED and wp & 0xFFFF in IDS:
            self.on_click({1: 'prev', 2: 'play', 3: 'next'}[wp & 0xFFFF])
            return 0
        if msg == WM_TASKBAR_CREATED:  # 资源管理器重启过：按钮要重新加
            self.added = False
            self.add()
        return None
