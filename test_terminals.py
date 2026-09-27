import json
import os
import shlex
import subprocess
import unittest
from unittest.mock import patch

import terminals
from watcher import Observer

class Adapters(unittest.TestCase):
    def test_wezterm_does_not_inherit_kaku_socket(self):
        with patch.dict(os.environ, {'WEZTERM_UNIX_SOCKET': '/tmp/kaku.sock', 'WEZTERM_PANE': '99'}), \
             patch.object(terminals, 'executable', return_value='/tmp/wezterm'), \
             patch.object(terminals.subprocess, 'check_output', return_value='[]') as call:
            self.assertEqual(terminals.Terminal('wezterm').panes(), [])
            argv = call.call_args.args[0]
            self.assertEqual(argv[:3], ['/tmp/wezterm', 'cli', '--no-auto-start'])
            self.assertNotIn('WEZTERM_UNIX_SOCKET', call.call_args.kwargs['env'])
            self.assertNotIn('WEZTERM_PANE', call.call_args.kwargs['env'])

    def test_iterm_titles_are_json_not_delimited(self):
        panes = [dict(pane_id='uuid', tty_name='/dev/ttys1', tab_title='中文\t需求\n第二行')]
        with patch.object(terminals, 'osascript', return_value=json.dumps(panes)):
            self.assertEqual(terminals.Terminal('iterm2').panes(), panes)

    def test_iterm_spawn_passes_values_as_argv(self):
        title = '需求 "\n$(touch /tmp/should-not-exist)'
        cwd = '/tmp/project with spaces'
        argv = ['/bin/zsh', '-lc', 'printf "%s" "$1"', 'work', title]
        with patch.object(terminals, 'gui_identity', return_value=('iterm',)), \
             patch.object(terminals, 'osascript', return_value='uuid') as call:
            terminals.Terminal('iterm2').spawn(cwd, argv, title)
            script, values = call.call_args.args
            self.assertNotIn(title, script)
            self.assertEqual(values[1], title)
            tokens = shlex.split(values[0])
            self.assertEqual(tokens[4], cwd)
            self.assertEqual(tokens[5:], argv)

    def test_wezterm_new_tab_in_target_window(self):
        backend = terminals.Terminal('wezterm')
        with patch.object(terminals, 'gui_identity', return_value=('wez',)), \
             patch.object(backend, 'panes', return_value=[{'window_id': 7}]), \
             patch.object(backend, 'cli', return_value='31') as call:
            backend.spawn('/tmp', ['/bin/zsh'], '需求')
            self.assertEqual(call.call_args_list[0].args,
                             ('spawn', '--window-id', '7', '--cwd', '/tmp', '--', '/bin/zsh'))
            self.assertEqual(call.call_args_list[1].args, ('set-tab-title', '--pane-id', '31', '需求'))

    def test_ghostty_lists_terminals_with_working_directory(self):
        panes = [dict(pane_id='surface-1', window_id='win-1', tab_title='需求',
                      working_directory='/tmp/app')]
        with patch.object(terminals, 'osascript', return_value=json.dumps(panes)) as call:
            self.assertEqual(terminals.Terminal('ghostty').panes(), panes)
            self.assertTrue(call.call_args.kwargs['javascript'])
            self.assertEqual(call.call_args.kwargs['terminal'], 'ghostty')

    def test_ghostty_spawn_passes_values_as_argv(self):
        title = '需求 "\n$(touch /tmp/should-not-exist)'
        cwd = '/tmp/project with spaces'
        argv = ['/bin/zsh', '-lc', 'printf "%s" "$1"', 'work', title]
        with patch.object(terminals, 'gui_identity', return_value=('ghostty',)), \
             patch.object(terminals, 'osascript', return_value='tab-uuid') as call:
            self.assertEqual(terminals.Terminal('ghostty').spawn(cwd, argv, title), 'tab-uuid')
            script, values = call.call_args.args
            self.assertNotIn(title, script)
            self.assertEqual(values[0], cwd)
            self.assertEqual(values[2], title)
            tokens = shlex.split(values[1])
            self.assertEqual(tokens[4], cwd)
            self.assertEqual(tokens[5:], argv)

    def test_iterm_denied_permission_is_actionable(self):
        result = subprocess.CompletedProcess([], 1, '', 'Not authorized (-1743)')
        with patch.object(terminals.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(ValueError, 'work save --terminal iterm2'):
                terminals.osascript('script')

    def test_explicit_choice_and_multiple_running(self):
        self.assertEqual(terminals.choose('wezterm'), 'wezterm')
        with patch.dict(os.environ, {'TERM_WORK_TERMINAL': 'auto'}), \
             patch.object(terminals, 'installed', return_value=True), \
             patch.object(terminals, 'gui_identity', return_value=('running',)):
            with self.assertRaisesRegex(ValueError, '--terminal'):
                terminals.choose()

    def test_terminal_disconnect_does_not_touch_others(self):
        data = {'legacy': {'state': 'active'}, 'wez': {'terminal': 'wezterm', 'state': 'active'},
                'iterm': {'terminal': 'iterm2', 'state': 'active'}}
        Observer('wezterm').disconnected(data)
        self.assertEqual(data['legacy']['state'], 'active')
        self.assertEqual(data['wez']['state'], 'uncertain')
        self.assertEqual(data['iterm']['state'], 'active')

    def test_ghostty_without_tty_matches_unique_cwd(self):
        data = {}
        pane = {'pane_id': 'surface-1', 'working_directory': '/tmp/app', 'tab_title': '需求'}
        session = {'tty': None, 'sessionId': '11111111-1111-4111-8111-111111111111', 'cwd': '/tmp/app'}
        Observer('ghostty').update(data, [pane], [session], ('gui',), '/tmp/claude', 0)
        self.assertEqual(len(data), 1)
        task = next(iter(data.values()))
        self.assertEqual(task['session'], session['sessionId'])
        self.assertEqual(task['pane_id'], 'surface-1')

    def test_ghostty_exec_surface_tracked_by_bound_pane_id(self):
        sid = '11111111-1111-4111-8111-111111111111'
        data = {'需求': dict(key='k', config='/tmp/claude', terminal='ghostty', pane_id='s1',
                            gui=['gui1'], session=sid, state='active')}
        sessions = [{'tty': None, 'sessionId': sid, 'cwd': '/tmp/app'}]
        observer = Observer('ghostty')
        observer.update(data, [{'pane_id': 's1', 'working_directory': '', 'tab_title': '需求'}],
                        sessions, ('gui1',), '/tmp/claude', 0)
        observer.update(data, [{'pane_id': 's1', 'working_directory': '', 'tab_title': '需求-最新'}],
                        sessions, ('gui1',), '/tmp/claude', 3)
        self.assertEqual(data['需求']['state'], 'active')
        self.assertEqual(data['需求']['tab_title'], '需求-最新')

    def test_ghostty_exec_surface_ignored_when_session_dead(self):
        data = {'需求': dict(key='k', config='/tmp/claude', terminal='ghostty', pane_id='s1',
                            gui=['gui1'], session='11111111-1111-4111-8111-111111111111', state='active')}
        pane = {'pane_id': 's1', 'working_directory': '', 'tab_title': '需求'}
        observer = Observer('ghostty')
        observer.update(data, [pane], [], ('gui1',), '/tmp/claude', 0)
        observer.update(data, [pane], [], ('gui1',), '/tmp/claude', 3)
        self.assertNotIn('last_seen', data['需求'])
        self.assertEqual(data['需求']['state'], 'active')

    def test_ghostty_ambiguous_cwd_kept(self):
        data = {}
        pane = {'pane_id': 'surface-1', 'working_directory': '/tmp/app', 'tab_title': '需求'}
        sessions = [{'tty': None, 'sessionId': '11111111-1111-4111-8111-111111111111', 'cwd': '/tmp/app'},
                    {'tty': None, 'sessionId': '22222222-2222-4222-8222-222222222222', 'cwd': '/tmp/app'}]
        Observer('ghostty').update(data, [pane], sessions, ('gui',), '/tmp/claude', 0)
        self.assertEqual(data, {})

    def test_same_pane_ids_across_terminals_are_independent(self):
        data = {}
        pane = {'pane_id': 1, 'tty_name': '/dev/ttys1', 'tab_title': 'work'}
        a, b = Observer('kaku'), Observer('wezterm')
        session = {'tty': '/dev/ttys1', 'sessionId': '11111111-1111-4111-8111-111111111111', 'cwd': '/tmp'}
        a.update(data, [pane], [session], ('gui',), '/tmp', 0)
        session = dict(session, sessionId='22222222-2222-4222-8222-222222222222')
        b.update(data, [pane], [session], ('gui',), '/tmp', 0)
        self.assertEqual(len(data), 2)
        self.assertEqual({v['terminal'] for v in data.values()}, {'kaku', 'wezterm'})
        b.disconnected(data)
        self.assertEqual(next(v for v in data.values() if v['terminal'] == 'kaku')['state'], 'active')

if __name__ == '__main__':
    unittest.main()
