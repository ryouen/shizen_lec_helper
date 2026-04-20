# shizen_lec_helper

シゼンカンMBAのSOS（Moodle）から授業資料・動画を自動でダウンロードし、締切一覧をMarkdownで管理する軽量ツールです。

Claude Code、Gemini CLI、Codex、ChatGPTなど、どのAIエージェントとも組み合わせて使えます。

---

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

---

## AIにセットアップしてもらう

このツールのセットアップはAIエージェントに任せるのが最も簡単です。

**Claude Code、Gemini CLI、ChatGPT等のAIに以下を伝えてください:**

> 「このフォルダの `AI_SETUP.md` を読んで、セットアップを手伝ってください」

AIが環境チェックからMoodleトークン取得、初回同期まで案内してくれます。

---

## 自分でセットアップする場合

必要環境: Python 3.10以上

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# または uv を使う場合
uv pip install -r requirements.txt

# セットアップ（Moodleトークン取得 + 設定ファイル生成）
python -m shizen_lec_helper setup

# コース一覧を確認
python -m shizen_lec_helper courses --auto-detect

# 同期実行
python -m shizen_lec_helper sync
```

---

## 主なコマンド

| コマンド | 説明 |
|---------|------|
| `python -m shizen_lec_helper setup` | 初回セットアップ（トークン取得 + 設定生成） |
| `python -m shizen_lec_helper sync` | 授業資料・動画を同期 |
| `python -m shizen_lec_helper sync --dry-run` | ダウンロード対象の確認（書き込みなし） |
| `python -m shizen_lec_helper deadlines` | 締切一覧を表示＆`_deadlines.md`を更新 |
| `python -m shizen_lec_helper status` | 設定・最終同期日時・ディスク使用量を表示 |
| `python -m shizen_lec_helper courses` | コース一覧とアクティブ判定を表示 |

### テスト隔離フラグ

全コマンドで使えるグローバルフラグ:

| フラグ | 環境変数 | デフォルト | 説明 |
|--------|----------|---------|------|
| `--config-dir PATH` | `SLH_CONFIG_DIR` | `~/.config/shizen_lec_helper/` | 設定・トークン・状態ファイルの場所を上書き |
| `--base-path PATH` | `SLH_BASE_PATH` | `~/Shizenkan/` | ダウンロード先の場所を上書き |

優先順位: CLIフラグ > 環境変数 > デフォルトパス

---

## 保存先フォルダ構造

```
~/Shizenkan/
├── FINANCE_EN_2027/
│   ├── Session 1 - Introduction/
│   │   ├── slides.pdf
│   │   └── assignment.pdf
│   ├── Session 2 - .../
│   ├── LEC_VIDEO/
│   │   └── Lecture_Video_Session1.mp4
│   └── _links.md
├── MARKETING_EN_2027/
│   └── ...
└── _deadlines.md        ← 全コース横断の締切一覧
```

---

## 必要環境

- **Python**: 3.10以上
- **ストレージ**: 50GB以上の空き推奨
  - 動画1本あたり約500〜900MB（中央値625MB）
  - 1コースあたり3〜11GB
  - 学期全体で10〜20GB超になることがあります
- **動画ダウンロードに必要**: `yt-dlp`（自動インストール）、`ffmpeg`（Homebrewでインストール推奨）

### ffmpegのインストール（Mac）
```bash
brew install ffmpeg
```

---

## 設定ファイルの場所

- 設定: `~/.config/shizen_lec_helper/config.json`
- トークン: `~/.config/shizen_lec_helper/moodle-token.json`（パーミッション600、パスワードは保存されません）
- 同期状態: `~/.config/shizen_lec_helper/state.json`

---

## ライセンス

MIT License
