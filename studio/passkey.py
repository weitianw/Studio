"""私密空间用面容 ID / 指纹解锁（通行密钥 WebAuthn，2026-11-06 用户要求）。

- 只能在私密空间里、通过 https 打开的页面上开启（iPhone 要求安全的地址）；开启的是“这台手机”的通行密钥。
- 解锁：手机上按住页面标题不放（不显示任何按钮，和打密钥一样是隐藏的入口）→ 系统弹出面容 ID → 验证通过就进私密空间。
- 服务器只存公钥（.data/vault-passkeys.json）；每次解锁核对：一次性的挑战、网站地址、做过用户验证（面容 / 指纹 / 密码）、签名。
- 只支持 ES256（iPhone / Mac / Windows Hello 都用它）。
"""
import base64, hashlib, json, os, secrets, struct, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, '.data', 'vault-passkeys.json')
lock = threading.RLock()
_chal = {}  # 挑战 -> (用途, 时间)
TTL = 120
TEST_LOCALHOST = False  # 测试用：允许 http://localhost（无头浏览器的虚拟验证器）；正式运行不改它


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def ub64(s):
    s = str(s or '')
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def _load():
    try:
        d = json.load(open(CONF, encoding='utf-8'))
    except (OSError, ValueError):
        d = {}
    d.setdefault('creds', [])
    return d


def _save(d):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    tmp = CONF + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONF)


def _new_challenge(kind):
    c = secrets.token_bytes(32)
    with lock:
        now = time.time()
        for k in [k for k, (_, t) in _chal.items() if now - t > TTL]:
            _chal.pop(k, None)
        _chal[b64u(c)] = (kind, now)
    return b64u(c)


def _take_challenge(c, kind):
    with lock:
        v = _chal.pop(c, None)
    return bool(v) and v[0] == kind and time.time() - v[1] <= TTL


# ---- 极简 CBOR（只解 WebAuthn 用到的：整数、字节串、文字、数组、表）
def _cbor(b, i=0):
    ib = b[i]; mt, ai = ib >> 5, ib & 31; i += 1
    if ai < 24:
        v = ai
    elif ai in (24, 25, 26, 27):
        n = 1 << (ai - 24); v = int.from_bytes(b[i:i + n], 'big'); i += n
    else:
        raise ValueError('不支持的 CBOR')
    if mt == 0:
        return v, i
    if mt == 1:
        return -1 - v, i
    if mt == 2:
        return bytes(b[i:i + v]), i + v
    if mt == 3:
        return b[i:i + v].decode('utf-8'), i + v
    if mt == 4:
        out = []
        for _ in range(v):
            x, i = _cbor(b, i); out.append(x)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(v):
            k, i = _cbor(b, i); x, i = _cbor(b, i); out[k] = x
        return out, i
    if mt == 7:
        return {20: False, 21: True, 22: None}.get(ai), i
    raise ValueError('不支持的 CBOR')


def _client(cdj, kind, chal_kind):
    c = json.loads(cdj.decode('utf-8'))
    if c.get('type') != kind:
        raise ValueError('类型不对')
    if not _take_challenge(c.get('challenge', ''), chal_kind):
        raise ValueError('验证已过期，请再试一次')
    o = str(c.get('origin') or '')
    if TEST_LOCALHOST and o.startswith('http://localhost:'):  # 只有测试脚本会打开（正式运行永远是 False）
        return 'localhost'
    if not o.startswith('https://'):
        raise ValueError('需要通过 https 地址打开')
    return o[len('https://'):].split('/')[0].split(':')[0]


def _auth_flags(ad, rp):
    if ad[:32] != hashlib.sha256(rp.encode()).digest():
        raise ValueError('网站地址不对')
    fl = ad[32]
    if not (fl & 1 and fl & 4):  # UP 用户在场、UV 做过面容 / 指纹 / 密码验证
        raise ValueError('没有完成面容 / 指纹验证')
    return fl, struct.unpack('>I', ad[33:37])[0]


