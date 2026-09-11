import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import install

class InstallerTests(unittest.TestCase):
    def test_paths_and_plist_support_spaces_and_apple_silicon(self):
        home = Path('/Users/example user')
        p = install.make_plist(home, '/opt/homebrew/bin/python3',
                               '/Applications/Kaku.app/Contents/MacOS/kaku', '/tmp/claude')
        self.assertEqual(plistlib.loads(plistlib.dumps(p)), p)
        self.assertEqual(p['ProgramArguments'][0], '/opt/homebrew/bin/python3')
        self.assertIn('example user', p['ProgramArguments'][1])
        self.assertTrue(p['KeepAlive'])

    def test_install_upgrade_uninstall_preserves_records(self):
        with tempfile.TemporaryDirectory(prefix='kaku work ') as temp:
            home = Path(temp)
            root, app, launcher, plist = install.paths(home)
            fake_work = types.SimpleNamespace(executable=lambda n: '/tmp/' + n)
            with patch.object(Path, 'home', return_value=home), \
                 patch.object(sys, 'platform', 'darwin'), \
                 patch.object(sys, 'argv', ['install.py', '--no-start']), \
                 patch.object(install.importlib.machinery.SourceFileLoader, 'load_module', return_value=fake_work), \
                 patch.object(install.subprocess, 'run', return_value=types.SimpleNamespace(returncode=1)):
                install.main()
                records = root / 'tasks.json'
                records.write_text('{"test":"keep"}')
                install.main()
                self.assertTrue((app / 'watcher.py').exists())
                self.assertEqual(plistlib.loads(plist.read_bytes())['Label'], install.LABEL)
                self.assertIn(install.MARKER, launcher.read_text())
            # Execute the actual generated wrapper with spaces in its app path.
            result = subprocess.run([str(launcher), '--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with patch.object(Path, 'home', return_value=home), \
                 patch.object(sys, 'platform', 'darwin'), \
                 patch.object(sys, 'argv', ['install.py', '--uninstall']), \
                 patch.object(install.subprocess, 'run', return_value=types.SimpleNamespace(returncode=1)):
                install.main()
            self.assertFalse(launcher.exists())
            self.assertFalse(plist.exists())
            self.assertEqual(records.read_text(), '{"test":"keep"}')

    def test_refuses_unrelated_work_command(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            launcher = install.paths(home)[2]
            launcher.parent.mkdir(parents=True)
            launcher.write_text('#!/bin/sh\necho unrelated\n')
            with patch.object(Path, 'home', return_value=home), \
                 patch.object(sys, 'platform', 'darwin'), \
                 patch.object(sys, 'argv', ['install.py']):
                with self.assertRaises(ValueError):
                    install.main()
            self.assertIn('unrelated', launcher.read_text())

if __name__ == '__main__':
    unittest.main()
