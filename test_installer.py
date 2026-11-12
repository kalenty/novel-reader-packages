import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name('install.sh').resolve()

class InstallerTest(unittest.TestCase):
    def bash(self, body):
        return subprocess.run(['bash', '-c', 'source "$1"; '+body, 'test', str(SCRIPT)], capture_output=True, text=True)

    def test_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)

    def test_platform_rejects_non_termux(self):
        self.assertNotEqual(self.bash('PREFIX=/invalid; nr_platform').returncode, 0)

    def test_wrong_key_and_extra_certificate_rejected(self):
        for info in ['pub:::::::::\nfpr:::::::::WRONG:', 'pub:::::::::\nfpr:::::::::4A5257DA36C1DD201DD5725A7D02DF8EE817027D:\npub:::::::::']:
            result = self.bash("gpg() { printf '%s\n' '"+info+"'; }; nr_key unused")
            self.assertNotEqual(result.returncode, 0)

    def test_expected_key(self):
        result = self.bash("gpg() { printf 'pub:::::::::\\nfpr:::::::::4A5257DA36C1DD201DD5725A7D02DF8EE817027D:\\n'; }; nr_key unused")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_backup_rotation_and_data_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            data, state = root/'data', root/'state'
            data.mkdir(); state.mkdir()
            book = data/'library.db'
            for value in ['first', 'second', 'third']:
                book.write_text(value)
                result = self.bash(f'nr_backup "{data}" "{state}"')
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(book.read_text(), 'third')
            self.assertEqual(sorted(p.name for p in state.iterdir()), ['backup.previous.tar', 'backup.tar'])
            for name, content in [('backup.tar','third'), ('backup.previous.tar','second')]:
                result = subprocess.run(['tar', '-xOf', str(state/name), './library.db'], capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout, content)

    def test_install_and_repeat_and_network_failure(self):
        for mode in ['fresh', 'current', 'network-failure']:
            with tempfile.TemporaryDirectory() as root:
                body = r''' 
PREFIX="ROOT/prefix"; HOME="ROOT/home"; TMPDIR="ROOT/tmp"
mkdir -p "$PREFIX" "$HOME" "$TMPDIR"
nr_platform() { :; }
realpath() { printf '%s\n' "${@: -1}"; }
pkg() { :; }; flock() { :; }
curl() { while (($#)); do if [[ $1 == -o ]]; then shift; touch "$1"; fi; shift; done; }
nr_key() { :; }
apt-get() { echo "apt:$*" >> "$HOME/events"; [[ MODE != network-failure ]]; }
apt-cache() { echo 'Candidate: 0.18.5~rc1'; }
dpkg-query() { [[ MODE == current ]] && printf '0.18.5~rc1'; }
novel-reader() { echo "reader:$*" >> "$HOME/events"; }
nr_main
'''.replace('ROOT', root).replace('MODE', mode)
                result = self.bash(body)
                events = (pathlib.Path(root)/'home/events').read_text()
                if mode == 'network-failure':
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('reader:', events)
                    self.assertNotIn('完成。', result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('reader:start', events)
                    if mode == 'current':
                        self.assertNotIn('--download-only', events)
                        self.assertNotIn('reader:stop', events)
                    else:
                        self.assertIn('--download-only', events)

    def test_failed_backup_preserves_last(self):
        with tempfile.TemporaryDirectory() as root:
            state = pathlib.Path(root)
            (state/'backup.tar').write_text('existing')
            result = self.bash(f'nr_backup /does-not-exist "{state}"')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((state/'backup.tar').read_text(), 'existing')
            self.assertEqual(len(list(state.iterdir())), 1)

if __name__ == '__main__':
    unittest.main()
