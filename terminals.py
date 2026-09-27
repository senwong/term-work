"""Terminal adapters. iTerm2 and Ghostty use macOS scripting; no third-party Python modules."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

NAMES = ('kaku', 'wezterm', 'iterm2', 'ghostty')
APP_NAMES = {'kaku': 'Kaku.app', 'wezterm': 'WezTerm.app', 'iterm2': 'iTerm.app', 'ghostty': 'Ghostty.app'}
PROCESS_NAMES = {'kaku': ('kaku-gui',), 'wezterm': ('wezterm-gui',), 'iterm2': ('iTerm2', 'iTerm'),
                 'ghostty': ('ghostty',)}
# Ghostty's CLI cannot open windows on macOS and exposes no pane list; AppleScript
# is the only supported scripting surface. Its terminal object has no TTY property,
# so panes() also reports `working_directory` for the watcher's cwd fallback.
APPLE_SCRIPTED = {'iterm2': 'iTerm2', 'ghostty': 'Ghostty'}


def executable(name):
    override = os.environ.get('TERM_WORK_' + name.upper())
    candidates = [override, shutil.which(name)]
    if name == 'kaku':
        candidates.append(str(Path.home() / '.config/kaku/zsh/bin/kaku'))
    if name in ('kaku', 'wezterm', 'ghostty'):
        for directory in (Path('/Applications'), Path.home() / 'Applications'):
            candidates.append(str(directory / APP_NAMES[name] / 'Contents/MacOS' / name))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise ValueError(f'找不到 {name}；请安装，或设置 TERM_WORK_{name.upper()}。')


def installed(name):
    if name == 'iterm2':
        return any((p / APP_NAMES[name]).is_dir() for p in (Path('/Applications'), Path.home() / 'Applications'))
    try:
        executable(name)
        return True
    except ValueError:
        return False


def gui_identity(name):
    rows = subprocess.check_output(['ps', '-axo', 'pid=,lstart=,comm='], text=True, timeout=10)
    return tuple(sorted(row.strip() for row in rows.splitlines()
                        if any(row.strip().endswith('/' + n) for n in PROCESS_NAMES[name])))


def choose(requested=None):
    requested = requested or os.environ.get('TERM_WORK_TERMINAL')
    if requested and requested != 'auto':
        if requested not in NAMES:
            raise ValueError('终端必须是 ' + '、'.join(NAMES) + '。')
        return requested
    available = [n for n in NAMES if installed(n)]
    running = [n for n in available if gui_identity(n)]
    if len(running) == 1:
        return running[0]
    if not running and len(available) == 1:
        return available[0]
    raise ValueError('请用 --terminal ' + '|'.join(NAMES) + ' 指定终端。')


# JSON preserves tabs, newlines and Unicode in session titles without delimiter guessing.
ITERM_LIST = '''function run() {
    const app = Application('com.googlecode.iterm2');
    if (!app.running()) throw new Error('iTerm2 is not running');
    const result = [];
    app.windows().forEach(function(w) {
        w.tabs().forEach(function(t) {
            t.sessions().forEach(function(s) {
                result.push({pane_id: s.id(), tty_name: s.tty(),
                             tab_title: s.name(), window_id: w.id()});
            });
        });
    });
    return JSON.stringify(result);
}'''

# User values are argv, never interpolated into AppleScript source or an existing shell.
ITERM_SPAWN = '''on run argv
    set launchCommand to item 1 of argv
    set taskName to item 2 of argv
    tell application id "com.googlecode.iterm2"
        if not running then error "Please open iTerm2 first"
        if (count of windows) is 0 then
            set newWindow to (create window with default profile command launchCommand)
            set targetSession to current session of newWindow
        else
            tell current window
                set newTab to (create tab with default profile command launchCommand)
                set targetSession to current session of newTab
            end tell
        end if
        set name of targetSession to taskName
        return id of targetSession
    end tell
end run'''


# Ghostty surfaces expose id/title/working directory but no TTY; the watcher joins
# by cwd instead. Tab ids are stable while the tab is open, so they serve as pane_id.
GHOSTTY_LIST = '''function run() {
    const app = Application('com.mitchellh.ghostty');
    if (!app.running()) throw new Error('Ghostty is not running');
    const result = [];
    app.windows().forEach(function(w) {
        w.tabs().forEach(function(t) {
            t.terminals().forEach(function(s) {
                result.push({pane_id: s.id(), window_id: w.id(), tab_title: t.name(),
                             working_directory: s.workingDirectory()});
            });
        });
    });
    return JSON.stringify(result);
}'''

# Values arrive as argv; the shell command string is quoted with shlex, never interpolated raw.
# Ghostty 1.3 raises -1708 ("Message not understood") from `new tab` even though the tab is
# created, so the id is recovered by diffing surfaces instead of trusting the return value.
GHOSTTY_SPAWN = '''function run(argv) {
    const app = Application('com.mitchellh.ghostty');
    if (!app.running()) throw new Error('Ghostty is not running');
    function surfaces() {
        const found = [];
        app.windows().forEach(function(w) {
            w.tabs().forEach(function(t) {
                t.terminals().forEach(function(s) { found.push({id: s.id(), terminal: s}); });
            });
        });
        return found;
    }
    const before = surfaces().map(function(s) { return s.id; });
    const config = app.newSurfaceConfiguration({from: {initialWorkingDirectory: argv[0], command: argv[1]}});
    try { app.newTab({withConfiguration: config}); } catch (error) {}
    let created = null;
    for (let attempt = 0; attempt < 20 && created === null; attempt++) {
        surfaces().forEach(function(s) { if (before.indexOf(s.id) < 0) created = s; });
        if (created === null) delay(0.05);
    }
    if (created === null) throw new Error('Ghostty did not open a new tab');
    try { app.performAction('set_tab_title:' + argv[2], {on: created.terminal}); } catch (error) {}
    return created.id;
}'''


def osascript(script, arguments=(), javascript=False, terminal='iterm2'):
    argv = ['/usr/bin/osascript']
    if javascript:
        argv += ['-l', 'JavaScript']
    result = subprocess.run(argv + ['-'] + list(arguments), input=script, text=True,
                            capture_output=True, timeout=20)
    if result.returncode:
        detail = result.stderr.strip()
        label = APPLE_SCRIPTED[terminal]
        if '-1743' in detail or 'not authorized' in detail.lower():
            raise ValueError(f'{label} 自动化未获授权。请在前台执行 work save --terminal {terminal}，'
                             f'并在 macOS 隐私与安全性 → 自动化中允许控制 {label}。')
        raise ValueError(f'{label} scripting failed: ' + detail)
    return result.stdout.strip()


class Terminal:
    def __init__(self, name):
        if name not in NAMES:
            raise ValueError('Unknown terminal: ' + name)
        self.name = name

    def cli(self, *args):
        # Kaku and WezTerm share env names. Never let a parent terminal's socket
        # or pane ID route a cross-terminal request to the wrong GUI.
        env = {k: v for k, v in os.environ.items()
               if k not in ('WEZTERM_UNIX_SOCKET', 'WEZTERM_PANE', 'WEZTERM_EXECUTABLE', 'WEZTERM_EXECUTABLE_DIR')}
        return subprocess.check_output([executable(self.name), 'cli', '--no-auto-start', *args],
                                       text=True, timeout=10, env=env).strip()

    def panes(self):
        if self.name == 'iterm2':
            return json.loads(osascript(ITERM_LIST, javascript=True, terminal='iterm2'))
        if self.name == 'ghostty':
            return json.loads(osascript(GHOSTTY_LIST, javascript=True, terminal='ghostty'))
        return json.loads(self.cli('list', '--format', 'json'))

    def spawn(self, cwd, argv, title):
        if not gui_identity(self.name):
            raise ValueError('请先打开 ' + self.name + '。')
        if self.name in APPLE_SCRIPTED:
            # create-tab runs a fresh command, never writes text into an existing pane.
            command = shlex.join(['/bin/zsh', '-lc', 'cd -- "$1" && shift && exec "$@"',
                                  'work', cwd, *argv])
            if self.name == 'iterm2':
                return osascript(ITERM_SPAWN, [command, title], terminal='iterm2')
            return osascript(GHOSTTY_SPAWN, [cwd, command, title], javascript=True, terminal='ghostty')
        panes = self.panes()
        window = ['--window-id', str(panes[0]['window_id'])] if panes else ['--new-window']
        pane = self.cli('spawn', *window, '--cwd', cwd, '--', *argv)
        self.cli('set-tab-title', '--pane-id', pane, title)
        return pane
