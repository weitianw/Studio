"""Studio 主窗口的“自绘标题栏”：去掉系统标题栏，但保留 Windows 自己的边框（拖边改大小、贴边分屏、最大化动画都照常）。
标题栏上的按钮（精简模式 / 最小化 / 最大化 / 关闭）画在网页里；拖动标题栏空白处、双击最大化，由网页调这里的函数交给系统处理。

做法：接管窗口消息
- WM_NCCALCSIZE：把客户区往上扩到窗口顶边（标题栏没了），左右下的边框保留（那是看不见的改大小区域）；
  最大化时顶边留出系统边框的厚度，否则会伸出屏幕；自绘全屏时整个窗口都是客户区。
- WM_NCHITTEST：精简模式下只允许左右拖（改宽度），展开字幕时再允许往下拖（改字幕区高度）。
- WM_GETMINMAXINFO：精简模式下限制最小 / 最大宽度和高度。
全屏也自己做（不用 pywebview 的 toggle_fullscreen：它改 FormBorderStyle 会让 WinForms 重建窗口，网页就收不到鼠标了）。"""
import ctypes
from ctypes import wintypes

u32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
u32.CallWindowProcW.restype = LRESULT
u32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.SetWindowLongPtrW.restype = ctypes.c_void_p
u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
u32.GetWindowLongPtrW.restype = ctypes.c_void_p
u32.DefWindowProcW.restype = LRESULT
u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

