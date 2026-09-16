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

from adresses import COMBATTANT_JOUEUR, PAS_COMBATTANT
from combattants import (TAILLE_COMBATTANT, enrichir_equipe, lire_combattant,
                         lire_etat, lire_le_plateau, lire_struct_combattant)

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


# ----------------------------------------------------------------------------
# Les noms d'attaques du COMBATTANT -- la manette ne depend plus de l'oeil
# ----------------------------------------------------------------------------
# ⚠ Mesure qui l'a rendu necessaire : un combattant a DEUX attaques dont l'une
# porte une apostrophe ; l'oeil n'en lit qu'UNE, le compte ne tombe pas juste,
# et chaque demande de la premiere est refusee -- en boucle.

class _SondeAttaques:
    """Rend ALPHA pour l'attaque 1, BRAVO pour la 2, refuse le reste. COMPTE."""

    def __init__(self, leve=False):
        self.requetes = 0
        self.leve = leve

    def dump(self, adresse, longueur):
        from noms_rom import ATTAQUES
        self.requetes += 1
        if self.leve:
            raise OSError("canal coupe")
        for identifiant, nom in ((1, "ALPHA"), (2, "BRAVO")):
            if adresse == ATTAQUES.base + identifiant * ATTAQUES.pas:
                return (_surnom(nom) + bytes(longueur))[:longueur]
        return None


def _membre(emplacement, pid, identifiants, au_combat=False):
    fiche = _fiche(emplacement, pid)
    fiche["attaques"] = [{"id": i, "pp": 10} for i in identifiants]
    if au_combat:
        fiche["au_combat"] = True
    return fiche


def test_ATTAQUES_seul_le_membre_AU_COMBAT_est_nomme():
    from combattants import nommer_attaques_au_combat
    lu = {"equipe": [_membre(0, 0xAAAA0001, [1, 2]),
                     _membre(1, 0xAAAA0002, [1, 2], au_combat=True)]}
    sonde = _SondeAttaques()
    rendu = nommer_attaques_au_combat(sonde, lu)
    assert [a.get("nom") for a in rendu["equipe"][1]["attaques"]] == ["ALPHA", "BRAVO"]
    assert all("nom" not in a for a in rendu["equipe"][0]["attaques"])
    assert sonde.requetes == 2, "une requete par attaque du combattant, pas plus"
    assert "nom" not in lu["equipe"][1]["attaques"][0], "la lecture d'origine est intacte"


def test_ATTAQUES_un_nom_refuse_reste_ABSENT_jamais_devine():
    from combattants import nommer_attaques_au_combat
    lu = {"equipe": [_membre(0, 0xAAAA0001, [1, 99], au_combat=True)]}
    rendu = nommer_attaques_au_combat(_SondeAttaques(), lu)
    assert [a.get("nom") for a in rendu["equipe"][0]["attaques"]] == ["ALPHA", None]


def test_ATTAQUES_sans_membre_au_combat_la_sonde_n_est_pas_derangee():
    from combattants import nommer_attaques_au_combat
    sonde = _SondeAttaques()
    nommer_attaques_au_combat(sonde, {"equipe": [_membre(0, 0xAAAA0001, [1, 2])]})
    assert sonde.requetes == 0


def test_ATTAQUES_un_canal_coupe_ne_REMONTE_pas_et_s_arrete():
    from combattants import nommer_attaques_au_combat
    lu = {"equipe": [_membre(0, 0xAAAA0001, [1, 2], au_combat=True)]}
    sonde = _SondeAttaques(leve=True)
    rendu = nommer_attaques_au_combat(sonde, lu)
    assert all("nom" not in a for a in rendu["equipe"][0]["attaques"])
    assert sonde.requetes == 1, "un canal coupe ne se re-sollicite pas"


# ----------------------------------------------------------------- le PLATEAU
# ⚠⚠ MESURE DU 2026-09-16 (chevre a trouve un double dans sa partie). Le
# controle est le combat SIMPLE lu la meme journee : fiches 2 et 3 a PID NUL.
# Aucune valeur d'une partie ici -- especes 101-104, PID 0xAAAA000x fabriques.

class _SondePlateau:
    """Rend une fiche par ADRESSE, et compte ce qu'on lui demande."""

    def __init__(self, par_indice, noms=True):
        self.par_indice, self.noms, self.demandes = par_indice, noms, []

    def dump(self, adresse, longueur):
        self.demandes.append(adresse)
        if longueur != TAILLE_COMBATTANT:      # une lecture de nom d'espece
            return bytes([TERMINATEUR]) if self.noms else None
        indice = (adresse - COMBATTANT_JOUEUR) // PAS_COMBATTANT
        octets = self.par_indice.get(indice)
        return octets[:longueur] if octets else None


def _plateau_double():
    return {0: _struct(espece=101, surnom="ALPHA", pid=0xAAAA0001),
            1: _struct(espece=102, surnom="BETA", pid=0xAAAA0002),
            2: _struct(espece=103, surnom="GAMMA", pid=0xAAAA0003),
            3: _struct(espece=104, surnom="DELTA", pid=0xAAAA0004)}


