# shizen_lec_helper

Moodleから授業資料・動画を自動ダウンロードし、締切一覧をMarkdownで管理する軽量ツール。
A lightweight tool that auto-downloads course materials and videos from Moodle, and manages deadlines as Markdown.

Claude Code / Gemini CLI / Codex / ChatGPT など、どのAIエージェントとも組み合わせて使えます。
Works with any AI agent: Claude Code, Gemini CLI, Codex, ChatGPT, etc.

---

**日本語:** 本ツールはMoodleで学習する学生が自分の履修コースの資料を個人学習用にローカル保存することを想定しています。大学・コース・教員が本ツールのような利用を禁止している場合は、それに従ってください。

本ツールを使って取得した資料を第三者に再配布することは禁止です。本ツールの使用によって生じたいかなる規則違反・不利益についても、作者は責任を負いません。

**English:** This tool is intended for students learning on Moodle to locally save materials from their own enrolled courses for personal study. If your university, course, or instructor prohibits this kind of use, please follow their rules.

Redistributing materials obtained through this tool to third parties is prohibited. The author assumes no responsibility for any rule violations or adverse consequences resulting from the use of this tool.

---

# 日本語

## 入手方法

### A. Git でクローン（推奨）
```bash
git clone https://github.com/ryouen/shizen_lec_helper.git
cd shizen_lec_helper
```

### B. Zip ダウンロード
1. https://github.com/ryouen/shizen_lec_helper の緑の「Code」ボタン
2. 「Download ZIP」を選択
3. 解凍して好きな場所に置く

## AIにセットアップしてもらう（推奨）

**Claude Code / Gemini CLI / ChatGPT 等のAIに以下を伝えてください:**

> 「このフォルダの `AI_SETUP.md` を読んで、セットアップを手伝ってください」

AIが環境チェックからMoodleトークン取得、初回同期まで案内します。

## 自分でセットアップする場合

必要環境: Python 3.10 以上

```bash
# 依存パッケージのインストール
pip install -r requirements.txt
# または uv: uv pip install -r requirements.txt

# セットアップ（Moodleトークン取得 + 設定ファイル生成）
python -m shizen_lec_helper setup

# アクティブコースの自動検出
python -m shizen_lec_helper courses --auto-detect

# 同期実行
python -m shizen_lec_helper sync
```

## Moodleトークン取得（非対話モード）

AIエージェントに手伝ってもらう場合は、パスワードファイル経由の方式を使います:

1. パスワードを保存するファイルを作成:
   エディタで `~/.shizen_lec_password` を開き、パスワードを1行だけ入力して保存
2. パーミッション変更:
   ```bash
   chmod 600 ~/.shizen_lec_password
   ```
3. セットアップ実行（`EMAIL` は自分のMoodleアカウント）:
   ```bash
   python -m shizen_lec_helper setup --username EMAIL --creds-file ~/.shizen_lec_password
   ```
4. 成功するとファイルが自動削除されます。失敗時は残るので、
   パスワードを修正して再実行できます。

詳細手順は `AI_SETUP.md` の「Step 4 方式A」を参照してください。

## 主なコマンド

| コマンド | 説明 |
|---------|------|
| `python -m shizen_lec_helper setup` | 初回セットアップ（対話型）|
| `python -m shizen_lec_helper setup --username EMAIL --creds-file PATH` | 初回セットアップ（非対話型）|
| `python -m shizen_lec_helper sync` | 授業資料・動画を同期 |
| `python -m shizen_lec_helper sync --dry-run` | DL対象の確認（書き込みなし） |
| `python -m shizen_lec_helper deadlines` | 締切一覧＋`_deadlines.md`更新 |
| `python -m shizen_lec_helper status` | 設定・最終同期・ディスク使用量 |
| `python -m shizen_lec_helper courses` | コース一覧とアクティブ判定 |

### テスト隔離フラグ

| フラグ | 環境変数 | デフォルト | 説明 |
|--------|----------|---------|------|
| `--config-dir PATH` | `SLH_CONFIG_DIR` | `~/.config/shizen_lec_helper/` | 設定ファイルの場所を上書き |
| `--base-path PATH` | `SLH_BASE_PATH` | `~/Shizenkan/` | ダウンロード先を上書き |

