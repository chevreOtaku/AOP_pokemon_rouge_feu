"""Les noms se lisent dans la CARTOUCHE -- les verrous, ecrits avant le code.

    python -m pytest test_noms_rom.py -q

⚠⚠⚠ CES TESTS ONT ETE ECRITS AVANT LE CODE, et contre-eprouves avant de servir
de contrat : une implementation de reference les passe, un mutant sans borne
en fait tomber exactement un, un mutant a base decalee d'un pas en fait tomber
cinq. Un test qui ne peut pas tomber ne garde rien.

=== CE QUI A ETE MESURE, ET QUE CES TESTS FIGENT ===

Les noms d'attaques, d'especes et d'objets sont des TABLES dans la ROM, a pas
fixe, encodees avec la table de caracteres deja verifiee contre l'ecran. Les
entrees relevees A L'ECRAN dans `attaques_connues.py` et `objets_connus.py`
-- qui n'ont servi a trouver aucune table -- y sont toutes identiques.

⚠ CE QUE CA CHANGE A LA DOCTRINE D'ACQUISITION : rien tant qu'elle n'est pas
amendee. Si elle l'est, la ROM devient la SOURCE et l'acquisition le TEMOIN
permanent -- c'est exactement ce que fait le groupe C.

=== TROIS GROUPES ===

A. le decodeur        -- un octet inconnu se COMPTE, il ne se devine jamais
B. la table           -- sur une ROM FABRIQUEE ; les refus sont des contrats
C. la vraie cartouche -- SAUTE AVEC SA RAISON si la ROM n'est pas fournie
D. par la sonde       -- une fiche demandee, la meme lecture que l'image

⚠⚠ AUCUNE VALEUR ICI NE VIENT D'UNE PARTIE (meme doctrine que
`test_veilleur.py`). Les groupes A et B travaillent sur des noms FABRIQUES
(ALPHA, BETA...). Le groupe C n'ecrit AUCUN nom nouveau dans ce depot : il
confronte la ROM aux entrees deja publiques des deux tables d'acquisition, et
son jeu de temoins grandit tout seul a chaque releve.
"""
import os
import struct

import pytest

from noms_rom import (ATTAQUES, ESPECES, OBJETS, Table, decoder, lire_nom,
                      lire_nom_par_sonde)

TERMINATEUR = 0xFF
VIDE = 0xAC           # « ? » -- ce que la cartouche met dans un emplacement inutilise
BASE_ROM = 0x08000000


def _enc(texte: str) -> bytes:
    """Majuscules et espace seulement : le reste de la table n'est pas exerce ici."""
    octets = bytearray()
    for c in texte:
        if c == " ":
            octets.append(0x00)
        elif c == "-":
            octets.append(0xAE)
        else:
            octets.append(0xBB + ord(c) - ord("A"))
    return bytes(octets)


def _rom(noms, pas, largeur, identifiant_a=None, decalage=0x40, apres=b""):
    """Une ROM fabriquee : une table a `decalage`, puis `apres`.

    ⚠ `apres` sert a poser des octets PLAUSIBLES derriere la derniere entree :
    une vraie cartouche continue apres ses tables, et ce qui suit se decode en
    lettres. Un test de borne qui ne mettrait que des zeros ne prouverait rien.
    """
    rom = bytearray(b"\x00" * decalage)
    for index, nom in enumerate(noms):
        fiche = bytearray(b"\xff" * pas)
        brut = nom if isinstance(nom, (bytes, bytearray)) else _enc(nom) + bytes([TERMINATEUR])
        # ⚠ On ecrit jusqu'au PAS, pas jusqu'a la largeur : une fiche porte des
        # octets apres le nom, et c'est eux que la largeur doit ignorer. Une
        # tranche de longueur differente raccourcirait la fiche et decalerait
        # toutes les suivantes -- le helper mentirait avant le code.
        brut = bytes(brut[:pas])
        fiche[:len(brut)] = brut
        if identifiant_a is not None:
            fiche[identifiant_a:identifiant_a + 2] = struct.pack("<H", index)
        rom += fiche
    rom += apres
    table = Table(base=BASE_ROM + decalage, pas=pas, largeur=largeur,
                  borne=len(noms) - 1, identifiant_a=identifiant_a)
    return bytes(rom), table