def test_PLATEAU_les_quatre_fiches_se_suivent_d_un_PAS():
    sonde = _SondePlateau(_plateau_double())
    lire_le_plateau(sonde)
    fiches = [a for a in sonde.demandes
              if (a - COMBATTANT_JOUEUR) % PAS_COMBATTANT == 0][:4]
    assert fiches == [COMBATTANT_JOUEUR + n * PAS_COMBATTANT for n in range(4)]


def test_PLATEAU_les_camps_alternent():
    plateau = lire_le_plateau(_SondePlateau(_plateau_double()))
    assert [f["notre_camp"] for f in plateau] == [True, False, True, False]
    assert [f["indice"] for f in plateau] == [0, 1, 2, 3]


def test_PLATEAU_en_combat_SIMPLE_les_deux_dernieres_sont_vides():
    """⚠ LE CONTROLE : sans lui, « les quatre sont pleines » ne prouve rien."""
    simple = {0: _struct(espece=101, surnom="ALPHA", pid=0xAAAA0001),
              1: _struct(espece=102, surnom="BETA", pid=0xAAAA0002),
              2: bytes(TAILLE_COMBATTANT), 3: bytes(TAILLE_COMBATTANT)}
    plateau = lire_le_plateau(_SondePlateau(simple))
    assert [f["plausible"] for f in plateau] == [True, True, False, False]


def test_PLATEAU_une_fiche_illisible_ne_fait_pas_tomber_les_autres():
    """⚠ Un plateau ampute se lirait comme un plateau complet -- on le DIT."""
    partiel = dict(_plateau_double())
    partiel[3] = None
    plateau = lire_le_plateau(_SondePlateau(partiel))
    assert [f["plausible"] for f in plateau] == [True, True, True, False]
    assert plateau[3]["pourquoi"]


def test_PLATEAU_une_sonde_qui_leve_ne_propage_pas():
    class _Casse:
        def dump(self, adresse, longueur):
            raise OSError("connexion fermee")

    plateau = lire_le_plateau(_Casse())
    assert [f["plausible"] for f in plateau] == [False] * 4
    assert all("connexion fermee" in f["pourquoi"] for f in plateau)


# ------------------------------------------------------------------- l'ETAT
# ⚠⚠ MESURE DU 2026-09-16 : le mot d'etat vaut 4 pendant le sommeil et 0 au
# reveil, a 0x4C dans la fiche de COMBAT et a 0x50 dans celle d'EQUIPE -- les
# deux au meme instant, par deux chemins d'ecriture differents.
# ⚠ SEUL LE SOMMEIL EST MESURE. Ces tests ne nomment rien d'autre.

def test_ETAT_un_mot_nul_est_un_Pokemon_sans_etat():
    etat = lire_etat(0)
    assert etat["lu"] is True
    assert etat["endormi"] is False
    assert etat["tours_de_sommeil"] is None
    assert etat["autre_non_nomme"] is None


def test_ETAT_quatre_est_un_COMPTEUR_de_tours_pas_un_drapeau():
    """La valeur mesuree en jeu : 4 endormi, 0 au reveil."""
    etat = lire_etat(4)
    assert etat["endormi"] is True
    assert etat["tours_de_sommeil"] == 4


def test_ETAT_un_seul_tour_restant_compte_encore_comme_endormi():
    assert lire_etat(1)["endormi"] is True


def test_ETAT_un_bit_HORS_du_sommeil_ne_se_nomme_PAS():
    """⚠⚠⚠ Le desassemblage decrit d'autres etats ; AUCUN n'a ete observe ici.
    On les rend tels quels plutot que de les baptiser -- une table d'etats ne
    s'etend pas en silence (meme regle que la table de caracteres, D-BO)."""
    etat = lire_etat(0x40)
    assert etat["endormi"] is False
    assert etat["autre_non_nomme"] == 0x40
    assert "paralys" not in repr(etat).lower()
    assert "poison" not in repr(etat).lower()


def test_ETAT_sommeil_ET_autre_bit_se_lisent_SEPAREMENT():
    etat = lire_etat(0x44)
    assert etat["tours_de_sommeil"] == 4
    assert etat["autre_non_nomme"] == 0x40


def test_ETAT_non_lu_n_est_pas_un_etat_vide():
    """⚠ « on n'a pas lu » et « il n'a aucun etat » n'autorisent pas les memes
    phrases."""
    assert lire_etat(None) == {"lu": False}


def test_ETAT_la_fiche_de_combat_le_porte():
    import struct as _s
    octets = bytearray(_struct())
    _s.pack_into("<I", octets, 0x4C, 4)
    fiche = lire_struct_combattant(bytes(octets))
    assert fiche["etat"]["endormi"] is True
    assert fiche["etat"]["tours_de_sommeil"] == 4
