#!/usr/bin/env python3
"""Install a per-user macOS command and LaunchAgent. No sudo or dependencies."""
import argparse
import importlib.machinery
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys

LABEL = 'local.term-work.watcher'
SOURCE = Path(__file__).resolve().parent
MARKER = '# Installed by term-work'

def install_sources(source):
    files = {}
    for name in ('work', 'watcher.py', 'terminals.py', 'install.py', 'README.md', 'LICENSE', 'VERSION'):
        file = source / name
        # Homebrew relocates documentation from libexec to the formula prefix.
        if not file.is_file() and name in ('README.md', 'LICENSE'):
            file = source.parent / name
        if not file.is_file():
            raise ValueError(f'Installation source is incomplete: {name}')
        files[name] = file
    return files

def paths(home):
    root = home / '.local/share/term-work'
    return root, root / 'app', home / '.local/bin/work', home / 'Library/LaunchAgents' / (LABEL + '.plist')

def make_plist(home, python, kaku, claude, wezterm=None, enabled=None):
    root, app, _, _ = paths(home)
    search = [str(Path(p).parent) for p in (kaku, wezterm, claude, python) if p] + [
              str(home / '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin',
              '/usr/bin', '/bin', '/usr/sbin', '/sbin']
    result = dict(Label=LABEL, ProgramArguments=[python, str(app / 'work'), 'watch'],
                RunAtLoad=True, KeepAlive=True, ThrottleInterval=10, WorkingDirectory=str(app),
                EnvironmentVariables=dict(PATH=':'.join(dict.fromkeys(search)), PYTHONUNBUFFERED='1',
                    TERM_WORK_KAKU=kaku, TERM_WORK_CLAUDE=claude,
                    CLAUDE_CONFIG_DIR=str(Path(os.environ.get('CLAUDE_CONFIG_DIR', str(home / '.claude'))).expanduser().resolve())),
                StandardOutPath=str(root / 'watcher.log'), StandardErrorPath=str(root / 'watcher.error.log'))
    env = result['EnvironmentVariables']
    if not kaku:
        env.pop('TERM_WORK_KAKU')
    if wezterm:
        env['TERM_WORK_WEZTERM'] = wezterm
    env['TERM_WORK_TERMINALS'] = ','.join(enabled or ['kaku'])
    return result

def owned_launcher(path):
    if path.is_symlink():
        # Allow upgrading this project's earlier symlink installation.
        return path.resolve() in (SOURCE / 'work', paths(Path.home())[1] / 'work')
    return path.is_file() and MARKER in path.read_text()

def main():
    parser = argparse.ArgumentParser(description='Install Term Work for the current macOS user')
    from terminals import NAMES, installed
    parser.add_argument('--terminal', choices=('auto',) + NAMES, default='auto',
                        help='auto monitors all installed supported terminals')
    parser.add_argument('--uninstall', action='store_true', help='Remove command/service; keep session records')
    parser.add_argument('--no-start', action='store_true', help='Install without starting service now')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise ValueError('This installer requires macOS.')
    home = Path.home()
    root, app, launcher, plist = paths(home)
    if (launcher.exists() or launcher.is_symlink()) and not owned_launcher(launcher):
        raise ValueError(f'{launcher} already exists and is not owned by this installer.')
    if plist.exists() and plistlib.loads(plist.read_bytes()).get('Label') != LABEL:
        raise ValueError(f'Refusing to overwrite unrelated service: {plist}')
    if not args.uninstall:
        sources = install_sources(SOURCE)
        work = importlib.machinery.SourceFileLoader('term_work_install', str(SOURCE / 'work')).load_module()
        enabled = [n for n in NAMES if installed(n)] if args.terminal == 'auto' else [args.terminal]
        if not enabled:
            raise ValueError('Install Kaku, WezTerm, iTerm2 or Ghostty first.')
        if 'iterm2' in enabled and not installed('iterm2'):
            raise ValueError('Install iTerm2 in /Applications or ~/Applications first.')
        kaku = work.executable('kaku') if 'kaku' in enabled else None
        wezterm = work.executable('wezterm') if 'wezterm' in enabled else None
        claude = work.executable('claude')
        config = make_plist(home, sys.executable, kaku, claude, wezterm, enabled)
    target = f'gui/{os.getuid()}'
    # Check before unloading so permission/errors never silently leave two services.
    loaded = subprocess.run(['launchctl', 'print', target + '/' + LABEL], capture_output=True).returncode == 0
    if loaded:
        subprocess.run(['launchctl', 'bootout', target + '/' + LABEL], check=True)
    if args.uninstall:
        launcher.unlink(missing_ok=True)
        plist.unlink(missing_ok=True)
        print(f'Command and service removed. Session records and installed code retained in {root}')
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    app.mkdir(parents=True, exist_ok=True)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    for filename, source in sources.items():
        dest = app / filename
        if source.resolve() != dest.resolve():
            shutil.copy2(source, dest)
    if launcher.is_symlink():
        launcher.unlink()
    launcher.write_text('#!/bin/sh\n' + MARKER + '\nexec ' +
                        shlex.join([sys.executable, str(app / 'work')]) + ' "$@"\n')
    launcher.chmod(0o755)
    plist.write_bytes(plistlib.dumps(config))
    if not args.no_start:
        subprocess.run(['launchctl', 'bootstrap', target, str(plist)], check=True)
    print(f'Installed: {launcher}\nService: {plist}')
    print('Add ~/.local/bin to PATH if needed: export PATH="$HOME/.local/bin:$PATH"')
    print('Open your terminal, then run: work list; work restore --dry-run')
    if 'iterm2' in enabled:
        print('For iTerm2, run work save --terminal iterm2 in the foreground and allow macOS Automation if prompted.')
    if 'ghostty' in enabled:
        print('For Ghostty, run work save --terminal ghostty in the foreground and allow macOS Automation if prompted.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'Install failed: {exc}')