def reg_options(host, dev_id=None):
    # 只排除这台设备自己的（11-21 用户 iPhone“开启失败：The object is in an invalid state”：手机重新配对后换了设备 id，
    # 旧 id 下的通行密钥还在列表里；以前把这个网址下所有设备的都排除，手机发现自己已有其中一个就拒绝新建）
    return {'challenge': _new_challenge('reg'), 'rp': {'id': host, 'name': 'Studio'},
            'user': {'id': b64u(secrets.token_bytes(16)), 'name': 'Studio', 'displayName': 'Studio'},
            'pubKeyCredParams': [{'type': 'public-key', 'alg': -7}], 'timeout': 60000, 'attestation': 'none',
            'authenticatorSelection': {'userVerification': 'required', 'residentKey': 'preferred', 'authenticatorAttachment': 'platform'},
            'excludeCredentials': [{'type': 'public-key', 'id': c['id']} for c in _load()['creds'] if c.get('rp') == host and c.get('dev') == dev_id]}


def _paired(dev):
    if dev == 'pc':
        return True
    try:
        import remote
        return any(x.get('id') == dev for x in remote.load()['devices'])
    except Exception:
        return True  # 读不到配对列表：不删


def register(b, dev_id, dev_name):
    cdj, att = ub64(b.get('clientDataJSON')), ub64(b.get('attestationObject'))
    rp = _client(cdj, 'webauthn.create', 'reg')
    ao, _ = _cbor(att)
    ad = ao['authData']
    fl, cnt = _auth_flags(ad, rp)
    if not fl & 64:
        raise ValueError('没有拿到通行密钥')
    n = struct.unpack('>H', ad[53:55])[0]
    cid = ad[55:55 + n]
    key, _ = _cbor(ad, 55 + n)
    if key.get(1) != 2 or key.get(3) != -7 or key.get(-1) != 1:
        raise ValueError('这台设备的通行密钥类型不支持')
    with lock:
        d = _load()
        d['creds'] = [c for c in d['creds'] if (c.get('dev') != dev_id or c.get('rp') != rp) and _paired(c.get('dev'))]  # 同一台手机只留一个；已经不在配对列表里的设备（重新配对前的旧 id）的也删掉
        d['creds'].append({'id': b64u(cid), 'x': b64u(key[-2]), 'y': b64u(key[-3]), 'rp': rp, 'dev': dev_id, 'name': (dev_name or '手机')[:40],
                           'count': cnt, 'created': time.time()})
        _save(d)
    return True


def auth_options(host, dev_id=None):
    # 只给这台设备登记过的（“面容 ID 解锁（本机）”；以前把这个网址下所有设备的都列上，同步过去的通行密钥在别的手机上也能解锁，审查 10）
    ids = [c['id'] for c in _load()['creds'] if c.get('rp') == host and (dev_id is None or c.get('dev') == dev_id)]
    return {'challenge': _new_challenge('auth'), 'rpId': host, 'timeout': 60000, 'userVerification': 'required',
            'allowCredentials': [{'type': 'public-key', 'id': i, 'transports': ['internal', 'hybrid']} for i in ids]}


def verify(b, dev_id=None):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    cid = str(b.get('id') or '')
    c = next((x for x in _load()['creds'] if x['id'] == cid), None)
    if not c or (dev_id is not None and c.get('dev') != dev_id):  # 别的设备登记的通行密钥不认（审查 10）
        raise ValueError('这台设备还没有开启面容 ID 解锁')
    cdj, ad, sig = ub64(b.get('clientDataJSON')), ub64(b.get('authenticatorData')), ub64(b.get('signature'))
    rp = _client(cdj, 'webauthn.get', 'auth')
    if rp != c['rp']:
        raise ValueError('网站地址不对')
    _, cnt = _auth_flags(ad, rp)
    pub = ec.EllipticCurvePublicNumbers(int.from_bytes(ub64(c['x']), 'big'), int.from_bytes(ub64(c['y']), 'big'), ec.SECP256R1()).public_key()
    pub.verify(sig, ad + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256()))  # 签名不对会抛 InvalidSignature
    if cnt and c.get('count') and cnt <= c['count']:  # 计数器倒退：可能是复制出来的密钥
        raise ValueError('通行密钥校验失败')
    with lock:
        d = _load()
        for x in d['creds']:
            if x['id'] == cid:
                x['count'], x['last'] = cnt, time.time()
        _save(d)
    return True


def has(dev_id, host):
    return any(c.get('dev') == dev_id and c.get('rp') == host for c in _load()['creds'])


def remove(dev_id, host):
    with lock:
        d = _load(); n = len(d['creds'])
        d['creds'] = [c for c in d['creds'] if not (c.get('dev') == dev_id and c.get('rp') == host)]
        _save(d)
        return n != len(d['creds'])
