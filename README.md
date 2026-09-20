# ai-chess-analysis

PGNをローカルのStockfishで解析し、Codex / Claude Codeで日本語の対局解説を仕上げるプロジェクト。APIキーやMCPサーバーは不要です。macOS と Windows に対応します。

## 対局解説

- [lichess：Harshit27092018戦・黒番（2026年9月19日）](output/2026-09-19-lichess-harshit27092018/game-001/article.md) — 局面図5枚付き。白の17.a4をとがめた17...Nd4と、勝勢での19...Bc5を振り返ります。
- [lichess：Mohammed1972戦・白番（2026年9月20日）](output/2026-09-20-lichess-mohammed1972/game-001/article.md) — 局面図5枚付き。黒のミス直後に3度逃したh4と、23.Qa5?でルークの守りが外れた場面を振り返ります。

解析結果と完成した解説は `output/<対局名>/game-NNN/` にまとめて保存します。完成記事は `article.md`、下書きは `draft.md` とし、局面図・PGN・解析JSONも同じ対局ディレクトリに置いて相対リンクで参照します。GitHub上でそのまま読めます。入力棋譜は `games/` に保存します。

新しい記事を作成したら、この一覧にもリンクを追加してください。対局の成果物はGitで管理し、サンプル出力（`output/sample/`）と公開用の一時ファイル（`output/*/publish/`）は管理対象外です。

## セットアップ

Python 3.10以上を使用します。Python用ライブラリはpython-chessの本体パッケージ `chess` を固定しています。以降のコマンドでは、仮想環境のPythonを次のように表記します。

| OS | 仮想環境のPython |
|---|---|
| macOS / Linux | `.venv/bin/python` |
| Windows | `.venv\Scripts\python.exe` |

### macOS

```bash
brew install stockfish
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### Windows（PowerShell）

```powershell
winget install Stockfish.Stockfish
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

wingetで入るStockfishの実体は `stockfish-windows-x86-64-universal.exe` で、`stockfish` というコマンド名では解決できないことがあります（`Get-Command stockfish` で確認）。その場合は、`.exe` まで含めたフルパスを環境変数 `STOCKFISH_PATH` に設定してください（設定後に開いたターミナルから有効）。

```powershell
$exe = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-universal.exe'
[Environment]::SetEnvironmentVariable('STOCKFISH_PATH', $exe, 'User')
```

## 棋譜を解析する

```bash
.venv/bin/python scripts/analyze_game.py examples/sample.pgn --output output/sample
.venv/bin/python scripts/analyze_game.py games/my-game.pgn --output output/my-game --orientation black
```

Windowsでは `.venv\Scripts\python.exe scripts\analyze_game.py ...` に読み替えてください。出力ファイルはOSによらずLF改行で保存されます。

`games/my-game.pgn` は自身の棋譜のパスに置き換えてください。UTF-8のPGNに対応し、複数対局がある場合も順番に処理します。通常チェスのみ対応。コメントや分岐は分析せず、本譜を使います。不正な棋譜はエラーにします。

出力例:

```text
output/my-game/game-001/
├── game.pgn
├── game.analysis.json
├── draft.md
├── article.md（解説を仕上げた後に保存）
└── images/position-01.svg ...
```

CLIは計算根拠・局面図・事実中心の日本語下書きを作成します。このプロジェクトをCodexまたはClaude Codeで開いて、次のように頼むと、スキルの手順で説明を仕上げて `article.md` に保存できます。

> games/my-game.pgnを解析して。私は黒です。重要局面を3〜5個選び、初級者向けに改善点を説明してください。

> output/my-game/game-001/game.analysis.jsonを使って、ブログ向けの解説に仕上げて。

スキルの実体は `.claude/skills/chess-game-review/SKILL.md` です。Claude Codeはプロジェクトのスキルとして自動で認識し、Codexはプロジェクトの `AGENTS.md` から参照します（Claude Codeは `CLAUDE.md` 経由で `AGENTS.md` を取り込みます）。個人用のグローバル設定は不要です。

## 候補外の局面を再確認する

自動選定は、すでに大差の局面での悪手（期待スコアの差が出にくい）や、軽量解析で見えないメイトを拾えないことがあります。気になる手は、解析済みの対局ディレクトリを指定して、深く探索し直せます。

```bash
.venv/bin/python scripts/verify_positions.py output/my-game/game-001 17.a4 34.g4 --seconds 6 --multipv 4
```

