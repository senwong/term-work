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

from terminals import NAMES, Terminal, installed, gui_identity

class Observer:
    def __init__(self, terminal='kaku'):
        self.terminal = terminal
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
        # AppleScript-only terminals (Ghostty) expose no TTY, so fall back to a cwd that
        # is unique across both panes and live sessions; ambiguity keeps recovery records.
        cwd_panes = {}
        cwd_sessions = {}
        for pane in current.values():
            if pane.get('working_directory'):
                cwd_panes[pane['working_directory']] = cwd_panes.get(pane['working_directory'], 0) + 1
        for session in sessions:
            cwd_sessions[session['cwd']] = cwd_sessions.get(session['cwd'], 0) + 1
        for pane_id, pane in current.items():
            tty = pane.get('tty_name')
            if tty:
                hits = [s for s in sessions if s['tty'] == tty]
            else:
                cwd = pane.get('working_directory')
                hits = [s for s in sessions if s['cwd'] == cwd] \
                    if cwd and cwd_panes.get(cwd) == 1 and cwd_sessions.get(cwd) == 1 else []
            session = hits[0] if len(hits) == 1 else None
            sid = str(uuid.UUID(session['sessionId'])) if session else None
            same = [(n, t) for n, t in data.items() if t['session'] == sid]
            if not same and continuous:
                same = [(n, t) for n, t in data.items()
                        if t.get('terminal', 'kaku') == self.terminal and str(t.get('pane_id')) == pane_id
                        and t.get('gui') == list(identity) and t.get('state') != 'done']
                # Ghostty may report no cwd for exec'd surfaces; reuse the pane's bound
                # session when it is still live so close detection keeps working.
                if session is None and len(same) == 1:
                    session = next((s for s in sessions
                                    if str(uuid.UUID(s['sessionId'])) == same[0][1]['session']), None)
                    sid = str(uuid.UUID(session['sessionId'])) if session else None
            if session is None:
                continue
            if not same:
                same = [(n, t) for n, t in data.items() if t['session'] == sid]
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
            task.update(terminal=self.terminal, session=sid, cwd=session['cwd'], pane_id=pane_id,
                        gui=list(identity), tab_title=pane.get('tab_title', ''),
                        state='active', last_seen=time.time())
            self.pending.pop(task['key'], None)

        if continuous:
            removed = set(previous['panes']) - set(current)
            survivors = set(previous['panes']) & set(current)
            for task in data.values():
                if task.get('terminal', 'kaku') != self.terminal or task.get('state') in ('done', 'closed'):
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
            if task.get('terminal', 'kaku') == self.terminal and task.get('state', 'active') == 'active':
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
        observers = {name: Observer(name) for name in NAMES}
        retry_after = {}
        config = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))).resolve()
        print('Workspace watcher started: Kaku / WezTerm / iTerm2 / Ghostty; interval=3s', flush=True)
        while True:
            sessions = work.live_sessions(config)
            enabled = os.environ.get('TERM_WORK_TERMINALS', ','.join(NAMES)).split(',')
            for name, observer in observers.items():
                if name not in enabled or time.monotonic() < retry_after.get(name, 0):
                    continue
                try:
                    identity = gui_identity(name)
                    if not identity:
                        with work.database() as data:
                            observer.disconnected(data)
                        continue
                    panes = Terminal(name).panes()
                    if gui_identity(name) != identity:
                        raise ValueError('Terminal changed during sample')
                    with work.database() as data:
                        observer.update(data, panes, sessions, identity, config, time.monotonic())
                except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                    print(f'{name}: keeping recovery records: {exc}', flush=True)
                    with work.database() as data:
                        observer.disconnected(data)
                    retry_after[name] = time.monotonic() + 60
            time.sleep(INTERVAL)
