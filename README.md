# shizenkan-lite

シゼンカンMBAのSOS（Moodle）から授業資料・動画を自動でダウンロードし、締切一覧をMarkdownで管理する軽量ツールです。

Claude Code、Gemini CLI、Codex、ChatGPTなど、どのAIエージェントとも組み合わせて使えます。

---

## 入手方法

### A. Git でクローン（推奨）
```bash
git clone https://github.com/[user]/shizenkan-lite.git
cd shizenkan-lite
```

### B. Zip ダウンロード
1. https://github.com/[user]/shizenkan-lite の緑の「Code」ボタン
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
python -m shizenkan_lite setup

# コース一覧を確認
python -m shizenkan_lite courses --auto-detect

# 同期実行
python -m shizenkan_lite sync
```

---

## 主なコマンド

| コマンド | 説明 |
|---------|------|
| `python -m shizenkan_lite setup` | 初回セットアップ（トークン取得 + 設定生成） |
| `python -m shizenkan_lite sync` | 授業資料・動画を同期 |
| `python -m shizenkan_lite sync --dry-run` | ダウンロード対象の確認（書き込みなし） |
| `python -m shizenkan_lite deadlines` | 締切一覧を表示＆`_deadlines.md`を更新 |
| `python -m shizenkan_lite status` | 設定・最終同期日時・ディスク使用量を表示 |
| `python -m shizenkan_lite courses` | コース一覧とアクティブ判定を表示 |

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

- 設定: `~/.config/shizenkan-lite/config.json`
- トークン: `~/.config/shizenkan-lite/moodle-token.json`（パーミッション600、パスワードは保存されません）
- 同期状態: `~/.config/shizenkan-lite/state.json`

---

## ライセンス

MIT License
