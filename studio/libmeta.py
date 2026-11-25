"""播放页歌曲表的“时长 / 作者”（2026-11-17 用户：只显示大小不如显示时长，作者、时长、大小都放上去）。

用项目自带的 ffprobe（tools/ffmpeg）读：format 的时长 + artist / album_artist 标签。
一个文件要起一次 ffprobe，几百个文件要几十秒，所以不在扫描音源库时同步读：
扫描时只把缓存里已有的（大小、修改时间都没变）填进去，缺的放到后台慢慢读（低优先级、不弹窗口），
读完一批存盘并通知调用方（server.py 把这个空间的扫描缓存作废，网页下一次轮询时指纹变了就会重画）。
缓存按文件存：每个空间一份（私密空间的放在私密空间自己的缓存文件夹里）。
"""
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LOW_PRI = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
_lock = threading.Lock()
_stores = {}    # 缓存文件 -> {相对路径: [大小, 修改时间, 时长, 作者]}
_running = set()  # 正在后台读的缓存文件


def probe(ffprobe, path, timeout=20):
    """返回 (时长秒数或 None, 作者或 '')。读不出来不报错。"""
    try:
        r = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:format_tags', '-of', 'json', path],
                           capture_output=True, timeout=timeout, creationflags=NO_WINDOW | LOW_PRI)
        f = json.loads(r.stdout.decode('utf-8', 'replace') or '{}').get('format') or {}
    except Exception:
        return None, ''
    try:
        dur = round(float(f.get('duration')), 1)
    except (TypeError, ValueError):
        dur = None
    tags = {str(k).lower(): str(v).strip() for k, v in (f.get('tags') or {}).items()}
    artist = tags.get('artist') or tags.get('album_artist') or tags.get('author') or ''
    return dur, artist[:120]


def _load(cache):
    s = _stores.get(cache)
    if s is None:
        try:
            with open(cache, encoding='utf-8') as fh:
                s = json.load(fh)
            if not isinstance(s, dict):
                s = {}
        except Exception:
            s = {}
        _stores[cache] = s
    return s


def _save(cache, s):
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        tmp = cache + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(s, fh, ensure_ascii=False)
        os.replace(tmp, cache)
    except Exception:
        pass


def fill(items, root, cache, ffprobe, on_done=None, workers=3):
    """把缓存里的时长 / 作者填进 items（就地加 'dur' / 'artist'），缺的放到后台读；返回缺几个。"""
    with _lock:
        s = _load(cache)
        missing = []
        for it in items:
            e = s.get(it['path'])
            if e and e[0] == it['size'] and e[1] == it['mtime']:
                if e[2] is not None:
                    it['dur'] = e[2]
                if e[3]:
                    it['artist'] = e[3]
            else:
                missing.append((it['path'], it['size'], it['mtime']))
        if not missing or cache in _running or not os.path.isfile(ffprobe):
            return len(missing)
        _running.add(cache)

    def work():
        try:
            def one(m):
                rel, size, mtime = m
                dur, artist = probe(ffprobe, os.path.join(root, *rel.split('/')))
                return rel, [size, mtime, dur, artist]
            done = 0
            with ThreadPoolExecutor(workers) as ex:
                for rel, e in ex.map(one, missing):
                    with _lock:
                        s[rel] = e
                    done += 1
                    if done % 200 == 0:  # 文件很多时分批存盘、分批让网页更新
                        with _lock:
                            _save(cache, dict(s))
                        if on_done:
                            on_done()
            with _lock:
                live = {it_rel for it_rel in s if os.path.exists(os.path.join(root, *it_rel.split('/')))} if len(s) > len(items) * 2 + 100 else None
                if live is not None:  # 删掉的文件太多时顺手清理一下
                    for k in list(s):
                        if k not in live:
                            s.pop(k, None)
                _save(cache, dict(s))
        finally:
            with _lock:
                _running.discard(cache)
            if on_done:
                on_done()
    threading.Thread(target=work, daemon=True, name='libmeta').start()
    return len(missing)
