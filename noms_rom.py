"""Les noms d'attaques, d'especes et d'objets -- lus dans la CARTOUCHE.

    python -m pytest test_noms_rom.py -q

=== CE QUI A ETE MESURE ===

Les trois tables sont dans la ROM, a pas fixe, encodees avec la table de
caracteres deja verifiee contre l'ecran (celle d'`equipe.py`). Elles ont ete
trouvees par une ancre encodee et un balayage des pas, puis confrontees aux
entrees relevees A L'ECRAN dans `attaques_connues.py` et `objets_connus.py` --
entrees qui n'avaient servi a trouver aucune table. Toutes identiques.

⚠⚠ CE N'EST PAS UNE TABLE RECOPIEE D'UN DESASSEMBLAGE. Le desassemblage a
seulement dit qu'une table existe. Les noms viennent de la cartouche qui
tourne, et le jeu affiche ses noms DEPUIS ces tables : une entree fausse ici
serait fausse a l'ecran aussi. La doctrine d'acquisition garde son role --
chaque releve a l'ecran reste un TEMOIN, confronte a la ROM par
`test_noms_rom.py`, et il peut la refuter.

=== QUATRE PIEGES, MESURES ===

1. L'espece en memoire est l'index INTERNE, pas le numero du Pokedex.
   Identiques de 1 a 251 ; au-dela, des emplacements vides, puis un ordre
   different. `pokedex.py` lit dans l'ordre NATIONAL -- ne jamais croiser.
2. Les emplacements inutilises sont remplis de « ? » (0xAC), ou valent « - ».
   Les rendre ecrirait un faux nom en toutes lettres : c'est un REFUS.
3. Apres la derniere entree, la cartouche continue en octets qui se decodent
   en caracteres plausibles. Lire au-dela ne plante pas : ca MENT. La borne
   est obligatoire, et son depassement est un REFUS.
4. Une fiche d'objet porte son propre identifiant. S'il ne vaut pas l'index,
   la table est mal alignee et TOUS les noms seraient ceux du voisin.

⚠ `lire_nom` travaille sur une image de ROM indexee depuis 0x08000000 (le
fichier, ou la region `ROM` que la sonde expose). Le branchement sur la sonde
n'est pas ecrit ici : il appartient a l'etape qui branche les consommateurs.
"""
from collections import namedtuple
from typing import Any, Dict, List

from equipe import TERMINATEUR, _TABLE as _TABLE_VERIFIEE

BASE_ROM = 0x08000000
VIDE = 0xAC
TIRET = 0xAE

Table = namedtuple("Table", "base pas largeur borne identifiant_a")

# ⚠ UNE SEULE table de caracteres : celle d'`equipe.py`, verifiee contre
# l'ecran, plus ce qui a ete verifie depuis. Une copie divergerait au premier
# octet ajoute a l'une et oublie dans l'autre.
#
# ✅ 0x1B « é » : un nom d'objet releve a l'ecran porte ce caractere a cette
#    position, et la cartouche y a 0x1B.
# ✅ 0xB4 « ' » : RELEVE A L'ECRAN le 2026-09-16 (deux captures du createur --
#    ecran de resume ET menu d'attaques en combat). La fiche de la cartouche
#    porte ...D4 B4 D3... la ou l'ecran affiche une apostrophe. Il etait garde
#    HORS de la table depuis le 15/09, faute de releve : « le contexte le
#    corrobore » n'est pas une preuve, un ecran l'est.
_TABLE = dict(_TABLE_VERIFIEE)
_TABLE[0x1B] = "é"
_TABLE[0xB4] = "'"

# Mesures du 2026-09-15 sur la cartouche francaise (code BPRF).
ATTAQUES = Table(base=0x082414A0, pas=13, largeur=13, borne=354, identifiant_a=None)
ESPECES = Table(base=0x082402EC, pas=11, largeur=11, borne=411, identifiant_a=None)

# ⚠⚠⚠ LA TABLE DE DONNEES DES ATTAQUES -- TROUVEE ET CONTROLEE LE 2026-09-16.
# Ce n'est PAS une adresse recopiee d'un desassemblage : elle a ete cherchee
# contre le jeu qui tourne, avec le predicat « l'octet +4 vaut le PP MAXIMUM de
# l'attaque » -- les identifiants venant de la MEMOIRE, les PP maximum de
# l'ECRAN (« 20/20 »). Quatre controles, tous passes :
#   a. 8 couples (id, pp) sur 8            -- la recherche
#   b. 6 attaques JAMAIS utilisees pour chercher : 6/6  -- le controle
#   c. la base decalee d'UN PAS : 0/8      -- la contre-epreuve
#   d. le champ +2 regroupe exactement les types LUS A L'ECRAN -- la corroboration
ATTAQUES_DONNEES_BASE = 0x0824B054
ATTAQUES_DONNEES_PAS = 12
ATTAQUE_TYPE = 0x02          # le type
ATTAQUE_PP = 0x04            # le PP maximum

