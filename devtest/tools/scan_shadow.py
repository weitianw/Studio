# 找“函数里 import 了文件开头已导入的模块，而在这句执行之前就可能用到它”——Python 会把整个函数里的这个名字当成局部变量，
# 先用就是 UnboundLocalError（2026-11-08 /api/video/status 就是这么坏的）。
# 用法：python -I scan_shadow.py [文件 ...]   不给参数扫 studio 下全部 .py
# 退出码：0 = 没发现；1 = 发现了（逐条打印）；2 = 文件读不了 / 语法错
# 2026-11-17 审查 C03：以前把“和 import 不在同一行”都当成“先用了”（import 之后再用也报），嵌套函数里的 import 也算到外层，最后只打印、退出码总是 0。
# 现在按 Python 的规则判断：
#   - 每个函数单独算，嵌套的函数 / 类 / lambda 是各自的作用域（它们里面的 import 不影响外层）；
#   - 用到的地方在 import 之后、并且 import 一定先执行过（import 所在的语句块里、排在它后面的语句）才算安全；
#     写在 import 之前的、或者 import 在 if / try / 循环里而用的地方在这个块外面的，都报；
#   - 函数里声明了 global 的名字不算局部。
import ast, glob, os, sys

sys.stdout.reconfigure(encoding='utf-8')
S = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'studio')
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def own_nodes(fn):
    """函数自己作用域里的节点（不进嵌套的函数 / 类 / lambda；推导式算在函数里：它读的是函数的局部变量）"""
    todo = list(ast.iter_child_nodes(fn))
    while todo:
        n = todo.pop()
        yield n
        if not isinstance(n, SCOPES):
            todo.extend(ast.iter_child_nodes(n))


def stmt_lists(node):
    """node 下面所有的语句列表（body / orelse / finalbody / handlers 的 body / match 的 case）"""
    for f in ('body', 'orelse', 'finalbody'):
        v = getattr(node, f, None)
        if isinstance(v, list) and v and isinstance(v[0], ast.stmt):
            yield v
    for h in getattr(node, 'handlers', []) or []:
        yield h.body
    for c in getattr(node, 'cases', []) or []:
        yield c.body


def contains(stmt, node):
    return any(n is node for n in ast.walk(stmt))


def guarded(fn, imp, use):
    """use 一定在 imp 执行之后：imp 所在的语句列表里，排在 imp 后面的某条语句包含 use"""
    todo = [fn]
    while todo:
        n = todo.pop()
        for L in stmt_lists(n):
            if any(s is imp for s in L):
                k = next(i for i, s in enumerate(L) if s is imp)
                return any(contains(s, use) for s in L[k + 1:])
            todo.extend(s for s in L if not isinstance(s, SCOPES) or s is fn)
    return False


def scan_fn(fn, top):
    nodes = list(own_nodes(fn))
    glob_names = {nm for n in nodes if isinstance(n, (ast.Global, ast.Nonlocal)) for nm in n.names}
    imps = {}
    for n in nodes:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                nm = (a.asname or a.name).split('.')[0]
                if nm in top and nm not in glob_names:
                    imps.setdefault(nm, []).append(n)
    out = []
    for nm, il in imps.items():
        for u in (n for n in nodes if isinstance(n, ast.Name) and n.id == nm and isinstance(n.ctx, ast.Load)):
            if not any(guarded(fn, i, u) for i in il):
                out.append((nm, min(i.lineno for i in il), u.lineno))
    return out


def scan_file(path):
    tree = ast.parse(open(path, encoding='utf-8').read(), path)
    top = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                top.add((a.asname or a.name).split('.')[0])
    found = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            hits = scan_fn(fn, top)
            if hits:
                found.append((fn, hits))
    return found


def main(argv):
    files = []
    for a in argv or sorted(glob.glob(os.path.join(S, '*.py'))):
        files.append(a if os.path.isfile(a) else os.path.join(S, os.path.basename(a)))  # 以前只认 studio 下的文件名；现在给完整路径也行
    bad = err = 0
    for p in files:
        try:
            found = scan_file(p)
        except (OSError, SyntaxError, UnicodeDecodeError) as e:
            print(f'?? {p}: 读不了（{e}）'); err += 1
            continue
        for fn, hits in found:
            for nm, il, ul in hits:
                print(f'!! {os.path.basename(p)}:{fn.lineno} {fn.name}(): 第 {il} 行 import {nm}，第 {ul} 行可能在它执行前就用了'); bad += 1
    print(f'扫描完：{len(files)} 个文件，发现 {bad} 处' + (f'，{err} 个读不了' if err else ''))
    return 2 if err else 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