# ============================================================================
# A. LE DECODEUR
# ============================================================================

def test_le_terminateur_arrete_la_lecture():
    octets = _enc("AB") + bytes([TERMINATEUR]) + _enc("C")
    assert decoder(octets)["texte"] == "AB"


def test_un_octet_inconnu_rend_un_point_d_interrogation_ET_se_compte():
    """⚠⚠ Un « ? » silencieux dans un nom se lit comme une faute de lecture
    alors que c'est un trou de table. Les deux ne se reparent pas au meme
    endroit -- d'ou le compte, qui est la moitie du contrat."""
    rendu = decoder(bytes([0xBB, 0x01, 0xBC, TERMINATEUR]))
    assert rendu["texte"] == "A?B"
    assert rendu["octets_inconnus"] == [0x01]


def test_0x1B_est_un_e_accent_aigu():
    """✅ Verifie : un nom d'objet releve a l'ecran porte ce caractere a cette
    position, et la cartouche y a 0x1B."""
    assert decoder(bytes([0xBC, 0x1B, TERMINATEUR]))["texte"] == "Bé"


def test_0xB4_EST_L_APOSTROPHE_releve_a_l_ecran_le_2026_09_16():
    """✅ RELEVE A L'ECRAN le 2026-09-16, deux captures du createur : l'ecran de
    resume ET le menu d'attaques en plein combat affichent le meme nom avec une
    APOSTROPHE, la ou la cartouche porte 0xB4 (verifie octet par octet sur la
    fiche : ...D4 B4 D3...).

    ⚠⚠ CE TEST A CHANGE DELIBEREMENT. Il exigeait « inconnu » tant qu'aucun
    releve ne l'avait prouve, et il disait lui-meme quoi faire ce jour-la. Le
    releve existe ; l'octet entre dans la table. Une table ne s'etend pas en
    silence -- elle s'etend par un test qu'on retourne, date.

    ⚠ Ce que ca change ailleurs : 20 noms d'attaques de la cartouche portaient
    « ? » a cette position (ECRAS?FACE, GROZ?YEUX, BULLES D?O...). Ils se lisent
    maintenant en entier."""
    rendu = decoder(bytes([0xBB, 0xB4, 0xBC, TERMINATEUR]))
    assert rendu["texte"] == "A'B"
    assert rendu["octets_inconnus"] == []


def test_le_decodeur_de_noms_et_celui_des_surnoms_sont_LA_MEME_table():
    """⚠ Zero duplication : deux tables de caracteres divergeraient au premier
    octet verifie ajoute a l'une et oublie dans l'autre."""
    import equipe
    for octet, lettre in equipe._TABLE.items():
        assert decoder(bytes([octet, TERMINATEUR]))["texte"] == lettre


# ============================================================================
# B. LA TABLE, SUR UNE ROM FABRIQUEE
# ============================================================================

def test_l_entree_k_est_a_base_plus_k_fois_pas():
    rom, table = _rom(["ALPHA", "BETA", "GAMMA"], pas=13, largeur=13)
    assert lire_nom(rom, table, 0)["nom"] == "ALPHA"
    assert lire_nom(rom, table, 2)["nom"] == "GAMMA"


def test_la_largeur_borne_le_nom_quand_la_fiche_est_plus_longue():
    """⚠ Les objets : un nom de 14 octets dans une fiche de 44. Le reste de la
    fiche porte prix, poche, pointeurs -- dont certains se decodent en lettres."""
    quatorze_lettres_sans_terminateur = _enc("ABCDEFGHIJKLMN") + _enc("ZZZZ")
    rom, table = _rom([quatorze_lettres_sans_terminateur], pas=44, largeur=14)
    assert lire_nom(rom, table, 0)["nom"] == "ABCDEFGHIJKLMN"


