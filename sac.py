"""Lire le sac en memoire -- ce que la partie possede, sans ouvrir un menu.

    python sac.py
    python sac.py --poche pokeballs
    python sac.py --json

Rend, pour chaque poche : les emplacements occupes, avec leur identifiant et
leur quantite dechiffree. Plus l'argent, qui sert de controle.

⚠⚠ IL NE REND PAS DE NOMS. Le sac stocke des identifiants ; le nom est a
l'ecran, et l'oeil le rend en `FFUR= DnLL`. La table identifiant -> nom se
construit par ACQUISITION -- on lit le sac, l'humain acquiert un objet, on
relit, un seul identifiant est neuf, il le nomme. Une methode par position a
ete refutee le 2026-09-01 : l'ordre depend de la partie, et la liste DEFILE,
donc la ligne vue n'est meme pas l'emplacement lu.

    La position n'est pas une identite. L'identifiant en est une.

=== POURQUOI UN SEUL DUMP, ET PAS 186 LECTURES ===

Les cinq poches font 186 emplacements, soit 372 lectures de 16 bits si on les
prenait une par une. Deux raisons de ne pas le faire, et la seconde est la
vraie :

1. 372 aller-retours TCP la ou un seul suffit ;
2. **le sac pourrait bouger entre la premiere lecture et la derniere.** Un
   inventaire compose de 372 instants differents n'est l'inventaire d'aucun
   instant. Un dump est une photo.

=== CE QUI SE REVERIFIE A CHAQUE APPEL ===

⚠ Les SaveBlocks DEMENAGENT en cours de partie. Les deux pointeurs se relisent
a chaque appel et l'adresse resolue n'est JAMAIS mise en cache -- meme regle
que pour la position et l'equipe.
"""

import argparse
import json
import sys

from adresses import (ARGENT, CLE_CHIFFREMENT, POCHES, PTR_SAVEBLOCK1,
                      PTR_SAVEBLOCK2, SAC_POCHE, sac_defilement, sac_ligne,
                      sac_selection)
from probe import DEFAULT_HOST, DEFAULT_PORT, EWRAM, Probe

TAILLE_ENTREE = 4


def _bloc(sonde, pointeur):
    """Resout un pointeur de SaveBlock. Rend None si la valeur ne pointe pas
    dans l'EWRAM -- partie non chargee, ou mauvaise cartouche."""
    adresse = sonde.read(pointeur, 32)
    lo, etendue = EWRAM
    if adresse is None or not lo <= adresse < lo + etendue:
        return None
    return adresse


def _u16(octets, position):
    return octets[position] | (octets[position + 1] << 8)


