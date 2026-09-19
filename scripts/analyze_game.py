#!/usr/bin/env python3
"""Local, two-pass PGN analysis. All serialized evaluations use White's POV."""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys

import chess
import chess.engine
import chess.pgn
import chess.svg

VERSION = 1


def score_data(score, ply):
    white = score.white()
    return {"cp": white.score(), "mate": white.mate(),
            "expectation_white": white.wdl(model="sf16", ply=ply).expectation()}


def relative(value, color):
    return value if color == chess.WHITE else -value


def loss_info(before, after, color):
    """Avoid treating mate distance as a large centipawn score."""
    loss = max(0.0, relative(before["expectation_white"] - after["expectation_white"], color))
    cp_loss = None
    if before["cp"] is not None and after["cp"] is not None:
        cp_loss = max(0, relative(before["cp"] - after["cp"], color))
    bm = relative(before["mate"], color) if before["mate"] is not None else None
    am = relative(after["mate"], color) if after["mate"] is not None else None
    reasons = []
    if bm is not None and bm > 0 and (am is None or am <= 0):
        reasons.append("missed_mate")
    if am is not None and am < 0 and (bm is None or bm >= 0):
        reasons.append("allowed_mate")
    # Mate(0) is the checkmated side; expectation supplies its unambiguous sign.
    if after["mate"] == 0 and relative(after["expectation_white"] - .5, color) < 0:
        if bm is None or bm >= 0:
            reasons.append("allowed_mate")
    label = "blunder_candidate" if loss >= .20 else "mistake_candidate" if loss >= .10 else "inaccuracy_candidate" if loss >= .05 else "stable"
    return {"cp_loss": cp_loss, "expectation_loss": round(loss, 5), "classification": label, "reasons": reasons}


def load_games(text):
    stream = io.StringIO(text)
    games = []
    while (game := chess.pgn.read_game(stream)) is not None:
        if game.errors:
            raise ValueError(f"対局{len(games)+1}: 不正なPGN: {game.errors[0]}")
        board = game.board()
        if board.chess960 or type(board) is not chess.Board or not board.is_valid():
            raise ValueError("通常チェスの有効な初期局面のみ対応しています")
        moves = list(game.mainline_moves())
        if not moves:
            raise ValueError(f"対局{len(games)+1}: 指し手がありません")
        for move in moves:
            if move not in board.legal_moves or board.is_game_over():
                raise ValueError(f"対局{len(games)+1}: 終局後または不正な指し手です")
            board.push(move)
        games.append(game)
    if not games:
        raise ValueError("PGNに対局がありません")
    return games


def search(engine, board, seconds, multipv=1, root_moves=None):
    outcome = board.outcome()
    if outcome:
        score = chess.engine.PovScore(chess.engine.Cp(0) if outcome.winner is None else chess.engine.Mate(0), board.turn)
        return [{"score": score_data(score, board.ply()), "pv_uci": [], "pv_san": [], "depth": 0, "nodes": 0}]
    infos = engine.analyse(board, chess.engine.Limit(time=seconds), multipv=multipv, root_moves=root_moves)
    results = []
    for info in infos:
        pv_board = board.copy()
        san = []
        pv = info.get("pv", [])[:12]
        for move in pv:
            san.append(pv_board.san(move))
            pv_board.push(move)
        results.append({"score": score_data(info["score"], board.ply()), "pv_uci": [m.uci() for m in pv],
                        "pv_san": san, "depth": info.get("depth"), "nodes": info.get("nodes")})
    return results


def priority(row):
    metrics = row.get("deep", row)["metrics"]
    return metrics["expectation_loss"] + .3 * len(metrics["reasons"])


def deep_review(engine, board, played, seconds, multipv):
    """Compare the played move with the engine's candidates from the same root and search budget."""
    lines = search(engine, board, seconds, multipv)
    # Include the actual move even when it falls outside MultiPV. Callers pass boards that keep game history.
    played_line = next((line for line in lines if line["pv_uci"] and line["pv_uci"][0] == played.uci()), None)
    if played_line is None:
        played_line = search(engine, board, seconds, root_moves=[played])[0]
    review = {"candidates": lines, "played": played_line,
              "metrics": loss_info(lines[0]["score"], played_line["score"], board.turn)}
    if len(lines) > 1:
        gap = loss_info(lines[0]["score"], lines[1]["score"], board.turn)["expectation_loss"]
        review["best_second_expectation_gap"] = gap
        review["only_move_candidate"] = gap >= .15
    return review


