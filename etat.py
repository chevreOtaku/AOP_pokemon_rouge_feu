"""L'etat des deux combattants, tel que la memoire le porte MAINTENANT.

Ce module expose l'ETAT -- la premiere des trois choses qu'un pont doit fournir
(protocole/ce-qu-un-pont-doit-exposer). Il ne fournit ni les ACTIONS ni le
RESULTAT : les actions sont pressees a la main pour l'instant, et le RESULTAT
est un delta, donc il demande une memoire -- que ce pont n'a pas et ne doit pas
avoir.

⚠ IL CONSTATE, IL NE JUGE PAS. Il ne dit jamais « on est en combat », parce
qu'il ne peut pas le savoir : la fiche adverse SURVIT a la fin du combat, et une
fiche perimee se lit exactement comme une fiche vivante (mesure du 2026-08-13 :
niveau 3, 0/15, hors combat). Il rend ce que les octets portent, avec un verdict
de PLAUSIBILITE, et l'appelant tranche avec ce qu'il voit par ailleurs.

⚠ AUCUN CONTEXTE ACCUMULE, aucune identite, aucun nom interne. Une lecture, une
reponse, et on oublie. C'est ce qui rend une mesure reproductible.

⚠⚠ UN ZERO SE VERIFIE A UN SECOND INSTANT. Une lecture prise pendant un fondu
de transition rend des structures vides qui, deux secondes plus tard, sont
intactes. Ce module ne re-lit pas de lui-meme -- il DECLARE l'implausibilite et
laisse l'appelant relire, parce qu'attendre ici bloquerait sa boucle.

Usage :
    python etat.py              # JSON sur la sortie standard
    python etat.py --lisible    # pour un humain
"""

import argparse
import json
import sys

from adresses import (NIVEAU, PV_ADVERSE, PV_EQUIPE, PV_MAX, STAGE_NEUTRE,
                      STAGES_ADVERSE, STAGES_EQUIPE)
from probe import DEFAULT_HOST, DEFAULT_PORT, Probe

# Bornes de plausibilite. Elles ne prouvent pas qu'une fiche est VIVANTE --
# seulement qu'elle n'est pas manifestement vide ou en cours de transition.
NIVEAU_MIN, NIVEAU_MAX = 1, 100

# Les sept modificateurs, dans l'ordre ou la memoire les range. L'emplacement 0
# est prevu pour les PV et ne sert pas.
NOMS_STAGES = ("", "attaque", "defense", "vitesse", "attaque_speciale",
               "defense_speciale", "precision", "esquive")
STAGE_MIN, STAGE_MAX = 0, 12


def lire_fiche(sonde, base):
    """Une fiche de combattant : niveau, PV, PV max, et si elle tient debout."""
    fiche = {"niveau": None, "pv": None, "pv_max": None,
             "plausible": False, "pourquoi": ""}

    fiche["niveau"] = sonde.read(base + NIVEAU, 8)
    fiche["pv"] = sonde.read(base, 16)
    fiche["pv_max"] = sonde.read(base + PV_MAX, 16)

    if None in (fiche["niveau"], fiche["pv"], fiche["pv_max"]):
        fiche["pourquoi"] = f"lecture refusee par la sonde : {sonde.last_reply}"
        return fiche
    if not NIVEAU_MIN <= fiche["niveau"] <= NIVEAU_MAX:
        fiche["pourquoi"] = (f"niveau {fiche['niveau']} hors bornes -- structure "
                             f"vide, ou lecture prise pendant une transition")
        return fiche
    if fiche["pv_max"] == 0:
        fiche["pourquoi"] = "PV max nuls -- meme cause qu'un niveau hors bornes"
        return fiche
    if fiche["pv"] > fiche["pv_max"]:
        fiche["pourquoi"] = (f"PV {fiche['pv']} > max {fiche['pv_max']} -- "
                             f"les octets ne decrivent pas un combattant")
        return fiche

    fiche["plausible"] = True
    return fiche