優先順位: CLIフラグ > 環境変数 > デフォルト

## 締切一覧の出力イメージ

`python -m shizen_lec_helper deadlines` を実行すると、2つの形式で締切が表示されます。

**ターミナル出力:**

```
Course                    Days  Due                   Assignment
--------------------------------------------------------------------------------
SUSTAINABILITY_EN_2027       0d  2026-04-20 23:59 JST  Pre-session Assignments 2 !
CORE_EN_2027                 5d  2026-04-26 12:00 JST  Post-assignment_worksheet 11
ENVISION_EN_2027             6d  2026-04-26 23:59 JST  FINAL INDIVIDUAL REPORT
SUSTAINABILITY_EN_2027      13d  2026-05-03 23:59 JST  Post-Class Assignment
```

`!` マーク: 締切まで2日以内。

**Markdownファイル (`~/Shizenkan/_deadlines.md`):**

| Course | Assignment | Due | Days Left |
|--------|-----------|-----|----------|
| SUSTAINABILITY_EN_2027 | 🔴 Pre-session Assignments 2 | 2026-04-20 23:59 JST | 0d |
| CORE_EN_2027 | 🟡 Post-assignment_worksheet 11 | 2026-04-26 12:00 JST | 5d |
| ENVISION_EN_2027 | 🟡 FINAL INDIVIDUAL REPORT | 2026-04-26 23:59 JST | 6d |
| SUSTAINABILITY_EN_2027 | Post-Class Assignment | 2026-05-03 23:59 JST | 13d |

色分け: 🔴 2日以内 / 🟡 7日以内 / 無印 8日以降（最大60日先まで表示）

Obsidianやお好きなエディタで `_deadlines.md` を開いて常時参照できます。自分のAIに「このファイルを見て今週の優先順位を教えて」と渡すのも便利です。

## 保存先フォルダ構造

```
~/Shizenkan/
├── FINANCE_EN_2027/
│   ├── Session 1 - Introduction/
│   │   ├── slides.pdf
│   │   └── assignment.pdf
│   ├── LEC_VIDEO/
│   │   └── Lecture_Video_Session1.mp4
│   └── _links.md
└── _deadlines.md        ← 全コース横断の締切一覧
```

## 必要環境

- **Python 3.10 以上**
- **ストレージ 50GB 以上推奨**
  - 動画1本 約 500〜900MB（中央値 625MB）
  - 1コース 3〜11GB
  - 学期全体で 10〜20GB 超になることがあります
- **動画DLに必要**: `yt-dlp`（自動インストール）、`ffmpeg`（Mac: `brew install ffmpeg`）

## 設定ファイルの場所

- 設定: `~/.config/shizen_lec_helper/config.json`
- トークン: `~/.config/shizen_lec_helper/moodle-token.json`（パーミッション600、パスワードは保存されません）
- 同期状態: `~/.config/shizen_lec_helper/state.json`

---

# English

## Installation

### A. Git clone (recommended)
```bash
git clone https://github.com/ryouen/shizen_lec_helper.git
cd shizen_lec_helper
```

### B. Zip download
1. Visit https://github.com/ryouen/shizen_lec_helper and click the green "Code" button
2. Choose "Download ZIP"
3. Unzip and place the folder wherever you like

## Let an AI set it up for you (recommended)

**Tell your AI (Claude Code / Gemini CLI / ChatGPT / etc.):**

> "Please read `AI_SETUP.md` in this folder and help me set this up."

The AI will guide you through environment checks, Moodle token acquisition, and your first sync.

## Manual setup

Required: Python 3.10+

```bash
# Install dependencies
pip install -r requirements.txt
# or with uv: uv pip install -r requirements.txt

# First-time setup (Moodle token + config generation)
python -m shizen_lec_helper setup

# Auto-detect active courses
python -m shizen_lec_helper courses --auto-detect

# Run sync
python -m shizen_lec_helper sync
```

## Moodle token acquisition (non-interactive mode)

When working with an AI agent, use the password file method:

