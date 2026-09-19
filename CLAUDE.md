@AGENTS.md

## Windows での補足

- Python は `.venv\Scripts\python.exe` を使う（`.venv/bin/python` は存在しない）。
- Stockfish は `winget install Stockfish.Stockfish` で入るが、実体が `stockfish-windows-x86-64-universal.exe` でPATH上の `stockfish` では解決できない場合がある。その場合はユーザー環境変数 `STOCKFISH_PATH` に `.exe` まで含めたフルパスを設定する。環境変数は設定後に起動したターミナル・Claude Codeから有効になる。
- 出力ファイルはLFで保存される（`scripts/analyze_game.py` が `newline="\n"` を指定）。Gitで管理する成果物にCRLFを混入させない。
- macOSで生成した既存の `output/` は再解析しない。キャッシュキーにエンジンのハッシュが含まれるため、Windowsで再実行すると全再計算になり、解析値が変わる。
