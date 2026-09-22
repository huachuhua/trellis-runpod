import base64
import gzip
import unittest
from result_transport import build_model_output

class TransportTests(unittest.TestCase):
    def test_compresses_large_result_losslessly(self):
        ply = b'ply\n' + b'gaussian data ' * 900000
        glb = b'glTF' + b'textures' * 1000
        with self.assertRaisesRegex(ValueError, 'supera'):
            build_model_output(ply, glb)
        result = build_model_output(ply, glb, 'gzip')
        self.assertEqual(gzip.decompress(base64.b64decode(result['ply_gzip_base64'])), ply)
        self.assertEqual(gzip.decompress(base64.b64decode(result['glb_gzip_base64'])), glb)

    def test_oversize_compressed_result_raises_before_sdk_submission(self):
        with self.assertRaisesRegex(ValueError, 'supera'):
            build_model_output(b'ply\n' + bytes(range(256))*10, b'glTF', 'gzip', max_bytes=128)

    def test_rejects_empty_model(self):
        with self.assertRaisesRegex(ValueError, 'PLY'):
            build_model_output(b'', None, 'gzip')

if __name__ == '__main__':
    unittest.main()
