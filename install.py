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

LABEL = 'local.kaku-work.watcher'
SOURCE = Path(__file__).resolve().parent
MARKER = '# Installed by kaku-work'

def install_sources(source):
    files = {}
    for name in ('work', 'watcher.py', 'install.py', 'README.md', 'LICENSE', 'VERSION'):
        file = source / name
        # Homebrew relocates documentation from libexec to the formula prefix.
        if not file.is_file() and name in ('README.md', 'LICENSE'):
            file = source.parent / name
        if not file.is_file():
            raise ValueError(f'Installation source is incomplete: {name}')
        files[name] = file
    return files

def paths(home):
    root = home / '.local/share/kaku-work'
    return root, root / 'app', home / '.local/bin/work', home / 'Library/LaunchAgents' / (LABEL + '.plist')

def make_plist(home, python, kaku, claude):
    root, app, _, _ = paths(home)
    search = [str(Path(kaku).parent), str(Path(claude).parent), str(Path(python).parent),
              str(home / '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin',
              '/usr/bin', '/bin', '/usr/sbin', '/sbin']
    return dict(Label=LABEL, ProgramArguments=[python, str(app / 'work'), 'watch'],
                RunAtLoad=True, KeepAlive=True, ThrottleInterval=10, WorkingDirectory=str(app),
                EnvironmentVariables=dict(PATH=':'.join(dict.fromkeys(search)), PYTHONUNBUFFERED='1',
                    KAKU_WORK_KAKU=kaku, KAKU_WORK_CLAUDE=claude,
                    CLAUDE_CONFIG_DIR=str(Path(os.environ.get('CLAUDE_CONFIG_DIR', str(home / '.claude'))).expanduser().resolve())),
                StandardOutPath=str(root / 'watcher.log'), StandardErrorPath=str(root / 'watcher.error.log'))

def owned_launcher(path):
    if path.is_symlink():
        # Allow upgrading this project's earlier symlink installation.
        return path.resolve() in (SOURCE / 'work', paths(Path.home())[1] / 'work')
    return path.is_file() and MARKER in path.read_text()

def main():
    parser = argparse.ArgumentParser(description='Install Kaku Work for the current macOS user')
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
        work = importlib.machinery.SourceFileLoader('kaku_work_install', str(SOURCE / 'work')).load_module()
        kaku, claude = work.executable('kaku'), work.executable('claude')
        config = make_plist(home, sys.executable, kaku, claude)
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
    print('Open Kaku, then run: work list; work restore --dry-run')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'Install failed: {exc}')
