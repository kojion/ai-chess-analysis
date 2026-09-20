# PGN分析プロジェクト

PGNの分析・解説・大会レポートを依頼されたら `.claude/skills/chess-game-review/SKILL.md` を読み、その手順を使う（Claude Codeではスキルとして自動認識される）。
実装変更の検証: `<venv-python> -m unittest discover -s tests -v`（`<venv-python>` は macOS/Linuxなら `.venv/bin/python`、Windowsなら `.venv\Scripts\python.exe`）。
Stockfishによる計算結果と人間向けの解釈を区別し、白視点の評価と手番側の損失を混同しない。

解析結果と完成記事は `output/<日付>-<相手>/`（例: `output/2026-09-20-evgen1y57/`）に統一する。対面の大会棋譜は `<日付>-<大会>-<相手>`、同日・同相手が重なるときは末尾に `-2`。複数局入りのPGNだけ `output/<名前>/game-NNN/` に分かれる。完成記事は `article.md`、下書きは `draft.md`、PGN・解析JSON・局面図も同じ対局ディレクトリに保存し、`reviews/` などへ複製しない。既存対局は同じ保存先を再利用する。成果物はGit管理し、新しい記事はトップの `README.md` に相対リンクを追加する。
