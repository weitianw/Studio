"""测试 Studio 起来以后的快速自检：python -I probe.py <端口> → 视频状态、作品数、素材库在哪（只读）"""
import json, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
B = 'http://127.0.0.1:' + (sys.argv[1] if len(sys.argv) > 1 else '7897')
g = lambda p: json.loads(op.open(B + p, timeout=30).read().decode('utf-8'))
st = g('/api/video/status'); gal = g('/api/video/gallery'); m = g('/api/mats?dir=')
print(json.dumps({'port': B[-4:], 'video_ok': bool(st.get('models')), 'edit_vg': (st.get('edit') or {}).get('vg'), 'videos_in_gallery': len(gal), 'mats_root': m.get('root'),
                  'mats_dirs': len(m.get('dirs') or []), 'status': g('/api/status').get('engine') is not None}, ensure_ascii=False))
