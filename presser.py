"""Presser un bouton, une fois, et le dire.

Ce module expose la moitie ACTION d'un pont. Il ne decide rien, ne retient rien,
et ne juge pas le resultat : presser est un geste, pas une reussite.

⚠⚠ IL NE RAPPORTE PAS « CA A MARCHE ». La sonde rend la position du personnage
apres stabilisation -- utile pour marcher, **sans aucun sens dans un menu**, ou
la position ne bouge pas. Un appelant qui veut savoir ce que la pression a fait
doit RELIRE l'ecran. C'est la regle du protocole : un pont constate, il ne juge
pas, et juger supposerait de connaitre l'intention -- qu'il n'a pas.

⚠ AUCUN ETAT. Une pression, une reponse, et on oublie.

Usage :
    python presser.py A
    python presser.py DOWN --frames 6
"""

import argparse
import json
import sys

from probe import DEFAULT_HOST, DEFAULT_PORT, Probe

TOUCHES = ("A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L")


def _principal():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("touche", help=f"une de : {' '.join(TOUCHES)}")
    ap.add_argument("--frames", type=int, default=None,
                    help="duree de la pression (defaut : celui de la sonde)")
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    touche = args.touche.upper()
    if touche not in TOUCHES:
        # ⚠ On refuse AVANT d'ouvrir la connexion : une touche inconnue est une
        # faute d'appelant, pas une panne de sonde, et les confondre enverrait
        # chercher le probleme au mauvais endroit.
        print(json.dumps({"presse": False,
                          "message": f"touche inconnue : {args.touche} "
                                     f"(connues : {' '.join(TOUCHES)})"},
                         ensure_ascii=False))
        return 2

    try:
        sonde = Probe(args.hote, args.port)
    except OSError as e:
        print(json.dumps({"presse": False,
                          "message": f"sonde injoignable sur {args.hote}:"
                                     f"{args.port} -- {e}"},
                         ensure_ascii=False))
        return 2

    try:
        if sonde.ask("ping") != "ok pong":
            print(json.dumps({"presse": False,
                              "message": f"la sonde repond mais pas 'pong' : "
                                         f"{sonde.last_reply}"},
                             ensure_ascii=False))
            return 2

        apres = (sonde.press(touche, args.frames) if args.frames
                 else sonde.press(touche))
        # ⚠ `apres` est la POSITION du personnage. En menu elle ne bouge pas :
        # ce champ ne dit donc PAS si la pression a eu un effet. Il est rendu
        # tel quel, nomme pour ce qu'il est, et surtout pas appele « resultat ».
        reponse = {"presse": sonde.last_reply.startswith("ok"),
                   "touche": touche,
                   "position_apres": apres,
                   "message": sonde.last_reply,
                   "note": "la position n'a aucun sens en menu -- relire "
                           "l'ecran pour savoir ce que la pression a fait"}
    finally:
        sonde.close()

    print(json.dumps(reponse, ensure_ascii=False))
    return 0 if reponse["presse"] else 1


if __name__ == "__main__":
    sys.exit(_principal())