局面は半手番号（`33`）または手の表記（`17.a4`、黒の手は `17...Nd4`）で指定します。結果は `verification.analysis.json` に保存され、構造は `game.analysis.json` の `deep` と同じです（`candidates`・`played`・`metrics`）。実行のたびにファイル全体が上書きされるため、必要な局面をまとめて指定してください。`--seconds`（既定6秒）、`--multipv`（既定4）、`--engine`、`--threads`、`--hash` で変更できます。Windowsでは `.venv\Scripts\python.exe scripts\verify_positions.py ...` に読み替えてください。

## 記事用の局面図を作る

自動生成される図（`images/position-NN.svg`）とは別に、記事に載せる局面を選んで図を作れます。実戦手は赤、最善候補は緑の矢印で描き、実戦手が最善なら緑だけにします。最善候補は、あれば `verification.analysis.json`、なければ `game.analysis.json` の詳細解析から取ります。

```bash
.venv/bin/python scripts/render_review.py output/my-game/game-001 17.a4 17...Nd4 19...f5 --orientation black --arrow 19...f5:d4f3:blue
```

図は、指定した局面を手数順に `images/review-01.svg` から保存します。`--arrow 局面:UCI[:色]` で説明用の矢印を足せます（色の既定は青。複数指定可）。既存の図は `--force` を付けない限り上書きしません。あとから図を足すときは `--start 6` のように番号を指定してください。Windowsでは `.venv\Scripts\python.exe scripts\render_review.py ...` に読み替えてください。

## 探索と設定

- 全局面: 1探索0.15秒。期待スコアの低下とメイトの変化から候補を抽出。
- 詳細解析: 最大8局面、1探索2秒、MultiPV 3。実戦手が候補外なら追加探索。
- 重要局面: 詳細解析後の候補から最大4局面。AIアシスタントが内容を見て最終選定。
- CPU: 既定1スレッド、ハッシュ128MB。`--threads` と `--hash` で変更。
- `--quick 0.3 --deep 5 --candidates 12 --positions 5 --multipv 3` などで調整。
- `--engine /path/to/stockfish` または環境変数 `STOCKFISH_PATH` でエンジン指定。Windowsでフルパスを渡すときは `.exe` まで書いてください（例: `--engine C:\tools\stockfish\stockfish.exe`）。
- `--orientation white|black|mover` で盤面の向きを変更。

80半手なら既定で約30〜50秒が目安です。探索時間は各呼び出しの予算であり、棋力の保証や固定深度ではありません。

## 評価の読み方・限界

JSONの `cp` は白視点のセンチポーン（100 = 表示上1.00）、`mate` は白視点のメイト表記。メイトを大きなcpに変換しません。`expectation_white` はpython-chessの固定sf16モデルが出す期待スコア（勝ち＋引き分けの半分）で、人間の勝率ではありません。

手番側の期待スコア低下が5/10/20ポイント以上なら、それぞれ不正確な手/ミス/大きなミスの「候補」とします。メイトの見逃し・許容は別に記録します。これらは本ツール独自の仮基準です。勝勢間のcp変動だけで大きなミスと決めつけません。第2候補との差も保存しますが、唯一手とは断定しません。

軽量解析は前後の局面を比較、詳細解析は同じ手番の根局面で推奨手と実戦手を比較します。探索ノイズによって実戦手の評価が上回ることもあります。選ばれなかった静かな好手・戦術を網羅する保証はありません。

JSONにはFEN、SAN/UCI、PV、探索深度・ノード数、エンジン名、設定を記録します。入力・設定・エンジン実行ファイル・ライブラリが一致するとJSONを再利用し、`--force` で再計算できます。再利用時もStockfishの起動は必要です。文章だけの編集ではJSONを直接使ってください。再実行は `draft.md` とSVGを更新しますが、`article.md` は変更しません。外部NNUEを差し替えた場合は `--force` を使ってください。

キャッシュキーにはエンジン実行ファイルのSHA-256が含まれます。そのため、別のOSやバージョンのStockfishで生成済みの `output/` を再実行するとキャッシュが効かず、解析が丸ごとやり直されて評価値も変わります。公開済みの記事の根拠値を保つため、既存の対局は再解析せず、文章の修正は既存のJSONを使って行ってください。

## 検証

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Windowsでは `.venv\Scripts\python.exe -m unittest discover -s tests -v` です。統合テスト（実エンジンの起動）はStockfishが見つからない場合にスキップされます。`STOCKFISH_PATH` の設定を確認してください。

API参考: [python-chess engine documentation](https://python-chess.readthedocs.io/en/latest/engine.html)
