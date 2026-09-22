import base64
import gzip
import unittest
import hashlib
import json
import os
from result_transport import build_model_output, stream_model_output

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

class StreamTransportTests(unittest.TestCase):
    def test_large_incompressible_files_have_bounded_lossless_chunks(self):
        ply = os.urandom(70 * 1024 * 1024)
        glb = os.urandom(300000)
        original = {"ply": ply, "glb": glb}
        digests = {kind: hashlib.sha256() for kind in original}
        indexes = {kind: 0 for kind in original}
        wire_bytes = 0
        for event in stream_model_output(ply, glb):
            wire = len(json.dumps({"output": event}).encode())
            wire_bytes += wire
            self.assertLess(wire, 1024 * 1024)
            if event["type"] == "manifest":
                for kind, data in original.items():
                    self.assertEqual(event["files"][kind]["sha256"], hashlib.sha256(data).hexdigest())
            elif event["type"] == "chunk":
                kind = event["file"]
                self.assertEqual(event["index"], indexes[kind])
                indexes[kind] += 1
                digests[kind].update(gzip.decompress(base64.b64decode(event["data"])))
        self.assertEqual(event["type"], "complete")
        self.assertGreater(wire_bytes, 66.12 * 1024 * 1024)
        for kind, data in original.items():
            self.assertEqual(digests[kind].digest(), hashlib.sha256(data).digest())

if __name__ == '__main__':
    unittest.main()
