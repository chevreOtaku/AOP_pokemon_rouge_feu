"""Trouver l'index du curseur sur l'ecran d'equipe -- en memoire, pas a l'oeil.

⚠⚠⚠ NE PAS LANCER CE SCRIPT. Ecrit le 2026-08-21, jamais lance, et le
2026-09-02 on a appris pourquoi il ne faut pas :

    LE CURSEUR VIVANT DE L'ECRAN D'EQUIPE EST SUR LE TAS.

Une integration de reference a fait cette chasse, trouve une adresse, et
constate ensuite que c'etait un OCTET FANTOME -- une copie qui correle le temps
d'une session puis se deplace. Leur note, verbatim : *« the wedge was a
WRONG-ADDRESS derivation (the old PARTY_CURSOR was a shadow byte) ; live cursor
is a heap struct »*.

⚠⚠ CE SCRIPT AURAIT DONC REUSSI, ET EU TORT. C'est le pire resultat possible :
trois captures, un croisement propre, une adresse qui passe tous les controles
du jour -- et qui ment la semaine suivante. Un faux positif qui a l'air d'une
mesure ne se distingue pas d'une mesure.

⚠ CE QUI MARCHE, ET CE N'EST NI LA RAM NI L'OCR : le contour orange se lit AU
PIXEL. `(255,115,49)` en phase vive, `~(123,90,57)` en phase de fondu, sur le
bord superieur de chaque case. Voir la decision D-K.

➜ Le script est garde pour sa METHODE -- trois captures, deux contraintes
croisees, et un second jeu de candidats sans contrainte de valeur. Elle reste
bonne pour une adresse qui EXISTE. Elle ne peut rien contre une qui n'existe pas.


    (ouvrir l'ecran d'equipe, curseur sur le PREMIER Pokemon)
    python chasse_curseur.py
    python chasse_curseur.py --direction RIGHT     # si DOWN ne bouge pas

⚠⚠⚠ POURQUOI CET ECRAN NE SE LIT PAS COMME LES AUTRES. Mesure du 2026-08-21 :
sur l'ecran d'equipe, l'OCR ne rend que « Choisir un POKeMON. » et « SORTIR ».
Ni les noms, ni les niveaux, ni les PV -- et surtout, **le curseur est un
CONTOUR ORANGE, pas du texte**. Aucun oeil ne le lira jamais.

Consequence directe : la methode de l'ecran d'attaques -- presser, relire, voir
si la signature a change -- **ne peut pas fonctionner ici**. La signature lue
est identique quelle que soit la position du curseur, donc chaque pas se
lirait « butee ». Il n'y a pas de reglage a ajuster : l'information n'est pas
a l'ecran.

➜ Elle est en memoire. Le reste (surnom, niveau, PV, K.O.) y est deja.

=== LA METHODE, ET ELLE EST LA PLUS SELECTIVE DU DOSSIER ===

Trois captures, deux contraintes croisees :

    A  curseur sur le premier          on attend  0
    B  apres une pression              on attend  1
    C  apres la pression inverse       on attend  0

Une adresse doit AVOIR CHANGE puis ETRE REVENUE **et** porter exactement
0 / 1 / 0. Un compteur d'animation ne tient aucune des deux.

⚠ 0/1/0 est une HYPOTHESE sur l'encodage : le jeu pourrait compter a partir de
1, ou ranger un pointeur. C'est pour ca que le second jeu de candidats --
« a change puis est revenu », sans contrainte de valeur -- est rapporte AUSSI.
Ne rien trouver dans le premier ne veut pas dire que le curseur n'est pas la.
"""

import argparse
import sys

from chasse import capturer, charger, parcourir
from probe import DEFAULT_HOST, DEFAULT_PORT, Probe

OPPOSEES = {"DOWN": "UP", "UP": "DOWN", "RIGHT": "LEFT", "LEFT": "RIGHT"}


def _presser(sonde, touche: str) -> None:
    """⚠ Une pression qui echoue ARRETE la chasse. Continuer produirait trois
    captures dont on ne sait plus a quel etat elles correspondent -- et une
    capture mal etiquetee est pire qu'une capture manquante."""
    apres = sonde.press(touche)
    if apres is None:
        raise SystemExit(f"pression {touche} refusee : {sonde.last_reply}")


def _valeurs(etiquette, taille):
    return dict(parcourir(charger(etiquette), taille))


def _principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--direction", default="DOWN", choices=sorted(OPPOSEES))
    ap.add_argument("--taille", type=int, default=1, choices=(1, 2))
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    retour = OPPOSEES[args.direction]
    print(f"⚠ L'ecran d'equipe doit etre OUVERT, curseur sur le PREMIER "
          f"Pokemon. Sequence : {args.direction} puis {retour}.\n")

    sonde = Probe(args.hote, args.port)
    try:
        print("[A] curseur au depart...")
        capturer(sonde, "curseur_a")
        _presser(sonde, args.direction)
        print(f"\n[B] apres {args.direction}...")
        capturer(sonde, "curseur_b")
        _presser(sonde, retour)
        print(f"\n[C] apres {retour} -- on doit etre revenu...")
        capturer(sonde, "curseur_c")
    finally:
        sonde.close()

    a = _valeurs("curseur_a", args.taille)
    b = _valeurs("curseur_b", args.taille)
    c = _valeurs("curseur_c", args.taille)

    revenues = [addr for addr, va in a.items()
                if b.get(addr) != va and c.get(addr) == va]
    exactes = [addr for addr in revenues
               if a[addr] == 0 and b[addr] == 1]

    print(f"\na change PUIS est revenu : {len(revenues)} adresse(s)")
    print(f"dont exactement 0 / 1 / 0 : {len(exactes)} adresse(s)")
    for addr in exactes[:20]:
        print(f"   0x{addr:08X}   {a[addr]} -> {b[addr]} -> {c[addr]}")
    if not exactes:
        # ⚠ On ne rend pas une liste vide en silence : « rien trouve » et
        # « l'hypothese d'encodage etait fausse » demandent deux gestes
        # opposes, et seule la seconde liste permet de les distinguer.
        print("\n⚠ Aucune adresse en 0/1/0. Deux lectures possibles :")
        print("   - la direction ne deplace pas le curseur "
              f"-> reessayer avec --direction {'RIGHT' if args.direction == 'DOWN' else 'DOWN'}")
        print("   - l'encodage n'est pas 0/1 -> regarder les revenues :")
        for addr in revenues[:20]:
            print(f"   0x{addr:08X}   {a[addr]} -> {b[addr]} -> {c[addr]}")
    return 0


if __name__ == "__main__":
    sys.exit(_principal())