def lire_sac(sonde):
    """Le sac entier, en une photo. Rend un dict, jamais une exception.

    ⚠ Les erreurs se RAPPORTENT, elles ne se lancent pas : un appelant qui lit
    un sac veut savoir POURQUOI il n'a rien, et « pointeur invalide » n'appelle
    pas le meme geste que « la sonde ne repond plus ».
    """
    sb1 = _bloc(sonde, PTR_SAVEBLOCK1)
    if sb1 is None:
        return {"lu": False, "message": f"SaveBlock1 illisible -- {sonde.last_reply}"}
    sb2 = _bloc(sonde, PTR_SAVEBLOCK2)
    if sb2 is None:
        return {"lu": False, "message": f"SaveBlock2 illisible -- {sonde.last_reply}"}

    cle = sonde.read(sb2 + CLE_CHIFFREMENT, 32)
    if cle is None:
        return {"lu": False, "message": f"cle illisible -- {sonde.last_reply}"}
    cle16 = cle & 0xFFFF

    debut = min(off for _, off, _ in POCHES)
    fin = max(off + n * TAILLE_ENTREE for _, off, n in POCHES)
    octets = sonde.dump(sb1 + debut, fin - debut)
    if octets is None or len(octets) != fin - debut:
        recu = 0 if octets is None else len(octets)
        # ⚠ UN DUMP TRONQUE RESTE DE L'HEXA VALIDE. Sans ce controle de
        # longueur, une reponse coupee se lirait comme un sac plus petit --
        # et un objet manquant ne ressemble a rien d'anormal.
        return {"lu": False,
                "message": f"dump tronque : {recu} octets sur {fin - debut}"}

    poches = {}
    for nom, decalage, emplacements in POCHES:
        contenu = []
        for i in range(emplacements):
            position = decalage - debut + i * TAILLE_ENTREE
            identifiant = _u16(octets, position)
            if identifiant == 0:
                continue
            contenu.append({"emplacement": i,
                            "identifiant": identifiant,
                            "quantite": _u16(octets, position + 2) ^ cle16})
        poches[nom] = contenu

    # ⚠⚠ L'ETAT DU MENU N'A DE SENS QUE LE SAC OUVERT -- c'est un etat de MENU,
    # pas un etat de partie. Lu sac ferme il rend une valeur qui RESSEMBLE a une
    # lecture. On le rend quand meme, mais sous une cle qui le dit : c'est a
    # l'appelant, qui sait s'il vient d'ouvrir le sac, de decider.
    # ➜ Cote agent, l'ecran donne la seconde source : la liste porte « SORTIR ».
    menu = None
    poche = sonde.read(SAC_POCHE, 16)
    if poche is not None and 0 <= poche < len(POCHES):
        ligne = sonde.read(sac_ligne(poche), 16)
        defilement = sonde.read(sac_defilement(poche), 16)
        if ligne is not None and defilement is not None:
            menu = {"poche": poche,
                    "nom_poche": POCHES[poche][0],
                    "ligne": ligne,
                    "defilement": defilement,
                    # ⚠ Le curseur SEUL ment : mesure, `ligne = 3` sur deux
                    # objets differents. La somme est la seule position vraie.
                    "selection": sac_selection(ligne, defilement)}

    argent_brut = sonde.read(sb1 + ARGENT, 32)
    return {"lu": True,
            "saveblock1": sb1,
            "saveblock2": sb2,
            "poches": poches,
            "menu_si_ouvert": menu,
            # ⚠ L'argent n'est pas un ornement : c'est le SEUL nombre du sac
            # qui ait un temoin verifiable a l'ecran. Si la cle derive un jour,
            # c'est lui qui le dira -- les quantites, elles, n'ont rien contre
            # quoi se comparer.
            "argent": None if argent_brut is None else (argent_brut ^ cle) & 0xFFFFFFFF}


def _principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--poche", choices=[nom for nom, _, _ in POCHES],
                    help="n'afficher qu'une poche")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    sonde = Probe(args.hote, args.port)
    try:
        sac = lire_sac(sonde)
    finally:
        sonde.close()

    if args.json:
        print(json.dumps(sac, ensure_ascii=False))
        return 0 if sac["lu"] else 1

    if not sac["lu"]:
        print(f"sac non lu : {sac['message']}")
        return 1

    print(f"SaveBlock1 0x{sac['saveblock1']:08X}   "
          f"SaveBlock2 0x{sac['saveblock2']:08X}")
    argent = sac["argent"]
    print(f"argent : {argent if argent is not None else 'illisible'}"
          f"   <- se compare a l'ecran, c'est le controle de la cle")
    menu = sac["menu_si_ouvert"]
    if menu:
        print(f"menu   : poche {menu['poche']} ({menu['nom_poche']})   "
              f"ligne {menu['ligne']} + defilement {menu['defilement']} = "
              f"SELECTION {menu['selection']}"
              f"   <- ⚠ n'a de sens que le sac OUVERT")
    print()
    for nom, contenu in sac["poches"].items():
        if args.poche and nom != args.poche:
            continue
        if not contenu:
            print(f"{nom} : vide")
            continue
        print(f"{nom} :")
        for objet in contenu:
            print(f"   emplacement {objet['emplacement']:<3} "
                  f"id {objet['identifiant']:<5} x{objet['quantite']}")
    return 0


if __name__ == "__main__":
    sys.exit(_principal())
