"""iPhone 锁屏遥控测试（2026-11-16）：手机锁屏 / 放口袋里时，电脑发的命令还能不能让手机的播放有反应。

只用自己生成的测试音（ffmpeg 现做），不碰任何用户文件，也不碰 Studio。
- 模式一：手机网页自己放三首测试音（一首 25 秒，放完接下一首），每秒报一次心跳，同时挂一个“等命令”的长连接。
  看锁屏后心跳还在不在、命令还能不能收到、放完一首会不会自动接下一首。
- 模式二：手机一切到后台（锁屏 / 切走），播放器就换成这里持续送出的一路 MP3 声音（像网络电台 Icecast 那样），
  之后换首 / 暂停都由这里决定，跟手机网页的程序停没停无关；手机回到前台再换回自己放。

用法：python -I devtest/tools/ios_lock_probe.py [--port 7991]
  命令（只限本机）：curl -X POST http://127.0.0.1:7991/cmd -d '{"c":"next"}'   （next / pause / play）
  日志：控制台输出，或 GET http://127.0.0.1:7991/log
手机通过 tailscale serve --https=8443 转发到这里（见 README / 运行时打印的说明）。"""
import http.server, json, os, secrets, socketserver, struct, subprocess, sys, threading, time, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FFMPEG = os.path.join(ROOT, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
OUT = os.path.join(ROOT, 'devtest', 'state', 'ios_probe')
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 7991
_TF = os.path.join(OUT, 'token.txt')
TOKEN = open(_TF).read().strip() if os.path.isfile(_TF) else secrets.token_urlsafe(9)  # 重启后地址不变
PITCH = {1: 440, 2: 660, 3: 880}
SR, FRAME_SAMPLES = 44100, 1152
LEAD = 1.5  # 直播流比实时多送多少秒（越大越不容易断，命令生效越慢）

lock = threading.Lock()
cmd_cv = threading.Condition(lock)
CMDS = []  # {'seq', 'c', 't'}
LOG = []
LIVE = {'track': 1, 'paused': False, 'clients': 0}


def log(what, **kw):
    e = {'t': round(time.time(), 2), 'what': what, **kw}
    with lock:
        LOG.append(e)
        del LOG[:-3000]
    print(time.strftime('%H:%M:%S'), what, json.dumps(kw, ensure_ascii=False), flush=True)


def ff(args, out):
    if not os.path.isfile(out):
        subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *args, out], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def make_audio():
    os.makedirs(OUT, exist_ok=True)
    mp3 = ['-c:a', 'libmp3lame', '-b:a', '128k', '-ar', str(SR), '-ac', '1']
    for n, f in PITCH.items():
        beeps = f'0.12*sin(2*PI*{f}*t)*lt(mod(t,1),0.12*{n})'  # 第 n 首：每秒一声，声音越来越长，音高越来越高
        ff(['-f', 'lavfi', '-i', f"aevalsrc='{beeps}':s={SR}:d=25", *mp3], os.path.join(OUT, f't{n}.mp3'))
        ff(['-f', 'lavfi', '-i', f"aevalsrc='{beeps}':s={SR}:d=10", *mp3, '-reservoir', '0', '-write_xing', '0', '-id3v2_version', '0'],
           os.path.join(OUT, f'live{n}.mp3'))
    ff(['-f', 'lavfi', '-i', f'anullsrc=r={SR}:cl=mono', '-t', '10', *mp3], os.path.join(OUT, 't0.mp3'))  # 软暂停时循环放的无声
    ff(['-f', 'lavfi', '-i', f'anullsrc=r={SR}:cl=mono', '-t', '10', *mp3, '-reservoir', '0', '-write_xing', '0', '-id3v2_version', '0'],
       os.path.join(OUT, 'live0.mp3'))


