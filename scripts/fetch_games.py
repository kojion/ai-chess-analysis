#!/usr/bin/env python3
"""Download games from lichess into games/ and optionally analyze the new ones. Files match the game page's PGN download."""
import argparse
from datetime import datetime, timezone
import functools
import os
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_game as core  # noqa: E402

SITE = "https://lichess.org"
# No clocks/evals, but the opening tags: this is what the game page's PGN download contains.
EXPORT = {"clocks": "false", "evals": "false", "opening": "true"}
ANALYSIS_ARGS = ["--quick", "0.3", "--candidates", "12", "--positions", "6"]
HEADER = re.compile(r'^\[(\w+) "([^"]*)"\]', re.M)
GAME_ID = re.compile(r"(?:https?://)?(?:www\.)?(?:lichess\.org/)?([A-Za-z0-9]{8})(?:[A-Za-z0-9]{4})?(?:/(?:white|black))?/?(?:#\d+)?")


@functools.lru_cache(maxsize=1)
def ssl_context():
    """Certificate verification stays on. SSL_CERT_FILE may name a CA bundle.

    On Windows only the ROOT store is trusted. Python also loads the CA (intermediate) store as trust anchors, and an
    expired intermediate left there (an old Let's Encrypt R3, for example) fails every request with "certificate has expired".
    """
    if os.environ.get("SSL_CERT_FILE"):
        return ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
    if sys.platform != "win32":
        return ssl.create_default_context()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for certificate, encoding, trust in ssl.enum_certificates("ROOT"):
        if encoding == "x509_asn" and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
            try:
                context.load_verify_locations(cadata=certificate)
            except ssl.SSLError:
                pass  # a certificate OpenSSL cannot parse
    return context


