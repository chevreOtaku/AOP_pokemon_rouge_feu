"""Combien d'appuis depuis la derniere fois -- et qui les a faits.

⚠ SEMANTIQUE DE VIDANGE : chaque appui n'est rendu qu'une fois. Lire consomme.

⚠⚠ `humain` et `moi` sont separes : la sonde voit ses propres pressions -- celles
qu'un client envoie via `press` -- exactement comme celles d'un humain. Sans
cette separation, un pilote automatique se declencherait sur lui-meme, en boucle.

⚠ CE CANAL DIT « QUAND REGARDER », JAMAIS « TOUT CE QUI ARRIVE ». Un adversaire
qui attaque, un niveau qui monte, une animation qui se joue : rien de tout cela
ne presse une touche.

Usage :
    python touches.py
"""

import argparse
import json
import sys

from probe import DEFAULT_HOST, DEFAULT_PORT, Probe


def _principal():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    try:
        sonde = Probe(args.hote, args.port)
    except OSError as e:
        print(json.dumps({"lu": False, "message": f"sonde injoignable : {e}"},
                         ensure_ascii=False))
        return 2

    # ⚠ `except` ET `finally` : `Probe.ask()` leve, et sans filet ce script
    # cracherait un traceback la ou l'appelant attend du JSON. Le defaut a ete
    # mesure sur les deux CLI voisines le 2026-08-16.
    try:
        reponse = sonde.ask("keys")
        if not reponse.startswith("ok "):
            print(json.dumps({"lu": False, "message": reponse},
                             ensure_ascii=False))
            return 1
        champs = dict(p.split("=", 1) for p in reponse[3:].split() if "=" in p)
        resultat = {"lu": True,
                    "humain": int(champs.get("humain", 0)),
                    "moi": int(champs.get("moi", 0)),
                    "dernier": int(champs.get("dernier", 0)),
                    "frame": int(champs.get("frame", -1))}
    except (OSError, ConnectionError, ValueError) as e:
        print(json.dumps({"lu": False,
                          "message": f"{type(e).__name__} : {e}"},
                         ensure_ascii=False))
        return 2
    finally:
        sonde.close()

    print(json.dumps(resultat, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_principal())
