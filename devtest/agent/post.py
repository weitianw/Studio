import json, sys, urllib.request
import os
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
sys.stdout.reconfigure(encoding='utf-8')
path, body, out = sys.argv[1], json.loads(open(sys.argv[2], encoding='utf-8').read()), sys.argv[3] if len(sys.argv) > 3 else None
m = 'POST' if body is not None else 'GET'
r = urllib.request.Request('http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897') + '' + path, json.dumps(body).encode() if body is not None else None, {'Content-Type': 'application/json'}, method=m)
try:
    d = urllib.request.urlopen(r, timeout=900).read().decode('utf-8')
except urllib.error.HTTPError as e:
    d = e.read().decode('utf-8')
if out:
    open(out, 'w', encoding='utf-8').write(d)
print(d[:1500])
