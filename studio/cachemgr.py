"""设置页 · 存储：可以清掉的缓存（都能自动重新生成）。只看当前空间（普通 / 私密各管各的）。
不碰：作品（视频、图片、音频）、原视频、音色、字幕（字幕要重新识别，不算缓存）、设置。
按“最近一次用到”的时间（访问时间和修改时间取较晚的）算多久没用；最近 1 小时内用过的一律不删（可能正在用），
临时文件最近 1 天内的也不删（可能是还在跑的任务的）。2026-11-05 用户要求加。"""
import os
import time

DAY = 86400
MIN_AGE = 3600          # 1 小时内用过的不删
TMP_MIN_AGE = DAY       # 临时文件：1 天内的不删
AGES = (30, 90, 180, 365)


def _last_use(st):
    return max(st.st_mtime, st.st_atime)


def _walk(d, recursive):
    """目录里的普通文件（不跟随链接）。recursive=False 只看这一层。"""
    if not d or not os.path.isdir(d):
        return
    stack = [d]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir():
                            if recursive:
                                stack.append(e.path)
                        elif e.is_file():
                            yield e
                    except OSError:
                        continue
        except OSError:
            continue


def cats(videos_dir, covers_dir, conv_dir, tmp_dir):
    """可清理的几类缓存：(key, 名称, 说明, [(目录, 只看这一层？, 文件名过滤)], 最短保留秒数)"""
    scrub = lambda n: n.endswith('.scrub.mp4')
    return [
        ('scrub', '播放副本', '拖动进度条时用的视频副本；删除后播放时会自动重新生成',
         [(videos_dir, False, scrub), (covers_dir, False, scrub)], MIN_AGE),
        ('covers', '封面与缩略图', '音频、视频的封面和图片的缩略图；删除后打开时会自动重新生成',
         [(covers_dir, False, lambda n: not scrub(n) and not n.endswith('.tmp.mp4'))], MIN_AGE),
        ('conv', '格式转换', '浏览器不能直接播放的文件转好的副本；删除后再次播放时会重新转换',
         [(conv_dir, False, lambda n: not n.endswith('.tmp'))], MIN_AGE),
        ('tmp', '临时文件', '上传、试听和生成过程中留下的临时文件；最近 1 天内的不会删除',
         [(tmp_dir, False, lambda n: True)], TMP_MIN_AGE),  # False：子文件夹也看
    ]


def stats(cs, busy=()):
    now = time.time(); out = []
    for key, name, desc, srcs, keep in cs:
        size = files = 0; old = {str(a): 0 for a in AGES}; seen = set()
        for d, top, ok in srcs:
            for e in _walk(d, not top):
                if e.path in seen or not ok(e.name):
                    continue
                seen.add(e.path)
                try:
                    st = e.stat()
                except OSError:
                    continue
                size += st.st_size; files += 1
                idle = now - _last_use(st)
                for a in AGES:
                    if idle >= a * DAY:
                        old[str(a)] += st.st_size
        out.append({'key': key, 'name': name, 'desc': desc, 'size': size, 'files': files, 'old': old})
    return out


def clean(cs, keys, days, busy=()):
    """删掉选中的几类里、超过 days 天没用过的文件（days=0：不管多久，但仍保留最近 1 小时 / 1 天内的）"""
    now = time.time(); freed = n = 0; busy = set(busy); seen = set()
    for key, name, desc, srcs, keep in cs:
        if key not in keys:
            continue
        lim = max(keep, (days or 0) * DAY)
        for d, top, ok in srcs:
            for e in _walk(d, not top):
                if e.path in seen or not ok(e.name) or e.path in busy:
                    continue
                seen.add(e.path)
                try:
                    st = e.stat()
                    if now - _last_use(st) < lim:
                        continue
                    os.remove(e.path)
                    freed += st.st_size; n += 1
                except OSError:
                    continue
        if key == 'tmp':  # 临时文件夹里删空了的子文件夹也去掉（最上面那层留着）
            for d, top, ok in srcs:
                for root, dirs, fs in os.walk(d, topdown=False):
                    if root != d and not os.listdir(root):
                        try:
                            if now - os.stat(root).st_mtime >= lim:
                                os.rmdir(root)
                        except OSError:
                            pass
    return {'freed': freed, 'files': n}
