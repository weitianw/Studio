"""Regression checks for private tasks, restart protection and video refresh."""
import os
import sys
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'studio'))  # devtest/tests/unit → studio
import server
import videogen
import imagegen


class PrivateTaskTests(unittest.TestCase):
    def test_restart_guard_counts_running_and_queued_private_videos(self):
        tasks = {key: {'id': key, 'space': 'v', 'state': state} for key, state in [('a', 'running'), ('b', 'queued'), ('c', 'done')]}
        with patch.object(server, 'jobs', {}), patch.object(imagegen, 'jobs', {}), patch.object(videogen, 'jobs', tasks), \
                patch.object(server.stt, 'stt_jobs', {}), patch.object(server.promptgen.Engine, 'busy', 0):
            self.assertEqual(server.busy_work(), ['2 个视频任务'])

    def test_restart_endpoint_refuses_active_private_video_without_force(self):
        handler = object.__new__(server.Handler)
        handler.remote = False
        handler.jbody = lambda: {}
        handler.send_json = Mock(side_effect=lambda data, *args, **kwargs: data)
        task = {'id': 'private', 'space': 'v', 'state': 'running'}
        with patch.object(server, 'jobs', {}), patch.object(imagegen, 'jobs', {}), patch.object(videogen, 'jobs', {'private': task}), \
                patch.object(server.stt, 'stt_jobs', {}), patch.object(server.promptgen.Engine, 'busy', 0), \
                patch.object(server.threading, 'Thread') as thread:
            # Exercise the routing branch used by the actual restart request.
            result = handler.dispatch('POST', ['api', 'restart'], {})
            self.assertEqual(result, {'busy': ['1 个视频任务']})
            thread.assert_not_called()

    def test_private_lock_does_not_cancel_or_forget_video(self):
        task = {'id': 'private', 'space': 'v', 'state': 'running', 'cancel': False, 'created': 1}
        handler = object.__new__(server.Handler)
        handler.headers = {'Cookie': 'vault=testtoken'}
        handler.send_json = Mock(side_effect=lambda data, *args, **kwargs: data)
        with patch.object(videogen, 'jobs', {'private': task}), patch.object(server, 'VTOKS', {'testtoken': {'remote': False, 'last': 1}}), \
                patch.object(server, 'clean_vtmp'):
            handler.vault_api('POST', ['lock'], {})
            self.assertIs(videogen.jobs['private'], task)
            self.assertEqual(task['state'], 'running')
            self.assertFalse(task['cancel'])
            self.assertEqual(videogen.list_jobs('n'), [])
            self.assertEqual(videogen.list_jobs('v')[0]['id'], 'private')

    def test_video_revision_changes_only_in_its_own_space(self):
        task = {'id': 'private', 'space': 'v', 'state': 'running'}
        with patch.object(server, 'jobs', {}), patch.object(imagegen, 'jobs', {}), patch.object(videogen, 'jobs', {'private': task}), \
                patch.object(server.stt, 'stt_jobs', {}), patch.object(server, '_mt', return_value=0):
            with patch.object(server, 'space', return_value='n'):
                normal_before = server.space_rev()['video']
            with patch.object(server, 'space', return_value='v'):
                private_before = server.space_rev()['video']
            task['state'] = 'done'
            with patch.object(server, 'space', return_value='n'):
                self.assertEqual(server.space_rev()['video'], normal_before)
            with patch.object(server, 'space', return_value='v'):
                self.assertNotEqual(server.space_rev()['video'], private_before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
