#!/usr/bin/env python3
"""Re-check chosen positions of an analyzed game with a deeper search. All serialized evaluations use White's POV."""
import argparse
import io
import json
import os
from pathlib import Path
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_game as core  # noqa: E402


def boards_before(game):
    """Boards before each move. Copies keep the move stack so repetition is judged as in analyze_game.py."""
    board, boards = game.board(), []
    for move in game.mainline_moves():
        boards.append(board.copy())
        board.push(move)
    return boards


def resolve_plies(moves, specs):
    labels = {row["label"]: row["ply"] for row in moves}
    plies = set()
    for spec in specs:
        ply = int(spec) if spec.isdigit() else labels.get(spec)
        if ply is None or not 1 <= ply <= len(moves):
            raise ValueError(f"局面が見つかりません: {spec}（半手番号 1〜{len(moves)}、または 17.a4 / 17...Nd4 の形式）")
        plies.add(ply)
    return sorted(plies)


def main(argv=None):
    core.use_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir", type=Path, help="解析済みの対局ディレクトリ（output/NAME/game-NNN）")
    parser.add_argument("positions", nargs="+", help="半手番号（例: 33）または手の表記（例: 17.a4, 17...Nd4）")
    parser.add_argument("--engine", default=os.environ.get("STOCKFISH_PATH", "stockfish"))
    parser.add_argument("--seconds", type=core.positive_float, default=6, help="1探索あたり秒数")
    parser.add_argument("--multipv", type=core.positive_int, default=4)
    parser.add_argument("--threads", type=core.positive_int, default=1)
    parser.add_argument("--hash", type=core.positive_int, default=128)
    args = parser.parse_args(argv)
    try:
        analysis_path, pgn_path = args.game_dir / "game.analysis.json", args.game_dir / "game.pgn"
        if not analysis_path.exists() or not pgn_path.exists():
            raise ValueError("game.analysis.json と game.pgn が見つかりません。先に analyze_game.py で解析してください")
        moves = json.loads(analysis_path.read_text(encoding="utf-8"))["game"]["moves"]
        game = chess.pgn.read_game(io.StringIO(pgn_path.read_text(encoding="utf-8-sig")))
        if game is None:
            raise ValueError("game.pgn に対局がありません")
        boards = boards_before(game)
        if len(boards) != len(moves):
            raise ValueError("game.pgn と game.analysis.json の手数が一致しません")
        plies = resolve_plies(moves, args.positions)
        engine_path = core.find_engine(args.engine)
        positions = []
        with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
            engine.configure({"Threads": args.threads, "Hash": args.hash})
            for index, ply in enumerate(plies, 1):
                row, board = moves[ply - 1], boards[ply - 1]
                if board.fen() != row["fen_before"]:
                    raise ValueError(f'{row["label"]}: game.pgn と game.analysis.json の局面が一致しません')
                print(f'  再確認 {index}/{len(plies)}: {row["label"]}', file=sys.stderr)
                engine.configure({"Clear Hash": None})
                review = core.deep_review(engine, board, chess.Move.from_uci(row["played_uci"]), args.seconds, args.multipv)
                best = review["candidates"][0]
                print(f'    推奨 {(best["pv_san"] or ["-"])[0]} {core.evaluation(best["score"])}'
                      f' / 実戦 {row["played_san"]} {core.evaluation(review["played"]["score"])}', file=sys.stderr)
                positions.append({"ply": ply, "label": row["label"], "fen": row["fen_before"], **review})
            data = {"schema_version": core.VERSION, "engine": engine.id, "evaluation_pov": "white",
                    "expectation_model": "sf16", "seconds": args.seconds, "multipv": args.multipv, "positions": positions}
        path = args.game_dir / "verification.analysis.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        temporary.replace(path)
        print(path.resolve())
    except (OSError, ValueError, chess.engine.EngineError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
