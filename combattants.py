"""Qui COMBAT -- la fiche de combat, et le PID qui la relie a l'equipe.

    python -m pytest test_combattants.py -q

⚠⚠⚠ POURQUOI CE MODULE. `equipe.py` rend `actif = emplacement 0`, et plusieurs
docstrings du chantier affirmaient que « rien en memoire ne dit qui combat ».
C'etait faux : la fiche de combat (`adresses.COMBATTANT_*`) porte l'espece, le
niveau, les PV, le surnom et le PID du combattant REEL. Mesure du 2026-09-15,
apres un changement : le PID designait l'emplacement 2, et le 0 etait un autre
Pokemon. Tout ce qui supposait l'emplacement 0 ecrivait le nom de l'un avec les
nombres de l'autre.

⚠⚠ UNE LECTURE DE 88 OCTETS, PAS SIX. La fiche porte deja le surnom et les
nombres : l'equipe n'est relue que pour savoir QUEL EMPLACEMENT combat.

⚠ Hors combat, la fiche garde le DERNIER combattant. Ce module dit qui a
combattu ; il ne dit pas qu'un combat a lieu. Cette preuve reste a l'appelant.
"""
import struct
from typing import Any, Dict, Optional

from adresses import COMBATTANT_ADVERSE, COMBATTANT_JOUEUR, PAS_COMBATTANT
from equipe import lire_surnom

TAILLE_COMBATTANT = PAS_COMBATTANT
ESPECE_MAX = 411            # la derniere entree nommee de la table des especes


def lire_struct_combattant(octets: Optional[bytes]) -> Dict[str, Any]:
    """88 octets -> `{espece, niveau, pv, pv_max, surnom, pid, plausible, pourquoi}`. PURE."""
    fiche: Dict[str, Any] = {"plausible": False, "pourquoi": ""}
    if not octets or len(octets) < TAILLE_COMBATTANT:
        fiche["pourquoi"] = "fiche de combat trop courte"
        return fiche

    fiche["espece"] = struct.unpack_from("<H", octets, 0x00)[0]
    fiche["pv"] = struct.unpack_from("<H", octets, 0x28)[0]
    fiche["niveau"] = octets[0x2A]
    fiche["pv_max"] = struct.unpack_from("<H", octets, 0x2C)[0]
    surnom = lire_surnom(octets[0x30:0x3B])
    fiche["surnom"] = surnom["surnom"]
    fiche["surnom_octets_inconnus"] = surnom["octets_inconnus"]
    fiche["pid"] = struct.unpack_from("<I", octets, 0x48)[0]

    fiche["pourquoi"] = _pourquoi_implausible(fiche)
    fiche["plausible"] = not fiche["pourquoi"]
    return fiche


def _pourquoi_implausible(fiche: Dict[str, Any]) -> str:
    if fiche["pid"] == 0:
        return "PID nul -- fiche jamais remplie"
    if not 1 <= fiche["niveau"] <= 100:
        return f"niveau {fiche['niveau']} hors bornes"
    if fiche["pv_max"] == 0 or fiche["pv"] > fiche["pv_max"]:
        return f"PV {fiche['pv']}/{fiche['pv_max']} impossibles"
    if not 1 <= fiche["espece"] <= ESPECE_MAX:
        return f"espece {fiche['espece']} hors de la table"
    return ""


def enrichir_equipe(lu: Dict[str, Any], combattant: Dict[str, Any]) -> Dict[str, Any]:
    """Marque `au_combat` sur l'emplacement qui porte le PID du combattant. PURE.

    ⚠ Rend une COPIE et n'ajoute que des cles : `actif` garde son sens d'avant
    (l'emplacement 0), parce qu'un consommateur s'en sert pour une capture.
    ⚠⚠ Ne marque PERSONNE plutot que le mauvais, et dit pourquoi.
    """
    rendu = dict(lu)
    equipe = [dict(f) for f in (lu.get("equipe") or [])]
    rendu["equipe"] = equipe

    if not combattant.get("plausible"):
        rendu["au_combat_raison"] = (f"fiche de combat inutilisable -- "
                                     f"{combattant.get('pourquoi', '?')}")
        return rendu

    porteurs = [f for f in equipe
                if f.get("occupe") and f.get("pid") == combattant["pid"]]
    for f in porteurs:
        f["au_combat"] = True
    if len(porteurs) == 1:
        rendu["au_combat_raison"] = "structure de combat (PID)"
    else:
        rendu["au_combat_raison"] = (f"PID du combattant absent de l'equipe "
                                     f"({len(porteurs)} porteur(s)) -- personne "
                                     f"n'est marque")
        for f in porteurs:
            f["au_combat"] = False
    return rendu


