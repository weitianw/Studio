r"""任务计时：每个任务（生视频 / 生图 / 配音 / 换声 / 语音转文字）记下“开始了多久、分成哪几步、每步用了几秒”。
不用每个模块自己报：任务的状态文字（message）一变就算进入新的一步——进度数字（第 3/8 步、45%、2/5）先去掉，同一步里数字变化不算新的一步。
网页拿 export() 的结果显示计时，点开看每一步的用时。"""
import re
import threading
import time

_PROG = re.compile(r'[\s·:：,，]*(第\s*\d+\s*/\s*\d+\s*[步段张帧条句个次]?|\d+(?:\.\d+)?\s*%|[（(]\s*\d+\s*/\s*\d+\s*[）)]|\d+\s*/\s*\d+)')
_IDLE = {'排队中', '等待中', ''}
DONE_STATES = ('done', 'error', 'cancelled', 'warn')


def norm(msg):
    """状态文字 → 这一步的名字：去掉进度数字和结尾的省略号"""
    s = _PROG.sub('', str(msg or ''))
    return s.strip(' …·.:：，,').strip()[:60]


class Track:
    def __init__(self):
        self.t0 = self.t1 = None
        self.items = []  # [{'name', 't0', 't1'}]
        self.lock = threading.Lock()

    def start(self, now=None):
        with self.lock:
            if self.t0 is None:
                self.t0 = now or time.time()

    def note(self, msg, now=None):
        name = norm(msg)
        if name in _IDLE:
            return
        now = now or time.time()
        with self.lock:
            if self.t1 is not None:  # 2026-11-14 审查：已经结束了（先设 state = done、后写 message = 完成 的常见写法）：不再开新的一步，计时不再涨
                return
            if self.t0 is None:
                self.t0 = now
            if self.items and self.items[-1]['name'] == name and self.items[-1]['t1'] is None:
                return
            if self.items and self.items[-1]['t1'] is None:
                self.items[-1]['t1'] = now
            self.items.append({'name': name, 't0': now, 't1': None})

    def finish(self, now=None):
        now = now or time.time()
        with self.lock:
            if self.items and self.items[-1]['t1'] is None:
                self.items[-1]['t1'] = now
            if self.t0 is not None and self.t1 is None:
                self.t1 = now

    @classmethod
    def restore(cls, saved, t0=None, t1=None):
        """从存下来的计时（export() 的结果）恢复；已经结束的任务不会再计时（2026-11-17 审查 F13：以前恢复历史任务时
        重新赋值 state / message，计时从现在重新开始、“完成”那一步一直在涨）。
        saved 没有（旧记录）：用 t0（创建时间）和 t1（结束时间）当总时长，没有分步"""
        tr = cls()
        if isinstance(saved, dict) and saved.get('t0'):
            tr.t0 = float(saved['t0'])
            end = saved.get('t1') or t1 or saved.get('now') or tr.t0  # 存的时候还在跑（被关掉）：按结束 / 存盘时间收尾
            tr.t1 = float(end)
            cur = tr.t0
            for x in saved.get('stages') or []:
                sec = float(x.get('sec') or 0)
                tr.items.append({'name': str(x.get('name') or ''), 't0': cur, 't1': min(cur + sec, tr.t1) if x.get('live') else cur + sec})
                cur += sec
        elif t0:
            tr.t0, tr.t1 = float(t0), float(t1 or t0)
        return tr

    def export(self):
        now = time.time()
        with self.lock:
            if self.t0 is None:
                return None
            return {'t0': self.t0, 't1': self.t1, 'now': now,
                    'stages': [{'name': x['name'], 'sec': round((x['t1'] or now) - x['t0'], 1), 'live': x['t1'] is None and self.t1 is None} for x in self.items]}


class JobDict(dict):
    """生视频 / 生图的任务是 dict：赋值 message / state 时顺便记时间"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.track = Track()
        if self.get('state') == 'running':
            self.track.start()
        if self.get('message'):
            self.track.note(self['message'])

    def __setitem__(self, k, v):
        dict.__setitem__(self, k, v)
        if k == 'message':
            self.track.note(v)
        elif k == 'state':
            if v == 'running':
                self.track.start()
            elif v in DONE_STATES:
                self.track.finish()


class Tracked:
    """配音 / 换声 / 语音转文字的任务是对象：self.message / self.state 赋值时记时间（mixin，放在类定义最前面）"""

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if k in ('message', 'state'):
            tr = self.__dict__.get('_track')
            if tr is None:
                tr = Track()
                object.__setattr__(self, '_track', tr)
            if k == 'message':
                tr.note(v)
            elif v == 'running':
                tr.start()
            elif v in DONE_STATES:
                tr.finish()

    def timing(self):
        tr = self.__dict__.get('_track')
        return tr.export() if tr else None

    def restore_timing(self, saved, t0=None, t1=None):
        """从记录里恢复任务以后调用：换上存下来的计时（恢复时给 state / message 赋值会新开一个从现在算的计时）"""
        object.__setattr__(self, '_track', Track.restore(saved, t0, t1))
