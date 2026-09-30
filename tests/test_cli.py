import contextlib
import importlib.util
import io
import tempfile
import unittest
import wave
from pathlib import Path

spec = importlib.util.spec_from_file_location("cvtts", Path(__file__).resolve().parents[1] / "cvtts.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class VoiceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original = cli.VOICES
        cli.VOICES = self.root / "voices"
        self.reference = self.root / "input.wav"
        with wave.open(str(self.reference), "wb") as audio:
            audio.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x00" * 24000 * 4)
        self.transcript = self.root / "input.txt"
        self.transcript.write_text("今日はテストです。", encoding="utf-8")

    def tearDown(self):
        cli.VOICES = self.original
        self.temporary.cleanup()

    def register(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cli.add_voice(["test_voice", str(self.reference), str(self.transcript)])

    def test_exact_pair_and_duplicate_preservation(self):
        self.register()
        directory, _ = cli.read_voice("test_voice")
        self.assertEqual(self.reference.read_bytes(), (directory / "reference.wav").read_bytes())
        self.assertEqual(self.transcript.read_bytes(), (directory / "transcript.txt").read_bytes())
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.reference.read_bytes(), (directory / "reference.wav").read_bytes())

    def test_tampered_transcript_fails(self):
        self.register()
        (cli.VOICES / "test_voice" / "transcript.txt").write_text("別の台本")
        with self.assertRaises(ValueError):
            cli.read_voice("test_voice")

    def test_path_traversal_fails(self):
        for name in ("../escape", "/tmp/escape", ".", "name/subdir"):
            with self.assertRaises(ValueError):
                cli.voice_path(name)

    def test_reserved_prompt_in_transcript_fails_without_partial_profile(self):
        self.transcript.write_text("<|endofprompt|>test")
        with self.assertRaises(ValueError):
            self.register()
        self.assertFalse((cli.VOICES / "test_voice").exists())

    def test_nonfinite_speed_and_empty_text_fail_before_loading_model(self):
        self.register()
        for argv in (["--speed", "nan", "台本"], ["--speed", "inf", "台本"], [""]):
            with self.assertRaises(ValueError):
                cli.synthesize(["--voice", "test_voice", *argv, str(self.root / "output.wav")])

    def test_existing_output_is_not_overwritten(self):
        self.register()
        output = self.root / "output.wav"
        output.write_bytes(b"preserve")
        with self.assertRaises(ValueError):
            cli.synthesize(["--voice", "test_voice", "台本", str(output)])
        self.assertEqual(output.read_bytes(), b"preserve")

    def test_reference_cannot_be_output_even_with_force(self):
        self.register()
        output = cli.VOICES / "test_voice" / "reference.wav"
        before = output.read_bytes()
        with self.assertRaises(ValueError):
            cli.synthesize(["--voice", "test_voice", "--force", "台本", str(output)])
        self.assertEqual(before, output.read_bytes())

    def test_output_created_during_generation_is_preserved(self):
        first = self.root / "staged.wav"
        second = self.root / "staged.mp3"
        first.write_bytes(b"new wav")
        second.write_bytes(b"new mp3")
        output_wav = self.root / "output.wav"
        output_mp3 = self.root / "output.mp3"
        output_mp3.write_bytes(b"another process")
        with self.assertRaises(FileExistsError):
            cli.publish_results([(first, output_wav), (second, output_mp3)], False)
        self.assertFalse(output_wav.exists())
        self.assertEqual(output_mp3.read_bytes(), b"another process")


if __name__ == "__main__":
    unittest.main()
