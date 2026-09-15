"""Qui est EN FACE -- lu en memoire seule, et on se tait quand elle ne suffit pas.

    python -m pytest test_adversaire.py -q

⚠⚠⚠ POURQUOI. `equipe.py` rend `actif = emplacement 0`. Cote ADVERSE, c'est
faux des le premier K.O. : la fiche reste collee au Pokemon a terre pendant que
le suivant combat (mesure du 2026-09-15). Si les deux sont du meme niveau, le
controle de fraicheur par le niveau ne voit rien, et un nom EXACT mais FAUX
serait presente comme une certitude.

⚠⚠ L'ECRAN NE DEPARTAGE PAS. Mesure du meme jour : la graphie lue a l'ecran
ressemble autant a l'un qu'a l'autre des deux candidats (ecart 0.036), et contre
toute la table des especes elle designe une espece absente du combat. Ce module
ne consulte donc AUCUNE lecture d'ecran.

=== LA REGLE ===

    un seul adversaire vivant                    -> lui           « seul vivant »
    aucun K.O. encore, plusieurs vivants         -> le PREMIER    « ouvre le combat »
    un K.O. a eu lieu ET plusieurs vivants       -> REFUS
    aucun vivant, ou un PV illisible             -> REFUS

⚠ HYPOTHESE portee par la 2e ligne : un dresseur ouvre avec son premier Pokemon
et n'en change pas volontairement avant un K.O. Vraie pour les duels mesures,
pas verifiee en general. La lecture de l'index du combattant en memoire la
remplacera -- et la raison rendue (« ouvre le combat ») dit au journal qu'on
s'appuie dessus.

⚠ Ce module ne dit pas si un combat A LIEU : la fiche adverse survit a la fin
d'un combat. C'est a l'appelant d'avoir cette preuve.
"""
from typing import Any, Dict, List, Optional


VIDE = "emplacement vide"   # le libelle d'`equipe.lire_fiche` -- verrouille par test


def adversaire_actif(equipe: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Les fiches adverses -> `{emplacement, espece, raison}` ou `{refus}`. PURE."""
    # ⚠⚠⚠ UNE PANNE N'EST PAS UN VIDE. `lire_equipe` rend `occupe: False` aussi
    # quand la sonde REFUSE une lecture. Ignorer cet emplacement amputerait
    # l'equipe -- et « seul vivant » deviendrait un nom exact et FAUX.
    en_panne = [f for f in (equipe or [])
                if not f.get("occupe") and f.get("pourquoi") != VIDE]
    if en_panne:
        return {"refus": (f"emplacement {en_panne[0].get('emplacement')} "
                          f"illisible ({en_panne[0].get('pourquoi', '?')}) -- "
                          f"l'equipe est amputee, on ne conclut pas")}

    occupes = [f for f in (equipe or []) if f.get("occupe")]
    if not occupes:
        return {"refus": "aucune fiche adverse lisible"}

    if any(f.get("pv") is None for f in occupes):
        return {"refus": ("un PV adverse est illisible -- on ne sait pas qui est "
                          "vivant, on ne devine pas")}

    vivants = sorted((f for f in occupes if f["pv"] > 0),
                     key=lambda f: f["emplacement"])
    a_terre = [f for f in occupes if f["pv"] == 0]

    if not vivants:
        return {"refus": "aucun adversaire vivant"}
    if len(vivants) == 1:
        return _choix(vivants[0], "seul vivant")
    if not a_terre:
        return _choix(vivants[0], "ouvre le combat")
    return {"refus": (f"{len(a_terre)} a terre et {len(vivants)} vivants -- le "
                      f"dresseur envoie qui il veut, on ne sait pas lequel")}


def _choix(fiche: Dict[str, Any], raison: str) -> Dict[str, Any]:
    return {"emplacement": fiche["emplacement"], "espece": fiche["espece"],
            "raison": raison}


# ============================================================================
# LA FRONTIERE -- la seule partie qui parle a la sonde
# ============================================================================

def lire_adverse_actif(sonde) -> Dict[str, Any]:
    """L'adversaire actif, NOMME par la cartouche, avec ses nombres. Ou un refus.

    Rend `{emplacement, espece, raison, nom, octets_inconnus, plausible,
    niveau, pv, pv_max}` ou `{refus}`.

    ⚠⚠ NE LEVE JAMAIS. `etat.py` enveloppe tout son etat dans un seul `try` : si
    cette lecture levait, elle emporterait aussi les PV du joueur -- une piece
    ajoutee casserait celles qui marchaient. La panne devient un refus MOTIVE.

    ⚠ UNE lecture, aucun souvenir d'un appel a l'autre -- la doctrine d'`etat.py`.
    """
    from equipe import lire_equipe
    from noms_rom import ESPECES, lire_nom_par_sonde

    try:
        lu = lire_equipe(sonde, adverse=True)
        choix = adversaire_actif(lu.get("equipe"))
        if "refus" in choix:
            return choix
        fiche = next(f for f in lu["equipe"]
                     if f.get("emplacement") == choix["emplacement"])
        nom = lire_nom_par_sonde(sonde, ESPECES, choix["espece"])
    except (OSError, ValueError, StopIteration) as panne:
        return {"refus": f"lecture de l'adversaire interrompue : "
                         f"{type(panne).__name__} {panne}"}

    if "refus" in nom:
        return {"refus": f"espece {choix['espece']} sans nom -- {nom['refus']}"}
    return dict(choix, nom=nom["nom"], octets_inconnus=nom["octets_inconnus"],
                plausible=fiche["pv_max"] > 0 and 1 <= fiche["niveau"] <= 100,
                niveau=fiche["niveau"], pv=fiche["pv"], pv_max=fiche["pv_max"])
