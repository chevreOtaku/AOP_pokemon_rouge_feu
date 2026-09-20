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


# ⚠⚠⚠ MESURE DU 2026-09-16, AVEC SON CONTROLE. Le mot d'etat vit a 0x4C dans
# la fiche de COMBAT et a 0x50 dans la fiche d'EQUIPE -- les deux valaient 4
# pendant que le combattant dormait et 0 apres son reveil, au meme instant, par
# deux chemins d'ecriture differents.
# ⚠⚠ CE N'EST PAS UN DRAPEAU, C'EST UN COMPTEUR : 4 = quatre tours de sommeil
# restants. Il tombe a 0 au reveil.
ETAT_COMBAT = 0x4C
ETAT_EQUIPE = 0x50
MASQUE_SOMMEIL = 0x07


def lire_etat(valeur: Optional[int]) -> Dict[str, Any]:
    """Un mot d'etat -> ce qu'on en SAIT, et rien de plus. PURE.

    ⚠⚠⚠ SEUL LE SOMMEIL EST MESURE (16/09). Le desassemblage de la serie
    decrit d'autres bits -- poison, brulure, gel, paralysie -- et **aucun n'a ete
    observe ici**. On ne les nomme donc pas : tout bit hors du masque de sommeil
    ressort dans `autre_non_nomme`, tel quel.
    ➜ Le jour ou l'un d'eux est releve en jeu, il entre ICI avec sa date. Une
    table d'etats ne s'etend pas en silence -- meme regle que la table de
    caracteres (D-BO).
    """
    if valeur is None:
        return {"lu": False}
    sommeil = valeur & MASQUE_SOMMEIL
    autre = valeur & ~MASQUE_SOMMEIL
    return {"lu": True, "brut": valeur,
            "endormi": bool(sommeil),
            "tours_de_sommeil": sommeil or None,
            "autre_non_nomme": autre or None}


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
    fiche["etat"] = lire_etat(struct.unpack_from("<I", octets, ETAT_COMBAT)[0])

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


# ⚠⚠⚠ CE QUE LA ROM DIT D'UNE ATTAQUE NE CHANGE JAMAIS -- c'est de la cartouche,
# pas de la partie. Une attaque lue une fois n'est plus redemandee a la sonde,
# qui meurt sous la charge.
#
# ⚠⚠ RECTIFIE LE 2026-09-20, LE JOUR MEME : ce commentaire affirmait que le
# cache evitait « huit requetes par tour au lieu de quatre ». C'EST FAUX, et la
# mesure l'a montre le soir meme. Le client lit l'equipe en lancant ce depot en
# SOUS-PROCESSUS : le cache meurt avec lui, et les quatre identifiants d'un
# meme appel sont tous distincts -- il ne peut donc JAMAIS servir dans l'usage
# d'aujourd'hui.
#
#     lecture d'equipe, sans les noms          348 ms
#     lecture d'equipe, noms + types + PP max  480 ms   (+130 ms, mesure)
#
# ➜ Il est garde parce qu'il ne coute rien et qu'il protegera le jour ou ce
# module vivra dans un processus long. Mais il ne protege rien aujourd'hui, et
# le dire vaut mieux que de le laisser croire.
# ⚠ Le cache ne garde que ce qui a ete LU : un refus n'y entre pas, donc il se
# retente plutot que de se figer en absence definitive.
_MOVE_DATA_CACHE: Dict[int, Dict[str, Any]] = {}


def nommer_attaques_au_combat(sonde, lu: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute `nom`, `type` et `pp_max` a chaque attaque du membre `au_combat`.

    ⚠⚠ POURQUOI LE NOM. La manette resout le mot demande contre les noms LUS A
    L'ECRAN, et refuse si leur nombre differe du nombre d'attaques en memoire.
    Un nom a apostrophe n'a jamais ete lu : sur un combattant a deux attaques,
    chaque demande de la premiere etait refusee, en boucle.

    ⚠⚠ POURQUOI LE TYPE ET LE PP MAXIMUM (2026-09-20). La table de donnees des
    attaques a ete trouvee et controlee le 16/09, puis branchee NULLE PART. Deux
    usages l'attendaient : dire ses PP sous la forme que le jeu affiche
    (« 5/25 ») au lieu d'un nombre nu, et donner un SECOND temoin a l'arrivee du
    curseur quand l'oeil ne lit pas le compteur (BUG-050).

    ⚠ Le SEUL combattant, jamais l'equipe : la sonde meurt sous la charge. DEUX
    requetes par attaque -- son nom, puis ses donnees de ROM. Mesure du 20/09 :
    +130 ms sur la lecture d'equipe complete. Rend une COPIE. Ce qui est refuse
    laisse la cle ABSENTE. Un canal coupe arrete les lectures. Ne leve jamais.
    """
    from noms_rom import ATTAQUES, lire_donnees_attaque, lire_nom_par_sonde

    rendu = dict(lu)
    rendu["equipe"] = [dict(f) for f in (lu.get("equipe") or [])]
    for fiche in rendu["equipe"]:
        if not fiche.get("au_combat"):
            continue
        fiche["attaques"] = [dict(a) for a in fiche.get("attaques") or []]
        for attaque in fiche["attaques"]:
            identifiant = attaque.get("id")
            try:
                nom = lire_nom_par_sonde(sonde, ATTAQUES, identifiant)
            except (OSError, ValueError, TypeError):
                return rendu
            if nom.get("nom"):
                attaque["nom"] = nom["nom"]

            donnees = _MOVE_DATA_CACHE.get(identifiant)
            if donnees is None:
                try:
                    lues = lire_donnees_attaque(sonde, identifiant)
                except (OSError, ValueError, TypeError):
                    return rendu
                if "refus" not in lues:
                    donnees = _MOVE_DATA_CACHE.setdefault(identifiant, lues)
            if donnees:
                attaque.update(donnees)
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
