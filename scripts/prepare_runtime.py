"""Fetch only the pinned upstream and pinned model; preserve existing checkouts."""
from pathlib import Path
import hashlib
import json
import subprocess
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "upstream.lock").read_text())
RUNTIME = ROOT / ".runtime"
UPSTREAM = RUNTIME / "upstream"
MODEL = RUNTIME / "model"


def prepare_wetext():
    lock = json.loads((ROOT / "wetext.lock").read_text())
    directory = RUNTIME / "wetext"
    for filename, entry in lock["files"].items():
        path = directory / filename
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        query = urllib.parse.urlencode({"Revision": entry["revision"], "FilePath": filename})
        url = f"https://modelscope.cn/api/v1/models/{lock['model_id']}/repo?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "keiyo-voice-cli/1.0", "Cache-Control": "no-cache"})
        print(f"文字正規化データを取得: {filename}", flush=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                for attempt in range(4):
                    temporary.seek(0)
                    temporary.truncate()
                    try:
                        with urllib.request.urlopen(request, timeout=120) as response:
                            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                                temporary.write(chunk)
                        break
                    except urllib.error.HTTPError as error:
                        if error.code not in (403, 408, 429, 500, 502, 503, 504) or attempt == 3:
                            raise
                    except urllib.error.URLError:
                        if attempt == 3:
                            raise
                    delay = 5 * (attempt + 1)
                    print(f"配信先の一時エラー。{delay}秒後に再試行: {filename}", flush=True)
                    time.sleep(delay)
                temporary.flush()
                if hashlib.sha256(temporary_path.read_bytes()).hexdigest() != entry["sha256"]:
                    raise ValueError(f"文字正規化データが固定ハッシュと不一致: {filename}")
                os.replace(temporary_path, path)
            finally:
                temporary_path.unlink(missing_ok=True)


def prepare():
    RUNTIME.mkdir(exist_ok=True)
    if not UPSTREAM.exists():
        subprocess.run(["git", "clone", "--no-checkout", LOCK["repository"], str(UPSTREAM)], check=True)
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=UPSTREAM, text=True)
    # A new --no-checkout clone reports all tracked files deleted until its first checkout.
    if (UPSTREAM / "tts_worker.py").exists() and status:
        raise SystemExit(".runtime/upstreamに変更があります。保全してからfresh cloneしてください。")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True).strip()
    if current != LOCK["commit"] or not (UPSTREAM / "tts_worker.py").exists():
        subprocess.run(["git", "fetch", "origin", LOCK["commit"]], cwd=UPSTREAM, check=True)
        subprocess.run(["git", "checkout", "--detach", LOCK["commit"]], cwd=UPSTREAM, check=True)
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=LOCK["model_id"], revision=LOCK["model_revision"], local_dir=MODEL,
        ignore_patterns=["llm.rl.pt", "speech_tokenizer_v3.batch.onnx", "flow.decoder.estimator.fp32.onnx"],
    )
    # Record actual model bytes, so subsequent doctor calls detect accidental changes.
    files = {}
    for path in sorted(MODEL.rglob("*")):
        if not path.is_file() or ".cache" in path.parts:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        files[str(path.relative_to(MODEL))] = digest.hexdigest()
    (RUNTIME / "model-manifest.json").write_text(json.dumps({"revision": LOCK["model_revision"], "files": files}, indent=2) + "\n")
    prepare_wetext()


if __name__ == "__main__":
    prepare()
