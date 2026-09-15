"""Qui COMBAT -- lu dans la structure de combat, reconnu par son PID.

    python -m pytest test_combattants.py -q

⚠⚠⚠ CE QUI A ETE MESURE, ET QUE CES TESTS FIGENT.

`equipe.py` rendait `actif = emplacement 0`, et ses docstrings disaient « rien
en memoire ne dit qui combat ». C'etait faux : les deux adresses de
modificateurs de statistiques deja verifiees sont espacees de 0x58, la taille
d'une fiche de combattant. Leur debut est a -0x18. Lecture en jeu apres un
changement de Pokemon : l'espece, le niveau, les PV, le surnom ET le PID de la
fiche de combat designent un seul emplacement de l'equipe -- pas le 0.

Une integration de reference a fait ce chemin (reconnaitre l'actif par le PID
contre l'equipe COURANTE, et non contre une copie perimee).

⚠⚠ AUCUNE VALEUR ICI NE VIENT D'UNE PARTIE (doctrine de `test_veilleur.py`) :
especes 101-103, PID 0xAAAA000x, surnoms ALPHA/BETA fabriques.
"""
import struct

from combattants import (TAILLE_COMBATTANT, enrichir_equipe, lire_combattant,
                         lire_struct_combattant)

TERMINATEUR = 0xFF


def _surnom(texte):
    return bytes(0xBB + ord(c) - ord("A") for c in texte) + bytes([TERMINATEUR])


def _struct(espece=101, niveau=9, pv=20, pv_max=30, surnom="ALPHA", pid=0xAAAA0001):
    b = bytearray(TAILLE_COMBATTANT)
    struct.pack_into("<H", b, 0x00, espece)
    struct.pack_into("<H", b, 0x28, pv)
    b[0x2A] = niveau
    struct.pack_into("<H", b, 0x2C, pv_max)
    nom = _surnom(surnom)
    b[0x30:0x30 + len(nom)] = nom
    struct.pack_into("<I", b, 0x48, pid)
    return bytes(b)


def _fiche(emplacement, pid, espece=101):
    return {"occupe": True, "emplacement": emplacement, "pid": pid,
            "espece": espece, "surnom": "X", "niveau": 9, "pv": 20, "pv_max": 30}


# ----------------------------------------------------------------------------
# La fiche de combat -- PURE
# ----------------------------------------------------------------------------

def test_les_champs_sont_lus_a_leurs_decalages():
    lu = lire_struct_combattant(_struct())
    assert lu["plausible"] is True, lu
    assert (lu["espece"], lu["niveau"], lu["pv"], lu["pv_max"]) == (101, 9, 20, 30)
    assert lu["surnom"] == "ALPHA"
    assert lu["pid"] == 0xAAAA0001


def test_un_PID_nul_n_est_pas_un_combattant():
    """⚠ Une fiche jamais remplie (avant tout combat) porte des zeros."""
    assert lire_struct_combattant(_struct(pid=0))["plausible"] is False


def test_des_nombres_impossibles_ne_sont_pas_un_combattant():
    for mauvais in (_struct(niveau=0), _struct(niveau=101),
                    _struct(pv_max=0), _struct(pv=31, pv_max=30),
                    _struct(espece=0), _struct(espece=412)):
        lu = lire_struct_combattant(mauvais)
        assert lu["plausible"] is False, lu
        assert lu["pourquoi"], "un refus doit dire POURQUOI"


def test_des_octets_trop_courts_ne_levent_pas():
    assert lire_struct_combattant(b"\x01\x02")["plausible"] is False


# ----------------------------------------------------------------------------
# « Au combat » par le PID -- PURE
# ----------------------------------------------------------------------------

def test_AU_COMBAT_est_l_emplacement_qui_porte_le_PID_et_pas_le_0():
    """⚠⚠⚠ LE DEFAUT MESURE : apres un changement, le combattant est ailleurs
    que dans l'emplacement 0, et l'ordre de l'equipe ne bouge pas."""
    lu = {"equipe": [_fiche(0, 0xAAAA0001), _fiche(1, 0xAAAA0002),
                     {"occupe": False, "emplacement": 2}]}
    rendu = enrichir_equipe(lu, lire_struct_combattant(_struct(pid=0xAAAA0002)))
    marques = [f["emplacement"] for f in rendu["equipe"] if f.get("au_combat")]
    assert marques == [1]
    assert rendu["au_combat_raison"].startswith("structure de combat")


def test_AU_COMBAT_ne_touche_pas_a_la_cle_actif_d_avant():
    """⚠ `actif` reste l'emplacement 0 : un consommateur s'en sert pour
    identifier une capture. On AJOUTE une information, on ne change pas le sens
    d'une cle existante sous ses pieds."""
    lu = {"equipe": [_fiche(0, 0xAAAA0001), _fiche(1, 0xAAAA0002)],
          "actif": _fiche(0, 0xAAAA0001)}
    rendu = enrichir_equipe(lu, lire_struct_combattant(_struct(pid=0xAAAA0002)))
    assert rendu["actif"]["emplacement"] == 0


