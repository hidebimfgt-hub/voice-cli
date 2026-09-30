#!/usr/bin/env python3
"""Explicit, reviewable engine pin update. Does not publish or remove data."""
import argparse
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description="固定commitを明示したSHAへ変更。bootstrapと音声比較後にcommitしてください。")
parser.add_argument("commit", help="上流の完全な40桁SHA")
args = parser.parse_args()
if not re.fullmatch("[0-9a-f]{40}", args.commit):
    parser.error("完全な40桁SHAを指定してください。")
path = root / "upstream.lock"
lock = json.loads(path.read_text())
engine = root / ".runtime" / "upstream"
subprocess.run(["git", "fetch", "origin", args.commit], cwd=engine, check=True)
subprocess.run(["git", "cat-file", "-e", args.commit + "^{commit}"], cwd=engine, check=True)
backup = root / ".runtime" / f"upstream-{lock['commit']}.lock"
backup.write_bytes(path.read_bytes())
lock["commit"] = args.commit
path.write_text(json.dumps(lock, indent=2) + "\n")
print("固定commitを更新しました。./bootstrap.shと音声比較を行ってからGitへ保存してください。")
