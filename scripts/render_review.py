#!/usr/bin/env python3
"""Render review diagrams (SVG) for chosen positions of an analyzed game. Red arrow = played move, green = best candidate."""
import argparse
import json
from pathlib import Path
import re
import sys

import chess
import chess.svg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_game as core  # noqa: E402

COLOR = re.compile(r"[A-Za-z]+|#[0-9A-Fa-f]{6}")


def best_move(ply, row, rechecks):
    """First move of the top candidate, preferring a deeper re-check over the automatic deep analysis."""
    for review in (rechecks.get(ply), row.get("deep")):
        # verification.analysis.json written by hand in older reviews called the candidates "lines".
        lines = (review or {}).get("candidates") or (review or {}).get("lines") or []
        if lines and lines[0]["pv_uci"]:
            return chess.Move.from_uci(lines[0]["pv_uci"][0])
    return None


def parse_arrow(text, moves):
    """POSITION:UCI[:COLOR] -> (ply, Arrow). The default color is blue."""
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"矢印は 局面:UCI[:色] の形式で指定してください: {text}")
    ply = core.resolve_plies(moves, [parts[0]])[0]
    move = chess.Move.from_uci(parts[1])
    color = parts[2] if len(parts) == 3 else "blue"
    if not move or not COLOR.fullmatch(color):
        raise ValueError(f"矢印の指し手または色が正しくありません: {text}")
    return ply, chess.svg.Arrow(move.from_square, move.to_square, color=color)


def main(argv=None):
    core.use_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir", type=Path, help="解析済みの対局ディレクトリ（output/NAME。複数局のPGNは output/NAME/game-NNN）")
    parser.add_argument("positions", nargs="+", help="半手番号（例: 33）または手の表記（例: 17.a4, 17...Nd4）")
    parser.add_argument("--orientation", choices=["white", "black", "mover"], default="white")
    parser.add_argument("--arrow", action="append", default=[], metavar="局面:UCI[:色]",
                        help="矢印を追加する（例: 19...f5:d4f3:blue）。色の既定は blue")
    parser.add_argument("--start", type=core.positive_int, default=1, help="images/review-NN.svg の最初の番号")
    parser.add_argument("--force", action="store_true", help="既存の図を上書き")
    args = parser.parse_args(argv)
    try:
        analysis_path = args.game_dir / "game.analysis.json"
        if not analysis_path.exists():
            raise ValueError("game.analysis.json が見つかりません。先に analyze_game.py で解析してください")
        moves = json.loads(analysis_path.read_text(encoding="utf-8"))["game"]["moves"]
        recheck_path = args.game_dir / "verification.analysis.json"
        rechecks = {}
        if recheck_path.exists():
            rechecks = {p["ply"]: p for p in json.loads(recheck_path.read_text(encoding="utf-8"))["positions"]}
        plies = core.resolve_plies(moves, args.positions)
        extra = {}
        for text in args.arrow:
            ply, arrow = parse_arrow(text, moves)
            if ply not in plies:
                raise ValueError(f"矢印の局面が、指定した局面に含まれていません: {text}")
            extra.setdefault(ply, []).append(arrow)
        images = args.game_dir / "images"
        targets = {ply: images / f"review-{args.start + index:02}.svg" for index, ply in enumerate(plies)}
        existing = [path.name for path in targets.values() if path.exists()]
        if existing and not args.force:
            raise ValueError(f"既存の図があります（--force で上書き、--start で番号を変更）: {', '.join(existing)}")
        images.mkdir(exist_ok=True)
        for ply, target in targets.items():
            row = moves[ply - 1]
            board = chess.Board(row["fen_before"])
            played, best = chess.Move.from_uci(row["played_uci"]), best_move(ply, row, rechecks)
            arrows = []
            # When the played move is the best one, only the green arrow is drawn.
            if best != played:
                arrows.append(chess.svg.Arrow(played.from_square, played.to_square, color="red"))
            if best is not None:
                arrows.append(chess.svg.Arrow(best.from_square, best.to_square, color="green"))
            arrows += extra.get(ply, [])
            view = board.turn if args.orientation == "mover" else args.orientation == "white"
            target.write_text(chess.svg.board(board, orientation=view, arrows=arrows, size=640), encoding="utf-8", newline="\n")
            print(f'{target.name} <- {row["label"]}（実戦 {row["played_san"]} / 推奨 {board.san(best) if best else "解析なし"}）',
                  file=sys.stderr)
            print(target.resolve())
    except (OSError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
