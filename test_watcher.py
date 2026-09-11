import unittest
from watcher import Observer

SID = '11111111-1111-4111-8111-111111111111'
def pane(n):
    return dict(pane_id=n, tty_name=f'/dev/ttys{n}', tab_title=f'task{n}')

class Rules(unittest.TestCase):
    def setUp(self):
        self.o = Observer()
        self.data = {}
        self.sessions = [dict(tty='/dev/ttys1', sessionId=SID, cwd='/tmp')]
        self.sample([1, 2], 0)

    def sample(self, ids, now, identity=('gui1',)):
        self.o.update(self.data, [pane(i) for i in ids], self.sessions,
                      identity, '/tmp/claude', now)

    def state(self):
        return self.data['task1']['state']

    def test_single_close_has_grace(self):
        self.sample([2], 3)
        self.assertEqual(self.state(), 'uncertain')
        for t in range(6, 19, 3): self.sample([2], t)
        self.assertEqual(self.state(), 'closed')

    def test_whole_app_exit_during_grace(self):
        self.sample([2], 3)
        self.o.disconnected(self.data)
        self.sample([2], 30)
        self.assertEqual(self.state(), 'uncertain')

    def test_multiple_close_kept(self):
        self.sample([], 3)
        self.assertEqual(self.state(), 'uncertain')

    def test_gui_restart_and_reused_ids(self):
        self.sessions = []
        self.sample([2], 3, ('gui2',))
        self.assertNotEqual(self.state(), 'closed')

    def test_sleep_or_polling_gap_kept(self):
        self.sample([2], 3)
        self.sample([2], 100)
        self.assertEqual(self.state(), 'uncertain')

    def test_done_not_rediscovered(self):
        self.data['task1']['state'] = 'done'
        self.sample([1, 2], 3)
        self.assertEqual(self.state(), 'done')

    def test_clear_updates_session_in_same_pane(self):
        self.sessions[0]['sessionId'] = '22222222-2222-4222-8222-222222222222'
        self.sample([1, 2], 3)
        self.assertEqual(len(self.data), 1)
        self.assertEqual(self.data['task1']['session'], self.sessions[0]['sessionId'])

if __name__ == '__main__':
    unittest.main()
