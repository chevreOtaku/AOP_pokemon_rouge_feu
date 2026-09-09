"""Le repere « OU » -- releve chaque changement de CARTE, jamais de case.

    python cartes.py                 # jusqu'a Ctrl-C
    python cartes.py --duree 600     # dix minutes

=== LA QUESTION QU'IL SERT A TRANCHER ===

La RAM donne `mapGroup` et `mapNum` -- deux nombres. Personne ne sait s'ils
portent le TYPE du lieu.

    un NOM    « Jadielle »        une table de ~250 entrees, et le PIEGE DE LA
                                  LANGUE arme : la ROM est FRANCAISE, une table
                                  ecrite en anglais rendrait des noms faux avec
                                  l'autorite d'un fichier
    un TYPE   ville / route / interieur / grotte
                                  ce qui CHANGE LE SENS d'un evenement

⚠⚠ **Si `mapGroup` separe deja les types, le repere est GRATUIT** : pas de
table, pas de traduction, juste une lecture qu'on fait deja. C'est exactement
ce que ce script mesure -- et il ne repond pas a la question, il fournit de quoi
y repondre.

=== POURQUOI IL N'EMET QUE LES CHANGEMENTS DE CARTE ===

Chaque pas change `x` ou `y`. Un journal par case noierait le signal sous le
bruit : ce qu'on cherche, c'est la frontiere entre deux LIEUX.

⚠ La transition de porte (`mapGroup == 255`) est signalee mais **jamais
retenue comme une carte** : pendant ce laps, les coordonnees ne designent
aucune case.

=== CE QU'IL NE FAIT PAS ===

Il ne nomme rien et ne classe rien. C'est a l'humain qui marche d'annoter --
le script imprime une ligne par lieu, l'operateur ecrit a cote « ville »,
« route », « grotte ». **Un instrument qui devinerait le type produirait la
reponse qu'on veut mesurer.**
"""

import argparse
import datetime
import sys
import time
from typing import Optional, Tuple

from probe import DEFAULT_HOST, DEFAULT_PORT, Probe

PAS = 0.4
TRANSITION_DE_PORTE = 255


def _carte(etat) -> Optional[Tuple[int, int]]:
    """La carte courante, ou None si elle n'a pas de sens a cet instant."""
    if not etat:
        return None
    groupe, numero = etat.get("g"), etat.get("n")
    if groupe is None or numero is None or groupe == TRANSITION_DE_PORTE:
        return None
    return (groupe, numero)


def _principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--duree", type=float, default=3600.0)
    ap.add_argument("--pas", type=float, default=PAS)
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    try:
        sonde = Probe(args.hote, args.port)
    except OSError as panne:
        print(f"  sonde injoignable ({panne}) -- mGBA est-il ouvert, script charge ?")
        return 2

    print("  heure     groupe  numero   x    y     <- annote a la main : "
          "ville / route / interieur / grotte")
    print("  " + "-" * 78)

    precedente = None
    portes = 0
    debut = time.time()
    try:
        while time.time() - debut < args.duree:
            etat = sonde.state()
            carte = _carte(etat)
            if carte is None:
                # ⚠ On COMPTE les transitions au lieu de les taire : un journal
                # muet ne distingue pas « rien ne bouge » de « je ne lis plus ».
                if etat and etat.get("g") == TRANSITION_DE_PORTE:
                    portes += 1
            elif carte != precedente:
                heure = datetime.datetime.now().strftime("%H:%M:%S")
                fleche = "" if precedente is None else f"   (depuis {precedente})"
                print(f"  {heure}   {carte[0]:>5}   {carte[1]:>5}  "
                      f"{etat['x']:>3}  {etat['y']:>3}{fleche}", flush=True)
                precedente = carte
            time.sleep(args.pas)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sonde.close()
        except OSError as panne:
            print(f"  (fermeture imparfaite : {panne})")

    print(f"\n  {portes} passage(s) de porte ignore(s) -- coordonnees sans "
          f"signification pendant la transition.")
    return 0


if __name__ == "__main__":
    sys.exit(_principal())
