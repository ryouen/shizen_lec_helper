# AI_SETUP.md — AIエージェント向けセットアップガイド

## あなたへの宣言

このファイルを読んでいるのはAIエージェントです。以下の指示に従ってください。

- **あなたはこれからユーザーのセットアップを手伝います。**
- **パスワードは絶対にディスクに保存・ログ出力しないでください。** `token_setup.py` が `getpass` で入力を受け取り、メモリから即座に削除します。
- **不明な点は1問ずつ聞かず、まとめて確認してください**（下記のインタビュー手順を参照）。
- shizen_lec_helper専用の設定は `~/.config/shizen_lec_helper/` に保存します。ユーザーのホームディレクトリにある他のファイル・設定には触れないでください。

---

## Step 1: 環境チェック（自動）

以下をまとめて確認してください:

```bash
python3 --version        # 3.10以上が必要
which uv || which pip3   # パッケージマネージャーの確認
which ffmpeg             # 動画ダウンロード時に使用（なくても動作可）
df -h ~/                 # 空きディスク容量（50GB以上推奨）
uname -s                 # OS確認（Darwin=Mac, Linux, MINGW=Windows）
```

**確認ポイント:**
- Python < 3.10 の場合: `brew install python@3.12` または `pyenv install 3.12` を案内
- `ffmpeg` がない場合: `brew install ffmpeg` を案内（動画DLには必要）
- 空き容量 < 20GB の場合: ユーザーに警告を出すが、インストール自体は続行可

---

## Step 2: ユーザーへの初回インタビュー（まとめて質問）

以下の質問をすべてまとめて一度に聞いてください（1問ずつ聞かない）:

> 以下をまとめて教えてください:
> 1. Moodleトークンをお持ちですか？
>    - **お持ちでない場合（多くの方）**: 次のStep 4で `python -m shizen_lec_helper setup` を実行すると、MoodleのログインメールアドレスとパスワードからAPIトークンが自動取得されます。パスワードは `getpass` で入力され、メモリのみで使われ、ディスクには一切保存されません（保存されるのはトークンのみ）。
>    - **すでにお持ちの場合**: `~/.config/shizen_lec_helper/moodle-token.json` に `{"token": "...", "site_url": "...", "user_id": ...}` の形式で手動配置いただけます。
> 2. このPCは常時ONですか？（定期自動同期の設定方法が変わります）
> 3. 動画もダウンロードしますか？（1コースあたり3〜11GB必要です）
> 4. 資料の保存先（デフォルト: `~/Shizenkan/`）
> 5. 新しいコースが追加されたときの挙動: `auto`（自動追加）/ `ask`（確認）/ `ignore`（無視）

**収集した情報をもとに設定を決め、次のステップへ進んでください。**

---

## Step 3: 依存パッケージのインストール

