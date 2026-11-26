"""手机访问（通过 Tailscale）。

安全设计：
- 只在 Tailscale 的虚拟网卡地址（100.x.x.x，tailscale ip -4）上额外监听，不对公寓 Wi-Fi 开放；Tailscale 之间的流量本身是加密的。
- 手机第一次打开要输入电脑上显示的 6 位配对码（5 分钟有效、输错 5 次作废），配对成功后手机记住一个随机令牌（超过一年没用就失效，要重新配对），
  电脑上可以随时移除某台设备。没配对的设备什么都看不到。
- 配对过的手机能用全部功能；只有资源管理器、PotPlayer、手机访问设置这些只能在电脑上做（见 pc_only）。
- 添加到主屏幕：iPhone 主屏幕上的网页应用可能拿不到 Safari 里的登录信息，所以给它一个只属于这台设备的“安装令牌”，
  写在主屏幕应用的启动地址里；第一次打开时换成它自己的登录令牌（不用再配对）。安装令牌可以重复换（主屏幕应用的登录信息被系统清掉后靠它重新登录），
  只对那一台设备有效；电脑上移除这台设备就全部作废。
"""
import hashlib, json, os, secrets, subprocess, threading, time
import config  # noqa: E402  路径（开源泛化 ①，studio/config.py）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, 'outputs', 'remote.json')
TS_EXE = (lambda p: p if os.path.isfile(p) else (__import__('shutil').which('tailscale') or p))(r'C:\Program Files\Tailscale\tailscale.exe')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
lock = threading.RLock()  # 读-改-写整段都拿着它：两个请求同时改设备列表时不会互相覆盖
_code = {}  # {'code', 'exp', 'tries'}
_listener = {'ip': None, 'httpd': None}

# 配对过的手机能用全部功能，只有这些操作电脑本机（屏幕、资源管理器、PotPlayer）或手机访问设置本身的不行
def pc_only(method, parts):
    if parts[-1:] == ['reveal']:  # 在资源管理器中打开 / 显示
        return True
    if parts[:3] == ['api', 'play', 'external']:  # 用电脑上的 PotPlayer 打开
        return True
    if parts[:2] == ['api', 'remote'] and parts[2:] not in (['pair'], ['install']):  # 手机访问的设置（开关、配对码、设备列表）
        return True
    if parts[:2] == ['api', 'settings'] and method != 'GET':  # AI 校对用哪家、发到哪个地址、密钥，Whisper 的路径
        return True
    return False


PUBLIC = [('GET', ['pair']), ('POST', ['api', 'remote', 'pair']), ('GET', ['static']), ('GET', ['manifest.webmanifest'])]  # 没配对也能打开的：配对页


def load():
    try:
        d = json.load(open(CONF, encoding='utf-8'))
    except (OSError, ValueError):
        d = {}
    d.setdefault('enabled', False); d.setdefault('devices', [])
    return d


def save(d):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with lock:
        tmp = CONF + '.tmp'  # 先写临时文件再替换：读的一方不会读到写了一半的文件
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CONF)