WM_NCCALCSIZE, WM_NCHITTEST, WM_GETMINMAXINFO = 0x0083, 0x0084, 0x0024
HTCLIENT, HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 1, 10, 11, 12, 13, 14, 15, 16, 17


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [('rgrc', wintypes.RECT * 3), ('lppos', ctypes.c_void_p)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [('ptReserved', wintypes.POINT), ('ptMaxSize', wintypes.POINT), ('ptMaxPosition', wintypes.POINT),
                ('ptMinTrackSize', wintypes.POINT), ('ptMaxTrackSize', wintypes.POINT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [('length', wintypes.UINT), ('flags', wintypes.UINT), ('showCmd', wintypes.UINT), ('ptMinPosition', wintypes.POINT),
                ('ptMaxPosition', wintypes.POINT), ('rcNormalPosition', wintypes.RECT)]


class MARGINS(ctypes.Structure):
    _fields_ = [('l', ctypes.c_int), ('r', ctypes.c_int), ('t', ctypes.c_int), ('b', ctypes.c_int)]


class Chrome:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.fullscreen = False
        self.fs_saved = None
        self.compact = None  # {'min_w','max_w','h','drawer':bool,'min_h','max_h'}（物理像素）
        self.on_msg = None   # 其他模块想看的窗口消息（任务栏缩略图按钮，见 taskbar.py）；返回 None = 照常处理
        self._proc = WNDPROC(self._wndproc)
        self._old = u32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(self._proc, ctypes.c_void_p))  # GWLP_WNDPROC
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(0, 0, 1, 0)))  # 保留系统阴影
        u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)  # 让新的边框计算立刻生效

    def frame(self):
        dpi = u32.GetDpiForWindow(self.hwnd) or 96
        return u32.GetSystemMetricsForDpi(33, dpi) + u32.GetSystemMetricsForDpi(92, dpi)  # SM_CYFRAME + SM_CXPADDEDBORDER

    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if self.on_msg:
                r = self.on_msg(msg, wp, lp)
                if r is not None:
                    return r
            if msg == WM_NCCALCSIZE and wp:
                p = ctypes.cast(lp, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
                if self.fullscreen:
                    return 0  # 整个窗口都是内容
                top = p.rgrc[0].top
                u32.CallWindowProcW(self._old, hwnd, msg, wp, lp)  # 系统算好左右下的边框
                p.rgrc[0].top = top + (self.frame() if u32.IsZoomed(hwnd) else 0)  # 去掉标题栏
                return 0
            if msg == WM_NCHITTEST:
                r = u32.CallWindowProcW(self._old, hwnd, msg, wp, lp)
                if self.fullscreen:
                    return HTCLIENT
                c = self.compact
                if c:  # 精简模式：只能左右拖改宽度；展开字幕时还能往下拖改高度
                    if r in (HTLEFT, HTTOPLEFT, HTBOTTOMLEFT) and not (c['drawer'] and r == HTBOTTOMLEFT):
                        return HTLEFT
                    if r in (HTRIGHT, HTTOPRIGHT, HTBOTTOMRIGHT) and not (c['drawer'] and r == HTBOTTOMRIGHT):
                        return HTRIGHT
                    if r == HTBOTTOM and not c['drawer']:
                        return HTCLIENT
                    if r == HTTOP:
                        return HTCLIENT
                return r
            if msg == WM_GETMINMAXINFO and self.compact:
                r = u32.CallWindowProcW(self._old, hwnd, msg, wp, lp)
                m = ctypes.cast(lp, ctypes.POINTER(MINMAXINFO)).contents
                c = self.compact
                m.ptMinTrackSize.x, m.ptMaxTrackSize.x = c['min_w'], c['max_w']
                m.ptMinTrackSize.y, m.ptMaxTrackSize.y = c['min_h'], c['max_h']
                return r
        except Exception:
            pass
        return u32.CallWindowProcW(self._old, hwnd, msg, wp, lp)

    # ---- 网页调用 ----
    def drag(self):  # 拖动标题栏
        u32.ReleaseCapture(); u32.SendMessageW(self.hwnd, 0xA1, 2, 0)  # WM_NCLBUTTONDOWN + HTCAPTION

    def resize_edge(self, edge):  # 顶边改大小（顶边在网页里，系统不知道那是边框）
        ht = {'top': HTTOP, 'topleft': HTTOPLEFT, 'topright': HTTOPRIGHT}.get(edge)
        if ht:
            u32.ReleaseCapture(); u32.SendMessageW(self.hwnd, 0xA1, ht, 0)

    def toggle_max(self):
        """最大化前记下原来的大小，还原时原样放回（WinForms 还原时会按“有标题栏”多算一截高度）。"""
        if self.fullscreen:
            return
        if u32.IsZoomed(self.hwnd):
            u32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
            r = getattr(self, 'normal', None)
            if r:
                u32.SetWindowPos(self.hwnd, 0, r.left, r.top, r.right - r.left, r.bottom - r.top, 0x0004)
        else:
            self.normal = wintypes.RECT(); u32.GetWindowRect(self.hwnd, ctypes.byref(self.normal))
            u32.ShowWindow(self.hwnd, 3)  # SW_MAXIMIZE

    def minimize(self):
        u32.ShowWindow(self.hwnd, 6)

    def state(self):
        return {'max': bool(u32.IsZoomed(self.hwnd)), 'fs': self.fullscreen}

    def set_fullscreen(self, on):
        """用 WindowPlacement 记下 / 恢复原来的状态（包括最大化），全屏时窗口正好盖住整个屏幕（连任务栏）。"""
        if bool(on) == self.fullscreen:
            return
        if on:
            wp = WINDOWPLACEMENT(); wp.length = ctypes.sizeof(WINDOWPLACEMENT)
            u32.GetWindowPlacement(self.hwnd, ctypes.byref(wp))
            self.fs_saved = (wp.showCmd == 3, wp.rcNormalPosition, wp)
            mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
            u32.GetMonitorInfoW(u32.MonitorFromWindow(self.hwnd, 2), ctypes.byref(mi))
            m = mi.rcMonitor
            self.fullscreen = True
            if u32.IsZoomed(self.hwnd):  # 最大化的窗口不能直接挪：先换成“普通状态、大小 = 整个屏幕”
                w2 = WINDOWPLACEMENT(); ctypes.pointer(w2)[0] = wp
                w2.showCmd = 1; w2.rcNormalPosition = wintypes.RECT(m.left - mi.rcWork.left, m.top - mi.rcWork.top, m.right - mi.rcWork.left, m.bottom - mi.rcWork.top)
                u32.SetWindowPlacement(self.hwnd, ctypes.byref(w2))
            u32.SetWindowPos(self.hwnd, -1, m.left, m.top, m.right - m.left, m.bottom - m.top, 0x0020 | 0x0040)  # TOPMOST，盖住任务栏
        else:
            self.fullscreen = False
            u32.SetWindowPos(self.hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)  # 取消置顶
            if self.fs_saved:
                u32.SetWindowPlacement(self.hwnd, ctypes.byref(self.fs_saved[2]))  # 原来的位置、大小、是否最大化
            u32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