def frames(path):
    """把 MP3 拆成一帧一帧（只认 MPEG-1 Layer III，ffmpeg 生成的就是这种）"""
    b = open(path, 'rb').read()
    br_tab = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    sr_tab = [44100, 48000, 32000]
    out, i = [], 0
    while i + 4 <= len(b):
        h = struct.unpack('>I', b[i:i + 4])[0]
        if (h >> 21) & 0x7FF != 0x7FF or (h >> 19) & 3 != 3 or (h >> 17) & 3 != 1:
            i += 1
            continue
        br, sr, pad = br_tab[(h >> 12) & 15] * 1000, sr_tab[(h >> 10) & 3], (h >> 9) & 1
        n = 144 * br // sr + pad
        out.append(b[i:i + n])
        i += n
    return out


FR = {}

PAGE = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="apple-mobile-web-app-capable" content="yes">
<title>锁屏遥控测试</title>
<style>body{font:16px -apple-system,sans-serif;margin:16px;background:#111;color:#eee}button{display:block;width:100%;font-size:17px;padding:14px;margin:8px 0;border-radius:12px;border:0;background:#2a6df4;color:#fff}
button.g{background:#333}#st{margin:12px 0;font-size:15px;line-height:1.6}#lg{font:12px ui-monospace,monospace;white-space:pre-wrap;color:#aaa;max-height:40vh;overflow:auto}</style></head><body>
<h3>锁屏遥控测试</h3>
<button id="m1">开始：模式一（手机直接收命令）</button>
<button id="m2">开始：模式二（锁屏后换成电脑供声音）</button>
<button id="m3">开始：模式三（电脑暂停时手机放无声，保持连接）</button>
<button id="stop" class="g">停止</button>
<div id="st">未开始</div><div id="lg"></div>
<script>
const K = new URLSearchParams(location.search).get('k'), $ = s => document.querySelector(s);
const a = new Audio(); a.preload = 'auto';
let mode = 0, track = 1, seq = -1, live = false, polling = false, n = 0, soft = null;
const lg = m => { $('#lg').textContent = new Date().toLocaleTimeString() + ' ' + m + '\n' + $('#lg').textContent.slice(0, 4000); };
const paint = () => { $('#st').textContent = mode ? `模式${'一二三'[mode - 1]} · ${live ? '电脑供声音' : '第 ' + track + ' 首'} · ${soft ? '软暂停' : a.paused ? '暂停' : '播放中'}` : '未开始'; };
const post = (p, b) => fetch(p + '?k=' + K, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b), keepalive: true }).catch(() => { });
const ev = (type, x = {}) => post('/ev', { type, mode, track, live, n: n++, vis: document.visibilityState, paused: a.paused, soft: !!soft, sa: !!navigator.standalone, ct: +a.currentTime.toFixed(1), ...x });
function meta() {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({ title: live ? '测试音（电脑供声音）' : '测试音 ' + track, artist: '锁屏遥控测试' });
}
function playTrack(t, at = 0) { track = ((t - 1) % 3 + 3) % 3 + 1; live = false; soft = null; a.loop = false; if (at) a.addEventListener('loadedmetadata', () => { a.currentTime = at; }, { once: true }); a.src = '/t/' + track + '.mp3?k=' + K; a.play().catch(e => lg('play 失败 ' + e.message)); meta(); paint(); }
a.onended = () => { ev('ended'); if (!live && !soft) playTrack(track + 1); };
function softPause() { if (soft) return; soft = { track, at: a.currentTime }; a.loop = true; a.src = '/t/0.mp3?k=' + K; a.play().catch(e => ev('soft_fail', { e: e.message })); ev('soft_pause', soft); }
function softPlay() { if (!soft) return a.play(); const s = soft; ev('soft_play', s); playTrack(s.track, s.at); }
['play', 'pause', 'stalled', 'waiting', 'error'].forEach(t => a.addEventListener(t, () => { if (mode) ev('a_' + t, t === 'error' ? { err: a.error && a.error.code } : {}); paint(); }));
function run(c) {
  lg('收到命令 ' + c);
  if (live) return;  // 电脑供声音时，换首 / 暂停在电脑那边做
  if (c === 'next') playTrack(track + 1); else if (c === 'prev') playTrack(track - 1);
  else if (c === 'pause') mode === 3 ? softPause() : a.pause(); else if (c === 'play') mode === 3 ? softPlay() : a.play();
  paint();
}
async function poll() {
  if (polling) return; polling = true;
  while (mode) {
    try {
      const r = await fetch(`/wait?k=${K}&since=${seq}&mode=${mode}`); const l = await r.json();
      for (const c of l) { seq = c.seq; ev('got', { c: c.c, cs: c.seq }); if (c.old) continue; run(c.c); }
    } catch (e) { ev('poll_err', { e: String(e) }); await new Promise(ok => setTimeout(ok, 1000)); }
  }
  polling = false;
}
function toLive() { if (mode !== 2 || live) return; live = true; ev('to_live'); a.src = `/live.mp3?k=${K}&track=${track}&r=${Date.now()}`; a.play().catch(e => ev('live_play_fail', { e: e.message })); meta(); }
async function fromLive() {
  if (!live) return;
  const s = await fetch('/livestate?k=' + K).then(r => r.json()).catch(() => ({ track }));
  ev('from_live', s); playTrack(s.track || track); if (s.paused) a.pause();
}
document.addEventListener('visibilitychange', () => { ev('vis'); if (mode === 2) document.hidden ? toLive() : fromLive(); });
window.addEventListener('pagehide', () => ev('pagehide')); window.addEventListener('pageshow', () => ev('pageshow'));
document.addEventListener('freeze', () => ev('freeze')); document.addEventListener('resume', () => ev('resume'));
if ('mediaSession' in navigator) {
  navigator.mediaSession.setActionHandler('play', () => { ev('ms_play'); mode === 3 ? softPlay() : a.play(); });
  navigator.mediaSession.setActionHandler('pause', () => { ev('ms_pause'); mode === 3 ? softPause() : a.pause(); });
  navigator.mediaSession.setActionHandler('nexttrack', () => { ev('ms_next'); if (!live) playTrack(track + 1); });
}
setInterval(() => { if (mode) ev('beat'); }, 1000);
function start(m) { mode = m; lg('开始模式' + m); ev('start'); playTrack(1); poll(); }
$('#m1').onclick = () => start(1); $('#m2').onclick = () => start(2); $('#m3').onclick = () => start(3);
$('#stop').onclick = () => { ev('stop'); mode = 0; soft = null; a.loop = false; a.pause(); a.removeAttribute('src'); a.load(); paint(); };
</script></body></html>'''


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *a):
        pass

    def local(self):
        return self.client_address[0] in ('127.0.0.1', '::1') and not any(
            self.headers.get(h) for h in ('Tailscale-User-Login', 'Tailscale-Headers-Info', 'X-Forwarded-For'))

    def send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store'); self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        try:
            return json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return {}

    def route(self, method):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        p = u.path
        if method == 'POST' and p == '/cmd' and self.local():
            c = str(self.body().get('c', ''))
            with cmd_cv:
                e = {'seq': len(CMDS), 'c': c, 't': time.time()}
                CMDS.append(e)
                if c == 'next':
                    LIVE['track'] = LIVE['track'] % 3 + 1
                elif c == 'prev':
                    LIVE['track'] = (LIVE['track'] - 2) % 3 + 1
                elif c in ('pause', 'play'):
                    LIVE['paused'] = c == 'pause'
                cmd_cv.notify_all()
            log('CMD', c=c, seq=e['seq'], live=dict(LIVE))
            return self.send(200, e)
        if method == 'GET' and p == '/log' and self.local():
            since = float(q.get('since') or 0)
            with lock:
                return self.send(200, [e for e in LOG if e['t'] > since])
        if q.get('k') != TOKEN:
            return self.send(403, {'error': 'token'})
        if method == 'GET' and p == '/':
            return self.send(200, PAGE, 'text/html; charset=utf-8')
        if method == 'POST' and p == '/ev':
            b = self.body()
            log('ev', **b)
            return self.send(200, {'ok': 1})
        if method == 'GET' and p == '/wait':
            since, t0 = int(q.get('since', -1)), time.time()
            with cmd_cv:
                while not [c for c in CMDS if c['seq'] > since] and time.time() - t0 < 20:
                    cmd_cv.wait(1)
                now = time.time()
                out = [{**c, 'old': now - c['t'] > 15, 'lat': round(now - c['t'], 2)} for c in CMDS if c['seq'] > since]
            for c in out:
                log('DELIVER', c=c['c'], seq=c['seq'], lat=c['lat'], old=c['old'])
            return self.send(200, out)
        if method == 'GET' and p == '/livestate':
            with lock:
                return self.send(200, dict(LIVE))
        if method == 'GET' and p.startswith('/t/') and p.endswith('.mp3'):
            f = os.path.join(OUT, 't' + p[3:-4] + '.mp3')
            if not os.path.isfile(f):
                return self.send(404, {'error': 'no'})
            return self.send_file(f)
        if method == 'GET' and p == '/live.mp3':
            return self.live(int(q.get('track') or 1))
        return self.send(404, {'error': 'not found'})

    def send_file(self, f):
        data = open(f, 'rb').read()
        rng = self.headers.get('Range')
        if rng and rng.startswith('bytes='):
            a, _, b = rng[6:].partition('-')
            a = int(a or 0); b = int(b) if b else len(data) - 1
            part = data[a:b + 1]
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {a}-{a + len(part) - 1}/{len(data)}')
        else:
            part = data
            self.send_response(200)
        self.send_header('Content-Type', 'audio/mpeg'); self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(len(part))); self.end_headers()
        self.wfile.write(part)

    def live(self, track):
        with lock:
            LIVE['track'] = track if track in PITCH else 1
            LIVE['paused'] = False
            LIVE['clients'] += 1
        log('LIVE_OPEN', track=track, range=self.headers.get('Range'), ua=(self.headers.get('User-Agent') or '')[:60])
        self.send_response(200)
        self.send_header('Content-Type', 'audio/mpeg'); self.send_header('Cache-Control', 'no-store')
        self.send_header('icy-name', 'probe'); self.end_headers()
        fdur = FRAME_SAMPLES / SR
        t0, sent, idx, last = time.time(), 0, 0, None
        try:
            while True:
                with lock:
                    kind = 0 if LIVE['paused'] else LIVE['track']
                if kind != last:
                    log('LIVE_KIND', kind=kind, at=round(sent * fdur, 1))
                    last = kind
                fr = FR[kind]
                self.wfile.write(fr[idx % len(fr)])
                idx += 1; sent += 1
                ahead = t0 + sent * fdur - time.time() - LEAD
                if ahead > 0:
                    time.sleep(ahead)
        except (ConnectionError, OSError):
            pass
        finally:
            with lock:
                LIVE['clients'] -= 1
            log('LIVE_CLOSE', secs=round(sent * fdur, 1), wall=round(time.time() - t0, 1))

    do_GET = lambda self: self.route('GET')
    do_POST = lambda self: self.route('POST')


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


if __name__ == '__main__':
    make_audio()
    for k in range(4):
        FR[k] = frames(os.path.join(OUT, f'live{k}.mp3'))
    with open(os.path.join(OUT, 'token.txt'), 'w') as f:
        f.write(TOKEN)
    print(f'锁屏测试已启动：127.0.0.1:{PORT}  token={TOKEN}  帧数={[len(FR[k]) for k in range(4)]}', flush=True)
    S(('127.0.0.1', PORT), H).serve_forever()
