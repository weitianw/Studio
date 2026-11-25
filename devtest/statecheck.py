"""devtest/run.py --reset 前的核实（2026-11-17 审查 F06）：只删经过核实的、测试启动器生成的状态目录。
以前只要路径在 devtest 里就整个删：--state 指到 devtest/fixtures、devtest/tests 也会删掉源码 / 测试数据。"""
import os
import subprocess

MARK_NAME = '.devtest-state'


def reset_refusal(st, repo, here, known_states=()):
    """st 能不能整个删掉：能 → None；不能 → 原因（中文）"""
    ap, rp = os.path.normcase(os.path.abspath(st)), os.path.normcase(os.path.realpath(st))
    if os.path.islink(st) or ap != rp:
        return '是链接 / 联接点（可能指到别处）'
    protected = [repo, here, os.path.join(here, 'fixtures'), os.path.join(here, 'tests'), os.path.join(here, 'tools'), os.path.join(here, 'ui-audit'),
                 os.path.join(here, 'gpu-tests'), os.path.join(repo, 'studio'), os.path.join(repo, '.git'), os.path.dirname(repo)]
    for p in protected:
        p = os.path.normcase(os.path.realpath(p))
        if rp == p or p.startswith(rp.rstrip(os.sep) + os.sep):
            return f'是（或包含）受保护的目录 {p}'
    for p in (os.path.join(here, 'fixtures'), os.path.join(here, 'tests'), os.path.join(repo, 'studio')):
        if rp.startswith(os.path.normcase(os.path.realpath(p)) + os.sep):
            return f'在受保护的目录 {p} 里面'
    known = {os.path.normcase(os.path.realpath(k)) for k in known_states}
    if not os.path.isfile(os.path.join(st, MARK_NAME)) and rp not in known:
        return f'没有 {MARK_NAME} 标记，也不是哪个 profile 的默认状态目录'
    try:  # 里面有被 Git 跟踪的文件：肯定不是生成的
        r = subprocess.run(['git', '-C', repo, 'ls-files', '--', st], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return '里面有 Git 跟踪的文件'
    except Exception:
        pass
    return None