```bash
# uv が使える場合（推奨・高速）
uv pip install -r requirements.txt

# pip を使う場合
pip install -r requirements.txt

# venv を作る場合
python3 -m venv .venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

---

## Step 4: Moodleトークンの取得（2択）

### 方式A: 非対話型（AIエージェント経由で実行する場合、推奨）

**AIへの重要指示:**
- このステップでは認証情報ファイルを経由します
- ユーザーに作成してもらうファイルの中身（USERNAMEとPASSWORD）を
  あなた（AI）は絶対にReadツール等で読まないでください
- ユーザーに「自分のエディタで書いてください」と伝え、
  あなたはファイルパスだけを受け取ってください
- スクリプトがファイルを消去するので、後処理も不要です

ユーザーへの指示（コピペ用）:
「以下の内容のファイルを `~/.shizen_lec_creds` に作成してください（chmod 600にしてください）。
このファイルの中身は私（AI）には見せないでください。

  SOS_USERNAME=あなたのMoodleメールアドレス
  SOS_PASSWORD=あなたのMoodleパスワード

作成したら教えてください。次のコマンドを実行します。
（スクリプトが成功/失敗に関わらずこのファイルを上書きして削除します）」

実行:
```bash
chmod 600 ~/.shizen_lec_creds
python -m shizen_lec_helper setup --creds-file ~/.shizen_lec_creds
```

このコマンドが以下を行います:
1. ファイルの所有者・パーミッション（600以下）を検証
2. SOS_USERNAME / SOS_PASSWORD を読み取り（標準出力に値は一切出力しません）
3. Moodle APIでトークンを取得
4. `core_webservice_get_site_info` で動作確認（ユーザー名・フルネームが表示されます）
5. トークンを `~/.config/shizen_lec_helper/moodle-token.json` に保存（パーミッション600）
6. 設定ファイル `~/.config/shizen_lec_helper/config.json` を生成
7. 成功/失敗にかかわらず、認証情報ファイルをゼロ埋め上書き → fsync → 削除

### 方式B: 対話型（ユーザーが自分のターミナルで実行する場合）

```bash
python -m shizen_lec_helper setup
```

ユーザーがTTY環境（Terminal.app等）で直接実行する場合のみ動きます。
AIエージェントのBashツール経由ではTTYが繋がらず、EOFErrorになります。

このコマンドが以下を行います:
1. SOSのメールアドレスとパスワードを `getpass` で入力（パスワードは画面に表示されません）
2. Moodle APIでトークンを取得
3. `core_webservice_get_site_info` で動作確認（ユーザー名・フルネームが表示されます）
4. トークンを `~/.config/shizen_lec_helper/moodle-token.json` に保存（パーミッション600）
5. 設定ファイル `~/.config/shizen_lec_helper/config.json` を生成

**パスワードはディスクに書き込まれません。**

---

## Step 5: アクティブコースの確認と設定

```bash
python -m shizen_lec_helper courses --auto-detect
```

このコマンドが:
- 全受講コースを一覧表示
- 「未来の締切がある」または「直近2週間で更新あり」のコースを `ACTIVE` と表示

出力例:
```
Shortname                      Status     Full name
--------------------------------------------------------------------------------
FINANCE_EN_2027                ACTIVE     Market Principles and Corporate Finance
MARKETING_EN_2027              ACTIVE     Marketing: Principles and Practices
SOCIOLOGY_EN_2027              inactive   Social Systems Theory...
```

**ユーザーと一緒に確認し、`active_courses` を決定してください。**

設定の更新:
```bash
# ~/.config/shizen_lec_helper/config.json を編集して active_courses を設定
# または手動で編集:
cat ~/.config/shizen_lec_helper/config.json
```

---

## Step 6: 初回同期（ドライランで確認 → 本実行）

まずドライランで確認:
```bash
python -m shizen_lec_helper sync --dry-run
```

問題なければ本実行:
```bash
python -m shizen_lec_helper sync
```

**初回は時間がかかることがあります（特に動画をDLする場合）。**
- PDF・スライドのみ: 数分〜十数分
- 動画あり: 1コースあたり1〜3時間（動画サイズ次第）

---

## Step 7: 定期自動同期の設定

### Mac（常時ON）の場合: crontab

```bash
# 毎朝6時に同期
crontab -e
```

追加する行:
```
0 6 * * * cd /path/to/shizen_lec_helper && ./run.sh sync >> ~/Shizenkan/sync.log 2>&1
```

### Mac（必要な時だけ起動）の場合: ログイン時フック

```bash
# ~/.zprofile または ~/.bash_profile に追加
echo 'cd /path/to/shizen_lec_helper && ./run.sh sync --dry-run 2>/dev/null &' >> ~/.zprofile
```

または LaunchAgent を作成（詳しくはAIに相談してください）。

### Linux（systemd）の場合:
systemd user timerを設定してください。AIに相談してください。

---

## Windows / Linux の注意点

このツールはMac前提で書かれていますが、基本的にはPythonスクリプトなので他のOSでも動作します。

**Windows固有の注意:**
- cronの代わりに「タスクスケジューラ」を使ってください
- `run.sh` の代わりに `python -m shizen_lec_helper` を直接使ってください
- ffmpegのインストール: https://ffmpeg.org/download.html または `winget install ffmpeg`

**Linux固有の注意:**
- cronまたはsystemd-timerを使ってください
- ffmpeg: `sudo apt install ffmpeg` または `sudo dnf install ffmpeg`

「具体的な設定方法はあなたのAI（このセッションのAI）に聞いてください」

---

## トラブルシューティング

### トークン取得に失敗する

```
Login failed: Invalid login, please try again
```
→ メールアドレス/パスワードを確認してください。SOSにブラウザでログインできるか確認してください。

```
Could not reach Moodle server
```
→ インターネット接続を確認してください。VPNが必要な場合はVPNに接続してください。

再試行:
```bash
python -m shizen_lec_helper setup --force
```

### ダウンロードが途中で止まる

`Ctrl+C` で停止しても問題ありません。次回 `sync` を実行すると続きから再開します（ダウンロード済みファイルはスキップ）。

ディスク容量が足りない場合:
```bash
df -h ~/Shizenkan
```
古い動画ファイルを削除してから再実行してください。

### yt-dlp が見つからない

```bash
# Mac
brew install yt-dlp

# pip
pip install yt-dlp
```

### ffmpeg が見つからない（動画の結合に失敗する）

```bash
# Mac
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 動画のパスワードが違うと言われる

動画URLのパスワードはSOS（Moodle）の授業ページに記載されています。
`python -m shizen_lec_helper courses` でコース一覧を確認し、SOSのページで最新のパスワードを確認してください。

---

## 設定ファイルのリファレンス

`~/.config/shizen_lec_helper/config.json`:

| キー | 型 | デフォルト | 説明 |
|-----|-----|---------|------|
| `site_url` | string | `https://campus.shizenkan.ac.jp` | MoodleサイトのURL |
| `base_path` | string | `~/Shizenkan` | ファイル保存先のルートディレクトリ |
| `active_courses` | array | `[]` | 同期対象コースのshortname一覧 |
| `download_videos` | bool | `true` | 動画をダウンロードするか |
| `new_course_policy` | string | `"ask"` | 新コース検出時の挙動（`auto`/`ask`/`ignore`） |
| `notification_format` | string | `"markdown"` | 通知形式（`markdown`/`macos`/`email`） |

---

## セキュリティに関する注意

- **パスワードはディスクに保存されません。** `setup` コマンドでのみ使用し、メモリから即削除します。
- **トークンファイルは `chmod 600` で保護されます。** 自分のユーザーのみ読める設定です。
- **`~/.config/shizen_lec_helper/` 配下のファイルは機密情報です。** バックアップ時は注意してください。

---

_このファイルはAIエージェント向けの手順書です。ユーザーには `README.md` を案内してください。_
