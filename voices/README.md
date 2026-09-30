# Voice Profile

各Voiceは`NAME/reference.wav`、`transcript.txt`、`voice.json`の組です。
通常は`cvtts add-voice NAME 参照音声.wav 文字起こし.txt`で登録します。
参照WAVが24kHz・mono・PCM16なら変換せずバイト単位で保存し、それ以外はffmpegで変換します。
文字起こしを推測したり、音声を自動的に切ったりしません。音声と文字を同じ区間に合わせてください。

`add-voice`はローカル登録です。Gitに自動追加・自動送信しません。
共有可能と確認したVoiceだけ、`.gitignore`の例外として許可してGitに保存してください。
参照音声は数百KB程度なので、現状はGit LFSが不要です。
