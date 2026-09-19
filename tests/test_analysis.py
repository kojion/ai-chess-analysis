import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import chess
import chess.engine

spec = importlib.util.spec_from_file_location("analysis", Path(__file__).parents[1] / "scripts/analyze_game.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


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

    @unittest.skipUnless(shutil.which("stockfish"), "Stockfish required")
    def test_real_engine_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            args = [str(Path(__file__).parents[1] / "examples/sample.pgn"), "--output", temp,
                    "--quick", ".02", "--deep", ".05", "--candidates", "4", "--positions", "2"]
            self.assertEqual(a.main(args), 0)
            dest = Path(temp) / "game-001"
            path = dest / "game.analysis.json"
            data = json.loads(path.read_text())
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
            mtime = path.stat().st_mtime_ns
            (dest / "article.md").write_text("keep")
            self.assertEqual(a.main(args), 0)
            self.assertEqual(path.stat().st_mtime_ns, mtime)
            self.assertEqual((dest / "article.md").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
