"""Conservative polling: only infer an individual close with uninterrupted evidence."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

INTERVAL = 3
GRACE = 15

def gui_identity():
    rows = subprocess.check_output(['ps', '-axo', 'pid=,lstart=,comm='],
                                   text=True, timeout=10)
    return tuple(sorted(row.strip() for row in rows.splitlines()
                        if row.strip().endswith('/kaku-gui')))

class Observer:
    def __init__(self):
        self.previous = None
        self.pending = {}

    def update(self, data, panes, sessions, identity, config, now):
        current = {str(p['pane_id']): p for p in panes}
        previous = self.previous
        continuous = (previous is not None and identity and identity == previous['identity']
                      and 0 <= now - previous['time'] <= INTERVAL * 3)
        if not continuous:
            self.pending.clear()
        # Match using validated live process TTY; never infer session IDs from titles.
        for pane_id, pane in current.items():
            hits = [s for s in sessions if s['tty'] == pane.get('tty_name')]
            if len(hits) != 1:
                continue
            session = hits[0]
            sid = str(uuid.UUID(session['sessionId']))
            same = [(n, t) for n, t in data.items() if t['session'] == sid]
            if not same and continuous:
                same = [(n, t) for n, t in data.items()
                        if t.get('pane_id') == pane_id and t.get('gui') == list(identity)
                        and t.get('state') != 'done']
            if same:
                name, task = same[0]
                if task.get('state') == 'done':
                    continue
            else:
                name = pane.get('tab_title') or session.get('name') or sid[:8]
                if name in data:
                    name += '-' + sid[:8]
                task = dict(key=str(uuid.uuid4()), config=str(config), tracked=True)
                data[name] = task
            # Keep the command name stable; store the latest visible title separately.
            task.update(session=sid, cwd=session['cwd'], pane_id=pane_id,
                        gui=list(identity), tab_title=pane.get('tab_title', ''),
                        state='active', last_seen=time.time())
            self.pending.pop(task['key'], None)

        if continuous:
            removed = set(previous['panes']) - set(current)
            survivors = set(previous['panes']) & set(current)
            for task in data.values():
                if task.get('state') in ('done', 'closed'):
                    continue
                pane_id = task.get('pane_id')
                if task.get('gui') != list(identity) or pane_id not in removed:
                    continue
                task['state'] = 'uncertain'
                # Multiple disappearances or last pane: ambiguous, retain recovery.
                if len(removed) == 1 and survivors:
                    self.pending[task['key']] = (now, survivors)
            for task in data.values():
                pending = self.pending.get(task['key'])
                if not pending:
                    continue
                started, survivors = pending
                if not survivors.intersection(current):
                    self.pending.pop(task['key'], None)
                elif now - started >= GRACE:
                    if task.get('state') == 'uncertain':
                        task['state'] = 'closed'
                    self.pending.pop(task['key'], None)
        self.previous = dict(panes=current, identity=identity, time=now)

    def disconnected(self, data):
        for task in data.values():
            if task.get('state', 'active') == 'active':
                task['state'] = 'uncertain'
        self.previous = None
        self.pending.clear()

def watch(work):
    work.ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (work.ROOT / 'watch.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('监听器已经运行。')
        observer = Observer()
        config = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))).resolve()
        print('Kaku work watcher started; interval=3s, close grace=15s', flush=True)
        while True:
            try:
                identity = gui_identity()
                if not identity:
                    with work.database() as data:
                        observer.disconnected(data)
                else:
                    panes = json.loads(work.cli('list', '--format', 'json'))
                    sessions = work.live_sessions(config)
                    # Reject samples that straddle GUI exit/restart.
                    if gui_identity() != identity:
                        raise ValueError('Kaku changed during sample')
                    with work.database() as data:
                        observer.update(data, panes, sessions, identity, config, time.monotonic())
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                print(f'Sample unavailable; keeping recovery records: {exc}', flush=True)
                with work.database() as data:
                    observer.disconnected(data)
            time.sleep(INTERVAL)