1. Create the password file in your editor — open `~/.shizen_lec_password`
   and type just the password on one line, then save.
2. Set permissions:
   ```bash
   chmod 600 ~/.shizen_lec_password
   ```
3. Run setup (replace `EMAIL` with your Moodle account email):
   ```bash
   python -m shizen_lec_helper setup --username EMAIL --creds-file ~/.shizen_lec_password
   ```
4. On success the file is deleted automatically. On failure it is kept so
   you can fix the password and retry.

See `AI_SETUP.md` Step 4 Method A for the detailed flow.

## Commands

| Command | Description |
|---------|-------------|
| `python -m shizen_lec_helper setup` | First-time setup (interactive) |
| `python -m shizen_lec_helper setup --username EMAIL --creds-file PATH` | First-time setup (non-interactive) |
| `python -m shizen_lec_helper sync` | Sync course materials and videos |
| `python -m shizen_lec_helper sync --dry-run` | Preview downloads (no writes) |
| `python -m shizen_lec_helper deadlines` | Show deadlines and update `_deadlines.md` |
| `python -m shizen_lec_helper status` | Show config, last sync, disk usage |
| `python -m shizen_lec_helper courses` | List enrolled courses with active status |

### Isolation flags

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--config-dir PATH` | `SLH_CONFIG_DIR` | `~/.config/shizen_lec_helper/` | Override config location |
| `--base-path PATH` | `SLH_BASE_PATH` | `~/Shizenkan/` | Override download location |

Precedence: CLI flag > env var > default

## Deadline output examples

Running `python -m shizen_lec_helper deadlines` produces two formats.

**Terminal output:**

```
Course                    Days  Due                   Assignment
--------------------------------------------------------------------------------
SUSTAINABILITY_EN_2027       0d  2026-04-20 23:59 JST  Pre-session Assignments 2 !
CORE_EN_2027                 5d  2026-04-26 12:00 JST  Post-assignment_worksheet 11
ENVISION_EN_2027             6d  2026-04-26 23:59 JST  FINAL INDIVIDUAL REPORT
SUSTAINABILITY_EN_2027      13d  2026-05-03 23:59 JST  Post-Class Assignment
```

`!` marks deadlines within 2 days.

**Markdown file (`~/Shizenkan/_deadlines.md`):**

| Course | Assignment | Due | Days Left |
|--------|-----------|-----|----------|
| SUSTAINABILITY_EN_2027 | 🔴 Pre-session Assignments 2 | 2026-04-20 23:59 JST | 0d |
| CORE_EN_2027 | 🟡 Post-assignment_worksheet 11 | 2026-04-26 12:00 JST | 5d |
| ENVISION_EN_2027 | 🟡 FINAL INDIVIDUAL REPORT | 2026-04-26 23:59 JST | 6d |
| SUSTAINABILITY_EN_2027 | Post-Class Assignment | 2026-05-03 23:59 JST | 13d |

Color coding: 🔴 within 2 days / 🟡 within 7 days / no marker from 8 days onward (up to 60 days).

You can open `_deadlines.md` in Obsidian or any editor for always-visible reference. You can also pass the file to your AI: "Look at this file and tell me my priorities this week."

## Folder structure

```
~/Shizenkan/
├── FINANCE_EN_2027/
│   ├── Session 1 - Introduction/
│   │   ├── slides.pdf
│   │   └── assignment.pdf
│   ├── LEC_VIDEO/
│   │   └── Lecture_Video_Session1.mp4
│   └── _links.md
└── _deadlines.md        ← cross-course deadline summary
```

## Requirements

- **Python 3.10+**
- **50GB+ free storage recommended**
  - Per video: 500–900MB (median 625MB)
  - Per course: 3–11GB
  - Full semester: can exceed 10–20GB
- **Required for video downloads**: `yt-dlp` (auto-installed), `ffmpeg` (Mac: `brew install ffmpeg`)

## Config file locations

- Config: `~/.config/shizen_lec_helper/config.json`
- Token: `~/.config/shizen_lec_helper/moodle-token.json` (permissions 600, no password stored)
- Sync state: `~/.config/shizen_lec_helper/state.json`

---

## License

MIT License
