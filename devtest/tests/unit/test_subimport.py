"""载入字幕 / 歌词文件（2026-11-17）：LRC / SRT / VTT / ASS 解析、编码、出错提示。合成的字幕文本。"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))
import subimport as si


def test_lrc_multi_tags_offset_and_word_tags():
    t = '[ti:测试]\n[offset:500]\n[00:01.00][00:10.50]副歌一句\n[00:05.20]<00:05.20>逐<00:05.60>字\n[00:20.000]\n'
    s = si.parse('a.lrc', t.encode('utf-8'))
    assert [(x['s'], x['text']) for x in s] == [(0.5, '副歌一句'), (4.7, '逐字'), (10.0, '副歌一句')]
    assert s[0]['e'] == 4.7 and s[-1]['e'] == 14.0  # 结束 = 下一句开始；最后一句 +4 秒


def test_srt_and_vtt():
    srt = '1\n00:00:01,000 --> 00:00:02,500\n第一句\n第二行\n\n2\n00:00:03,000 --> 00:00:04,000\n<i>第二句</i>\n'
    assert si.parse('b.srt', srt.encode('utf-8')) == [{'s': 1.0, 'e': 2.5, 'text': '第一句 第二行'}, {'s': 3.0, 'e': 4.0, 'text': '第二句'}]
    vtt = 'WEBVTT\n\nc1\n00:01.000 --> 00:02.000 align:start\n你好\n\n01:00:00.500 --> 01:00:01.000\n再见'
    assert si.parse('c.vtt', vtt.encode('utf-8')) == [{'s': 1.0, 'e': 2.0, 'text': '你好'}, {'s': 3600.5, 'e': 3601.0, 'text': '再见'}]


def test_ass():
    t = '[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.50,0:00:03.00,Default,,0,0,0,,{\\an8}第一行\\N第二行, 带逗号\n'
    assert si.parse('d.ass', t.encode('utf-8')) == [{'s': 1.5, 'e': 3.0, 'text': '第一行 第二行, 带逗号'}]


def test_encodings_and_errors():
    t = '[00:01.00]中文歌词'
    assert si.parse('x.lrc', t.encode('gb18030'))[0]['text'] == '中文歌词'
    assert si.parse('x.lrc', t.encode('utf-16'))[0]['text'] == '中文歌词'
    assert si.parse('x.lrc', b'\xef\xbb\xbf' + t.encode('utf-8'))[0]['text'] == '中文歌词'
    with pytest.raises(ValueError):
        si.parse('x.txt', '只是普通文字，没有时间'.encode('utf-8'))
    with pytest.raises(ValueError):
        si.parse('x.lrc', b'0' * (si.MAX_BYTES + 1))


# ---------- QQ 音乐 QRC / 酷狗 KRC（2026-11-18；解密移植自 LDDC，见 studio/lyricdec.py） ----------
import zlib
import lyricdec

QRC_XML = ('<?xml version="1.0" encoding="utf-8"?><QrcInfos><LyricInfo LyricCount="1"><Lyric_1 LyricType="1" LyricContent="[ti:测试]\n'
           '[1000,2000]你(1000,500)好(1500,500)世(2000,500)界(2500,500)\n[4000,1500]再(4000,700)见(4700,800)\n[6000,10](6000,10)\n"/></LyricInfo></QrcInfos>')


def test_qrc_local_encrypted_roundtrip():
    raw = lyricdec.qrc_encrypt_local(QRC_XML)
    assert raw.startswith(lyricdec.QRC_MAGIC)
    assert lyricdec.qrc_decrypt(raw) == QRC_XML
    assert si.parse('歌.qrc', raw) == [{'s': 1.0, 'e': 3.0, 'text': '你好世界'}, {'s': 4.0, 'e': 5.5, 'text': '再见'}]


def test_qrc_hex_from_api_and_plain_xml():
    z = zlib.compress(QRC_XML.encode('utf-8')); z += bytes(-len(z) % 8)
    hexs = lyricdec._des3(z, lyricdec.ENCRYPT).hex().upper().encode()
    assert si.parse('歌.qrc', hexs)[0]['text'] == '你好世界'
    assert si.parse('歌.qrc', QRC_XML.encode('utf-8'))[1] == {'s': 4.0, 'e': 5.5, 'text': '再见'}


def test_krc():
    text = '\ufeff[ar:测试]\n[1000,2000]<0,500,0>你<500,500,0>好\n[3500,1000]<0,1000,0>呀\n'
    z = zlib.compress(text.encode('utf-8'))
    raw = b'krc1' + bytes(x ^ lyricdec.KRC_KEY[i % len(lyricdec.KRC_KEY)] for i, x in enumerate(z))
    assert si.parse('歌.krc', raw) == [{'s': 1.0, 'e': 3.0, 'text': '你好'}, {'s': 3.5, 'e': 4.5, 'text': '呀'}]


def test_qrc_bad_file():
    with pytest.raises(ValueError):
        si.parse('坏.qrc', b'not a qrc file at all')