def lire_stages(sonde, base):
    """Les modificateurs de statistiques, en CRANS relatifs au neutre.

    ⚠ On rend le nombre de crans (`-1`, `+2`), pas la valeur brute (5, 8) :
    l'octet stocke est un detail d'implementation du jeu, et le cran est ce que
    le jeu ANNONCE quand il change (« l'ATTAQUE de X baisse ! »).

    ⚠⚠ Rend `None` si les octets ne decrivent pas un tableau plausible. Hors
    combat cette zone porte des restes, et un tableau de restes se lit comme un
    tableau valide -- meme piege que la fiche adverse.
    """
    brut = [sonde.read(base + i, 8) for i in range(len(NOMS_STAGES))]
    if any(v is None or not STAGE_MIN <= v <= STAGE_MAX for v in brut):
        return None
    return {nom: brut[i] - STAGE_NEUTRE
            for i, nom in enumerate(NOMS_STAGES) if nom}


def etat(sonde):
    joueur = lire_fiche(sonde, PV_EQUIPE)
    adverse = lire_fiche(sonde, PV_ADVERSE)
    # ⚠ Les modificateurs vivent dans une AUTRE structure que les fiches
    # d'equipe -- une structure de COMBAT, qui n'existe que pendant un combat.
    # Ils sont donc lus separement et peuvent manquer alors que les PV sont la.
    joueur["stages"] = lire_stages(sonde, STAGES_EQUIPE)
    adverse["stages"] = lire_stages(sonde, STAGES_ADVERSE)
    return {"sonde": "ok", "joueur": joueur, "adverse": adverse}


def _principal():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--lisible", action="store_true")
    args = ap.parse_args()

    # ⚠ L'ECHEC DE CONNEXION SORT EN JSON LUI AUSSI. Un appelant qui parse la
    # sortie ne doit pas avoir a distinguer « du JSON » de « un message
    # d'erreur » : les deux formes obligeraient a deux chemins de lecture, et
    # c'est le second qu'on oublie d'ecrire.
    try:
        sonde = Probe(args.hote, args.port)
    except OSError as e:
        panne = {"sonde": f"injoignable sur {args.hote}:{args.port} -- {e}",
                 "joueur": None, "adverse": None}
        print(json.dumps(panne, ensure_ascii=False))
        return 2

    # ⚠⚠⚠ UN `except`, PAS SEULEMENT UN `finally`. `Probe.ask()` LEVE
    # (`ConnectionError`, `socket.timeout`), et sans ce filet ce script crachait
    # un TRACEBACK a la place du JSON -- exactement ce que le docstring de ce
    # fichier interdit. Le defaut a ete mesure sur le module frere le 2026-08-16 :
    # l'appelant a lu « reponse illisible » et interrompu son travail alors que
    # la sonde etait vivante.
    try:
        if sonde.ask("ping") != "ok pong":
            panne = {"sonde": f"repond mais pas 'pong' : {sonde.last_reply}",
                     "joueur": None, "adverse": None}
            print(json.dumps(panne, ensure_ascii=False))
            return 2
        resultat = etat(sonde)
    except (OSError, ConnectionError) as e:
        panne = {"sonde": f"{type(e).__name__} pendant la lecture : {e}",
                 "joueur": None, "adverse": None}
        print(json.dumps(panne, ensure_ascii=False))
        return 2
    finally:
        sonde.close()

    if not args.lisible:
        print(json.dumps(resultat, ensure_ascii=False))
        return 0

    for role in ("joueur", "adverse"):
        f = resultat[role]
        if f["plausible"]:
            print(f"  {role:8s} niveau {f['niveau']:3d}   "
                  f"{f['pv']}/{f['pv_max']} PV")
        else:
            print(f"  {role:8s} IMPLAUSIBLE -- {f['pourquoi']}")
    return 0


if __name__ == "__main__":
    sys.exit(_principal())
