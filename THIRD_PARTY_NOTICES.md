# 上流とモデル

このリポジトリはCLI・構築・Voice Profile管理のためのラッパーです。
音声合成エンジン自体を自作したものではありません。

- Apple Silicon向けエンジン: [drmhse/tts-funaudio-cozyvoice3](https://github.com/drmhse/tts-funaudio-cozyvoice3)
- 本家: [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice)
- モデル: [FunAudioLLM/Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)
- 文字正規化: [pengzhendong/wetext](https://modelscope.cn/models/pengzhendong/wetext)（`wetext.lock`で固定、元READMEも取得）

エンジン・モデルはApache 2.0。固定commit/revisionは`upstream.lock`に記録します。
bootstrapは上流のチェックアウトをそのまま取得し、各LICENSE・NOTICE・著作権表示を保持します。
上流に含まれるMatcha-TTS等の依存コードはそれぞれのライセンスに従います。
Python依存パッケージには各パッケージのライセンスが適用されます。
参照音声の権利はコードのApache 2.0ライセンスには含まれません。
