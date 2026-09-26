# ai-chess-analysis

PGNをローカルのStockfishで解析し、Codex / Claude Codeで日本語の対局解説を仕上げるプロジェクト。APIキーやMCPサーバーは不要です。macOS と Windows に対応します。

## 対局解説

- [lichess：Harshit27092018戦・黒番（2026年9月19日）](output/2026-09-19-harshit27092018/article.md) — 局面図5枚付き。白の17.a4をとがめた17...Nd4と、勝勢での19...Bc5を振り返ります。
- [lichess：Mohammed1972戦・白番（2026年9月20日）](output/2026-09-20-mohammed1972/article.md) — 局面図5枚付き。黒のミス直後に3度逃したh4と、23.Qa5?でルークの守りが外れた場面を振り返ります。
- [lichess：Evgen1y57戦・黒番（2026年9月20日）](output/2026-09-20-evgen1y57/article.md) — 局面図5枚付き。25.Qa4?をとがめた25...Nc5!と、優勢を手放した27...Kf8?・29...Nd3?を振り返ります。
- [lichess：Hamidsadr2戦・黒番（2026年9月20日）](output/2026-09-20-hamidsadr2/article.md) — 局面図5枚付き。9.h3?で空いたh2への狙いと、最善手の9...Bd6!からクイーンを奪った10手を振り返ります。
- [lichess：jawher5241戦・白番（2026年9月25日）](output/2026-09-25-jawher5241/article.md) — 局面図3枚付き。約+6の勝勢から18.d5?でf2を取られた場面と、まだ優勢だった投了局面（19.Kh1）を振り返ります。
- [lichess：pykkis戦・黒番（2026年9月26日）](output/2026-09-26-pykkis/article.md) — 局面図5枚付き。7.Qb5+?に対して見送った7...Nc6!と、互角から崩れた24...Nxd2?を振り返ります。

解析結果と完成した解説は `output/<日付>-<相手>/`（例: `output/2026-09-20-evgen1y57/`）にまとめて保存します。対面の大会棋譜は `<日付>-<大会>-<相手>`、同じ日に同じ相手と複数局あるときは末尾に `-2` を付けます。完成記事は `article.md`、下書きは `draft.md` とし、局面図・PGN・解析JSONも同じ対局ディレクトリに置いて相対リンクで参照します。GitHub上でそのまま読めます。入力棋譜は `games/` に保存します。

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

## lichess から対局を取得する

`scripts/fetch_games.py` が、lichess の対局を `games/` に保存します。ファイル名も中身も、対局ページからの手動ダウンロードと同じです（`lichess_pgn_日付_白_vs_黒.対局ID.pgn`）。標準ライブラリだけで動きます。

**1局だけ（トークン不要）：** 対局のURLかIDを渡します。

```bash
.venv/bin/python scripts/fetch_games.py https://lichess.org/pb65np0J
```

**新しい対局を一括で（要トークン）：** レート戦のクラシカル（`--perf` で種類、`--include-casual` でレートなしも）のうち、`games/` にある最新の対局より新しいものだけを取得します。

```bash
.venv/bin/python scripts/fetch_games.py --user zbxah
```

`--since 2026-09-01`（UTC）で開始日を、`--max` で最大局数を指定できます。`games/` が空で `--since` もないときは、直近10局だけを取得します。

**取得から解析まで一度に：** `--analyze` を付けると、取得した対局を標準の設定（`--quick 0.3 --candidates 12 --positions 6`）で解析します。`--user` が白番か黒番かを判断して盤面の向きを決め、`output/<日付>-<相手>/` に保存します。すでに解析済みの対局は飛ばします。`games/` に取得済みの対局のURLかIDを渡して、解析だけをやり直すこともできます。

```bash
.venv/bin/python scripts/fetch_games.py --user zbxah --analyze
```

`--dry-run` を付けると、保存も解析もせずに、対象だけを表示します。Windowsでは `.venv\Scripts\python.exe scripts\fetch_games.py ...` に読み替えてください。

### ユーザー名とトークン

