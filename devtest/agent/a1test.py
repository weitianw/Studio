import os, sys, time, json
os.environ['TORCH_HOME'] = r'D:\AI-TTS\models\allin1'
sys.path.append(r'D:\AI-TTS\tools\allin1_lib'); sys.path.append(r'D:\AI-TTS\tools\beat_this_lib')
from allin1_infer import analyze
S = os.path.dirname(os.path.abspath(__file__))
t0 = time.time()
r = analyze(sys.argv[1], device='cpu', multiprocess=False, demix_dir=os.path.join(S, 'demix'), spec_dir=os.path.join(S, 'spec'), keep_byproducts=False)
print('took', round(time.time() - t0, 1))
print('bpm', r.bpm, 'beats', len(r.beats), 'downbeats', len(r.downbeats))
print(json.dumps([[round(s.start, 2), round(s.end, 2), s.label] for s in r.segments]))
