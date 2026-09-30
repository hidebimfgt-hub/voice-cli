# voice-cli

CosyVoice 3で、登録したVoiceの声を使ってWAV/MP3を生成します。
CodexからCLIで呼び出せます。音声の学習やAPIキーは不要です。
上流エンジンは改変せず、CLI・構築・Voice管理をこのリポジトリで扱います。

## 別のMacで構築する

Apple SiliconのMacとHomebrew、Gitが必要です。Intel/Rosettaは対象外です。
Private GitHubにアクセスできるアカウントで実行します。

現在の`tiktok_male_01`はこのMacだけに保全しています。共有権限の確認が済むまでGitへ含めません。
別Macでは、共有可能な参照音声と文字起こしを`cvtts add-voice`で登録してから生成してください。
このMacには`tiktok_male_01`が登録済みです。

```bash
git clone https://github.com/hidebimfgt-hub/voice-cli.git
cd voice-cli
./bootstrap.sh
source .venv/bin/activate
cvtts list-voices
cvtts --voice tiktok_male_01 "これ、ただのカメラじゃありません。" generated/sample.mp3
```

初回はPythonと約5GBのモデルを取得します。仮想環境を含めて空き容量15GB以上を確保してください。
uv・ffmpegがなければHomebrewで導入します。既存の別プロジェクトの環境は変更しません。
実行環境はこのリポジトリの`.venv/`と`.runtime/`に作り、Gitへ送りません。
再実行は同じバージョンを使います。上流checkoutに変更があれば上書きせず停止します。
Macごとの環境差による失敗はエラーとして表示します。別Mac実機での成功は別途確認が必要です。

## 生成する

```bash
cvtts --voice tiktok_male_01 "台本をここに書きます。" generated/narration.mp3
cvtts --voice tiktok_male_01 --speed 1.2 --seed 42 "少し速い台本です。" generated/fast.mp3
cvtts --voice tiktok_male_01 --backend mlx "高速化を比較します。" generated/mlx.wav
cat script.txt | cvtts --voice tiktok_male_01 - generated/long.mp3
```

MP3の場合は同じ名前のWAVも残します。生成条件は`narration.mp3.json`等に保存します。
JSONには台本・Voiceのハッシュ・seed・速度・backend・上流commit・モデルrevisionを記録します。
長文が複数に分かれた場合も全結果を連結します。既存の出力は上書きしません。
置き換える場合だけ`--force`を指定してください。Voiceやモデルのフォルダは出力先にできません。

既定の`torch`は、似ていると評価された成功時のCPU/fp32経路です。
`mlx`はLLMをMLX/fp16、flowをMPS/fp32、vocoderをCPUで処理します。
flowのステップ数は双方10。MLXは出力がTorchと同じ音にはならないため、聴いて比較してください。
seedは乱数を固定しますが、異なるMacやバックエンドでのバイト一致を保証するものではありません。
速度は0.5〜2.0です。1.2から比較し、声質を優先するなら1.0を使ってください。

演技指示は`--style "明るく、一定のテンションで読み上げてください。"`で試せます。
zero-shotとは別のinstruct経路になるため、声質・読み方が変わる可能性があります。
ショート動画向けの高さ・鼻声・0.2秒の間が指定どおりになるかは聴いて調整する段階です。
希望された声の指示全文は`presets/shorts_ja.txt`に保存しています。比較する場合は次を使います。

```bash
cvtts --voice tiktok_male_01 --speed 1.2 --style "$(cat presets/shorts_ja.txt)" "台本をここに書きます。" generated/shorts.mp3
```

既定の生成には演技指示を混ぜず、参照Voiceの声質を基準にしています。
今回の全文指示では同じ台本が15.32秒になり、狙った速さに達していません。全文指示は比較用です。
実用の速度調整は、通常経路の`--speed 1.2`で6.70秒になった版を基準にしてください。

Codexに依頼する場合は、リポジトリ内の`bin/cvtts`の絶対パスと、Voice名・台本・出力先を伝えてください。
`source`しなくても`./bin/cvtts`を使えます。参照WAVと文字起こしの内容は勝手に変更しないでください。
常に`cvtts`と呼びたい場合は`./bootstrap.sh --install-command`でHomebrewのbinにコマンドを登録できます。
既存の別コマンドは上書きしません。リポジトリを移動する場合は、そのリンクも移動先へ更新してください。

## Voiceを追加・共有する

```bash
cvtts add-voice my_voice /path/to/reference.wav /path/to/transcript.txt
cvtts list-voices
```

参照は3〜30秒。文字起こしはその音声と一致するUTF-8テキストです。
登録後の音声・文字起こしを変更すると検証エラーになります。別名で登録してください。
Voiceはモデルの再学習ではなく、参照音声と文字の組です。複数Voiceで共通のモデルを使います。
新規Voiceはローカルのみ。共有権限を確認したVoiceだけPrivate GitHubで同期します。
共有相手のGitHubアカウントは未指定なので、共同編集者の招待はまだ行いません。

## 検証・更新

```bash
cvtts doctor
cvtts doctor --verify-model
python -m unittest discover -s tests
git pull --ff-only
./bootstrap.sh
```

依存は[uvのlock/sync方式](https://docs.astral.sh/uv/pip/compile/)で全バージョンを固定します。
SciPy PROPACKと、実際に使うMLXモジュールもdoctorで検証します。
WeTextの文字正規化データは`wetext.lock`でファイルごとのcommitとSHA256を固定し、構築時に取得します。
推論時の暗黙の最新データ取得を避け、登録済みVoiceの生成はネット接続なしで実行できます。
上流の指定に合わせ、mlx-lm 0.31.3はtransformers 4.51.3と依存解決せずに使用します。
そのため`uv pip check`にはtransformers>=5とsentencepiece不足が表示されます。
このCLIが利用するQwen2/cache/baseの部分だけを検証しており、mlx-lmの一般CLI用途は対象外です。
将来transformersを単独でアップグレードするとCosyVoiceが壊れる可能性があるため、変更は別環境で試してください。

エンジン更新は`python scripts/update_upstream.py 完全なcommitSHA`で明示します。
続けてbootstrap・テスト・同じ台本での音声比較を行い、変更した`upstream.lock`をGitへ保存します。
モデル更新は`upstream.lock`のmodel_revisionを変更して同様に比較します。
自動的に最新モデルや最新commitへ更新することはありません。
依存パッケージの更新も別のfresh cloneで検証し、lockを更新してください。

## 出典・保全

上流・モデル・ライセンスは[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。
既存の成功参照ペアと成功WAVは、2026-09-30の実環境バックアップにバイト単位で保全しました。
旧環境・旧モデル・Gemini関係・試験音声は、この構築作業では削除しません。
削除する場合は新経路での生成成功後、対象と理由を確認してから実施します。
