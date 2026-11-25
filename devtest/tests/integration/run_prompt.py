"""提示词助手的实际测试（对 devtest/run.py 起的测试 Studio）：流式生成、预设、参数、思考模式、和生图轮流用显卡、空间隔离。
用法：先起 devtest/run.py，再 python -I devtest/test_prompt.py"""
import json, sys, time, threading, urllib.error, urllib.request

B = 'http://127.0.0.1:7865'
OK, BAD = [], []


def req(path, body=None, method=None, timeout=120, cookie=''):
    h = {'Content-Type': 'application/json'}
    if cookie:
        h['Cookie'] = cookie
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, json.loads(x.read() or b'{}'), x.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}'), e.headers


def check(name, cond, info=''):
    (OK if cond else BAD).append(name)
    print(('  通过  ' if cond else '  失败  ') + name + (f'  ({str(info)[:160]})' if info else ''), flush=True)


def chat(body, cookie=''):
    h = {'Content-Type': 'application/json'}
    if cookie:
        h['Cookie'] = cookie
    r = urllib.request.Request(B + '/api/prompt/chat', json.dumps(body).encode(), h)
    text, reasoning, err, t0, first = '', '', None, time.time(), None
    with urllib.request.urlopen(r, timeout=900) as x:
        for raw in x:
            line = raw.decode('utf-8').strip()
            if not line.startswith('data:'):
                continue
            d = json.loads(line[5:])
            if d['type'] == 'text':
                first = first or time.time() - t0
                text += d['v']
            elif d['type'] == 'reasoning':
                reasoning += d['v']
            elif d['type'] == 'error':
                err = d['v']
    return text, reasoning, err, time.time() - t0, first


s, st, _ = req('/api/prompt/status')
check('模型文件在、能用', st.get('available'), st.get('model'))
check('有默认的 4 套预设', len(st.get('presets', [])) >= 4, [p['name'] for p in st.get('presets', [])])
# 1 生图提示词（第一次要载入模型）
t, r, e, sec, first = chat({'preset': 'img-zh', 'messages': [{'role': 'user', 'content': '一个女孩在雨夜的便利店门口'}], 'params': {'max_tokens': 400}})
check('生图提示词：写出来了', not e and len(t) > 60, e or f'{len(t)} 字，用时 {sec:.0f} 秒（首字 {first:.0f} 秒）')
print('    ', t[:160].replace('\n', ' '))
check('没有思考过程（默认关）', not r)
check('只输出提示词（没有“提示词：”之类的开头和代码块）', not t.strip().startswith(('提示词', '```', '**')), t[:30])
# 2 第二次：模型已经在显存里，看速度
t, r, e, sec, first = chat({'preset': 'tts', 'messages': [{'role': 'user', 'content': '一个刚失恋的男生在深夜给朋友打电话，压抑但强装没事'}], 'params': {'max_tokens': 300, 'temperature': 0.9}})
check('配音台词：写出来了', not e and len(t) > 40, e or f'{len(t)} 字，用时 {sec:.1f} 秒（首字 {first:.1f} 秒，约 {len(t) / max(.1, sec - (first or 0)):.0f} 字/秒）')
print('    ', t[:160].replace('\n', ' '))
# 3 多轮修改
t2, r, e, sec, _ = chat({'preset': 'img-zh', 'messages': [{'role': 'user', 'content': '一个女孩在雨夜的便利店门口'}, {'role': 'assistant', 'content': '雨夜，便利店门口，一个穿校服的女孩'},
                                                          {'role': 'user', 'content': '改成白天，阳光很好'}], 'params': {'max_tokens': 300}})
