#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:$PATH"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
INSTALL_COMMAND=0
if [ "${1:-}" = --install-command ] && [ "$#" = 1 ]; then
  INSTALL_COMMAND=1
elif [ "$#" != 0 ]; then
  echo '使い方: ./bootstrap.sh [--install-command]' >&2
  exit 1
fi
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'Apple Silicon Macで実行してください（Rosettaのシェルは使用不可）。' >&2
  exit 1
fi
for command in uv ffmpeg; do
  if ! command -v "$command" >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      brew install "$command"
    else
      echo "Homebrewを導入してから再実行してください: https://brew.sh/" >&2
      exit 1
    fi
  fi
done
# Pin the installer itself without modifying another project's uv.
mkdir -p .runtime
if [ ! -x .runtime/uv/bin/uv ]; then
  UV_TOOL_DIR="$ROOT/.runtime/uv-tools" UV_TOOL_BIN_DIR="$ROOT/.runtime/uv/bin" uv tool install uv==0.12.19
fi
UV="$ROOT/.runtime/uv/bin/uv"
"$UV" python install 3.11.16
if [ ! -x .venv/bin/python ]; then
  "$UV" venv --python 3.11.16 .venv
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:3] == (3,11,16), "Python version mismatch; keep old environment and use a fresh clone"'
"$UV" pip install --python .venv/bin/python --no-deps torch==2.3.1 torchaudio==2.3.1 setuptools==69.5.1 wheel==0.48.0 numpy==1.26.4 cython==3.3.0
# mlx-lm's full transformers>=5 dependency is intentionally not installed.
# The upstream SpeechLM uses only its Qwen2/cache/base modules; doctor checks those imports.
"$UV" pip sync --python .venv/bin/python --no-build-isolation requirements.lock
.venv/bin/python scripts/prepare_runtime.py
ln -sf "$ROOT/bin/cvtts" "$ROOT/.venv/bin/cvtts"
./bin/cvtts doctor
if [ "$INSTALL_COMMAND" = 1 ]; then
  COMMAND_PATH="$(brew --prefix)/bin/cvtts"
  if [ -e "$COMMAND_PATH" ] || [ -L "$COMMAND_PATH" ]; then
    if [ "$(readlink "$COMMAND_PATH" || true)" != "$ROOT/bin/cvtts" ]; then
      echo "$COMMAND_PATH が既に存在します。上書きせず停止しました。" >&2
      exit 1
    fi
  else
    ln -s "$ROOT/bin/cvtts" "$COMMAND_PATH"
  fi
  echo "コマンドを登録しました: $COMMAND_PATH"
fi
echo "構築完了。コマンドを使うには: source \"$ROOT/.venv/bin/activate\""