- ユーザー名は `--user`、または環境変数 `LICHESS_USER` で指定します。
- 一括取得には、lichessの個人用APIトークンが必要です。https://lichess.org/account/oauth/token で、権限（スコープ）を選ばずに発行し、環境変数 `LICHESS_TOKEN` に設定します（公式仕様で、この機能に必要なスコープはありません）。トークンは秘密の情報なので、コマンドの引数やリポジトリには書かず、環境変数だけで渡します。Windows（PowerShell）では次のとおりで、設定後に開いたターミナルから有効です。

```powershell
[Environment]::SetEnvironmentVariable('LICHESS_TOKEN', '<トークン>', 'User')
```

- lichessの案内に従い、リクエストは1つずつ送り、制限（429）のときは60秒待って再試行します。
- 証明書の検証は常に有効です。Windowsでは、ルート証明書のストアだけを信頼の起点にします（中間証明書のストアに期限切れの証明書が残っていると、Pythonが `certificate has expired` で失敗するため）。独自のCAバンドルを使うときは、環境変数 `SSL_CERT_FILE` で指定します。

## 棋譜を解析する

```bash
.venv/bin/python scripts/analyze_game.py examples/sample.pgn --output output/sample
.venv/bin/python scripts/analyze_game.py games/my-game.pgn --output output/my-game --orientation black
```

Windowsでは `.venv\Scripts\python.exe scripts\analyze_game.py ...` に読み替えてください。出力ファイルはOSによらずLF改行で保存されます。

`games/my-game.pgn` は自身の棋譜のパスに置き換えてください。UTF-8のPGNに対応し、複数対局がある場合も順番に処理します（1局のPGNは `--output` の直下、複数局のPGNは `--output/game-001/`、`game-002/` … に保存します。1局のPGNに後から局を足して再実行すると保存先が切り替わるので、直下の旧ファイルは手で片付けてください）。通常チェスのみ対応。コメントや分岐は分析せず、本譜を使います。不正な棋譜はエラーにします。

出力例:

```text
output/my-game/
├── game.pgn
├── game.analysis.json
├── draft.md
├── article.md（解説を仕上げた後に保存）
└── images/position-01.svg ...
```

CLIは計算根拠・局面図・事実中心の日本語下書きを作成します。このプロジェクトをCodexまたはClaude Codeで開いて、次のように頼むと、スキルの手順で説明を仕上げて `article.md` に保存できます。

> games/my-game.pgnを解析して。私は黒です。重要局面を3〜5個選び、初級者向けに改善点を説明してください。

> output/my-game/game.analysis.jsonを使って、ブログ向けの解説に仕上げて。

スキルの実体は `.claude/skills/chess-game-review/SKILL.md` です。Claude Codeはプロジェクトのスキルとして自動で認識し、Codexはプロジェクトの `AGENTS.md` から参照します（Claude Codeは `CLAUDE.md` 経由で `AGENTS.md` を取り込みます）。個人用のグローバル設定は不要です。

## 候補外の局面を再確認する

自動選定は、すでに大差の局面での悪手（期待スコアの差が出にくい）や、軽量解析で見えないメイトを拾えないことがあります。気になる手は、解析済みの対局ディレクトリを指定して、深く探索し直せます。

```bash
.venv/bin/python scripts/verify_positions.py output/my-game 17.a4 34.g4 --seconds 6 --multipv 4
```

局面は半手番号（`33`）または手の表記（`17.a4`、黒の手は `17...Nd4`）で指定します。結果は `verification.analysis.json` に保存され、構造は `game.analysis.json` の `deep` と同じです（`candidates`・`played`・`metrics`）。実行のたびにファイル全体が上書きされるため、必要な局面をまとめて指定してください。`--seconds`（既定6秒）、`--multipv`（既定4）、`--engine`、`--threads`、`--hash` で変更できます。Windowsでは `.venv\Scripts\python.exe scripts\verify_positions.py ...` に読み替えてください。

## 記事用の局面図を作る

自動生成される図（`images/position-NN.svg`）とは別に、記事に載せる局面を選んで図を作れます。実戦手は赤、最善候補は緑の矢印で描き、実戦手が最善なら緑だけにします。最善候補は、あれば `verification.analysis.json`、なければ `game.analysis.json` の詳細解析から取ります。

```bash
.venv/bin/python scripts/render_review.py output/my-game 17.a4 17...Nd4 19...f5 --orientation black --arrow 19...f5:d4f3:blue
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
