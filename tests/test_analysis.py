import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import chess
import chess.engine

spec = importlib.util.spec_from_file_location("analysis", Path(__file__).parents[1] / "scripts/analyze_game.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
spec = importlib.util.spec_from_file_location("verify", Path(__file__).parents[1] / "scripts/verify_positions.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
spec = importlib.util.spec_from_file_location("review", Path(__file__).parents[1] / "scripts/render_review.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class AnalysisTests(unittest.TestCase):
    def score(self, cp):
        return a.score_data(chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE), 30)

    def test_black_loss_has_correct_sign(self):
        self.assertGreater(a.loss_info(self.score(0), self.score(300), chess.BLACK)["expectation_loss"], .2)
        self.assertEqual(a.loss_info(self.score(0), self.score(300), chess.WHITE)["cp_loss"], 0)

    def test_mate_is_not_centipawns(self):
        mate = a.score_data(chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE), 30)
        loss = a.loss_info(mate, self.score(0), chess.WHITE)
        self.assertIsNone(loss["cp_loss"])
        self.assertIn("missed_mate", loss["reasons"])

    def test_mate_zero_winner(self):
        mate = a.score_data(chess.engine.PovScore(chess.engine.Mate(0), chess.WHITE), 4)
        self.assertIn("allowed_mate", a.loss_info(self.score(0), mate, chess.WHITE)["reasons"])
        self.assertNotIn("allowed_mate", a.loss_info(self.score(0), mate, chess.BLACK)["reasons"])

    def test_invalid_and_empty(self):
        for pgn in ["", '[Result "*"]\n\n*', '1. e4 e5 2. Bh6 *']:
            with self.assertRaises(ValueError):
                a.load_games(pgn)

    def test_setup_and_multiple_games(self):
        pgn = '[SetUp "1"]\n[FEN "7k/8/8/8/8/8/8/K7 b - - 0 25"]\n\n25... Kg8 *'
        # Insufficient-material positions are already over and must reject continuation.
        with self.assertRaises(ValueError):
            a.load_games(pgn)
        pgn = '[SetUp "1"]\n[FEN "7k/7p/8/8/8/8/P7/K7 b - - 0 25"]\n\n25... Kg8 *'
        games = a.load_games(pgn + '\n\n[Event "second"]\n\n1. e4 *')
        self.assertEqual(len(games), 2)
        self.assertEqual(games[0].board().fullmove_number, 25)
        self.assertEqual(games[0].board().turn, chess.BLACK)

    def test_resolve_plies(self):
        moves = [{"ply": 1, "label": "1.f3"}, {"ply": 2, "label": "1...e5"}, {"ply": 3, "label": "2.g4"}]
        self.assertEqual(a.resolve_plies(moves, ["2.g4", "1", "1...e5", "3"]), [1, 2, 3])
        for bad in ["0", "4", "9.e4", "-1"]:
            with self.assertRaises(ValueError):
                a.resolve_plies(moves, [bad])

    def test_verify_requires_analyzed_game(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(v.main([temp, "1"]), 1)

    def test_render_review(self):
        after_e4 = chess.Board()
        after_e4.push_uci("e2e4")
        after_e5 = after_e4.copy()
        after_e5.push_uci("e7e5")

        def row(ply, label, board, uci, san, best=None):
            item = {"ply": ply, "label": label, "played_uci": uci, "played_san": san, "fen_before": board.fen()}
            if best:
                item["deep"] = {"candidates": [{"pv_uci": [best]}]}
            return item

        moves = [row(1, "1.e4", chess.Board(), "e2e4", "e4", "d2d4"),   # played != best: red + green
                 row(2, "1...e5", after_e4, "e7e5", "e5", "e7e5"),      # played == best: green only
                 row(3, "2.Nf3", after_e5, "g1f3", "Nf3")]               # no analysis: red only
        red, green, blue = "#882020", "#15781B", "#003088"

        def arrows(svg):
            return svg.count('class="arrow"') // 2

        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            (game / "game.analysis.json").write_text(json.dumps({"game": {"moves": moves}}), encoding="utf-8")
            images = game / "images"

            def svg(number):
                return (images / f"review-{number:02}.svg").read_text(encoding="utf-8")

            self.assertEqual(r.main([str(game), "1.e4", "1...e5", "3", "--orientation", "black"]), 0)
            first = svg(1)
            self.assertEqual([arrows(svg(n)) for n in (1, 2, 3)], [2, 1, 1])
            self.assertTrue(red in first and green in first)
            self.assertTrue(red not in svg(2) and green in svg(2))
            self.assertTrue(red in svg(3) and green not in svg(3))
            for path in images.glob("*.svg"):
                self.assertNotIn(b"\r", path.read_bytes())
            # Existing figures are protected unless --force is given.
            self.assertEqual(r.main([str(game), "1.e4"]), 1)
            self.assertEqual(r.main([str(game), "1.e4", "--force", "--arrow", "1.e4:g1f3"]), 0)
            self.assertEqual(arrows(svg(1)), 3)
            self.assertIn(blue, svg(1))
            self.assertNotEqual(svg(1), first)  # white orientation differs from black
            # Older reviews named the candidates "lines"; a re-check overrides the automatic analysis.
            (game / "verification.analysis.json").write_text(
                json.dumps({"positions": [{"ply": 3, "lines": [{"pv_uci": ["f1c4"]}]}]}), encoding="utf-8")
            self.assertEqual(r.main([str(game), "3", "--start", "9"]), 0)
            self.assertEqual(arrows(svg(9)), 2)
            # Bad input.
            self.assertEqual(r.main([str(game), "1.e4", "--force", "--arrow", "3:g1f3"]), 1)
            self.assertEqual(r.main([str(game), "1.e4", "--force", "--arrow", "1.e4:zz99"]), 1)
            self.assertEqual(r.main([str(game), "1.e4", "--force", "--arrow", "1.e4:g1f3:not a color"]), 1)
            self.assertEqual(r.main([str(game / "missing"), "1"]), 1)

    @unittest.skipUnless(shutil.which(os.environ.get("STOCKFISH_PATH", "stockfish")), "Stockfish required")
    def test_real_engine_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            args = [str(Path(__file__).parents[1] / "examples/sample.pgn"), "--output", temp,
                    "--quick", ".02", "--deep", ".05", "--candidates", "4", "--positions", "2"]
            self.assertEqual(a.main(args), 0)
            dest = Path(temp) / "game-001"
            path = dest / "game.analysis.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data["game"]["moves"]
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[-1]["after"]["score"]["mate"], 0)
            self.assertEqual(rows[-1]["after"]["score"]["expectation_white"], 0)
            self.assertIn("allowed_mate", rows[2]["deep"]["metrics"]["reasons"])
            for row in rows:
                for line in row["deep"]["candidates"] + [row["deep"]["played"]]:
                    board = chess.Board(row["fen_before"])
                    for uci in line["pv_uci"]:
                        move = chess.Move.from_uci(uci)
                        self.assertIn(move, board.legal_moves)
                        board.push(move)
            self.assertEqual(len(list((dest / "images").glob("*.svg"))), 2)
            # Artifacts are committed to Git, so they must be byte-identical (LF) on every OS.
            for artifact in [dest / "draft.md", dest / "game.pgn", path, *(dest / "images").glob("*.svg")]:
                self.assertNotIn(b"\r", artifact.read_bytes(), artifact.name)
            mtime = path.stat().st_mtime_ns
            (dest / "article.md").write_text("keep", encoding="utf-8")
            self.assertEqual(a.main(args), 0)
            self.assertEqual(path.stat().st_mtime_ns, mtime)
            self.assertEqual((dest / "article.md").read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(shutil.which(os.environ.get("STOCKFISH_PATH", "stockfish")), "Stockfish required")
    def test_verify_positions(self):
        with tempfile.TemporaryDirectory() as temp:
            sample = str(Path(__file__).parents[1] / "examples/sample.pgn")
            self.assertEqual(a.main([sample, "--output", temp, "--quick", ".02", "--deep", ".05"]), 0)
            dest = Path(temp) / "game-001"
            self.assertEqual(v.main([str(dest), "2.g4", "2", "--seconds", ".05", "--multipv", "2"]), 0)
            path = dest / "verification.analysis.json"
            self.assertNotIn(b"\r", path.read_bytes())
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = json.loads((dest / "game.analysis.json").read_text(encoding="utf-8"))["game"]["moves"]
            self.assertEqual([p["ply"] for p in data["positions"]], [2, 3])
            for position in data["positions"]:
                row = rows[position["ply"] - 1]
                self.assertEqual((position["label"], position["fen"]), (row["label"], row["fen_before"]))
                self.assertEqual(set(position) & {"candidates", "played", "metrics"}, {"candidates", "played", "metrics"})
                board = chess.Board(row["fen_before"])
                self.assertEqual(position["played"]["pv_uci"][0], row["played_uci"])
                for line in position["candidates"] + [position["played"]]:
                    replay = board.copy()
                    for uci in line["pv_uci"]:
                        move = chess.Move.from_uci(uci)
                        self.assertIn(move, replay.legal_moves)
                        replay.push(move)
            self.assertEqual(v.main([str(dest), "9.e4"]), 1)


if __name__ == "__main__":
    unittest.main()
