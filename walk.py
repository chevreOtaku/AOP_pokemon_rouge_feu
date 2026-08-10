"""Marcheur manuel -- etape 2 : valider le capteur, deterministe.

Un humain tape une direction, le script l'envoie a la sonde Lua, relit la
position, et affiche AVANT -> APRES avec le delta.

Aucun protocole, aucun cerveau, aucun LLM. Cette etape existe pour une seule
raison : c'est le SEUL moment ou l'on dispose d'une verite de terrain -- on
sait ou l'on a demande d'aller. La sauter, c'est se condamner a ne plus
pouvoir distinguer "le modele erre" de "mon capteur est faux".

Usage :
    python walk.py                 # localhost:9601
    python walk.py --host 1.2.3.4 --port 9601

Commandes : z q s d (ou nord sud ouest est) . a b . state . quit
"""

import argparse
import socket
import sys

# L'adresse est une VALEUR DE CONFIGURATION, jamais une constante.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9601

DIRECTIONS = {
    "z": "UP", "s": "DOWN", "q": "LEFT", "d": "RIGHT",
    "nord": "UP", "sud": "DOWN", "ouest": "LEFT", "est": "RIGHT",
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
}
BUTTONS = {"a": "A", "b": "B", "start": "START", "select": "SELECT"}


class Probe:
    """Client ligne par ligne de la sonde Lua."""

    def __init__(self, host: str, port: int) -> None:
        self._sock = socket.create_connection((host, port), timeout=15)
        self._buf = b""

    def ask(self, line: str) -> str:
        self._sock.sendall((line + "\n").encode("ascii"))
        while b"\n" not in self._buf:
            chunk = self._sock.recv(512)
            if not chunk:
                raise ConnectionError("la sonde a ferme la connexion")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\n", 1)
        return raw.decode("ascii", errors="replace").strip()

    def close(self) -> None:
        self._sock.close()


def parse_state(reply: str):
    """'ok x=12 y=34 g=3 n=1' -> dict, ou None si la sonde a rendu une erreur."""
    if not reply.startswith("ok "):
        return None
    out = {}
    for token in reply[3:].split():
        key, _, value = token.partition("=")
        if value.lstrip("-").isdigit():
            out[key] = int(value)
    return out if {"x", "y", "g", "n"} <= out.keys() else None


def show(before, after, action: str) -> None:
    if before is None or after is None:
        print(f"  {action:6} -> etat illisible")
        return
    dx, dy = after["x"] - before["x"], after["y"] - before["y"]
    moved = dx != 0 or dy != 0
    carte = "" if (before["g"], before["n"]) == (after["g"], after["n"]) else \
            f"  CARTE {before['g']}:{before['n']} -> {after['g']}:{after['n']}"
    if after["g"] == 255:
        carte += "  (transition de porte)"
    print(f"  {action:6} ({before['x']},{before['y']}) -> ({after['x']},{after['y']})"
          f"  delta=({dx:+d},{dy:+d}){'' if moved else '   MUR ou pas avale'}{carte}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--frames", type=int, default=16, help="duree de l'appui")
    args = ap.parse_args()

    try:
        probe = Probe(args.host, args.port)
    except OSError as exc:
        print(f"Connexion impossible a {args.host}:{args.port} -- {exc}")
        print("La sonde tourne-t-elle ? (mGBA > Outils > Scripting > probe.lua)")
        return 1

    print(f"Connecte a {args.host}:{args.port}")
    print(probe.ask("state"))
    print("z/q/s/d pour marcher, a/b pour les boutons, 'state', 'quit'.")
    print("ATTENTION: un dialogue ouvert AVALE les pas -- fermez-le par 'a' avant de marcher.")

    try:
        while True:
            try:
                cmd = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not cmd:
                continue
            if cmd in ("quit", "q!", "exit"):
                break
            if cmd == "state":
                print(" ", probe.ask("state"))
                continue

            key = DIRECTIONS.get(cmd) or BUTTONS.get(cmd)
            if not key:
                print("  ? z q s d / a b / state / quit")
                continue

            before = parse_state(probe.ask("state"))
            after = parse_state(probe.ask(f"press {key} {args.frames}"))
            show(before, after, cmd)
    finally:
        probe.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
