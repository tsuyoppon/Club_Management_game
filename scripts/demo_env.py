#!/usr/bin/env python3
"""Local demo environment bootstrapper for the Web multiplayer flow."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".demo"
COOKIE_DIR = STATE_DIR / "cookies"
STATE_FILE = STATE_DIR / "demo-state.json"
DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_WEB_BASE = "http://localhost:3000"
DEFAULT_CLUBS = ["Tokyo Training FC", "Osaka Workshop SC"]
DEFAULT_PLAYERS = ["Host GM", "Player Two", "Player Three", "Player Four", "Player Five"]


class DemoError(RuntimeError):
    pass


@dataclass
class DemoClient:
    api_base: str
    cookie_file: Path

    def __post_init__(self) -> None:
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookies = MozillaCookieJar(str(self.cookie_file))
        if self.cookie_file.exists():
            self.cookies.load(ignore_discard=True, ignore_expires=True)
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.api_base.rstrip("/") + "/", path.lstrip("/"))
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DemoError(f"{method} {url} failed: HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise DemoError(f"{method} {url} failed: {exc.reason}") from exc
        self.cookies.save(ignore_discard=True, ignore_expires=True)
        return json.loads(raw) if raw else {}


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT, text=True, check=check)


def run_capture(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def load_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def docker_compose(args: list[str]) -> None:
    run(["docker", "compose", *args])


def start_stack(args: argparse.Namespace) -> None:
    compose_args = ["--profile", "web", "up", "-d"]
    if args.build:
        compose_args.append("--build")
    docker_compose(compose_args)


def wait_for_json_health(api_base: str, timeout_seconds: int) -> None:
    client = DemoClient(api_base, COOKIE_DIR / "health.cookies")
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            health = client.request("GET", "/api/health")
            if health.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - preserve last failure for operator output.
            last_error = exc
        time.sleep(2)
    raise DemoError(f"API health did not become ready within {timeout_seconds}s: {last_error}")


def wait_for_web(web_base: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with build_opener().open(web_base, timeout=10) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(2)
    raise DemoError(f"Web did not become ready within {timeout_seconds}s: {last_error}")


def migrate_db() -> None:
    run(["docker", "compose", "exec", "-T", "api", "alembic", "upgrade", "head"])


def local_lan_ip() -> str | None:
    for command in (["ipconfig", "getifaddr", "en0"], ["hostname", "-I"]):
        output = run_capture(command)
        if output:
            first = output.split()[0]
            if first and first != "127.0.0.1":
                return first
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def normalize_clubs(values: list[str] | None) -> list[str]:
    clubs = [value.strip() for value in values or DEFAULT_CLUBS if value.strip()]
    if not 2 <= len(clubs) <= 5:
        raise DemoError("Demo room needs 2 to 5 club names.")
    return clubs


def seed_demo(args: argparse.Namespace) -> dict[str, Any]:
    clubs = normalize_clubs(args.clubs)
    players = DEFAULT_PLAYERS[: len(clubs)]
    room_name = args.room_name
    year_label = args.year_label or str(datetime.now().year)

    host = DemoClient(args.api_base, COOKIE_DIR / "host.cookies")
    room = host.request(
        "POST",
        "/api/rooms",
        {
            "display_name": players[0],
            "room_name": room_name,
            "club_names": clubs,
        },
    )
    room_id = room["id"]
    invite_code = room["invite_code"]
    created_clubs = room["clubs"]
    all_players: list[dict[str, Any]] = []

    host_club = created_clubs[0]
    room = host.request("POST", f"/api/rooms/{room_id}/clubs/{host_club['id']}/claim")
    room = host.request("PATCH", f"/api/rooms/{room_id}/memberships/me/ready", {"ready": True})
    all_players.append(
        {
            "display_name": players[0],
            "club_id": host_club["id"],
            "club_name": host_club["name"],
            "cookie_file": str((COOKIE_DIR / "host.cookies").relative_to(ROOT)),
            "is_host": True,
        }
    )

    for index, club in enumerate(created_clubs[1:], start=2):
        cookie_file = COOKIE_DIR / f"player{index}.cookies"
        player = DemoClient(args.api_base, cookie_file)
        player.request(
            "POST",
            f"/api/rooms/{invite_code}/join",
            {"display_name": players[index - 1]},
        )
        player.request("POST", f"/api/rooms/{room_id}/clubs/{club['id']}/claim")
        player.request("PATCH", f"/api/rooms/{room_id}/memberships/me/ready", {"ready": True})
        all_players.append(
            {
                "display_name": players[index - 1],
                "club_id": club["id"],
                "club_name": club["name"],
                "cookie_file": str(cookie_file.relative_to(ROOT)),
                "is_host": False,
            }
        )

    season_id = None
    if not args.lobby_only:
        started = host.request("POST", f"/api/rooms/{room_id}/start", {"year_label": year_label})
        room = started["room"]
        season_id = started["season_id"]

    state = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "web_base": args.web_base,
        "room_name": room_name,
        "room_id": room["id"],
        "game_id": room["game_id"],
        "room_status": room["status"],
        "invite_code": room["invite_code"],
        "season_id": season_id,
        "year_label": year_label,
        "players": all_players,
        "state_file": str(STATE_FILE.relative_to(ROOT)),
    }
    save_state(state)
    return state


def delete_current_state(args: argparse.Namespace, *, missing_ok: bool) -> bool:
    state = load_state()
    if not state:
        if missing_ok:
            return False
        raise DemoError(f"No demo state found at {STATE_FILE}")

    host = DemoClient(state.get("api_base", args.api_base), ROOT / state["players"][0]["cookie_file"])
    game_id = state["game_id"]
    invite_code = state["invite_code"]

    try:
        host.request("POST", f"/api/games/{game_id}/archive")
    except DemoError as exc:
        if "HTTP 409" not in str(exc):
            raise
    try:
        host.request("DELETE", f"/api/games/{game_id}", {"confirm": invite_code})
    except DemoError as exc:
        if missing_ok and ("HTTP 404" in str(exc) or "HTTP 403" in str(exc)):
            return False
        raise

    save_state({**state, "deleted_at": datetime.now().isoformat(timespec="seconds"), "room_status": "deleted"})
    return True


def archive_current(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state()
    if not state:
        raise DemoError(f"No demo state found at {STATE_FILE}")
    host = DemoClient(state.get("api_base", args.api_base), ROOT / state["players"][0]["cookie_file"])
    result = host.request("POST", f"/api/games/{state['game_id']}/archive")
    save_state({**state, "room_status": "archived", "archived_at": datetime.now().isoformat(timespec="seconds")})
    return result


def current_status(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state()
    if not state:
        raise DemoError(f"No demo state found at {STATE_FILE}")
    host = DemoClient(state.get("api_base", args.api_base), ROOT / state["players"][0]["cookie_file"])
    status: dict[str, Any] = {"state": state}
    try:
        status["recent"] = host.request("GET", "/api/rooms/recent?include_archived=true")
    except DemoError as exc:
        status["recent_error"] = str(exc)
    if state.get("game_id") and state.get("room_status") != "archived":
        try:
            status["play_state"] = host.request("GET", f"/api/games/{state['game_id']}/play-state")
        except DemoError as exc:
            status["play_state_error"] = str(exc)
    return status


def print_summary(state: dict[str, Any]) -> None:
    lan_ip = local_lan_ip()
    print()
    print("Demo environment is ready.")
    print(f"  Web:        {state['web_base']}")
    print(f"  API:        {state['api_base']}")
    if lan_ip:
        print(f"  Web LAN:    http://{lan_ip}:3000")
        print(f"  API LAN:    http://{lan_ip}:8000")
    print(f"  Room:       {state['room_name']} ({state['room_status']})")
    print(f"  Invite:     {state['invite_code']}")
    print(f"  Game ID:    {state['game_id']}")
    if state.get("season_id"):
        print(f"  Season ID:  {state['season_id']}")
    print(f"  State:      {STATE_FILE.relative_to(ROOT)}")
    print("  Players:")
    for player in state["players"]:
        marker = "host" if player["is_host"] else "player"
        print(f"    - {player['display_name']} / {player['club_name']} / {marker} / {player['cookie_file']}")
    print()
    print("Useful next commands:")
    print("  ./scripts/demo_env.py status")
    print("  ./scripts/demo_env.py reset")
    print("  ./scripts/demo_env.py archive")
    print("  docker compose --profile web down")


def print_status(status: dict[str, Any]) -> None:
    state = status["state"]
    print(f"State: {STATE_FILE.relative_to(ROOT)}")
    print(f"Room: {state.get('room_name')} / {state.get('room_status')} / invite {state.get('invite_code')}")
    print(f"Web: {state.get('web_base')}")
    if "play_state" in status:
        play = status["play_state"]
        turn = play.get("turn") or {}
        season = play.get("season") or {}
        print(f"Season: S{season.get('number')} {season.get('year_label')} ({season.get('status')})")
        print(f"Turn: {turn.get('month_name')} ({turn.get('state')})")
        for club in play.get("clubs", []):
            print(f"  - {club['name']}: committed={club['committed']} acked={club['acked']}")
    if "recent_error" in status:
        print(f"Recent rooms check failed: {status['recent_error']}")
    if "play_state_error" in status:
        print(f"Play state check failed: {status['play_state_error']}")


def command_up(args: argparse.Namespace) -> None:
    start_stack(args)
    wait_for_json_health(args.api_base, args.timeout)
    migrate_db()
    wait_for_web(args.web_base, args.timeout)
    if args.no_seed:
        print("Docker demo stack is ready. Seed skipped.")
        return
    if args.reset:
        delete_current_state(args, missing_ok=True)
    if STATE_FILE.exists() and not args.reset and not args.force_new:
        state = load_state()
        if state and state.get("room_status") != "deleted":
            print("Existing demo state found. Use --reset or --force-new to create another room.")
            print_summary(state)
            return
    state = seed_demo(args)
    print_summary(state)


def command_reset(args: argparse.Namespace) -> None:
    if args.hard:
        docker_compose(["--profile", "web", "down", "-v"])
    command_up(argparse.Namespace(**{**vars(args), "reset": not args.hard, "force_new": True, "no_seed": False}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start and prepare the local Web demo environment.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--web-base", default=DEFAULT_WEB_BASE)
    parser.add_argument("--timeout", type=int, default=120)

    subparsers = parser.add_subparsers(dest="command")

    def add_common_options(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--api-base", default=DEFAULT_API_BASE, help=argparse.SUPPRESS)
        command_parser.add_argument("--web-base", default=DEFAULT_WEB_BASE, help=argparse.SUPPRESS)
        command_parser.add_argument("--timeout", type=int, default=120, help=argparse.SUPPRESS)

    up = subparsers.add_parser("up", help="Start Docker, migrate DB, and seed a demo room.")
    add_common_options(up)
    up.add_argument("--no-build", action="store_false", dest="build", help="Do not rebuild Docker images.")
    up.add_argument("--reset", action="store_true", help="Archive/delete the previous scripted demo before seeding.")
    up.add_argument("--force-new", action="store_true", help="Seed a new room even if .demo state already exists.")
    up.add_argument("--no-seed", action="store_true", help="Only start Docker and run migrations.")
    up.add_argument("--lobby-only", action="store_true", help="Stop after all clubs are claimed and ready.")
    up.add_argument("--room-name", default="Demo Training League")
    up.add_argument("--year-label")
    up.add_argument("--clubs", nargs="+")
    up.set_defaults(func=command_up, build=True, hard=False)

    reset = subparsers.add_parser("reset", help="Reset the scripted demo and create a fresh one.")
    add_common_options(reset)
    reset.add_argument("--hard", action="store_true", help="Use docker compose down -v before recreating the demo.")
    reset.add_argument("--no-build", action="store_false", dest="build", help="Do not rebuild Docker images.")
    reset.add_argument("--lobby-only", action="store_true", help="Stop after all clubs are claimed and ready.")
    reset.add_argument("--room-name", default="Demo Training League")
    reset.add_argument("--year-label")
    reset.add_argument("--clubs", nargs="+")
    reset.set_defaults(func=command_reset, build=True, reset=False, force_new=True, no_seed=False)

    archive = subparsers.add_parser("archive", help="Archive the current scripted demo via the Web API.")
    add_common_options(archive)
    archive.set_defaults(func=lambda args: print(json.dumps(archive_current(args), ensure_ascii=False, indent=2)))

    delete = subparsers.add_parser("delete", help="Archive and permanently delete the current scripted demo.")
    add_common_options(delete)
    delete.set_defaults(func=lambda args: print(f"deleted={delete_current_state(args, missing_ok=False)}"))

    status = subparsers.add_parser("status", help="Show saved demo state and current play-state.")
    add_common_options(status)
    status.set_defaults(func=lambda args: print_status(current_status(args)))

    down = subparsers.add_parser("down", help="Stop containers while keeping the PostgreSQL volume.")
    add_common_options(down)
    down.set_defaults(func=lambda args: docker_compose(["--profile", "web", "down"]))

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        args = parser.parse_args(["up"])
    try:
        args.func(args)
    except DemoError as exc:
        print(f"demo_env.py: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"demo_env.py: command failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