def analyze(engine, game, args):
    board = game.board()
    boards, rows = [], []
    before = search(engine, board, args.quick)[0]
    for ply, move in enumerate(game.mainline_moves(), 1):
        boards.append(board.copy())
        row = {"ply": ply, "move_number": board.fullmove_number, "side": "white" if board.turn else "black",
               "label": f'{board.fullmove_number}{"." if board.turn else "..."}{board.san(move)}',
               "played_uci": move.uci(), "played_san": board.san(move), "fen_before": board.fen(), "before": before}
        color = board.turn
        board.push(move)
        after = search(engine, board, args.quick)[0]
        row.update(fen_after=board.fen(), after=after, metrics=loss_info(before["score"], after["score"], color))
        rows.append(row)
        before = after
    candidates = sorted(rows, key=priority, reverse=True)[:args.candidates]
    for index, row in enumerate(candidates, 1):
        print(f'  詳細解析 {index}/{len(candidates)}: {row["label"]}', file=sys.stderr)
        row["deep"] = deep_review(engine, boards[row["ply"] - 1], chess.Move.from_uci(row["played_uci"]),
                                  args.deep, args.multipv)
    selected = sorted(candidates, key=priority, reverse=True)[:args.positions]
    return {"headers": dict(game.headers), "initial_fen": game.board().fen(), "moves": rows,
            "selected_plies": sorted(row["ply"] for row in selected)}


def evaluation(score):
    if score["mate"] is not None:
        winner = "白" if score["expectation_white"] > .5 else "黒"
        return f'{winner}のメイト（エンジン表記 #{score["mate"]}）'
    return f'{score["cp"]/100:+.2f}'


def render(game, dest, orientation):
    images = dest / "images"
    images.mkdir(exist_ok=True)
    h = game["headers"]
    text = [f'# {h.get("White", "白")} vs {h.get("Black", "黒")}', '',
            f'結果: {h.get("Result", "*")} / 日付: {h.get("Date", "?")}', '',
            'これはStockfishの計算結果に基づく解説下書きです。候補の選定と戦術・戦略の説明はAIアシスタントで仕上げます。', '',
            '評価値は常に白視点（＋は白有利）。メイトは数値評価と分けて表示します。', '',
            '「期待スコア」はsf16モデルによる勝ち＋引き分けの半分の推定値で、人間の勝率ではありません。分類は暫定です。', '']
    for index, ply in enumerate(game["selected_plies"], 1):
        row = game["moves"][ply - 1]
        board = chess.Board(row["fen_before"])
        deep = row["deep"]
        best = deep["candidates"][0]
        played = deep["played"]
        actual = chess.Move.from_uci(row["played_uci"])
        arrows = [chess.svg.Arrow(actual.from_square, actual.to_square, color="red")]
        if best["pv_uci"]:
            m = chess.Move.from_uci(best["pv_uci"][0])
            arrows.append(chess.svg.Arrow(m.from_square, m.to_square, color="green"))
        view = board.turn if orientation == "mover" else orientation == "white"
        filename = f"position-{index:02}.svg"
        (images / filename).write_text(chess.svg.board(board, orientation=view, arrows=arrows, size=640), encoding="utf-8", newline="\n")
        text += [f'## 注目局面 {row["label"]}', '', f'![{row["label"]}を指す前](images/{filename})', '',
                 f'実戦は **{row["played_san"]}**。推奨候補は **{best["pv_san"][0]}** です。', '',
                 f'推奨候補の評価: {evaluation(best["score"])} / 実戦手を選んだ場合: {evaluation(played["score"])}。', '',
                 f'手番側の期待スコアの低下: {deep["metrics"]["expectation_loss"]*100:.1f}ポイント。', '']
        reasons = deep["metrics"]["reasons"]
        if "missed_mate" in reasons:
            text += ['推奨手ではメイトが示されていますが、実戦手ではそのメイトが確認できなくなりました。', '']
        if "allowed_mate" in reasons:
            text += ['実戦手の変化では、相手側のメイトが示されています。', '']
        if deep.get("only_move_candidate"):
            text += ['第2候補との評価差が大きく、最善候補を見つけることが重要な局面です。唯一手かどうかは追加検証が必要です。', '']
        text += [f'推奨手からの参考変化: {" → ".join(best["pv_san"][:6])}', '',
                 f'実戦手からの参考変化: {" → ".join(played["pv_san"][:6])}', '',
                 '<!-- AIアシスタント: PVと盤面で裏付けられる狙い、相手の応手、改善点を説明する。未検証の戦術名や心理を創作しない。 -->', '']
    (dest / "draft.md").write_text('\n'.join(text), encoding="utf-8", newline="\n")


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("正の有限値を指定してください")
    return number


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("1以上を指定してください")
    return number


