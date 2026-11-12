import io,tarfile,tempfile,unittest
from pathlib import Path
from deploy import allowed,unpack,validate_manifest,FINGERPRINT
class BundleTests(unittest.TestCase):
    def test_reject_private_and_traversal_names(self):
        for name in ['../secret','/etc/passwd','data/reader.db','.env','novel-reader-source.tar.gz','build.log','pool/main/openssl_1_aarch64.deb']:
            self.assertFalse(allowed(name))
        self.assertTrue(allowed('pool/main/novel-reader_0.17.24~rc1_aarch64.deb'))
    def test_channels_and_manifest_semantics(self):
        good={'tag':'testing-0.18.5-rc1-'+'a'*12,'sha256':'b'*64,'primaryFingerprint':FINGERPRINT,'channel':'testing','applicationVersion':'0.18.5-rc1'}
        validate_manifest(good)
        with self.assertRaises(ValueError):validate_manifest(dict(good,channel='stable',tag='stable-0.18.5-rc1-'+'a'*12))
        self.assertTrue(allowed('dists/stable/InRelease'))
        self.assertFalse(allowed('dists/other/InRelease'))
        self.assertFalse(allowed('dists/stable/main/binary-aarch64/Packagesxgz'))
    def test_reject_link_and_duplicate_members(self):
        for kind in ['link','duplicate','traversal']:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);bundle=root/'test.tar.gz'
                with tarfile.open(bundle,'w:gz') as tar:
                    m=tarfile.TarInfo('../escape' if kind=='traversal' else 'index.html')
                    if kind=='link':m.type=tarfile.SYMTYPE;m.linkname='/etc/passwd';tar.addfile(m)
                    else:
                        m.size=1;tar.addfile(m,io.BytesIO(b'x'))
                        if kind=='duplicate':tar.addfile(m,io.BytesIO(b'y'))
                with self.assertRaises(ValueError):unpack(bundle,root/'site')
                self.assertFalse((root/'escape').exists())
if __name__=='__main__':unittest.main()
