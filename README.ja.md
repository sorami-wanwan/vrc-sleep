# vrc-sleep

[English](README.md) | [日本語](README.ja.md)

VRChatで寝るときにDiscordへインスタンスURLを通知し、起きたらそのメッセージを「閉鎖」に書き換えるCLIツールです。

Pythonの標準ライブラリだけで動くので、外部パッケージのインストールは不要です。

## 動作環境

- Python 3.10 以上

## インストール

リポジトリをクローンしてそのまま実行するか、pipでインストールしてください。

```bash
git clone https://github.com/sorami-wanwan/vrc_position_nofy.git
cd vrc_position_nofy

# pipで入れる場合（vrc-sleep コマンドがどこからでも使えるようになります）
pip install .
```

## 初期設定

初回にDiscordのWebhook URLと、通知に表示したい名前を設定します。

```bash
python3 vrc_sleep.py config --webhook "https://discord.com/api/webhooks/..." --username "SORAMI"
```

環境変数で渡すことも可能です。
- `DISCORD_WEBHOOK_URL`
- `VRC_SLEEP_USERNAME`

設定内容は `python3 vrc_sleep.py config` で確認できます。

## 使い方

### 1. 寝るとき
インスタンスURLを指定して `start` を実行します。

```bash
python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..."
```

短縮URL（`https://vrch.at/...`）にも対応しています。

### 2. 起きたとき
`close` を実行すると、先ほどDiscordに投稿したメッセージが自動で「閉鎖済み」に編集されます。

```bash
python3 vrc_sleep.py close
```

### 3. 状態確認
現在セッション中かどうかを確認できます。

```bash
python3 vrc_sleep.py status
```

## コマンド一覧

- `start <URL>`: 睡眠通知を投稿（`-f` でセッション上書き）
- `close`: 投稿済みメッセージを閉鎖に更新してセッション終了
- `status`: 現在のセッション状態と設定を表示
- `config`: 設定の確認・変更（`--webhook`, `--username`, `--show-secret`）

※別の場所にある設定ファイルを使いたい場合は、`--config /path/to/config.json` を指定してください。

## 開発・テスト

Python標準の `unittest` で単体テストを実行できます（外部パッケージ不要）。

```bash
python3 -m unittest discover -s tests -v
```

## ライセンス

MIT License
