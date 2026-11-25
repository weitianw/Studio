"""放视频时叠加音轨（2026-11-18 用户：叠加以后“音效与声道”里没有视频那一轨、叠加的没声音，暂停再播放才有）。
真点击：播放页放一个测试视频 → 进“音乐”点一首的“叠加” → 看面板里有没有主音轨（视频）、叠加的那轨有没有在放、有没有声音（电平）。
扬声器那一路接到静音节点上，只量电平。用法：python t_layer_video.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from np_desk import EXE, B
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ok = bad = 0


def check(n, c, info=''):
    global ok, bad
    if c: ok += 1; print('  ' + n)
    else: bad += 1; print('✗ ' + n, info)


MUTE = """(() => { const oc = AudioNode.prototype.connect; AudioNode.prototype.connect = function (d, ...a) {
  if (d instanceof AudioDestinationNode) { if (!d.__m) { d.__m = d.context.createGain(); d.__m.gain.value = 0; oc.call(d.__m, d); } return oc.call(this, d.__m, ...a); }
  return oc.call(this, d, ...a); }; })()"""
STATE = """(() => { const L = Sound.layers; return { main: !qAudio.paused, mt: +qAudio.currentTime.toFixed(2), layers: L.map(l => [l.playing, +l.t.toFixed(2)]),
  meter: (Sound.meter() || []).map(v => +v.toFixed(3)), ctx: Sound._ctx()?.state || null, hooked: Sound.hooked(),
  rows: [...document.querySelectorAll('#spanel .sp-track')].map(t => t.innerText.replace(/\\s+/g, ' ').slice(0, 30)) }; })()"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE)
    pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.add_init_script(MUTE)
    pg.goto(B + '/'); pg.wait_for_timeout(2500); pg.add_style_tag(content='img,video{visibility:hidden!important}')
    pg.evaluate("go('play')"); pg.wait_for_timeout(1500)
    pg.locator('#play-src button', has_text='视频').first.click(); pg.wait_for_timeout(1500)
    pg.locator('#play-list .pl-row[data-i]', has_text='H264 720p').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.loop = true")
    check('视频在放', pg.evaluate("!qAudio.paused && /\\.mp4/.test(qAudio.currentSrc)"))
    pg.locator('#play-src button', has_text='音乐').first.click(); pg.wait_for_timeout(1500)
    row = pg.locator('#play-list .pl-row[data-i]', has_text='长音频').first
    row.hover(); row.locator('[data-layer]').click(); pg.wait_for_timeout(2000)
    pg.evaluate('Sound.meter()'); pg.wait_for_timeout(500)  # 电平表第一次调用时才接上，先接好再读
    s = pg.evaluate(STATE); print('叠加后 2.5 秒', s)
    check('面板里有主音轨（视频）和叠加的音轨', len(s['rows']) == 2 and 'H264' in s['rows'][0], s['rows'])
    check('叠加的音轨在放（不用暂停再播放）', s['layers'] and s['layers'][0][0] and s['layers'][0][1] > .5, s)
    check('有声音（电平 > 0）', s['meter'] and max(s['meter']) > .005, s)
    check('视频还在放', s['main'], s)
    # 拖叠加音轨的进度：拖到 60 秒，之后跟着主音轨往前走
    pg.evaluate("spOpen()"); pg.wait_for_timeout(400)
    pg.evaluate("(() => { const r = document.querySelector('#spanel [data-seek]'); r.value = 60; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); })()"); pg.wait_for_timeout(1200)
    lt = pg.evaluate("Sound.layers[0].t"); check(f'拖进度到 60 秒：叠加音轨在 60 秒附近接着放（{lt:.2f}）', 60 <= lt < 62.5, lt)
    lab = pg.evaluate("document.querySelector('#spanel .sp-st')?.textContent"); check(f'进度旁边显示时间（{lab}）', bool(lab) and '/' in lab)
    # 主音轨暂停：叠加的也停
    pg.evaluate("qAudio.pause()"); pg.wait_for_timeout(600)
    check('主音轨暂停：叠加的也停', not pg.evaluate("Sound.layers[0].playing"))
    pg.evaluate("Sound.clearLayers(); spClose()")
    # 别处放的视频（生视频、素材库……都是这样登记到底栏的）：叠加的跟着它走，面板里主音轨是它
    pg.evaluate("""(() => { const v = document.createElement('video'); v.id = 'tv-ext'; v.src = qAudio.currentSrc; v.loop = true; document.body.append(v);
      pbRegister(v, () => ({ title: '别处的测试视频' })); v.play(); })()"""); pg.wait_for_timeout(1500)
    check('底栏换成别处的视频、播放页的停了', pg.evaluate("PB.a.id === 'tv-ext' && qAudio.paused && !PB.a.paused"))
    row.hover(); row.locator('[data-layer]').click(); pg.wait_for_timeout(2500)
    s = pg.evaluate(STATE); print('别处视频 + 叠加', s)
    check('面板里主音轨是别处的那个视频', s['rows'] and '别处的测试视频' in s['rows'][0], s['rows'])
    check('叠加的音轨跟着别处的视频在放', s['layers'] and s['layers'][0][0], s)
    vt = pg.evaluate("document.querySelector('#tv-ext').currentTime"); check(f'和那个视频同步（视频 {vt:.2f}，叠加 {s["layers"][0][1] if s["layers"] else None}）', s['layers'] and abs(s['layers'][0][1] - vt) < 1.0)
    check('有声音（电平 > 0）', s['meter'] and max(s['meter']) > .005, s)
    # 键盘快进快退只动主音轨（2026-11-18 用户）：主音轨换成 2 分钟的长音频，叠加同一个文件，按 → 跳 5 秒
    pg.evaluate("Sound.clearLayers(); document.querySelector('#tv-ext')?.pause()")
    pg.locator('#play-list .pl-row[data-i]', has_text='长音频').first.dblclick(); pg.wait_for_timeout(1500)
    pg.evaluate("qAudio.currentTime = 20"); pg.wait_for_timeout(500)
    pg.evaluate("Sound.addLayer({ url: qAudio.currentSrc, title: '同一首' })"); pg.wait_for_timeout(1800)
    a0 = pg.evaluate("[qAudio.currentTime, Sound.layers[0].t]")
    pg.mouse.click(720, 40); pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(1200)
    a1 = pg.evaluate("[qAudio.currentTime, Sound.layers[0].t, Sound.layers[0].offset]"); print('按 → 前后', a0, a1)
    check(f'按 →：主音轨往前跳了约 5 秒（{a0[0]:.1f} → {a1[0]:.1f}）', 5.5 < a1[0] - a0[0] < 7.5)
    check(f'叠加的音轨没跟着跳（{a0[1]:.1f} → {a1[1]:.1f}，错开 {a1[2]}）', 0.5 < a1[1] - a0[1] < 2.5 and abs(a1[2] - 5) < .3)
    pg.keyboard.press('ArrowLeft'); pg.wait_for_timeout(1000)
    a2 = pg.evaluate("[qAudio.currentTime, Sound.layers[0].t, Sound.layers[0].offset]")
    check(f'按 ←：主音轨退回、叠加的照样往前走（错开 {a2[2]}）', a2[0] < a1[0] and a2[1] > a1[1] and abs(a2[2]) < .3, a2)
    check('没有页面报错', not errs, errs[:3])
    b.close()
print(f'通过 {ok}，失败 {bad}')
