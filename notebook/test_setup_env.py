import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import setup_env as setup


class SetupTests(unittest.TestCase):
    def test_typst_discovery_reuses_managed_binary_without_installing(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            binary = setup.typst_binary(home)
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'placeholder')
            with patch.dict(setup.os.environ, {'CLAUDE_NOTEBOOK_TYPST': ''}), patch.object(setup.shutil, 'which', return_value=None), patch.object(setup, 'typst_works', return_value=True), patch.object(setup.urllib.request, 'urlopen') as download:
                self.assertEqual(setup.find_typst(home), str(binary))
                self.assertEqual(setup.install_typst(home), str(binary))
                download.assert_not_called()

    def test_typst_lookup_respects_override_and_does_not_create_a_home(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'not-created'
            with patch.dict(setup.os.environ, {'CLAUDE_NOTEBOOK_TYPST': '/custom/typst'}), patch.object(setup, 'typst_works', return_value=True):
                self.assertEqual(setup.find_typst(home), '/custom/typst')
            with patch.dict(setup.os.environ, {'CLAUDE_NOTEBOOK_TYPST': ''}), patch.object(setup.shutil, 'which', return_value=None):
                self.assertIsNone(setup.find_typst(home))
            self.assertFalse(home.exists())

    def test_platforms_and_requirements_fingerprint(self):
        for system in ('Windows', 'Darwin', 'Linux'):
            for machine in ('AMD64', 'x86_64', 'arm64', 'aarch64'):
                asset, digest = setup.typst_asset(system, machine)
                self.assertEqual(len(digest), 64)
                self.assertTrue(asset.endswith('.zip' if system == 'Windows' else '.tar.xz'))
        with self.assertRaises(RuntimeError):
            setup.typst_asset('Plan9', 'mips')
        self.assertNotEqual(setup.environment_key('pandas>=2'), setup.environment_key('pandas>=3'))
        self.assertEqual(setup.environment_key('pandas>=2'), setup.environment_key('pandas>=2'))

    def test_reuse_avoids_pip_and_repair_preserves_old_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            envs = home / 'environments'
            old = envs / 'old'
            old.mkdir(parents=True)
            (old / 'user-package.txt').write_text('keep me')
            marker = envs / (setup.environment_key((setup.ROOT / 'requirements.txt').read_text()) + '.json')
            marker.write_text(json.dumps({'directory': 'old'}))
            with patch.object(setup, 'healthy', return_value=True), patch.object(setup.venv.EnvBuilder, 'create') as create, patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertEqual(setup.managed_python(home, home / 'setup.log'), setup.env_python(old))
                create.assert_not_called()
                run.assert_not_called()
                fresh = setup.managed_python(home, home / 'setup.log', repair=True)
                self.assertNotEqual(fresh, setup.env_python(old))
                self.assertTrue((old / 'user-package.txt').exists())
                self.assertEqual(json.loads(marker.read_text())['directory'], fresh.parent.parent.name)
                self.assertIn('--only-binary=:all:', run.call_args.args[0])

    def test_failed_install_keeps_old_pointer_and_retry_can_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            envs = home / 'environments'
            envs.mkdir()
            marker = envs / (setup.environment_key((setup.ROOT / 'requirements.txt').read_text()) + '.json')
            marker.write_text(json.dumps({'directory': '../../foreign'}))
            with patch.object(setup, 'healthy', return_value=True), patch.object(setup.venv.EnvBuilder, 'create'), patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaisesRegex(RuntimeError, 'installation'):
                    setup.managed_python(home, home / 'setup.log')
            self.assertEqual(json.loads(marker.read_text())['directory'], '../../foreign')
            self.assertFalse(any(p.is_dir() for p in envs.iterdir()))
            with patch.object(setup, 'healthy', return_value=True), patch.object(setup.venv.EnvBuilder, 'create'), patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                python = setup.managed_python(home, home / 'setup.log')
            self.assertEqual(python.parent.parent.parent, envs)

    def test_archive_paths_and_links_are_never_extracted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, dest = root / 'test.zip', root / 'typst'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('../../outside.txt', 'bad')
                bundle.writestr('release/typst', b'valid')
            setup.unpack_binary(archive, dest, 'release/typst')
            self.assertEqual(dest.read_bytes(), b'valid')
            self.assertEqual({p.name for p in root.iterdir()}, {'test.zip', 'typst'})
            archive = root / 'test.tar.xz'
            with tarfile.open(archive, 'w:xz') as bundle:
                entry = tarfile.TarInfo('release/typst')
                entry.type, entry.linkname = tarfile.SYMTYPE, '/bin/sh'
                bundle.addfile(entry)
            with self.assertRaises(ValueError):
                setup.unpack_binary(archive, dest, 'release/typst')

    def test_checksum_failure_never_extracts_or_runs_download(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(setup.shutil, 'which', return_value=None), patch.dict(setup.os.environ, {'CLAUDE_NOTEBOOK_TYPST': ''}), patch.object(setup.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad download')), patch.object(setup, 'unpack_binary') as unpack:
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    setup.install_typst(Path(temp))
                unpack.assert_not_called()

    def test_optional_typst_failure_keeps_python_ready_and_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            with patch.object(setup, 'managed_python', return_value=Path(sys.executable)), patch.object(setup, 'install_typst', side_effect=OSError('offline')):
                result = setup.setup(home, home / 'setup.log')
                self.assertEqual(result['python'], sys.executable)
                self.assertFalse(result['latex'])
                self.assertIn('/lab setup', result['warning'])
            with patch.object(setup, 'managed_python', return_value=Path(sys.executable)), patch.object(setup, 'install_typst', return_value='typst'), patch.object(setup, 'prepare_latex'):
                result = setup.setup(home, home / 'setup.log')
                self.assertTrue(result['latex'])
                self.assertIsNone(result['warning'])

    def test_competing_process_cannot_acquire_install_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            source = 'import sys; from pathlib import Path; from setup_env import install_lock;\nwith install_lock(Path(sys.argv[1]), timeout=0.1): print("unexpected")'
            with setup.install_lock(home):
                child = subprocess.run([sys.executable, '-c', source, str(home)], cwd=setup.ROOT,
                                       capture_output=True, text=True, timeout=10)
            self.assertNotEqual(child.returncode, 0)
            self.assertIn('Another setup', child.stderr)
            with setup.install_lock(home, timeout=0.1):
                pass


if __name__ == '__main__':
    unittest.main()
