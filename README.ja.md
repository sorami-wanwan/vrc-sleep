# vrc-sleep

[English](README.md) | [日本語](README.ja.md)

VRChatで寝るときにDiscordへインスタンスURLを通知し、起きたらそのメッセージを「クローズ」に書き換えるツールです。
CLIとGUI（デスクトップアプリ）の両方を提供しています。

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

## 使い方

初回のみDiscordのWebhook URL等の設定が必要です。GUI版（`vrc_sleep_gui.py`）を使用する場合は、起動後に右上の **Settings** ボタンから設定できます。

CLIの場合は以下のように `config` を実行するか、環境変数（`DISCORD_WEBHOOK_URL`, `VRC_SLEEP_USERNAME`）を使用してください。

```bash
python3 vrc_sleep.py config --webhook "https://discord.com/api/webhooks/..." --username "SORAMI"
```

### 1. 寝るとき

**GUI版**:
`python3 vrc_sleep_gui.py` で起動し、「Instance URL」を入力して **Start Sleep** をクリックします。任意でワールド名や画像URLも指定できます。

**CLI版**:
インスタンスURLを指定して `start` を実行します。ワールド名（`-w`）や画像URL（`-i`）を指定して通知をリッチにすることもできます。
```bash
python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..." -w "おやすみベッドルーム" -i "https://example.com/sleep_thumbnail.png"
```
※短縮URL（`https://vrch.at/...`）にも対応しています。

### 2. 起きたとき

**GUI版**:
起床時に **Close Session** をクリックすると、通知が更新されてセッションが終了します。

**CLI版**:
`close` を実行すると、先ほどDiscordに投稿したメッセージが自動で「クローズ」に編集されます。
```bash
python3 vrc_sleep.py close

# 万が一ローカルの状態が消えてしまった場合はメッセージIDを手動指定してクローズ可能
python3 vrc_sleep.py close --message-id "123456789012345678"
```

### 3. 状態確認・その他

- 現在セッション中かどうかは `python3 vrc_sleep.py status` で確認できます（GUI版はステータスバーに常時表示されます）。
- 別の場所にある設定ファイルを使いたい場合は `--config /path/to/config.json` オプションを指定してください。

## 開発・テスト

Python標準の `unittest` で単体テストを実行できます（外部パッケージ不要）。

```bash
python3 -m unittest discover -s tests -v
```

## ライセンス

MIT License