def test_au_dela_de_la_borne_c_est_un_REFUS_et_pas_un_nom():
    """⚠⚠⚠ MESURE : apres la derniere attaque, la cartouche continue en octets
    qui se decodent en caracteres plausibles. Lire au-dela ne plante pas :
    ca MENT. Un nom invente se lirait dans une phrase adressee a quelqu'un."""
    lettres_plausibles = _enc("DELTA") + bytes([TERMINATEUR]) + b"\xff" * 7
    rom, table = _rom(["ALPHA", "BETA"], pas=13, largeur=13, apres=lettres_plausibles)
    rendu = lire_nom(rom, table, table.borne + 1)
    assert "nom" not in rendu
    assert "refus" in rendu


def test_un_index_negatif_est_un_refus():
    rom, table = _rom(["ALPHA"], pas=13, largeur=13)
    assert "refus" in lire_nom(rom, table, -1)


def test_un_emplacement_rempli_de_points_d_interrogation_est_VIDE_pas_un_nom():
    """⚠ MESURE : la cartouche remplit ses emplacements inutilises de 0xAC.
    Les rendre donnerait « ?????????? » -- un faux nom, en toutes lettres."""
    rom, table = _rom(["ALPHA", bytes([VIDE] * 11), "GAMMA"], pas=11, largeur=11)
    assert "refus" in lire_nom(rom, table, 1)
    assert lire_nom(rom, table, 2)["nom"] == "GAMMA"


def test_un_tiret_seul_est_un_emplacement_vide():
    """⚠ MESURE : l'attaque 0 de la cartouche est « - » -- « pas d'attaque »."""
    rom, table = _rom(["-", "ALPHA"], pas=13, largeur=13)
    assert "refus" in lire_nom(rom, table, 0)


def test_une_fiche_dont_l_identifiant_ne_vaut_pas_son_index_est_un_REFUS():
    """⚠⚠ La table des objets se verifie elle-meme : chaque fiche porte son
    identifiant. S'il ne vaut pas l'index, la table est mal alignee -- et TOUS
    les noms qu'on en tirerait seraient ceux du voisin."""
    rom, table = _rom(["ALPHA", "BETA"], pas=44, largeur=14, identifiant_a=14)
    fausse = bytearray(rom)
    debut_beta = (table.base - BASE_ROM) + 1 * table.pas
    fausse[debut_beta + 14:debut_beta + 16] = struct.pack("<H", 7)
    assert "refus" in lire_nom(bytes(fausse), table, 1)
    assert lire_nom(bytes(fausse), table, 0)["nom"] == "ALPHA"


def test_contre_epreuve_une_base_decalee_d_UN_pas_ne_rend_plus_le_bon_nom():
    """⚠⚠⚠ La preuve que les temoins PEUVENT tomber. Sans elle, un groupe C
    toujours vert ne distinguerait pas « la table est juste » de « le test ne
    regarde rien »."""
    rom, table = _rom(["ALPHA", "BETA", "GAMMA"], pas=13, largeur=13)
    decalee = Table(base=table.base + table.pas, pas=table.pas,
                    largeur=table.largeur, borne=table.borne - 1,
                    identifiant_a=None)
    assert lire_nom(rom, decalee, 0)["nom"] != "ALPHA"


# ============================================================================
# C. LA VRAIE CARTOUCHE -- les releves a l'ecran sont les temoins
# ============================================================================

@pytest.fixture(scope="module")
def cartouche():
    chemin = os.environ.get("AOP_ROM_ROUGE_FEU")
    if not chemin:
        pytest.skip("AOP_ROM_ROUGE_FEU non defini : la ROM n'est pas dans ce depot, "
                    "et ce groupe ne prouve RIEN sans elle -- saute, pas vert")
    with open(chemin, "rb") as f:
        return f.read()


def _pareil(releve: str, lu: str) -> bool:
    """⚠ La saisie humaine note « é » par « e » (« POKe BALL ») : on compare
    sans l'accent et sans la casse, et RIEN d'autre n'est tolere."""
    return releve.replace("é", "e").upper() == lu.replace("é", "e").upper()