check('多轮修改', not e and ('阳光' in t2 or '白天' in t2 or '日' in t2), e or t2[:60])
# 4 思考模式
t, r, e, sec, _ = chat({'preset': 'img-zh', 'messages': [{'role': 'user', 'content': 'a cat astronaut'}], 'params': {'thinking': True, 'effort': 'low', 'max_tokens': 1500}})
check('思考模式：有思考过程、也有结果', not e and len(r) > 20 and len(t) > 30, e or f'思考 {len(r)} 字，结果 {len(t)} 字')
# 5 固定种子、温度 0：两次一样
p = {'temperature': 0.0, 'seed': 42, 'max_tokens': 120}
a = chat({'preset': 'img-zh', 'messages': [{'role': 'user', 'content': '今天天气很好我们去公园'}], 'params': p})[0]
b = chat({'preset': 'img-zh', 'messages': [{'role': 'user', 'content': '今天天气很好我们去公园'}], 'params': p})[0]
check('温度 0 + 固定种子：结果一样', a and a == b, f'{a[:30]} | {b[:30]}')
# 6 自定义 system prompt（不存预设，直接带）
t, r, e, *_ = chat({'system': '无论用户说什么，只回答两个字：收到', 'messages': [{'role': 'user', 'content': '你好'}], 'params': {'temperature': 0, 'max_tokens': 20}})
check('临时的 system prompt 生效', '收到' in t, t)
# 7 预设的增删改、两个空间分开
s, st, _ = req('/api/prompt/status')
mine = st['presets'] + [{'name': '测试预设', 'target': 'img', 'system': '测试用'}]
s, saved, _ = req('/api/prompt/presets', {'presets': mine})
check('新增预设', s == 200 and any(x['name'] == '测试预设' for x in saved))
s, e2, _ = req('/api/prompt/presets', {'presets': []})
check('不能删光（至少留一个）', s == 400, e2.get('error'))
s, _, h = req('/api/vault/unlock', {'key': 'testky'})
vc = (h.get('Set-Cookie') or '').split(';')[0]
s, vst, _ = req('/api/prompt/status', cookie=vc)
check('私密空间里看不到普通空间新加的预设', not any(x['name'] == '测试预设' for x in vst['presets']))
req('/api/prompt/presets', {'presets': st['presets']})  # 还原
req('/api/vault/lock', {}, cookie=vc)
# 8 和生图轮流用显卡：写的时候提交生图，生图等着；写完生图开始，提示词模型退出
res = {}
th = threading.Thread(target=lambda: res.update(r=chat({'preset': 'tts', 'messages': [{'role': 'user', 'content': '写一段 300 字的悬疑旁白'}], 'params': {'max_tokens': 600}})))
th.start(); time.sleep(4)
s, j, _ = req('/api/img/jobs', {'prompt': '一盏台灯', 'width': 512, 'height': 512, 'steps': 4})
time.sleep(2)
s, jj, _ = req('/api/img/jobs/' + j['id'])
check('写的时候生图在排队', jj['state'] == 'queued', jj.get('message'))
th.join()
for _ in range(240):
    s, jj, _ = req('/api/img/jobs/' + j['id'])
    if jj['state'] in ('done', 'error'):
        break
    time.sleep(1)
s, st, _ = req('/api/prompt/status')
check('写完以后生图完成、提示词模型让出显存', jj['state'] == 'done' and not st['running'], f"{jj['state']} {jj.get('error') or ''} running={st['running']}")
# 9 生图引擎开着的时候再写：生图引擎让开
t, r, e, sec, first = chat({'preset': 'img-zh', 'messages': [{'role': 'user', 'content': '风很大'}], 'params': {'max_tokens': 60}})
check('生图之后再写也正常', not e and t, e or f'用时 {sec:.0f} 秒')
s, v, _ = req('/api/vram')
check('显存面板里有提示词模型', any(x['id'] == 'prompt' for x in v.get('items', [])), [x['name'] for x in v.get('items', [])])
s, _, _ = req('/api/vram', {'id': 'prompt'})
s, st, _ = req('/api/prompt/status')
check('显存面板里能释放提示词模型', not st['running'])
print(f'\n通过 {len(OK)} 项，失败 {len(BAD)} 项' + (('：' + '、'.join(BAD)) if BAD else ''))
sys.exit(1 if BAD else 0)