# ⚠⚠ SEULS CES SIX TYPES SONT MESURES, chacun corrobore par ce que l'ECRAN
# affichait. Il y a dix-sept types dans la serie ; les onze autres ne sont PAS
# nommes, et un type inconnu rend son NUMERO.
#   16/09, ligne « THPE/... » du menu de combat : NORMAL, EAU, DRAGON, TENEBRES
#   16/09, CAPTURE de l'ecran de resume (temoin de chevre) : FEU, ACIER
# ⚠⚠ FEU est corrobore DEUX FOIS, par deux attaques differentes affichant le
# meme type et portant le meme octet -- un controle interne, pas un seul releve.
# ⚠ Le jour ou l'ecran en montre un autre, il entre ICI avec sa date, et le
# test qui exige son ANONYMAT change deliberement -- meme protocole que 0xB4
# (D-BO). C'est exactement ce qui vient de se passer pour le type 10.
TYPES_MESURES = {0: "NORMAL", 8: "ACIER", 10: "FEU", 11: "EAU",
                 16: "DRAGON", 17: "TENEBRES"}
OBJETS = Table(base=0x083D3324, pas=44, largeur=14, borne=374, identifiant_a=14)


def decoder(octets: bytes) -> Dict[str, Any]:
    """Octets -> texte, et ce qu'on n'a pas su lire. PURE.

    ⚠ Un octet inconnu rend « ? » ET se compte. Un « ? » silencieux se lirait
    comme une faute de lecture alors que c'est un trou de table -- les deux ne
    se reparent pas au meme endroit.
    """
    lettres: List[str] = []
    inconnus: List[int] = []
    for octet in octets:
        if octet == TERMINATEUR:
            break
        if octet in _TABLE:
            lettres.append(_TABLE[octet])
        else:
            lettres.append("?")
            inconnus.append(octet)
    return {"texte": "".join(lettres), "octets_inconnus": inconnus}


def _est_vide(nom_brut: bytes) -> bool:
    utiles = bytes(nom_brut).split(bytes([TERMINATEUR]))[0]
    if not utiles:
        return True
    return all(octet == VIDE for octet in utiles) or utiles == bytes([TIRET])


def _hors_borne(table: Table, index: int) -> Dict[str, Any]:
    if index < 0 or index > table.borne:
        return {"refus": f"index {index} hors de la table (0..{table.borne})"}
    return {}


def lire_nom(rom: bytes, table: Table, index: int) -> Dict[str, Any]:
    """L'entree `index` de `table` -> `{nom, octets_inconnus}` ou `{refus}`. PURE.

    ⚠ Ne devine JAMAIS. Hors borne, emplacement vide, fiche mal alignee :
    chacun est un refus MOTIVE, pas un nom approximatif.
    """
    refus = _hors_borne(table, index)
    if refus:
        return refus
    debut = table.base - BASE_ROM + index * table.pas
    fiche = rom[debut:debut + table.pas]
    if len(fiche) < table.pas:
        return {"refus": f"fiche {index} tronquee -- l'image de ROM est trop courte"}
    return _nom_de_fiche(fiche, table, index)


def lire_donnees_attaque(sonde, identifiant: int) -> Dict[str, Any]:
    """Le TYPE et le PP maximum d'une attaque. Une requete. Ne leve jamais.

    ⚠ Rend `type_nom` seulement si le type a ete MESURE ; sinon la cle est
    ABSENTE et `type` porte le numero. Un nom devine se lirait comme un nom lu.
    """
    if identifiant is None or identifiant < 0:
        return {"refus": "identifiant d'attaque absent"}
    try:
        fiche = sonde.dump(
            ATTAQUES_DONNEES_BASE + identifiant * ATTAQUES_DONNEES_PAS,
            ATTAQUES_DONNEES_PAS)
    except (OSError, ValueError) as panne:
        return {"refus": f"lecture interrompue : {type(panne).__name__}"}
    if not fiche or len(fiche) < ATTAQUES_DONNEES_PAS:
        return {"refus": f"la sonde n'a pas rendu l'attaque {identifiant}"}
    return donnees_de_fiche(fiche)


def donnees_de_fiche(fiche: bytes) -> Dict[str, Any]:
    """Une fiche d'attaque deja lue -> son type et son PP. PURE."""
    numero = fiche[ATTAQUE_TYPE]
    rendu = {"type": numero, "pp_max": fiche[ATTAQUE_PP]}
    if numero in TYPES_MESURES:
        rendu["type_nom"] = TYPES_MESURES[numero]
    return rendu


def lire_nom_par_sonde(sonde, table: Table, index: int) -> Dict[str, Any]:
    """La meme lecture que `lire_nom`, en demandant UNE fiche a la sonde.

    ⚠ La sonde meurt sous la charge : un nom = une requete, jamais la table.
    Hors borne, on ne la derange meme pas.
    """
    refus = _hors_borne(table, index)
    if refus:
        return refus
    fiche = sonde.dump(table.base + index * table.pas, table.pas)
    if fiche is None or len(fiche) < table.pas:
        return {"refus": f"la sonde n'a pas rendu la fiche {index}"}
    return _nom_de_fiche(fiche, table, index)


def _nom_de_fiche(fiche: bytes, table: Table, index: int) -> Dict[str, Any]:
    """Une fiche deja lue -> son nom ou un refus. PURE. Le coeur des deux chemins."""
    nom_brut = fiche[:table.largeur]
    if _est_vide(nom_brut):
        return {"refus": f"emplacement {index} vide -- pas un nom"}

    if table.identifiant_a is not None:
        a = table.identifiant_a
        identifiant = int.from_bytes(fiche[a:a + 2], "little")
        if identifiant != index:
            return {"refus": (f"table mal alignee : la fiche {index} porte "
                              f"l'identifiant {identifiant}")}

    rendu = decoder(nom_brut)
    return {"nom": rendu["texte"], "octets_inconnus": rendu["octets_inconnus"]}