def test_chaque_attaque_RELEVEE_A_L_ECRAN_est_celle_de_la_cartouche(cartouche):
    import attaques_connues
    assert attaques_connues.NOMS, "aucun temoin : ce test ne prouverait rien"
    ecarts = {}
    for identifiant, releve in attaques_connues.NOMS.items():
        lu = lire_nom(cartouche, ATTAQUES, identifiant).get("nom")
        if lu is None or not _pareil(releve, lu):
            ecarts[identifiant] = (releve, lu)
    assert ecarts == {}


def test_chaque_objet_RELEVE_A_L_ECRAN_est_celui_de_la_cartouche(cartouche):
    import objets_connus
    assert objets_connus.NOMS, "aucun temoin : ce test ne prouverait rien"
    ecarts = {}
    for identifiant, releve in objets_connus.NOMS.items():
        lu = lire_nom(cartouche, OBJETS, identifiant).get("nom")
        if lu is None or not _pareil(releve, lu):
            ecarts[identifiant] = (releve, lu)
    assert ecarts == {}


def test_la_table_des_objets_se_verifie_elle_meme_sur_TOUTE_sa_longueur(cartouche):
    mal_alignees = [i for i in range(OBJETS.borne + 1)
                    if "aligne" in lire_nom(cartouche, OBJETS, i).get("refus", "")]
    assert mal_alignees == []


@pytest.mark.parametrize("table", [ATTAQUES, ESPECES, OBJETS],
                         ids=["attaques", "especes", "objets"])
def test_la_derniere_entree_dans_la_borne_est_un_vrai_nom(cartouche, table):
    """⚠ Une borne trop GRANDE lirait les octets d'apres. La derniere entree
    doit donc etre un nom entier, sans octet inconnu."""
    rendu = lire_nom(cartouche, table, table.borne)
    assert "nom" in rendu
    assert rendu["octets_inconnus"] == []


# ============================================================================
# D. PAR LA SONDE -- la meme lecture, une seule fiche demandee
# ============================================================================

class _SondeFactice:
    """Repond a `dump` depuis une image de ROM, et note ce qu'on lui demande."""

    def __init__(self, rom, refuse=False):
        self.rom, self.refuse, self.demandes = rom, refuse, []

    def dump(self, adresse, longueur):
        self.demandes.append((adresse, longueur))
        debut = adresse - BASE_ROM
        if self.refuse or debut < 0 or debut + longueur > len(self.rom):
            return None
        return self.rom[debut:debut + longueur]


def test_par_la_sonde_on_lit_EXACTEMENT_ce_que_lit_l_image():
    """⚠ Deux chemins, un seul contrat. S'ils divergeaient, le pont en direct
    et le test contre le fichier ne prouveraient pas la meme chose."""
    rom, table = _rom(["ALPHA", bytes([VIDE] * 13), "GAMMA"], pas=13, largeur=13)
    for index in (0, 1, 2, 3, -1):
        assert lire_nom_par_sonde(_SondeFactice(rom), table, index) ==             lire_nom(rom, table, index)


def test_par_la_sonde_UNE_seule_fiche_est_demandee():
    """⚠ La sonde est lente et meurt sous la charge (43 pressions par geste
    l'ont deja tuee). Un nom = une requete, jamais la table entiere."""
    rom, table = _rom(["ALPHA", "BETA", "GAMMA"], pas=13, largeur=13)
    sonde = _SondeFactice(rom)
    lire_nom_par_sonde(sonde, table, 2)
    assert sonde.demandes == [(table.base + 2 * table.pas, table.pas)]


def test_hors_borne_on_ne_DERANGE_meme_pas_la_sonde():
    rom, table = _rom(["ALPHA"], pas=13, largeur=13)
    sonde = _SondeFactice(rom)
    assert "refus" in lire_nom_par_sonde(sonde, table, 5)
    assert sonde.demandes == []


def test_une_sonde_qui_refuse_rend_un_refus_MOTIVE():
    """⚠ « la sonde n'a pas repondu » n'est pas « emplacement vide » : les deux
    n'appellent pas le meme geste."""
    rom, table = _rom(["ALPHA"], pas=13, largeur=13)
    rendu = lire_nom_par_sonde(_SondeFactice(rom, refuse=True), table, 0)
    assert "sonde" in rendu.get("refus", "")