def _h(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def match(method, parts, rules):
    for m, pre in rules:
        if m == method and parts[:len(pre)] == pre and (pre or not parts):
            return True
    return False


def device_of(cookie_header):
    tok = ''
    for kv in (cookie_header or '').split(';'):
        k, _, v = kv.strip().partition('=')
        if k == 'dev':
            tok = v
    if not tok:
        return None
    h = _h(tok)
    with lock:
        d = load()
        for dev in d['devices']:
            if secrets.compare_digest(dev['hash'], h) or (dev.get('alt') and secrets.compare_digest(dev['alt'], h)) or any(secrets.compare_digest(x, h) for x in dev.get('alts') or []):
                if time.time() - (dev.get('last') or dev.get('created') or 0) > 365 * 86400:  # 2026-11-14 审查：说明里的“一年有效”以前没检查；按最后一次用算（一直在用的不会过期）
                    return None
                if time.time() - dev.get('last', 0) > 60:  # 记“最近使用”，不用每个请求都写文件
                    dev['last'] = time.time(); save(d)
                return dev
    return None


def new_code():
    _code.clear()
    _code.update({'code': f'{secrets.randbelow(10 ** 6):06d}', 'exp': time.time() + 300, 'tries': 0})
    return _code['code'], 300


def pair(code, name):
    """手机输入配对码：对了就发一个令牌（返回令牌），错了返回 None。"""
    with lock:
        return _pair(code, name)


def _pair(code, name):
    if not _code or time.time() > _code['exp']:
        return None, '配对码已过期，请在电脑上重新生成'
    _code['tries'] += 1
    if _code['tries'] > 5:
        _code.clear()
        return None, '输错次数过多，请在电脑上重新生成配对码'
    if not secrets.compare_digest(str(code).strip(), _code['code']):
        return None, '配对码错误'
    _code.clear()
    tok = secrets.token_urlsafe(32)
    d = load()
    d['devices'].append({'id': secrets.token_hex(4), 'hash': _h(tok), 'name': (name or '手机')[:40], 'created': time.time(), 'last': time.time()})
    save(d)
    return tok, ''


def install_token(dev_id):
    """给这台设备发一个“添加到主屏幕”用的令牌（每次重新发，旧的作废）。"""
    tok = secrets.token_urlsafe(24)
    with lock:
        d = load()
        for dev in d['devices']:
            if dev['id'] == dev_id:
                dev['itok'] = _h(tok); save(d)
                return tok
    return None


def redeem(itok):
    """主屏幕应用第一次打开（还没有自己的登录信息）：用安装令牌换一个它自己的登录令牌。"""
    h = _h(str(itok))
    with lock:
        d = load()
        for dev in d['devices']:
            if dev.get('itok') and secrets.compare_digest(dev['itok'], h):
                tok = secrets.token_urlsafe(32)
                # 以前每换一次就把上一个主屏幕应用的登录令牌盖掉（同一个安装链接在别处打开一次，原来的主屏幕应用就掉线，审查 24）：留最近 4 个
                olds = [x for x in [dev.get('alt')] + list(dev.get('alts') or []) if x]
                dev['alts'] = list(dict.fromkeys(olds))[:3]
                dev['alt'], dev['last'] = _h(tok), time.time(); save(d)
                return tok
    return None


def remove_device(did):
    with lock:
        d = load(); d['devices'] = [x for x in d['devices'] if x['id'] != did]; save(d)
    try:  # 它的推送订阅也删掉（以前移除了手机还照样收到“任务完成”，2026-11-15 审查）
        import push
        push.unsubscribe(did)
    except Exception:
        pass
    try:  # 它的面容 ID 通行密钥也删掉（11-21）
        import passkey
        with passkey.lock:
            d = passkey._load(); d['creds'] = [c for c in d['creds'] if c.get('dev') != did]; passkey._save(d)
    except Exception:
        pass


def tailscale():
    """Tailscale 的状态：有没有装、地址、电脑名（MagicDNS）。"""
    if not os.path.isfile(TS_EXE):
        return {'installed': False}
    try:
        p = subprocess.run([TS_EXE, 'status', '--json'], capture_output=True, text=True, timeout=6, creationflags=NO_WINDOW, encoding='utf-8', errors='replace')
        st = json.loads(p.stdout or '{}')
        me = st.get('Self') or {}
        ips = [x for x in (me.get('TailscaleIPs') or []) if '.' in x]
        return {'installed': True, 'running': st.get('BackendState') == 'Running', 'ip': ips[0] if ips else None,
                'name': (me.get('DNSName') or '').rstrip('.'), 'host': me.get('HostName')}
    except Exception as e:
        return {'installed': True, 'running': False, 'error': str(e)}


def keep_listening(make_server, port, log):
    """后台每 20 秒看一次：开启了手机访问、并且 Tailscale 有地址，就在那个地址上监听；关掉或地址变了就停掉 / 重新监听。"""
    def loop():
        while True:
            try:
                want = None
                if load()['enabled']:
                    ts = tailscale()
                    if ts.get('running') and ts.get('ip'):
                        want = ts['ip']
                if want != _listener['ip']:
                    old = _listener['httpd']
                    if old:
                        old.shutdown(); old.server_close()
                    _listener.update(ip=None, httpd=None)
                    if want:
                        httpd = make_server((want, port))
                        threading.Thread(target=httpd.serve_forever, daemon=True).start()
                        _listener.update(ip=want, httpd=httpd)
                        log(f'手机访问已开启：http://{want}:{port}')
                    else:
                        log('手机访问已关闭')
            except Exception as e:
                log(f'手机访问监听失败：{e}')
            time.sleep(20)
    threading.Thread(target=loop, daemon=True).start()


def listening():
    return _listener['ip']
