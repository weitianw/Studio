"""手机推送：生成完成 / 失败时通知配对过的手机（2026-11-06 用户要求）。

- 只有通过 https（tailscale serve）打开、加到主屏幕的手机才能订阅（iPhone 的网页推送要求）。
- 推送本身不带内容（不用加密载荷）：手机收到后由 sw.js 来取 /api/push/last，显示最近完成的是什么。
- 私密空间的任务只说“有任务已完成”，不带名字、提示词。
- 手机这会儿正开着 Studio（20 秒内有过请求）就不推：页面里自己会提示。
- VAPID 密钥第一次用时生成，存在 outputs/push.json（和手机配对信息 remote.json 放在一起）。
"""
import base64, json, os, threading, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, 'outputs', 'push.json')
lock = threading.RLock()
SEEN = {}    # 设备 id -> 最近一次请求的时间（页面开着时不推）
NOTES = []   # 最近几条通知 {t, title, body, url}
SUB = 'mailto:studio@localhost'


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _load():
    try:
        d = json.load(open(CONF, encoding='utf-8'))
    except (OSError, ValueError):
        d = {}
    d.setdefault('subs', [])
    return d


def _save(d):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    tmp = CONF + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONF)


def _keys():
    """(私钥对象, 公钥 65 字节)；没有就生成一对存起来"""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    with lock:
        d = _load()
        if not d.get('vapid'):
            k = ec.generate_private_key(ec.SECP256R1())
            d['vapid'] = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            _save(d)
        k = serialization.load_pem_private_key(d['vapid'].encode(), None)
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return k, pub


def public_key():
    return b64u(_keys()[1])


def subscribe(dev_id, sub, origin):
    ep = str((sub or {}).get('endpoint') or '')
    if not ep.startswith('https://'):
        raise ValueError('订阅信息不对')
    with lock:
        d = _load()
        d['subs'] = [s for s in d['subs'] if s.get('endpoint') != ep and s.get('dev') != dev_id]
        d['subs'].append({'dev': dev_id, 'endpoint': ep, 'origin': origin, 'created': time.time()})
        _save(d)


def unsubscribe(dev_id):
    with lock:
        d = _load(); n = len(d['subs'])
        d['subs'] = [s for s in d['subs'] if s.get('dev') != dev_id]
        _save(d)
        return n != len(d['subs'])


def subscribed(dev_id):
    return any(s.get('dev') == dev_id for s in _load()['subs'])


def _jwt(aud, sub_claim):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    k, pub = _keys()
    h = b64u(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    c = b64u(json.dumps({'aud': aud, 'exp': int(time.time()) + 12 * 3600, 'sub': sub_claim}, separators=(',', ':')).encode())
    r, s = decode_dss_signature(k.sign(f'{h}.{c}'.encode(), ec.ECDSA(hashes.SHA256())))
    return f'{h}.{c}.{b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}', b64u(pub)


def _send(s):
    """推一条（不带内容）。返回 HTTP 状态码；订阅失效（404 / 410）时由调用方删掉"""
    u = urllib.parse.urlparse(s['endpoint'])
    tok, pk = _jwt(f'{u.scheme}://{u.netloc}', f"https://{s['origin']}" if s.get('origin') else SUB)  # 苹果要求 sub 是 https 地址或 mailto；用自己的网址最稳
    rq = urllib.request.Request(s['endpoint'], data=b'', method='POST', headers={
        'Authorization': f'vapid t={tok}, k={pk}', 'TTL': '3600', 'Urgency': 'normal', 'Content-Length': '0'})
    try:
        with urllib.request.urlopen(rq, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def notify(title, body, url='/play'):
    """记下这条，并推给所有订阅了、现在没开着 Studio 的手机"""
    with lock:
        NOTES.append({'t': time.time(), 'title': title, 'body': body, 'url': url}); del NOTES[:-20]
        subs = list(_load()['subs'])
    dead = []
    for s in subs:
        if time.time() - SEEN.get(s.get('dev'), 0) < 20:  # 手机上正开着：页面自己会提示
            continue
        st = _send(s)
        if st in (404, 410):
            dead.append(s['endpoint'])
        elif st and not 200 <= st < 300:
            print(f'[推送] 发送失败 {st}', flush=True)
    if dead:
        with lock:
            d = _load(); d['subs'] = [s for s in d['subs'] if s['endpoint'] not in dead]; _save(d)


def last():
    with lock:
        return dict(NOTES[-1]) if NOTES else {'title': 'Studio', 'body': '任务已完成', 'url': '/play'}


def _state(j):
    return j.get('state') if isinstance(j, dict) else getattr(j, 'state', None)


def _get(j, k, d=None):
    return j.get(k, d) if isinstance(j, dict) else getattr(j, k, d)


def watch(sources):
    """sources：[(种类, 取任务表的函数, 打开哪一页)]。每 4 秒看一次，新做完 / 失败的就通知（一次做完好几个合成一条）"""
    def run():
        done, t0 = set(), time.time()  # t0 之前就结束的不推：旧记录有的是启动后才从硬盘读回来的（改录音打开页面时才读），以前会推一条假的“N 个任务完成”（2026-11-15 审查）
        for _, get, _u in sources:  # 启动前就已经结束的不算
            try:
                done |= {k for k, j in list(get().items()) if _state(j) in ('done', 'error', 'cancelled')}
            except Exception:
                pass
        while True:
            time.sleep(4)
            try:
                subs = bool(_load()['subs'])
                new = []
                for kind, get, url in sources:
                    for k, j in list(get().items()):
                        stt = _state(j)
                        if stt in ('done', 'error', 'cancelled') and k not in done:
                            done.add(k)  # 没订阅时也记下，之后第一次订阅不会把以前的一次全推出去
                            if not subs or (_get(j, 'created') is not None and float(_get(j, 'created') or 0) < t0) or (stt == 'error' and str(_get(j, 'message', '') or '') == '已取消'):
                                continue  # 配音的“已取消”也是 error 状态
                            if stt != 'cancelled':
                                new.append((kind, j, stt, url))
                if not new:
                    continue
                priv = any((_get(j, 'space') or _get(j, '_space') or 'n') == 'v' for _, j, _, _ in new)  # 改录音记在 _space（以前只认 space：私密改录音的详情被推出去，2026-11-16 审查）
                bad = [x for x in new if x[2] == 'error']
                if priv:  # 私密空间：不说是什么
                    title, body = 'Studio', ('有任务失败' if bad and len(bad) == len(new) else '有任务已完成')
                elif len(new) == 1:
                    kind, j, stt, _u = new[0]
                    name = _get(j, 'model_name') or _get(j, 'title') or ''
                    title = f"{kind}{'完成' if stt == 'done' else '失败'}"
                    body = str(name)[:60] + ('' if stt == 'done' else ('：' + str(_get(j, 'error') or '')[:80]))
                else:
                    title = f'{len(new) - len(bad)} 个任务完成' + (f'，{len(bad)} 个失败' if bad else '')
                    body = '、'.join(dict.fromkeys(k for k, *_ in new))
                notify(title, body or '点开查看', new[-1][3])
            except Exception as e:
                print('[推送] 出错：', e, flush=True)
    threading.Thread(target=run, daemon=True).start()
