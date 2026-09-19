# ai-chess-analysis

PGNをローカルのStockfishで解析し、Codexで日本語の対局解説を仕上げるプロジェクト。APIキーやMCPサーバーは不要です。

## 公開した対局解説

- [町田シルバーウィークオープン：Vyom Walia戦・黒番（2026年9月19日）](reviews/2026-09-19-machida-walia/README.md) — 局面図5枚付き。中央の前進から昇格メイトまでを振り返ります。

解説は `reviews/` にMarkdownで保存し、局面図・PGN・解析JSONを相対リンクで参照しています。GitHub上でそのまま読めます。

## セットアップ（macOS）

```bash
brew install stockfish
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Python 3.10以上を使用します。Python用ライブラリはpython-chessの本体パッケージ `chess` を固定しています。

## 棋譜を解析する

```bash
.venv/bin/python scripts/analyze_game.py examples/sample.pgn --output output/sample
.venv/bin/python scripts/analyze_game.py games/my-game.pgn --output output/my-game --orientation black
```

`games/my-game.pgn` は自身の棋譜のパスに置き換えてください。UTF-8のPGNに対応し、複数対局がある場合も順番に処理します。通常チェスのみ対応。コメントや分岐は分析せず、本譜を使います。不正な棋譜はエラーにします。

出力例:

```text
output/my-game/game-001/
├── game.pgn
├── game.analysis.json
├── draft.md
└── images/position-01.svg ...
```

CLIは計算根拠・局面図・事実中心の日本語下書きを作成します。このプロジェクトをCodexで開いて、次のように頼むと、スキルの手順で説明を仕上げて `article.md` に保存できます。

> games/my-game.pgnを解析して。私は黒です。重要局面を3〜5個選び、初級者向けに改善点を説明してください。

> output/my-game/game-001/game.analysis.jsonを使って、ブログ向けの解説に仕上げて。

プロジェクトの `AGENTS.md` から `skills/chess-game-review/SKILL.md` を参照します。個人用のグローバル設定は不要です。

## 探索と設定

- 全局面: 1探索0.15秒。期待スコアの低下とメイトの変化から候補を抽出。
- 詳細解析: 最大8局面、1探索2秒、MultiPV 3。実戦手が候補外なら追加探索。
- 重要局面: 詳細解析後の候補から最大4局面。Codexが内容を見て最終選定。
- CPU: 既定1スレッド、ハッシュ128MB。`--threads` と `--hash` で変更。
- `--quick 0.3 --deep 5 --candidates 12 --positions 5 --multipv 3` などで調整。
- `--engine /path/to/stockfish` または環境変数 `STOCKFISH_PATH` でエンジン指定。
- `--orientation white|black|mover` で盤面の向きを変更。

80半手なら既定で約30〜50秒が目安です。探索時間は各呼び出しの予算であり、棋力の保証や固定深度ではありません。

## 評価の読み方・限界

JSONの `cp` は白視点のセンチポーン（100 = 表示上1.00）、`mate` は白視点のメイト表記。メイトを大きなcpに変換しません。`expectation_white` はpython-chessの固定sf16モデルが出す期待スコア（勝ち＋引き分けの半分）で、人間の勝率ではありません。

手番側の期待スコア低下が5/10/20ポイント以上なら、それぞれ不正確な手/ミス/大きなミスの「候補」とします。メイトの見逃し・許容は別に記録します。これらは本ツール独自の仮基準です。勝勢間のcp変動だけで大きなミスと決めつけません。第2候補との差も保存しますが、唯一手とは断定しません。

軽量解析は前後の局面を比較、詳細解析は同じ手番の根局面で推奨手と実戦手を比較します。探索ノイズによって実戦手の評価が上回ることもあります。選ばれなかった静かな好手・戦術を網羅する保証はありません。

JSONにはFEN、SAN/UCI、PV、探索深度・ノード数、エンジン名、設定を記録します。入力・設定・エンジン実行ファイル・ライブラリが一致するとJSONを再利用し、`--force` で再計算できます。再利用時もStockfishの起動は必要です。文章だけの編集ではJSONを直接使ってください。再実行は `draft.md` とSVGを更新しますが、`article.md` は変更しません。外部NNUEを差し替えた場合は `--force` を使ってください。

## 検証

```bash
.venv/bin/python -m unittest discover -s tests -v
```

API参考: [python-chess engine documentation](https://python-chess.readthedocs.io/en/latest/engine.html)
