"""La sonde Lua, cote Python -- les yeux et les mains.

Client ligne par ligne du serveur TCP ouvert par lua/probe.lua dans mGBA.

Ce module existe pour une raison precise : le marcheur manuel (walk.py) et la
brique (brick.py) parlent a la meme sonde. Deux copies de ce code finiraient
par diverger, et ce serait la mesure qui mentirait -- pas le code.

Protocole de la sonde (une ligne par requete, une ligne par reponse) :
    ping                 -> ok pong
    state                -> ok x=<n> y=<n> g=<n> n=<n>
    press <KEY> [frames] -> ok x=<n> y=<n> g=<n> n=<n>   (etat APRES stabilisation)
    read8|16|32 <addr>   -> ok <valeur>
    dump <addr> <len>    -> ok <hexa>
    blocks <a> <l> <b>   -> ok <somme par bloc>
    err <message>        en cas d'echec

⚠ Les trois dernieres servent a CHERCHER une adresse, pas a lire un etat connu.
Aucune carte memoire n'existe pour la version FR : chaque adresse se trouve par
scan et correlation, comme le pointeur de position en juillet. Le tri se fait
ici, en Python -- la sonde rend des octets et ne decide rien.
"""

import socket

# L'adresse est une VALEUR DE CONFIGURATION, jamais une constante.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9601

# ⚠ CETTE VALEUR EST CELLE DE LA MARCHE, ET SEULEMENT D'ELLE.
# Un pas fait ~16 frames sur GBA. Mesure par execution le 2026-08-10 :
# six appuis, six pas, aucun double. Le test etait le BON -- un test de
# doublement -- et il portait sur le DEPLACEMENT.
PRESS_FRAMES = 16

# ⚠⚠ DANS UN MENU, 16 FAIT DEUX PAS DE CURSEUR. Mesure du 2026-09-06 sur
# l'ecran d'equipe : presser BAS, relire la position surlignee.
#
#     images   duree a 59,9 fps   pas mesures
#        16         267 ms        2 2 2
#        14         234 ms        2 2 2
#        13         217 ms        1 1 2   <- la frontiere, INSTABLE dessus
#        12         200 ms        1 1 1
#         8         134 ms        1 1 1 1 1 1 1 1
#
# Le jeu REPETE une direction maintenue. Ce n'est pas la repetition clavier du
# systeme : elle vaut ~500 ms sur le poste d'essai, le DOUBLE du seuil observe.
#
# ⚠ IMAGES OU MILLISECONDES : NON TRANCHE. Le tableau vient d'un seul regime
# (59,9 fps), ou les deux grandeurs sont proportionnelles -- donc indiscernables
# par cette mesure. 8 est retenu parce qu'il est sur SOUS LES DEUX hypotheses :
# loin du seuil en images (8 < 13) et court en temps (134 ms).
#
# ⚠ Mesure faite en maintenant la touche cote SYSTEME, pas via `press` de
# cette sonde -- qui compte, elle, en images emulees. Le seuil appartient au
# JEU et ne devrait pas dependre du chemin, mais la confirmation par la sonde
# RESTE A FAIRE.
#
# ⚠⚠ LA LECON VAUT MIEUX QUE LE NOMBRE :
#     *une mesure valide un nombre DANS SON CONTEXTE ; le nombre voyage, la
#      mesure non.*
# Le 16 ci-dessus est juste et mesure. Il est devenu faux en changeant d'usage,
# sans que personne ne le modifie et sans qu'aucun test n'echoue.
PRESS_FRAMES_MENU = 8

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
        # Derniere reponse brute. ⚠ `parse_state` reduit TOUTE reponse non-`ok`
        # au meme None, ce qui efface la raison : « pointeur invalide » et
        # « une pression est deja en cours » deviennent indiscernables alors
        # qu'elles demandent deux gestes opposes. La sonde nous dit pourquoi ;
        # sans ceci, l'appelant jette le message.
        self.last_reply = ""

    def ask(self, line: str) -> str:
        self._sock.sendall((line + "\n").encode("ascii"))
        while b"\n" not in self._buf:
            # 64 Ko : un `dump` de 4096 octets fait 8192 caracteres hexa. A 512
            # octets par tour, la meme reponse demandait seize fois plus d'appels.
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("la sonde a ferme la connexion")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\n", 1)
        self.last_reply = raw.decode("ascii", errors="replace").strip()
        return self.last_reply

    def state(self):
        return parse_state(self.ask("state"))

    def press(self, key: str, frames: int = PRESS_FRAMES):
        return parse_state(self.ask(f"press {key} {frames}"))

    def read(self, addr: int, taille: int = 8):
        """Lit 8, 16 ou 32 bits. Rend None sur refus -- la raison est dans
        `last_reply`, et elle compte : « hors region » et « lecture impossible »
        n'appellent pas le meme geste."""
        if taille not in (8, 16, 32):
            raise ValueError(f"taille inattendue: {taille}")
        reponse = self.ask(f"read{taille} 0x{addr:08X}")
        if not reponse.startswith("ok "):
            return None
        valeur = reponse[3:].strip()
        return int(valeur) if valeur.lstrip("-").isdigit() else None

    def dump(self, addr: int, longueur: int):
        """Rend `longueur` octets, ou None si la sonde refuse."""
        reponse = self.ask(f"dump 0x{addr:08X} {longueur}")
        if not reponse.startswith("ok "):
            return None
        try:
            return bytes.fromhex(reponse[3:].strip())
        except ValueError:
            return None

    def blocks(self, addr: int, longueur: int, taille_bloc: int = 256):
        """Une somme par bloc : de quoi comparer deux instants sans transporter
        la memoire entiere. Rend une liste d'entiers, ou None."""
        reponse = self.ask(f"blocks 0x{addr:08X} {longueur} {taille_bloc}")
        if not reponse.startswith("ok "):
            return None
        try:
            return [int(x) for x in reponse[3:].split()]
        except ValueError:
            return None

    def close(self) -> None:
        self._sock.close()


# Regions lisibles d'une GBA -- memes bornes que la sonde, cote Python pour
# qu'un appelant puisse cadrer sa recherche sans faire l'aller-retour.
EWRAM = (0x02000000, 0x00040000)   # 256 Ko : l'etat de partie vit surtout ici
IWRAM = (0x03000000, 0x00008000)   # 32 Ko : pointeurs et variables de travail


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
