"""私密空间密钥的本机校验记录（2026-11-17 审查 F08）。

以前：密钥的 SHA-256（不加盐）写在 server.py 源码里，所有安装共用；6 个字的密钥，拿到这个哈希几乎立刻就能试出来。
现在：每个安装一份自己的记录（私密空间文件夹里的 vault-key.json，不进 Git）：
  - scrypt（随机盐）算出的校验值，服务器核对用；
  - 另有一个随机的“提示盐”和 2 位提示：网页在本地先粗筛（打字时不用每 6 个字都问服务器），看不到真正的校验值。
迁移：老用户（没有记录、私密空间里已有数据）第一次用旧密钥解锁成功时自动写记录；有了记录以后旧的源码哈希不再被接受。
记录坏了（读不出）一律拒绝，不退回旧方式（防止降级）。
新安装 / 想换密钥：在这台电脑上运行  python -I studio/vaultkey.py  （输入两遍，不显示、不写日志）。"""
import base64, getpass, hashlib, json, os, secrets, sys, uuid

N, R, P = 2 ** 14, 8, 1  # scrypt 参数：约 16 MB、几十毫秒（解锁本来就限了次数）


def _kdf(key, salt, n=N, r=R, p=P):
    return hashlib.scrypt(key.encode('utf-8'), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * 1024 * 1024)


class Broken(Exception):
    """记录存在但读不出 / 内容不对"""


def load(path):
    """None = 没有记录；记录坏了 → Broken"""
    try:
        with open(path, encoding='utf-8') as f:
            rec = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Broken(str(e)) from e
    ok = isinstance(rec, dict) and rec.get('kdf') == 'scrypt' and all(isinstance(rec.get(k), str) for k in ('salt', 'hash', 'hint', 'hint_salt'))
    if not ok:
        raise Broken('内容不对')
    return rec


def make(key):
    salt, hs = os.urandom(16), secrets.token_hex(8)
    return {'v': 1, 'kdf': 'scrypt', 'n': N, 'r': R, 'p': P, 'salt': base64.b64encode(salt).decode(), 'hash': base64.b64encode(_kdf(key, salt)).decode(),
            'hint_salt': hs, 'hint': hashlib.sha256((hs + key).encode('utf-8')).hexdigest()[:2]}


def save(path, rec):
    """原子写入：写到临时文件再替换（迁移中途断掉不会留下半个记录）"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{uuid.uuid4().hex[:6]}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rec, f)
    os.replace(tmp, path)


def verify(rec, key):
    try:
        want = base64.b64decode(rec['hash'])
        got = _kdf(key, base64.b64decode(rec['salt']), int(rec.get('n', N)), int(rec.get('r', R)), int(rec.get('p', P)))
    except Exception:
        return False
    return secrets.compare_digest(got, want)


def check(path, key, legacy_sha='', legacy_allowed=lambda: False, log=lambda msg: None):
    """核对密钥。返回 True / False。老用户第一次用旧密钥成功时顺便迁移"""
    try:
        rec = load(path)
    except Broken:
        log('私密空间密钥记录读不出：拒绝解锁（不退回旧方式）。可在这台电脑上运行 python -I studio/vaultkey.py 重新设置')
        return False
    if rec:
        return verify(rec, key)
    if legacy_sha and legacy_allowed() and secrets.compare_digest(hashlib.sha256(key.encode('utf-8')).hexdigest(), legacy_sha):
        try:
            save(path, make(key))
            log('私密空间密钥已迁移到本机记录（之后不再使用旧的校验方式）')
        except OSError:
            log('私密空间密钥迁移没写成，下次解锁时再试')  # 这次照样放行
        return True
    return False


def hint(path, legacy_sha='', legacy_allowed=lambda: False):
    """给网页本地粗筛用：{'vk': 2 位提示, 'vks': 提示盐}；没有可用的密钥 → {'vk': None}"""
    try:
        rec = load(path)
    except Broken:
        return {'vk': None, 'vks': ''}
    if rec:
        return {'vk': rec['hint'], 'vks': rec['hint_salt']}
    if legacy_sha and legacy_allowed():
        return {'vk': legacy_sha[:2], 'vks': ''}
    return {'vk': None, 'vks': ''}


if __name__ == '__main__':  # 在这台电脑上设置 / 更换密钥
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, '.data', 'vault-key.json')
    k1 = getpass.getpass('新的私密空间密钥（6 个字母或数字）：').strip().lower()
    if len(k1) != 6 or not k1.isalnum():
        sys.exit('需要 6 个字母或数字')
    if getpass.getpass('再输入一遍：').strip().lower() != k1:
        sys.exit('两次不一样，没有修改')
    save(path, make(k1))
    print('已设置。重启 Studio 后生效。')