def lire_combattant(sonde, adverse: bool = False) -> Dict[str, Any]:
    """La fiche de combat d'un camp, NOMMEE par la cartouche. Ne leve jamais."""
    from noms_rom import ESPECES, lire_nom_par_sonde

    base = COMBATTANT_ADVERSE if adverse else COMBATTANT_JOUEUR
    try:
        octets = sonde.dump(base, TAILLE_COMBATTANT)
        if octets is None:
            return {"plausible": False,
                    "pourquoi": "la sonde a refuse la fiche de combat"}
        fiche = lire_struct_combattant(octets)
        if fiche["plausible"]:
            nom = lire_nom_par_sonde(sonde, ESPECES, fiche["espece"])
            fiche["nom"] = nom.get("nom")
            if "refus" in nom:
                fiche["nom_refus"] = nom["refus"]
        return fiche
    except (OSError, ValueError) as panne:
        return {"plausible": False,
                "pourquoi": f"lecture interrompue : {type(panne).__name__} {panne}"}


def lire_le_plateau(sonde) -> list:
    """Les QUATRE fiches de combat -- le plateau d'un combat DOUBLE.

    ⚠⚠⚠ MESURE DU 2026-09-16, AVEC SON CONTROLE. Les fiches se suivent a
    `PAS_COMBATTANT` : 0 et 2 de notre cote, 1 et 3 en face.

        combat SIMPLE   fiches 0 et 1 pleines, 2 et 3 a PID NUL (jamais remplies)
        combat DOUBLE   LES QUATRE pleines

    Sans le temoin du simple, « les quatre sont pleines » ne prouverait rien :
    elles pourraient l'etre toujours.

    ⚠ Ne leve jamais. Une fiche illisible se rend NON plausible avec sa raison :
    un plateau ampute se lirait sinon comme un plateau complet.
    """
    from noms_rom import ESPECES, lire_nom_par_sonde

    plateau = []
    for indice in range(4):
        adresse = COMBATTANT_JOUEUR + indice * PAS_COMBATTANT
        try:
            octets = sonde.dump(adresse, TAILLE_COMBATTANT)
            fiche = (lire_struct_combattant(octets) if octets else
                     {"plausible": False,
                      "pourquoi": "la sonde a refuse la fiche de combat"})
        except (OSError, ValueError) as panne:
            fiche = {"plausible": False,
                     "pourquoi": f"lecture interrompue : {type(panne).__name__} {panne}"}
        fiche["indice"] = indice
        fiche["notre_camp"] = indice % 2 == 0
        if fiche.get("plausible"):
            nom = lire_nom_par_sonde(sonde, ESPECES, fiche["espece"])
            fiche["nom"] = nom.get("nom")
            if "refus" in nom:
                fiche["nom_refus"] = nom["refus"]
        plateau.append(fiche)
    return plateau


def nommer_especes(sonde, lu: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute `espece_nom` a chaque membre occupe. Une requete par membre.

    ⚠ Rend une COPIE. Un nom refuse laisse la cle ABSENTE -- jamais un nom
    approximatif. Ne leve jamais.
    """
    from noms_rom import ESPECES, lire_nom_par_sonde

    rendu = dict(lu)
    rendu["equipe"] = [dict(f) for f in (lu.get("equipe") or [])]
    for fiche in rendu["equipe"]:
        if not fiche.get("occupe") or not fiche.get("espece"):
            continue
        try:
            nom = lire_nom_par_sonde(sonde, ESPECES, fiche["espece"])
        except (OSError, ValueError):
            continue
        if nom.get("nom"):
            fiche["espece_nom"] = nom["nom"]
    return rendu


def nommer_attaques_au_combat(sonde, lu: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute `nom` a chaque attaque du membre `au_combat`. Une requete par attaque.

    ⚠⚠ POURQUOI. La manette resout le mot demande contre les noms LUS A L'ECRAN,
    et refuse si leur nombre differe du nombre d'attaques en memoire. Un nom
    a apostrophe n'a jamais ete lu : sur un combattant a deux attaques, chaque
    demande de la premiere etait refusee, en boucle.

    ⚠ Le SEUL combattant, jamais l'equipe : la sonde meurt sous la charge.
    Rend une COPIE. Un nom refuse laisse la cle ABSENTE. Un canal coupe arrete
    les lectures. Ne leve jamais.
    """
    from noms_rom import ATTAQUES, lire_nom_par_sonde

    rendu = dict(lu)
    rendu["equipe"] = [dict(f) for f in (lu.get("equipe") or [])]
    for fiche in rendu["equipe"]:
        if not fiche.get("au_combat"):
            continue
        fiche["attaques"] = [dict(a) for a in fiche.get("attaques") or []]
        for attaque in fiche["attaques"]:
            try:
                nom = lire_nom_par_sonde(sonde, ATTAQUES, attaque.get("id"))
            except (OSError, ValueError, TypeError):
                return rendu
            if nom.get("nom"):
                attaque["nom"] = nom["nom"]
    return rendu


def adverse_depuis_struct(fiche: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fiche de combat adverse -> la forme `adverse_actif`, ou None. PURE.

    ⚠ None veut dire « la fiche ne suffit pas » : l'appelant retombe alors sur
    la regle d'`adversaire.py`, qui porte une hypothese et le dit.
    """
    if not fiche.get("plausible") or not fiche.get("nom"):
        return None
    return {"espece": fiche["espece"], "nom": fiche["nom"], "pid": fiche["pid"],
            "raison": "structure de combat (PID)", "plausible": True,
            "niveau": fiche["niveau"], "pv": fiche["pv"],
            "pv_max": fiche["pv_max"], "octets_inconnus": []}
