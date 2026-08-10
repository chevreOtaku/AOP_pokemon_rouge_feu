"""La sonde Lua, cote Python -- les yeux et les mains.

Client ligne par ligne du serveur TCP ouvert par lua/probe.lua dans mGBA.

Ce module existe pour une raison precise : le marcheur manuel (walk.py) et la
brique (brick.py) parlent a la meme sonde. Deux copies de ce code finiraient
par diverger, et ce serait la mesure qui mentirait -- pas le code.

Protocole de la sonde (une ligne par requete, une ligne par reponse) :
    ping                 -> ok pong
    state                -> ok x=<n> y=<n> g=<n> n=<n>
    press <KEY> [frames] -> ok x=<n> y=<n> g=<n> n=<n>   (etat APRES stabilisation)
    err <message>        en cas d'echec
"""

import socket

# L'adresse est une VALEUR DE CONFIGURATION, jamais une constante.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9601

# Un pas fait ~16 frames sur GBA. Mesure par execution le 2026-08-10 :
# six appuis, six pas, aucun double.
PRESS_FRAMES = 16

# mapGroup == 255 : le jeu traverse une porte. Les coordonnees lues pendant
# cette fenetre ne designent aucune case stable -- les rapporter comme une
# position serait une etiquette fausse.
DOOR_TRANSITION = 255

KEYS = ("A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L")


class Probe:
    """Client ligne par ligne de la sonde Lua."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 15.0) -> None:
        self._sock = socket.create_connection((host, port), timeout=timeout)
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

    def state(self):
        return parse_state(self.ask("state"))

    def press(self, key: str, frames: int = PRESS_FRAMES):
        return parse_state(self.ask(f"press {key} {frames}"))

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


def is_stable(state) -> bool:
    """Faux pendant une transition de porte, ou si l'etat est illisible."""
    return state is not None and state["g"] != DOOR_TRANSITION