def use_utf8_stdio():
    """Japanese messages must survive redirection under a non-UTF-8 locale (e.g. cp932 on Windows)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def find_engine(name):
    path = shutil.which(name)
    if not path:
        raise ValueError("Stockfishが見つかりません。インストール（macOS: brew install stockfish / Windows: winget install Stockfish.Stockfish）後、"
                         "--engine または環境変数 STOCKFISH_PATH に実行ファイルのパスを指定してください")
    return path


def resolve_plies(moves, specs):
    """Turn half-move numbers ("33") or labels ("17.a4", "17...Nd4") into sorted, unique plies."""
    labels = {row["label"]: row["ply"] for row in moves}
    plies = set()
    for spec in specs:
        ply = int(spec) if spec.isdigit() else labels.get(spec)
        if ply is None or not 1 <= ply <= len(moves):
            raise ValueError(f"局面が見つかりません: {spec}（半手番号 1〜{len(moves)}、または 17.a4 / 17...Nd4 の形式）")
        plies.add(ply)
    return sorted(plies)


def main(argv=None):
    use_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgn", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--engine", default=os.environ.get("STOCKFISH_PATH", "stockfish"))
    parser.add_argument("--quick", type=positive_float, default=.15, help="全局面の1探索あたり秒数")
    parser.add_argument("--deep", type=positive_float, default=2, help="詳細解析の1探索あたり秒数")
    parser.add_argument("--candidates", type=positive_int, default=8)
    parser.add_argument("--positions", type=positive_int, default=4)
    parser.add_argument("--multipv", type=positive_int, default=3)
    parser.add_argument("--threads", type=positive_int, default=1)
    parser.add_argument("--hash", type=positive_int, default=128)
    parser.add_argument("--orientation", choices=["white", "black", "mover"], default="white")
    parser.add_argument("--force", action="store_true", help="既存キャッシュを再計算")
    args = parser.parse_args(argv)
    if args.deep < args.quick:
        parser.error("--deep は --quick 以上にしてください")
    if args.positions > args.candidates:
        parser.error("--positions は --candidates 以下にしてください")
    try:
        raw = args.pgn.read_bytes()
        games = load_games(raw.decode("utf-8-sig"))
        engine_path = find_engine(args.engine)
        settings = {k: getattr(args, k) for k in ("quick", "deep", "candidates", "positions", "multipv", "threads", "hash")}
        key_data = {"version": VERSION, "pgn_sha256": hashlib.sha256(raw).hexdigest(), "settings": settings,
                    "engine_sha256": hashlib.sha256(Path(engine_path).read_bytes()).hexdigest(), "chess_version": chess.__version__}
        args.output.mkdir(parents=True, exist_ok=True)
        with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
            engine.configure({"Threads": args.threads, "Hash": args.hash})
            for index, game in enumerate(games, 1):
                dest = args.output / f"game-{index:03}"
                dest.mkdir(exist_ok=True)
                path = dest / "game.analysis.json"
                cache_key = dict(key_data, game_index=index)
                data = None
                if path.exists() and not args.force:
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                        if cached.get("cache_key") == cache_key:
                            data = cached
                    except (ValueError, OSError):
                        pass
                if data is None:
                    print(f"対局 {index}/{len(games)} を解析", file=sys.stderr)
                    engine.configure({"Clear Hash": None})
                    data = {"schema_version": VERSION, "cache_key": cache_key, "engine": engine.id,
                            "evaluation_pov": "white", "expectation_model": "sf16", "game": analyze(engine, game, args)}
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
                    temporary.replace(path)
                else:
                    print(f"対局 {index}: 保存済み解析を使用", file=sys.stderr)
                (dest / "game.pgn").write_text(str(game) + '\n', encoding="utf-8", newline="\n")
                render(data["game"], dest, args.orientation)
                print(dest.resolve())
    except (OSError, ValueError, chess.engine.EngineError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