def test_un_PID_absent_de_l_equipe_ne_marque_PERSONNE_et_le_dit():
    """⚠⚠ Fiche de combat perimee, ou autre partie : ne rien marquer vaut mieux
    que marquer le mauvais -- et on dit pourquoi."""
    lu = {"equipe": [_fiche(0, 0xAAAA0001), _fiche(1, 0xAAAA0002)]}
    rendu = enrichir_equipe(lu, lire_struct_combattant(_struct(pid=0xAAAA0009)))
    assert not any(f.get("au_combat") for f in rendu["equipe"])
    assert "absent" in rendu["au_combat_raison"]


def test_une_fiche_de_combat_implausible_ne_marque_personne():
    lu = {"equipe": [_fiche(0, 0xAAAA0001)]}
    rendu = enrichir_equipe(lu, lire_struct_combattant(_struct(pid=0)))
    assert not any(f.get("au_combat") for f in rendu["equipe"])
    assert rendu["au_combat_raison"]


def test_enrichir_ne_modifie_pas_la_lecture_d_origine():
    lu = {"equipe": [_fiche(0, 0xAAAA0001)]}
    enrichir_equipe(lu, lire_struct_combattant(_struct(pid=0xAAAA0001)))
    assert "au_combat" not in lu["equipe"][0]


# ----------------------------------------------------------------------------
# La lecture par la sonde -- la frontiere
# ----------------------------------------------------------------------------

class _Sonde:
    def __init__(self, octets=None, exception=None):
        self.octets, self.exception = octets, exception

    def dump(self, adresse, longueur):
        if self.exception:
            raise self.exception
        return None if self.octets is None else self.octets[:longueur]


def test_LECTURE_une_sonde_qui_refuse_rend_un_combattant_implausible():
    lu = lire_combattant(_Sonde(None))
    assert lu["plausible"] is False and "sonde" in lu["pourquoi"], lu


def test_LECTURE_une_exception_ne_REMONTE_pas():
    """⚠⚠ `etat.py` enveloppe tout dans un seul `try` : une piece ajoutee qui
    leve emporterait les pieces qui marchaient."""
    lu = lire_combattant(_Sonde(exception=ConnectionError("coupee")))
    assert lu["plausible"] is False and "ConnectionError" in lu["pourquoi"], lu


# ----------------------------------------------------------------------------
# L'espece a cote du surnom -- « Surnom (ESPECE) »
# ----------------------------------------------------------------------------

class _SondeNoms:
    """Rend un nom FABRIQUE pour l'espece 101, refuse le reste."""

    def __init__(self, refuse=False):
        self.refuse = refuse

    def dump(self, adresse, longueur):
        from noms_rom import ESPECES
        if self.refuse or adresse != ESPECES.base + 101 * ESPECES.pas:
            return None
        return (_surnom("ALPHA") + bytes(longueur))[:longueur]


def test_ESPECE_chaque_membre_occupe_recoit_le_nom_de_son_espece():
    """⚠⚠ Mesure du 15/09 : le noeud montrait un surnom seul, sans son espece
    -- et le sujet a demande une attaque Plante a un Pokemon Eau. Le surnom est ce que le joueur a choisi ; l'espece, ce que le jeu est."""
    from combattants import nommer_especes
    lu = {"equipe": [_fiche(0, 0xAAAA0001, espece=101),
                     {"occupe": False, "emplacement": 1}]}
    rendu = nommer_especes(_SondeNoms(), lu)
    assert rendu["equipe"][0]["espece_nom"] == "ALPHA"
    assert "espece_nom" not in rendu["equipe"][1]
    assert "espece_nom" not in lu["equipe"][0], "la lecture d'origine est intacte"


def test_ESPECE_un_nom_refuse_reste_ABSENT_et_ne_leve_pas():
    """⚠ Pas de nom deviné : la cle manque, et l'appelant affiche le surnom seul."""
    from combattants import nommer_especes
    lu = {"equipe": [_fiche(0, 0xAAAA0001, espece=101)]}
    rendu = nommer_especes(_SondeNoms(refuse=True), lu)
    assert rendu["equipe"][0].get("espece_nom") is None


# ----------------------------------------------------------------------------
# L'adversaire actif par la fiche de combat -- la regle devient un REPLI
# ----------------------------------------------------------------------------

def test_ADVERSE_une_fiche_plausible_et_nommee_donne_l_adversaire_actif():
    """⚠⚠ La regle « seul vivant / ouvre le combat » portait une HYPOTHESE (le
    dresseur ne change pas volontairement). La fiche de combat n'en porte pas."""
    from combattants import adverse_depuis_struct
    fiche = dict(lire_struct_combattant(_struct(espece=102, pv=26, pv_max=26)),
                 nom="BETA")
    rendu = adverse_depuis_struct(fiche)
    assert rendu["nom"] == "BETA" and (rendu["pv"], rendu["pv_max"]) == (26, 26)
    assert rendu["plausible"] is True
    assert "structure de combat" in rendu["raison"]


def test_ADVERSE_une_fiche_implausible_ou_sans_nom_rend_None_pour_le_repli():
    from combattants import adverse_depuis_struct
    assert adverse_depuis_struct(lire_struct_combattant(_struct(pid=0))) is None
    sans_nom = dict(lire_struct_combattant(_struct()), nom=None)
    assert adverse_depuis_struct(sans_nom) is None
