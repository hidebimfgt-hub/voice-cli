import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prepare_runtime", Path(__file__).resolve().parents[1] / "scripts/prepare_runtime.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class DownloadSafetyTests(unittest.TestCase):
    def test_rate_limit_is_retried_and_only_verified_content_is_saved(self):
        payload = b"fixed normalization data"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock = {"model_id": "pengzhendong/wetext", "files": {"en/tn/tagger.fst": {"revision": "a" * 40, "sha256": hashlib.sha256(payload).hexdigest()}}}
            (root / "wetext.lock").write_text(json.dumps(lock))
            error = urllib.error.HTTPError("https://modelscope.cn/", 403, "rate limit", {}, None)
            with patch.object(prepare, "ROOT", root), patch.object(prepare, "RUNTIME", root / ".runtime"), patch.object(prepare.urllib.request, "urlopen", side_effect=[error, io.BytesIO(payload)]) as fetch, patch.object(prepare.time, "sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
                prepare.prepare_wetext()
                self.assertEqual(fetch.call_count, 2)
                sleep.assert_called_once_with(5)
            self.assertEqual((root / ".runtime/wetext/en/tn/tagger.fst").read_bytes(), payload)

    def test_wrong_hash_never_replaces_existing_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock = {"model_id": "pengzhendong/wetext", "files": {"tagger.fst": {"revision": "a" * 40, "sha256": hashlib.sha256(b"expected").hexdigest()}}}
            (root / "wetext.lock").write_text(json.dumps(lock))
            path = root / ".runtime/wetext/tagger.fst"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"preserve previous file")
            with patch.object(prepare, "ROOT", root), patch.object(prepare, "RUNTIME", root / ".runtime"), patch.object(prepare.urllib.request, "urlopen", return_value=io.BytesIO(b"unexpected")), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):
                    prepare.prepare_wetext()
            self.assertEqual(path.read_bytes(), b"preserve previous file")
            self.assertEqual(list(path.parent.iterdir()), [path])
