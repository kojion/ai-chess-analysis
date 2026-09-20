import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import urllib.parse

spec = importlib.util.spec_from_file_location("fetch", Path(__file__).parents[1] / "scripts/fetch_games.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def game_text(game_id, white="zbxah", black="opponent", date="2026.09.20", clock="04:56:24", moves="1. f3 e5 2. g4 Qh4# 0-1"):
    return (f'[Event "rated classical game"]\n[Site "https://lichess.org/{game_id}"]\n[Date "{date}"]\n[Round "-"]\n'
            f'[White "{white}"]\n[Black "{black}"]\n[Result "0-1"]\n[GameId "{game_id}"]\n[UTCDate "{date}"]\n'
            f'[UTCTime "{clock}"]\n[TimeControl "1800+20"]\n\n{moves}\n\n\n')


def millis(text):
    return int(datetime.strptime(text, "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


class Http:
    """Stands in for fetch_games.http_get: returns the queued (status, text) answers and records every request."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, headers=None, timeout=60):
        self.calls.append((url, headers or {}))
        return self.answers.pop(0)


class FetchTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("LICHESS_TOKEN", "LICHESS_USER"):
            os.environ.pop(name, None)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.games, self.output = Path(temp.name) / "games", Path(temp.name) / "output"

    def run_main(self, http, *args):
        """Run main() with a fake network; returns (exit code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(f, "http_get", http), mock.patch.object(f.time, "sleep") as sleep, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = f.main([*args, "--games-dir", str(self.games), "--output-root", str(self.output)])
        self.sleep = sleep
        return code, out.getvalue(), err.getvalue()

    def stored(self):
        return sorted(p.name for p in self.games.glob("*.pgn")) if self.games.exists() else []

    def test_tls_verification_stays_on(self):
        f.ssl_context.cache_clear()
        context = f.ssl_context()
        self.assertEqual(context.verify_mode, f.ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(len(context.get_ca_certs()), 0)

    def test_parse_game_id(self):
        for text in ["pb65np0J", "https://lichess.org/pb65np0J", "https://lichess.org/pb65np0J/black",
                     "lichess.org/pb65np0J12ab", "https://lichess.org/pb65np0J#42", "  pb65np0J\n"]:
            self.assertEqual(f.parse_game_id(text), "pb65np0J", text)
        for text in ["", "abc", "https://example.com/x", "pb65np0J/green"]:
            with self.assertRaises(ValueError):
                f.parse_game_id(text)

    def test_split_games_and_file_names(self):
        text = game_text("aaaaaaa1") + game_text("bbbbbbb2", white="Some Name", black="zb/xah").replace("\n", "\r\n")
        games = f.split_games(text)
        self.assertEqual(len(games), 2)
        self.assertTrue(all(g.endswith("\n") and "\r" not in g for g in games))
        self.assertEqual(f.file_name(f.parse_headers(games[0])), "lichess_pgn_2026.09.20_zbxah_vs_opponent.aaaaaaa1.pgn")
        self.assertEqual(f.file_name(f.parse_headers(games[1])), "lichess_pgn_2026.09.20_Some_Name_vs_zb_xah.bbbbbbb2.pgn")
        with self.assertRaises(ValueError):
            f.file_name({"Date": "2026.09.20", "White": "a"})

    def test_side_of(self):
        headers = {"White": "ZbXah", "Black": "opponent"}
        self.assertEqual(f.side_of(headers, "zbxah"), "white")
        self.assertEqual(f.side_of(headers, "OPPONENT"), "black")
        self.assertIsNone(f.side_of(headers, "someone"))

    def test_local_games(self):
        self.games.mkdir()
        (self.games / "a.pgn").write_text(game_text("aaaaaaa1", clock="04:00:00"), encoding="utf-8")
        (self.games / "b.pgn").write_text(game_text("bbbbbbb2", clock="05:30:00"), encoding="utf-8")
        (self.games / "no-id.pgn").write_text('[Event "x"]\n\n1. e4 *\n', encoding="utf-8")
        paths, newest = f.local_games(self.games)
        self.assertEqual(set(paths), {"aaaaaaa1", "bbbbbbb2"})
        self.assertEqual(newest, millis("2026.09.20 05:30:00"))

    def test_single_game_needs_no_token(self):
        http = Http((200, game_text("aaaaaaa1")))
        code, out, _ = self.run_main(http, "https://lichess.org/aaaaaaa1/white")
        self.assertEqual(code, 0)
        self.assertEqual(self.stored(), ["lichess_pgn_2026.09.20_zbxah_vs_opponent.aaaaaaa1.pgn"])
        url, headers = http.calls[0]
        self.assertEqual(url, "https://lichess.org/game/export/aaaaaaa1?clocks=false&evals=false&opening=true")
        self.assertNotIn("Authorization", headers)
        path = self.games / self.stored()[0]
        self.assertEqual(path.read_bytes().decode("utf-8"), game_text("aaaaaaa1").strip() + "\n")
        self.assertNotIn(b"\r", path.read_bytes())
        self.assertIn(str(path.resolve()), out)
        # A game that is already stored is not requested again.
        code, _, err = self.run_main(http, "aaaaaaa1")
        self.assertEqual((code, len(http.calls)), (0, 1))
        self.assertIn("取得済み", err)

    def test_single_game_errors_write_nothing(self):
        for answer in [(404, "Not found"), (500, "boom")]:
            code, _, err = self.run_main(Http(answer), "aaaaaaa1")
            self.assertEqual(code, 1, answer)
            self.assertIn("エラー", err)
        self.assertEqual(self.run_main(Http(), "not a game")[0], 1)
        self.assertEqual(self.stored(), [])

    def test_bulk_needs_user_and_token(self):
        http = Http()
        self.assertEqual(self.run_main(http)[0], 1)                                   # neither
        self.assertEqual(self.run_main(http, "--user", "zbxah")[0], 1)                 # no token
        os.environ["LICHESS_TOKEN"] = "secret-token"
        code, _, err = self.run_main(http)                                            # no user
        self.assertEqual(code, 1)
        self.assertIn("ユーザー名", err)
        self.assertEqual(http.calls, [])

    def test_bulk_is_incremental_and_never_prints_the_token(self):
        self.games.mkdir()
        (self.games / "old.pgn").write_text(game_text("aaaaaaa1", clock="04:00:00"), encoding="utf-8")
        os.environ["LICHESS_TOKEN"] = "secret-token"
        os.environ["LICHESS_USER"] = "zbxah"
        http = Http((200, game_text("bbbbbbb2", clock="05:00:00") + game_text("aaaaaaa1", clock="04:00:00")))
        code, out, err = self.run_main(http)
        self.assertEqual(code, 0)
        url, headers = http.calls[0]
        self.assertTrue(url.startswith("https://lichess.org/api/games/user/zbxah?"))
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.assertEqual(query, {"perfType": "classical", "max": "100", "clocks": "false", "evals": "false", "opening": "true",
                                 "rated": "true", "since": str(millis("2026.09.20 04:00:00") + 1000)})
        self.assertEqual(headers["Authorization"], "Bearer secret-token")
        self.assertEqual(sorted(p.name for p in self.games.glob("lichess_pgn_*")), ["lichess_pgn_2026.09.20_zbxah_vs_opponent.bbbbbbb2.pgn"])
        self.assertEqual(len(list(self.games.glob("*.pgn"))), 2)                      # the known game was not duplicated
        self.assertNotIn("secret-token", out + err)

    def test_bulk_options(self):
        os.environ["LICHESS_TOKEN"] = "secret-token"
        http = Http((200, ""), (200, ""))
        self.run_main(http, "--user", "zbxah")                                         # empty games/: small first download
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(http.calls[0][0]).query))
        self.assertEqual((query["max"], "since" in query), ("10", False))
        code, _, err = self.run_main(http, "--user", "zbxah", "--since", "2026-09-01", "--max", "5", "--perf", "rapid", "--include-casual")
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(http.calls[1][0]).query))
        self.assertEqual((code, query["since"], query["max"], query["perfType"], "rated" in query),
                         (0, str(millis("2026.09.01 00:00:00")), "5", "rapid", False))
        self.assertIn("新しい対局はありません", err)
        self.assertEqual(self.run_main(Http(), "--user", "zbxah", "--since", "yesterday")[0], 1)

    def test_bulk_http_errors_and_rate_limit(self):
        os.environ["LICHESS_TOKEN"] = "secret-token"
        for status in (401, 404, 500):
            code, _, err = self.run_main(Http((status, "")), "--user", "zbxah")
            self.assertEqual(code, 1, status)
            self.assertIn(f"HTTP {status}", err)
        code, _, _ = self.run_main(Http((429, ""), (200, game_text("aaaaaaa1"))), "--user", "zbxah")
        self.assertEqual(code, 0)
        self.sleep.assert_called_once_with(60)
        # Three attempts in total, and no pointless wait after the last one.
        self.assertEqual(self.run_main(Http((429, ""), (429, ""), (429, "")), "--user", "zbxah")[0], 1)
        self.assertEqual(self.sleep.call_count, 2)

    def test_dry_run_writes_nothing(self):
        http = Http((200, game_text("aaaaaaa1")))
        code, out, _ = self.run_main(http, "aaaaaaa1", "--dry-run", "--analyze", "--user", "zbxah")
        self.assertEqual(code, 0)
        self.assertIn("[dry-run] 保存", out)
        self.assertIn("[dry-run] 解析", out)
        self.assertFalse(self.games.exists() or self.output.exists())

    def test_output_dir_names(self):
        headers = f.parse_headers(game_text("aaaaaaa1", white="zbxah", black="Opp_One"))
        expected = self.output / "2026-09-20-opp_one"
        self.assertEqual(f.output_dir(headers, "zbxah", self.output), (expected, False))
        # The opponent is the other player, whichever color the user had.
        black = f.parse_headers(game_text("aaaaaaa1", white="Opp_One", black="zbxah"))
        self.assertEqual(f.output_dir(black, "zbxah", self.output), (expected, False))
        # A name taken by another game gets a suffix; the same game is recognized as already analyzed.
        expected.mkdir(parents=True)
        (expected / "game.pgn").write_text(game_text("zzzzzzz9"), encoding="utf-8")
        self.assertEqual(f.output_dir(headers, "zbxah", self.output), (self.output / "2026-09-20-opp_one-2", False))
        (self.output / "2026-09-20-opp_one-2").mkdir()
        (self.output / "2026-09-20-opp_one-2" / "game.pgn").write_text(game_text("aaaaaaa1"), encoding="utf-8")
        self.assertEqual(f.output_dir(headers, "zbxah", self.output), (self.output / "2026-09-20-opp_one-2", True))

    def test_analyze_passes_the_users_side(self):
        path = self.games / "x.pgn"
        for white, black, side in [("zbxah", "opp", "white"), ("opp", "zbxah", "black")]:
            headers = f.parse_headers(game_text("aaaaaaa1", white=white, black=black))
            with mock.patch.object(f.core, "main", return_value=0) as run:
                self.assertTrue(f.analyze_new(path, headers, "zbxah", self.output))
            self.assertEqual(run.call_args.args[0], [str(path), "--output", str(self.output / "2026-09-20-opp"),
                                                     "--orientation", side, *f.ANALYSIS_ARGS])
        with mock.patch.object(f.core, "main") as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(f.analyze_new(path, f.parse_headers(game_text("aaaaaaa1")), "someone-else", self.output))
        run.assert_not_called()

    def test_analyze_needs_a_user(self):
        http = Http()
        code, _, err = self.run_main(http, "aaaaaaa1", "--analyze")
        self.assertEqual(code, 1)
        self.assertIn("--user", err)
        self.assertEqual(http.calls, [])

    @unittest.skipUnless(shutil.which(os.environ.get("STOCKFISH_PATH", "stockfish")), "Stockfish required")
    def test_fetch_and_analyze(self):
        tiny = ["--quick", ".02", "--deep", ".05", "--candidates", "4", "--positions", "2"]
        http = Http((200, game_text("cccccc33", white="zbxah", black="Opp")))
        with mock.patch.object(f, "ANALYSIS_ARGS", tiny):
            code, _, _ = self.run_main(http, "cccccc33", "--user", "zbxah", "--analyze")
            self.assertEqual(code, 0)
            out = self.output / "2026-09-20-opp"
            for name in ("game.analysis.json", "game.pgn", "draft.md"):
                self.assertTrue((out / name).exists(), name)
            self.assertFalse((out / "game-001").exists())
            stamp = (out / "game.analysis.json").stat().st_mtime_ns
            # Running again neither downloads nor analyzes the same game a second time.
            code, _, err = self.run_main(http, "cccccc33", "--user", "zbxah", "--analyze")
            self.assertEqual((code, len(http.calls), (out / "game.analysis.json").stat().st_mtime_ns), (0, 1, stamp))
            self.assertIn("解析済み", err)


if __name__ == "__main__":
    unittest.main()
