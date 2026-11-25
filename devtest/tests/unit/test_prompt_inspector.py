"""CPU-only checks: preview fidelity, untouched inputs, capture, and space isolation.

Run: python -I devtest/test_prompt_inspector.py
"""
import copy
import json
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))  # devtest/tests/unit → studio
import prompttrace
import promptgen
import videoedit
import videogen
import imagegen


class PromptInspectorTests(unittest.TestCase):
    def test_image_limits_keep_the_entire_original(self):
        raw = '  保留前半段蓝色外套。\n' + '原文' * 2500 + '  '
        trace = prompttrace.image_preview({'prompt': raw, 'negative': 'x' * 2100})
        self.assertEqual(trace['input'], raw)
        self.assertEqual(trace['stages'][0]['text'], raw.strip()[:4000])
        self.assertEqual(len(trace['stages'][0]['negative']), 2000)

    def test_image_detail_uses_the_same_fallback_as_inference(self):
        trace = prompttrace.image_preview({'prompt': 'a red jacket', 'detail': {'face': True, 'prompt': ''}})
        self.assertEqual(trace['stages'][1]['text'], 'a red jacket')

    def test_video_preview_matches_actual_workflow(self):
        user = '前半段保留蓝色外套，后半段换成红色外套。保留帽子。'
        # 2026-11-14：预览按 videoedit.parse 的规则推出做法（作者配方 / 换头做法），这里给 build 的也是 parse 之后的样子
        cases = [('outfit', None, {}), ('swap', 'ref', {}), ('swap', 'v11', {'recipe': 'cs11'}), ('motion', None, {'recipe': 'motion'}),
                 ('head', None, {'head_by': 'fs'})]
        for task, by, extra in cases:
            for tpl in (True, False):
                for ref in (True, False):
                    with self.subTest(task=task, by=by, extra=extra, tpl=tpl, ref=ref):
                        e = {'task': task, 'method': 'ref', 'swap_by': by, 'tpl': tpl, 'target': '', 'own': True,
                             'ref': ref, 'plang': 'zh', 'audio': 'keep', 'base': 'full', 'vfx': False, **extra}
                        j = {'edit': e, 'prompt': user}
                        trace = prompttrace.video_preview({**j, 'has_ref': ref})
                        wf = videoedit.build(j, 640, 480, 124, 'test.mp4', False, 'test.png' if ref else None)
                        self.assertEqual(trace['stages'][-1]['text'], wf['7']['inputs']['prompt'])
                        self.assertEqual(trace['input'], user)

    def test_complete_structured_input_stays_unchanged(self):
        text = 'subject_definitions:\n<Subject 1> wears a red jacket.\nsummary:\nKeep the first half unchanged.'
        trace = prompttrace.video_preview({'prompt': text, 'has_ref': False, 'edit': {'task': 'outfit', 'method': 'ref', 'tpl': True, 'own': True}})
        self.assertEqual(trace['stages'][-1]['text'], text)  # 第一段是“识别结果”的说明，最后一段是真正发给模型的

    def test_h3_reference_annotations_are_included(self):
        trace = prompttrace.video_preview({'model': 'h3', 'prompt': 'clouds', 'h3x': {'refs': [{}], 'rvids': [{'audio': 'lock'}], 'raudios': [{}]}})
        text = trace['stages'][0]['text']
        for tag in ('<Picture 1>', '<Video 1>', '<Audio 1>', '<Audio 2>'):
            self.assertIn(tag, text)

    def test_preview_never_starts_models_or_translates(self):
        import ptrans  # 2026-11-14：bernini 已删除；预览不能启动视频引擎，也不能去翻译
        with patch.object(videogen.Engine, 'ensure', side_effect=AssertionError('GPU')), patch.object(ptrans, 'translate', side_effect=AssertionError('translation')):
            trace = prompttrace.video_preview({'prompt': '衣服换成红色外套', 'has_ref': False, 'edit': {'task': 'outfit', 'method': 'ref', 'tpl': True}})
        self.assertEqual([s['label'] for s in trace['stages']][-2:], ['参考图改图', '视频生成'])

    def test_capture_records_actual_requests_without_mutating_them(self):
        job = {'prompt': 'draft', 'prompt_trace': prompttrace.new('  original\n')}
        req = {'prompt': 'actual', 'negative_prompt': 'blur', 'ref_images': ['PRIVATE_IMAGE_BYTES']}
        before = copy.deepcopy(req)
        prompttrace.capture_image(job, req)
        self.assertEqual(req, before)
        saved = prompttrace.snapshot(job)
        self.assertEqual(saved['input'], '  original\n')
        self.assertNotIn('PRIVATE_IMAGE_BYTES', json.dumps(saved))
        job['prompt_trace']['stages'][0]['text'] = 'later'
        self.assertEqual(saved['stages'][0]['text'], 'actual')

    def test_image_engine_boundary_records_the_submitted_text(self):
        job = {'prompt': 'draft', 'cancel': False, 'prompt_trace': prompttrace.new('original')}
        request = {'prompt': 'actual final text', 'negative_prompt': 'blur'}
        replies = [{'id': 'mock-job'}, {'status': 'completed', 'result': {'images': [{'b64_json': 'aW1hZ2U='}]}}]
        with patch.object(imagegen, '_http', side_effect=replies) as send, patch.object(imagegen.time, 'sleep'):
            result = imagegen._gen_wait(job, request)
        self.assertEqual(result, b'image')
        self.assertEqual(send.call_args_list[0].args[1], request)
        self.assertEqual(job['prompt_trace']['stages'][0]['text'], 'actual final text')

    def test_workflow_capture_includes_t8_and_text_encoders(self):
        wf = {'7': {'class_type': 'MiniMaxH3AudioConditioningT8', 'inputs': {'prompt': 'actual'}},
              'n': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'negative'}},
              'other': {'class_type': 'LoadImage', 'inputs': {'image': 'private.png'}}}
        before = copy.deepcopy(wf)
        job = {'prompt': 'draft'}
        prompttrace.capture_workflow(job, wf)
        self.assertEqual(wf, before)
        self.assertEqual([s['text'] for s in job['prompt_trace']['stages']], ['actual', 'negative'])

    def test_chat_preview_uses_exact_messages_and_redacts_images(self):
        rows = [{'role': 'user', 'content': 'describe', 'images': ['data:image/png;base64,PRIVATE']}]
        with patch.object(promptgen, 'vision', return_value=True):
            msgs = promptgen.build_messages(rows, 'system')
        trace = prompttrace.chat_preview(msgs, ' describe ')
        self.assertEqual(trace['stages'][0]['text'], 'system')
        self.assertNotIn('PRIVATE', json.dumps(trace))
        self.assertIn('1 张图片', trace['stages'][1]['text'])

    def test_chat_repeated_messages_preserve_order(self):
        rows = [{'role': 'user', 'content': 'again'}, {'role': 'assistant', 'content': 'ok'}, {'role': 'user', 'content': 'again'}]
        trace = prompttrace.chat_preview(promptgen.build_messages(rows, ''))
        self.assertEqual([s['text'] for s in trace['stages']], ['again', 'ok', 'again'])

    def test_saved_traces_stay_in_their_space(self):
        with tempfile.TemporaryDirectory() as root:
            normal, private = os.path.join(root, 'normal'), os.path.join(root, 'private')
            trace = prompttrace.new('test')
            key = prompttrace.save(normal, trace)
            self.assertEqual(prompttrace.load(normal, key), trace)
            self.assertIsNone(prompttrace.load(private, key))
            self.assertIsNone(prompttrace.load(normal, '../normal/' + key))

    def test_chat_stream_saves_trace_and_returns_a_small_history_id(self):
        import server
        raw = '  Keep the blue jacket.\n'
        body = {'system': 'test system', 'prompt_input': raw, 'messages': [{'role': 'user', 'content': raw.strip()}]}
        handler = object.__new__(server.Handler)
        handler.jbody = lambda: body
        handler.wfile = io.BytesIO()
        handler.connection = Mock()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()

        def generated(*args):
            yield 'text', 'mock reply'
            yield 'done', {'seconds': 0}

        with tempfile.TemporaryDirectory() as root, patch.object(server, 'space', return_value='n'), patch.object(server, 'PROMPT_DIR', root), \
                patch.object(promptgen, 'load_presets', return_value=[]), patch.object(promptgen, 'chat_stream', side_effect=generated):
            handler.prompt_api('POST', ['chat'])
            events = [json.loads(s[6:]) for s in handler.wfile.getvalue().decode().splitlines() if s.startswith('data: ')]
            key = next(e['v'] for e in events if e['type'] == 'prompt_trace')
            self.assertEqual(len(key), 32)
            saved = prompttrace.load(os.path.join(root, 'prompt-traces'), key)
            self.assertEqual(saved['input'], raw)
            self.assertEqual(saved['stages'][0]['text'], 'test system')
            self.assertTrue(any(e['type'] == 'text' for e in events))


if __name__ == '__main__':
    unittest.main(verbosity=2)
