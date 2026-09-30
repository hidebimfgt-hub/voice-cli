#!/usr/bin/env python3
"""Small CLI around a pinned CosyVoice engine. No server or training required."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parent
VOICES = ROOT / "voices"
RUNTIME = ROOT / ".runtime"
PREFIX = "You are a helpful assistant.<|endofprompt|>"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_results(files, force):
    created = []
    try:
        for source, destination in files:
            if force:
                os.replace(source, destination)
            else:
                # Same-filesystem atomic create: another process cannot be overwritten.
                os.link(source, destination)
                created.append(destination)
    except OSError:
        for destination in created:
            destination.unlink()
        raise


def voice_path(name):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
        raise ValueError("Voice名は英数字・_・-で64文字以内にしてください。")
    return (VOICES / name).resolve()


def read_voice(name):
    directory = voice_path(name)
    info = json.loads((directory / "voice.json").read_text(encoding="utf-8"))
    for filename in ("reference.wav", "transcript.txt"):
        if sha256(directory / filename) != info["sha256"][filename]:
            raise ValueError(f"{name}/{filename}の内容が登録時から変わっています。別Voiceとして登録してください。")
    return directory, info


def configure_wetext():
    lock = json.loads((ROOT / "wetext.lock").read_text())
    directory = RUNTIME / "wetext"
    for filename, entry in lock["files"].items():
        if sha256(directory / filename) != entry["sha256"]:
            raise ValueError("文字正規化データが不一致です。bootstrapを再実行してください。")
    # Override this package's downloader only; use its original Normalizer unchanged.
    import wetext.wetext as wetext_model

    def local_snapshot(model_id):
        if model_id != lock["model_id"]:
            raise ValueError("未設定の文字正規化モデルです。")
        return str(directory)

    wetext_model.snapshot_download = local_snapshot


def add_voice(argv):
    parser = argparse.ArgumentParser(prog="cvtts add-voice", description="参照音声と、その音声だけに一致する文字起こしを登録します。")
    parser.add_argument("name")
    parser.add_argument("reference", type=Path)
    parser.add_argument("transcript", type=Path, help="UTF-8テキストファイル")
    args = parser.parse_args(argv)
    destination = voice_path(args.name)
    if destination.exists():
        raise ValueError("同名Voiceが存在します。既存Voiceは上書きしません。")
    text = args.transcript.read_text(encoding="utf-8")
    if not text.strip() or "<|" in text:
        raise ValueError("文字起こしは実際の発話のみを記載してください。")
    VOICES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".register-", dir=VOICES) as temporary:
        temp = Path(temporary)
        reference = temp / "reference.wav"
        exact = False
        try:
            with wave.open(str(args.reference)) as audio:
                exact = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)
        except (wave.Error, EOFError):
            pass
        if exact:
            shutil.copy2(args.reference, reference)
        else:
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(args.reference), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(reference)], check=True)
        with wave.open(str(reference)) as audio:
            duration = audio.getnframes() / audio.getframerate()
        if not 3 <= duration <= 30:
            raise ValueError("参照音声は3〜30秒にして、文字起こしも同じ区間に合わせてください。")
        shutil.copy2(args.transcript, temp / "transcript.txt")
        info = {
            "name": args.name, "sample_rate": 24000, "duration_seconds": duration,
            "defaults": {"backend": "torch", "speed": 1.0, "seed": 42},
            "sharing": "local", "sha256": {f: sha256(temp / f) for f in ("reference.wav", "transcript.txt")},
        }
        (temp / "voice.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        # rename preserves a complete reference/transcript pair; no partial profile is published.
        temp.rename(destination)
    print(f"登録しました: {args.name} ({duration:.3f}秒)")


def doctor(argv):
    parser = argparse.ArgumentParser(prog="cvtts doctor")
    parser.add_argument("--verify-model", action="store_true", help="約5GBのモデル全ファイルのSHA256を検証")
    args = parser.parse_args(argv)
    lock = json.loads((ROOT / "upstream.lock").read_text())
    if sys.version_info[:3] != (3, 11, 16):
        raise ValueError("Pythonは3.11.16が必要です。")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=RUNTIME / "upstream", text=True).strip()
    if commit != lock["commit"]:
        raise ValueError("上流commitがupstream.lockと一致しません。")
    import importlib.metadata as metadata
    for line in (ROOT / "requirements.lock").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.split("==")
            if metadata.version(name) != version:
                raise ValueError(f"依存バージョンが不一致: {name}")
    import numpy as np
    from scipy.sparse.linalg import svds
    svds(np.diag(np.array([1., 2., 3.])), k=1, solver="propack")
    from mlx_lm.models.qwen2 import ModelArgs, Qwen2Model
    from mlx_lm.models.cache import KVCache
    from mlx_lm.models.base import create_causal_mask
    if not all(callable(item) for item in (ModelArgs, Qwen2Model, KVCache, create_causal_mask)):
        raise ValueError("必要なMLXモジュールのAPIが見つかりません。")
    if not shutil.which("ffmpeg"):
        raise ValueError("ffmpegが見つかりません。")
    configure_wetext()
    manifest = json.loads((RUNTIME / "model-manifest.json").read_text())
    if manifest["revision"] != lock["model_revision"]:
        raise ValueError("モデルrevisionが不一致です。")
    for filename, digest in manifest["files"].items():
        path = RUNTIME / "model" / filename
        if not path.is_file() or (args.verify_model and sha256(path) != digest):
            raise ValueError(f"モデルファイルが不一致: {filename}")
    print("OK: Python / 固定依存 / SciPy PROPACK / MLXモジュール / ffmpeg / 上流 / モデル")
    print("MLXはQwen2/cache/baseのみ利用。mlx-lmの一般用途CLIとtransformers>=5の組合せは対象外です。")


def synthesize(argv):
    parser = argparse.ArgumentParser(prog="cvtts", description="参照Voiceの声で台本をWAV/MP3にします。")
    parser.add_argument("--voice", default="tiktok_male_01")
    parser.add_argument("--backend", choices=("torch", "mlx"), help="torch=成功時のCPU経路、mlx=高速化比較")
    parser.add_argument("--speed", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--style", help="演技指示（声質が変わる場合があるため比較用）")
    parser.add_argument("--force", action="store_true", help="既存の出力ファイルを置き換える")
    parser.add_argument("text", help="台本。-なら標準入力からUTF-8で読む")
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    directory, voice = read_voice(args.voice)
    defaults = voice["defaults"]
    backend = args.backend or defaults["backend"]
    speed = defaults["speed"] if args.speed is None else args.speed
    seed = defaults["seed"] if args.seed is None else args.seed
    if not math.isfinite(speed) or not 0.5 <= speed <= 2:
        raise ValueError("speedは0.5〜2.0の数値にしてください。")
    if not 0 <= seed < 2**32:
        raise ValueError("seedは0〜4294967295にしてください。")
    text = sys.stdin.read() if args.text == "-" else args.text
    if not text.strip():
        raise ValueError("台本が空です。")
    if args.style is not None and (not args.style.strip() or "<|" in args.style):
        raise ValueError("styleは空でない演技指示にしてください。")
    output = args.output.resolve()
    if output.suffix.lower() not in (".wav", ".mp3"):
        raise ValueError("出力拡張子は.wavか.mp3にしてください。")
    wav_path = output.with_suffix(".wav") if output.suffix.lower() == ".mp3" else output
    metadata_path = output.with_suffix(output.suffix + ".json")
    destinations = {output, wav_path, metadata_path}
    protected = {directory / "reference.wav", directory / "transcript.txt", directory / "voice.json"}
    if destinations & protected or any(path.is_relative_to(RUNTIME.resolve()) or path.is_relative_to(VOICES.resolve()) for path in destinations):
        raise ValueError("出力先にはVoiceや実行環境のフォルダを指定できません。")
    if not args.force and any(path.exists() for path in destinations):
        raise ValueError("出力が既に存在します。別名にするか--forceを指定してください。")
    if output.suffix.lower() == ".mp3" and not shutil.which("ffmpeg"):
        raise ValueError("ffmpegが見つかりません。")
    upstream = RUNTIME / "upstream"
    model = RUNTIME / "model"
    if not (model / "cosyvoice3.yaml").exists():
        raise ValueError("先にbootstrap.shを実行してください。")
    sys.path.insert(0, str(upstream))
    sys.path.append(str(upstream / "third_party" / "Matcha-TTS"))
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    configure_wetext()
    os.chdir(upstream)
    started = time.monotonic()
    from cosyvoice.utils.common import set_all_random_seed
    set_all_random_seed(seed)
    prompt = PREFIX + (directory / "transcript.txt").read_text(encoding="utf-8").strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cvtts-", dir=output.parent) as temporary:
        temp = Path(temporary)
        tmp_wav = temp / "audio.wav"
        if backend == "torch":
            import torch
            import torchaudio
            from cosyvoice.cli.cosyvoice import CosyVoice3
            cv = CosyVoice3(model_dir=str(model))
            if cv.frontend.text_frontend != "wetext":
                raise ValueError("固定した文字正規化データを利用できません。")
            set_all_random_seed(seed)
            if args.style:
                instruction = "You are a helpful assistant. " + args.style + "<|endofprompt|>"
                generated = cv.inference_instruct2(text, instruction, str(directory / "reference.wav"), stream=False, speed=speed)
            else:
                generated = cv.inference_zero_shot(text, prompt, str(directory / "reference.wav"), stream=False, speed=speed)
            chunks = [result["tts_speech"].cpu() for result in generated]
            if not chunks:
                raise ValueError("音声が生成されませんでした。")
            audio = torch.cat(chunks, dim=1)
            segments = len(chunks)
            if not torch.isfinite(audio).all() or audio.numel() == 0:
                raise ValueError("生成音声が不正です。")
            torchaudio.save(str(tmp_wav), audio.clamp(-1, 1), cv.sample_rate, encoding="PCM_S", bits_per_sample=16)
            device, precision = str(cv.model.device), "fp32"
        else:
            from tts_worker import ModelHost
            host = ModelHost({"model_dir": str(model), "device": "mps", "nfe": 10,
                              "prompt_text": prompt, "prompt_wav": str(directory / "reference.wav"),
                              "spk_id": args.voice, "llm_backend": "mlx", "llm_precision": "fp16", "llm_batch_size": 1})
            host.load()
            if host.cv.frontend.text_frontend != "wetext":
                raise ValueError("固定した文字正規化データを利用できません。")
            set_all_random_seed(seed)
            segments = len(host.cv.frontend.text_normalize(text, split=True, text_frontend=True))
            wav, _ = host.synthesize_wav({"mode": "instruct" if args.style else "zero_shot", "text": text, "speed": speed, "instruct_text": args.style or ""}, seed)
            tmp_wav.write_bytes(wav)
            device, precision = host.device, host.precision
        with wave.open(str(tmp_wav)) as audio:
            duration = audio.getnframes() / audio.getframerate()
            sample_rate = audio.getframerate()
        if duration <= 0:
            raise ValueError("空の音声が生成されました。")
        if output.suffix.lower() == ".mp3":
            tmp_output = temp / "audio.mp3"
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(tmp_wav), "-c:a", "libmp3lame", "-b:a", "192k", str(tmp_output)], check=True)
        else:
            tmp_output = tmp_wav
        lock = json.loads((ROOT / "upstream.lock").read_text())
        info = {"voice": args.voice, "text": text, "style": args.style, "speed": speed, "seed": seed,
                "backend": backend, "device": device, "llm_precision": precision, "nfe": 10,
                "sample_rate": sample_rate, "segments": segments, "duration_seconds": duration, "wall_seconds": round(time.monotonic() - started, 3),
                "voice_sha256": voice["sha256"], "upstream": lock,
                "wetext": json.loads((ROOT / "wetext.lock").read_text()),
                "output_sha256": sha256(tmp_output), "wav_sha256": sha256(tmp_wav)}
        (temp / "metadata.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # No user-visible result is replaced until generation and MP3 conversion both succeed.
        files = [(tmp_wav, wav_path)] if wav_path != output else []
        files += [(tmp_output, output), (temp / "metadata.json", metadata_path)]
        publish_results(files, args.force)
    print(f"生成しました: {output} ({duration:.2f}秒 / {backend})")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] == "list-voices":
            if argv[1:]:
                raise ValueError("list-voicesに追加引数は不要です。")
            for directory in sorted(VOICES.glob("*/voice.json")):
                name = directory.parent.name
                _, info = read_voice(name)
                print(f"{name}\t{info['duration_seconds']:.3f}秒\t{info['sharing']}")
        elif argv and argv[0] == "add-voice":
            add_voice(argv[1:])
        elif argv and argv[0] == "doctor":
            doctor(argv[1:])
        else:
            synthesize(argv)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