def http_get(url, headers=None, timeout=60):
    """Return (status, text). HTTP error statuses are returned so that callers can explain them."""
    request = urllib.request.Request(url, headers={"User-Agent": "ai-chess-analysis (personal game review)", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def get(url, headers=None):
    """lichess asks clients to send one request at a time and to wait a minute after a 429."""
    for attempt in range(3):
        status, text = http_get(url, headers)
        if status != 429 or attempt == 2:
            break
        print("lichessの制限（429）です。60秒待って再試行します", file=sys.stderr)
        time.sleep(60)
    return status, text


def parse_headers(text):
    return dict(HEADER.findall(text))


def split_games(text):
    """Split a PGN stream into games, keeping each game's text as lichess wrote it (LF only)."""
    return [chunk.strip() + "\n" for chunk in re.split(r'(?m)^(?=\[Event ")', text.replace("\r\n", "\n")) if chunk.strip()]


def parse_game_id(text):
    match = GAME_ID.fullmatch(text.strip())
    if not match:
        raise ValueError(f"対局のURLまたはIDとして読めません: {text}")
    return match.group(1)


def safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def file_name(headers):
    for key in ("Date", "White", "Black", "GameId"):
        if not headers.get(key):
            raise ValueError(f"PGNのヘッダー {key} がありません")
    return f'lichess_pgn_{headers["Date"]}_{safe(headers["White"])}_vs_{safe(headers["Black"])}.{headers["GameId"]}.pgn'


def timestamp_ms(headers):
    try:
        moment = datetime.strptime(f'{headers["UTCDate"]} {headers["UTCTime"]}', "%Y.%m.%d %H:%M:%S")
    except (KeyError, ValueError):
        return None
    return int(moment.replace(tzinfo=timezone.utc).timestamp() * 1000)


def local_games(games_dir):
    """Game id -> path of the games already in games/, and the newest game's timestamp in ms."""
    paths, newest = {}, None
    for path in sorted(games_dir.glob("*.pgn")):
        headers = parse_headers(path.read_text(encoding="utf-8-sig"))
        if headers.get("GameId"):
            paths[headers["GameId"]] = path
        stamp = timestamp_ms(headers)
        if stamp is not None and (newest is None or stamp > newest):
            newest = stamp
    return paths, newest


def side_of(headers, user):
    """The color the user played, or None when the user is not one of the players."""
    for color in ("white", "black"):
        if headers.get(color.capitalize(), "").lower() == user.lower():
            return color
    return None


def output_dir(headers, user, root):
    """output/<date>-<opponent>, with -2, -3 ... when another game already uses the name. Returns (path, already analyzed)."""
    opponent = headers["Black" if side_of(headers, user) == "white" else "White"]
    base = f'{headers["Date"].replace(".", "-")}-{safe(opponent).lower()}'
    for number in range(1, 100):
        path = root / (base if number == 1 else f"{base}-{number}")
        pgn = path / "game.pgn"
        if not path.exists():
            return path, False
        if pgn.exists() and parse_headers(pgn.read_text(encoding="utf-8-sig")).get("GameId") == headers["GameId"]:
            return path, True
    raise ValueError(f"出力先の名前が決まりません: {base}")


def analyze_new(path, headers, user, root):
    side = side_of(headers, user)
    if side is None:
        print(f"解析しません（{user} が対局者に含まれません）: {path.name}", file=sys.stderr)
        return False
    out, done = output_dir(headers, user, root)
    if done:
        print(f"解析済み: {out}", file=sys.stderr)
        return True
    print(f"解析: {out}（{side}番）", file=sys.stderr)
    return core.main([str(path), "--output", str(out), "--orientation", side, *ANALYSIS_ARGS]) == 0


def fetch_ids(ids, known):
    """Games by id need no token. Returns the PGN texts of the ids that are not stored yet."""
    texts = []
    for game_id in ids:
        if game_id in known:
            print(f"取得済み: {game_id}", file=sys.stderr)
            continue
        status, text = get(f"{SITE}/game/export/{game_id}?{urllib.parse.urlencode(EXPORT)}")
        if status == 404:
            raise ValueError(f"対局が見つかりません: {game_id}")
        if status != 200:
            raise ValueError(f"対局 {game_id} を取得できません（HTTP {status}）")
        texts.append(text)
    return texts


def fetch_user(args, since):
    token = os.environ.get("LICHESS_TOKEN")
    if not args.user:
        raise ValueError("ユーザー名を --user か環境変数 LICHESS_USER で指定してください")
    if not token:
        raise ValueError("一括取得にはlichessのAPIトークンが必要です（環境変数 LICHESS_TOKEN）。1局だけなら、URLまたはIDを渡してください")
    query = {"perfType": args.perf, "max": args.max or (100 if since else 10), **EXPORT}
    if not args.include_casual:
        query["rated"] = "true"
    if since:
        query["since"] = since
    url = f"{SITE}/api/games/user/{urllib.parse.quote(args.user)}?{urllib.parse.urlencode(query)}"
    status, text = get(url, {"Authorization": f"Bearer {token}", "Accept": "application/x-chess-pgn"})
    if status == 401:
        raise ValueError("トークンが無効です（HTTP 401）。LICHESS_TOKEN を確認してください")
    if status == 404:
        raise ValueError("対局リストを取得できません（HTTP 404）。トークンの設定とユーザー名を確認してください")
    if status != 200:
        raise ValueError(f"対局リストを取得できません（HTTP {status}）")
    return [text]


def main(argv=None):
    core.use_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("games", nargs="*", metavar="URLまたはID", help="取得する対局。省略すると --user の新しい対局を一括取得（要トークン）")
    parser.add_argument("--user", default=os.environ.get("LICHESS_USER"), help="lichessのユーザー名（既定は環境変数 LICHESS_USER）")
    parser.add_argument("--perf", default="classical", help="一括取得する持ち時間の種類（既定 classical）")
    parser.add_argument("--include-casual", action="store_true", help="一括取得にレートなしの対局も含める")
    parser.add_argument("--since", help="一括取得の開始日（YYYY-MM-DD、UTC）。既定は games/ にある最新の対局より後")
    parser.add_argument("--max", type=core.positive_int, help="一括取得の最大局数（既定は100、games/ が空で --since もないときは10）")
    parser.add_argument("--games-dir", type=Path, default=Path("games"))
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument("--analyze", action="store_true", help="取得した対局を analyze_game.py で解析する（--user が必要）")
    parser.add_argument("--dry-run", action="store_true", help="保存も解析もせず、対象を表示する")
    args = parser.parse_args(argv)
    try:
        if args.analyze and not args.user:
            raise ValueError("--analyze には --user（または環境変数 LICHESS_USER）が必要です")
        known, newest = local_games(args.games_dir) if args.games_dir.exists() else ({}, None)
        targets = []  # (path, headers) of every game to analyze: the new ones and, for ids, the ones already stored
        if args.games:
            ids = [parse_game_id(text) for text in args.games]
            texts = fetch_ids(ids, known)
            targets = [(known[i], parse_headers(known[i].read_text(encoding="utf-8-sig"))) for i in ids if i in known]
        else:
            since = newest + 1000 if newest else None
            if args.since:
                try:
                    since = int(datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
                except ValueError:
                    raise ValueError("--since は YYYY-MM-DD の形式で指定してください") from None
            texts = fetch_user(args, since)
        seen = set(known)
        for chunk in (game for text in texts for game in split_games(text)):
            headers = parse_headers(chunk)
            path = args.games_dir / file_name(headers)
            if headers["GameId"] in seen:
                continue
            seen.add(headers["GameId"])
            targets.append((path, headers))
            if args.dry_run:
                print(f"[dry-run] 保存: {path}")
                continue
            args.games_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(chunk, encoding="utf-8", newline="\n")
            print(path.resolve())
        if len(seen) == len(known):
            print("新しい対局はありません", file=sys.stderr)
        failed = False
        if args.analyze:
            for path, headers in targets:
                if args.dry_run:
                    out, done = output_dir(headers, args.user, args.output_root) if side_of(headers, args.user) else (None, True)
                    print(f"[dry-run] 解析: {out}" if not done else f"[dry-run] 解析しません（解析済み、または対局者に含まれません）: {path.name}")
                elif not analyze_new(path, headers, args.user, args.output_root):
                    failed = True
        return 1 if failed else 0
    except (OSError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
