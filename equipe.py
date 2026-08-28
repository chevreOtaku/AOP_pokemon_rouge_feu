"""L'EQUIPE, dechiffree -- espece, attaques, PP, PV, identifiant unique.

    python equipe.py              # JSON sur la sortie standard
    python equipe.py --lisible    # pour un humain
    python equipe.py --adverse    # l'equipe d'en face (⚠ survit au combat)

⚠⚠⚠ POURQUOI CE MODULE EXISTE, ET CE QU'IL REMPLACE. Jusqu'au 2026-08-19, les
attaques du Pokemon actif etaient lues **par OCR** sur l'ecran de selection. Un
consommateur a documente trois defauts nes de ce seul choix :

    - un nom d'espece compare au caractere pres fabriquait de faux
      remplacements (« RQlCQQL » puis « RQlCQ@L », le meme Roucool)
    - l'etiquette de type, privee de son slash par l'oeil (« NORMAL » au lieu
      de « THPE/NORMAL »), devenait une QUATRIEME attaque
    - d'ou un garde de comptes, un souvenir des attaques, et un garde de
      peremption sur ce souvenir -- trois pieces pour compenser UNE source

**Tout cela disparait ici.** Les attaques, leurs PP, l'espece et un identifiant
unique sont en memoire, exacts, sans un seul caractere a deviner.

⚠⚠ CE QUE L'OEIL GARDE, ET IL FAUT LE DIRE. Ce module ne rend PAS ce que le jeu
ECRIT -- « RATTATA est K.O. », « la DEFENSE baisse », la parole d'un PNJ. Cette
prose n'est nulle part en memoire, et c'est a elle qu'un sujet reagit. L'oeil
cesse d'etre un verificateur d'etat ; il reste le canal du recit.

⚠ ET UNE CHOSE N'A PAS DE REMPLACANT : le drapeau « en combat ». La fiche
adverse SURVIT a la fin d'un combat (mesure du 2026-08-13), donc aucune lecture
memoire ne distingue « en combat » de « le combat vient de finir ». Ce module ne
le pretend pas.

=== LE CHIFFREMENT, ET IL SE FRANCHIT SANS SECRET ===

Les 48 octets qui portent l'espece, les attaques et les PP sont chiffres. La
cle est **lisible en clair juste a cote** :

    cle = personality XOR otId          (deux u32, aux offsets 0 et 4)

Chaque u32 du bloc est XORe par cette cle. Puis les quatre sous-blocs de 12
octets sont **melanges**, dans un ordre donne par `personality % 24`.

⚠ La signature qui met sur la voie : dans un dump brut, un motif se repete tous
les QUATRE octets (ici « 00 E2 »). C'est la marque d'un XOR par une cle u32 --
pas du bruit.
"""

import json
import struct
import sys
from typing import Any, Dict, List, Optional

from adresses import PAS_EQUIPE, PV_ADVERSE, PV_EQUIPE
from probe import DEFAULT_HOST, DEFAULT_PORT, Probe

# ⚠ `hp` est a l'offset 86 de `struct Pokemon`. C'est ce qui relie l'adresse
# deja connue (PV_EQUIPE) au DEBUT de la fiche -- et c'est verifie : a
# `base + 84` on lit le niveau, a `+86` les PV, a `+88` le maximum, exactement
# ce que la chasse du 2026-08-13 avait etabli par une autre voie.
DECALAGE_PV = 86
TAILLE_FICHE = 100

# Les 48 octets chiffres commencent apres l'en-tete en clair :
# personality(4) otId(4) surnom(10) langue(1) drapeaux(1) dresseur(7)
# marques(1) somme(2) inconnu(2) = 32
DEBUT_CHIFFRE = 32
TAILLE_CHIFFRE = 48

# ⚠⚠ LES 24 ORDRES DE MELANGE. Les quatre sous-blocs sont Growth, Attacks,
# EVs, Misc ; `personality % 24` designe leur ordre. Ce n'est pas une
# convention qu'on choisit -- c'est celle du jeu, et se tromper d'ordre rend
# des nombres plausibles mais faux, ce qui est pire qu'une erreur bruyante.
ORDRES = ("GAEM GAME GEAM GEMA GMAE GMEA AGEM AGME AEGM AEMG AMGE AMEG "
          "EGAM EGMA EAGM EAMG EMGA EMAG MGAE MGEA MAGE MAEG MEGA MEAG").split()


# ⚠⚠⚠ LA TABLE DE CARACTERES DU JEU, ET ELLE EST VERIFIEE, PAS SUPPOSEE.
# Gen 3 n'ecrit pas en ASCII. Le surnom vit EN CLAIR dans l'en-tete (offset 8,
# 10 octets) -- il n'est pas dans le bloc chiffre.
#
# Contre-epreuve du 2026-08-21, sur une partie en cours :
#     c2 d9 e6 d6 d9              -> « Herbe »    <- le nom affiche a l'ecran
#     be dd db e2 dd e8 d9        -> « Dignite »
# Deux surnoms, dont un lu independamment sur l'ecran de combat. Les plages
# alphabetiques sont donc etablies par la donnee, pas par une documentation.
#
# ⚠ CE QUI N'EST PAS VERIFIE ICI : les accents (region basse) et la ponctuation
# rare. Ils sont laisses HORS de la table -- un octet inconnu rend « ? » et se
# compte, plutot que de deviner une lettre. Un surnom mal devine se lirait
# comme un vrai nom, et rien ne le signalerait.
TERMINATEUR = 0xFF

_TABLE = {0x00: " ", 0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-",
          0xB8: ",", 0xBA: "/"}
_TABLE.update({0xA1 + n: chr(ord("0") + n) for n in range(10)})
_TABLE.update({0xBB + n: chr(ord("A") + n) for n in range(26)})
_TABLE.update({0xD5 + n: chr(ord("a") + n) for n in range(26)})


def lire_surnom(octets: bytes) -> Dict[str, Any]:
    """10 octets -> le surnom et ce qu'on n'a pas su lire. PURE.

    ⚠ Rend AUSSI `inconnus` : un « ? » silencieux dans un nom se lit comme une
    faute d'OCR alors que c'est un trou de table. Les deux ne se reparent pas
    au meme endroit.
    """
    lettres, inconnus = [], []
    for octet in octets:
        if octet == TERMINATEUR:
            break
        if octet in _TABLE:
            lettres.append(_TABLE[octet])
        else:
            lettres.append("?")
            inconnus.append(octet)
    return {"surnom": "".join(lettres), "octets_inconnus": inconnus}


def dechiffrer(fiche: bytes) -> Optional[Dict[str, bytes]]:
    """Rend les quatre sous-blocs en clair, ou None si la fiche est vide.

    ⚠ PURE : aucune E/S. On lui passe les 100 octets, elle rend des octets.
    """
    if len(fiche) < DEBUT_CHIFFRE + TAILLE_CHIFFRE:
        return None
    personality, ot_id = struct.unpack_from("<II", fiche, 0)
    # ⚠ `personality == 0` designe un emplacement VIDE, pas une panne. Les deux
    # rendraient la meme absence de donnees, et l'appelant doit pouvoir les
    # distinguer -- d'ou None ici et un champ explicite plus bas.
    if personality == 0:
        return None

    cle = personality ^ ot_id
    chiffre = fiche[DEBUT_CHIFFRE:DEBUT_CHIFFRE + TAILLE_CHIFFRE]
    clair = b"".join(
        struct.pack("<I", struct.unpack_from("<I", chiffre, i)[0] ^ cle)
        for i in range(0, TAILLE_CHIFFRE, 4))

    ordre = ORDRES[personality % 24]
    return {ordre[i]: clair[i * 12:(i + 1) * 12] for i in range(4)}


def lire_fiche(fiche: bytes) -> Dict[str, Any]:
    """Une fiche de 100 octets -> ce qu'elle contient. PURE.

    ⚠ Les nombres du bas (niveau, PV, statistiques) sont EN CLAIR ; seuls
    l'espece, les attaques et les PP sont chiffres. Deux regions, deux
    traitements -- les confondre ferait dechiffrer des octets qui ne le sont
    pas.
    """
    vide = {"occupe": False}
    if len(fiche) < TAILLE_FICHE:
        return dict(vide, pourquoi="fiche trop courte")

    blocs = dechiffrer(fiche)
    if blocs is None:
        return dict(vide, pourquoi="emplacement vide")

    croissance, attaques_bloc = blocs["G"], blocs["A"]
    espece = struct.unpack_from("<H", croissance, 0)[0]
    attaques = struct.unpack_from("<4H", attaques_bloc, 0)
    pp = tuple(attaques_bloc[8:12])

    # ⚠ Le surnom est dans l'EN-TETE EN CLAIR (offset 8), pas dans le bloc
    # chiffre. Le dechiffrer avec les autres rendrait dix octets de bruit.
    nom = lire_surnom(fiche[8:18])

    niveau = fiche[84]
    pv, pv_max = struct.unpack_from("<HH", fiche, 86)
    stats = struct.unpack_from("<5H", fiche, 90)

    return {
        "occupe": True,
        # ⚠⚠ LE PID EST L'IDENTITE, et rien d'autre ne l'est. Un u32 unique par
        # Pokemon. `pv_max` et le niveau se repetent d'un Pokemon a l'autre ; un
        # consommateur qui s'en sert pour reconnaitre « le meme combattant »
        # se trompera un jour sans le savoir. L'integration Pokemon officielle
        # a fait ce chemin avant nous (son issue #23).
        "pid": struct.unpack_from("<I", fiche, 0)[0],
        "espece": espece,
        # ⚠⚠ LE SURNOM EST CE QUE LE JOUEUR VOIT, l'espece un numero. Rendre
        # « espece 1 » a un consommateur l'obligerait a une table d'especes --
        # 386 entrees a maintenir -- pour retrouver un nom que le jeu porte
        # DEJA, et qui en plus tient compte des surnoms donnes par le joueur.
        "surnom": nom["surnom"],
        "surnom_octets_inconnus": nom["octets_inconnus"],
        "niveau": niveau,
        "pv": pv, "pv_max": pv_max,
        # ⚠ Un identifiant d'attaque a 0 = EMPLACEMENT VIDE, pas une attaque
        # nommee « 0 ». On les rend appariees a leurs PP et on retire les vides.
        "attaques": [{"id": a, "pp": p}
                     for a, p in zip(attaques, pp) if a],
        "stats": {"attaque": stats[0], "defense": stats[1], "vitesse": stats[2],
                  "attaque_speciale": stats[3], "defense_speciale": stats[4]},
        "ko": pv == 0,
    }


def lire_equipe(sonde: Probe, adverse: bool = False) -> Dict[str, Any]:
    """Les six emplacements. Rend toujours un dictionnaire, jamais une liste nue.

    ⚠ Le pas `+100` a ete VERIFIE le 2026-08-19 : le fichier d'adresses le
    portait comme « HYPOTHESE NON VERIFIEE » depuis le 13/08. Deux emplacements
    occupes lus d'affilee, especes et attaques coherentes avec l'ecran.
    """
    # ⚠⚠⚠ LES DEUX EQUIPES SONT CONTIGUES, ET C'EST DE L'ARITHMETIQUE, PAS UNE
    # SUPPOSITION. Les deux adresses etaient connues separement depuis le
    # 2026-08-13 ; leur ECART n'avait jamais ete calcule :
    #
    #     (PV_EQUIPE - 86) - (PV_ADVERSE - 86) = 600 = 6 x 100
    #
    # Six emplacements de 100 octets. L'equipe adverse tient donc au meme
    # format, juste avant celle du joueur.
    #
    # ⚠⚠ CE QUI RESTE A MESURER, et ce document ne le cache pas : personne n'a
    # encore LU ces six emplacements pendant un vrai combat de dresseur. Le
    # releve du 19/08 porte « equipe ADVERSE : non tentee ».
    #
    # ⚠ DEUX PIEGES CONNUS D'AVANCE :
    #   - la fiche adverse SURVIT a la fin d'un combat (mesure du 13/08) : une
    #     lecture hors combat rend une equipe PERIMEE qui se lit comme vivante ;
    #   - contre un Pokemon SAUVAGE, un seul emplacement est rempli. Deux
    #     emplacements ou plus PROUVENT donc un dresseur -- des le premier tour,
    #     la ou `combat.py` doit attendre un remplacement. ⚠ Mais un dresseur a
    #     UN seul Pokemon reste indiscernable d'un sauvage : l'inference garde
    #     le meme sens unique.
    base = (PV_ADVERSE if adverse else PV_EQUIPE) - DECALAGE_PV
    equipe: List[Dict[str, Any]] = []
    for n in range(6):
        brut = sonde.dump(base + PAS_EQUIPE * n, TAILLE_FICHE)
        # ⚠ `dump` rend None quand la sonde REFUSE -- ce n'est pas un
        # emplacement vide, c'est une panne. Les confondre ferait annoncer une
        # equipe amputee comme une equipe complete.
        fiche = ({"occupe": False, "pourquoi": "la sonde a refuse la lecture"}
                 if brut is None else lire_fiche(brut))
        fiche["emplacement"] = n
        equipe.append(fiche)

    occupes = [f for f in equipe if f["occupe"]]
    return {
        "equipe": equipe,
        "occupes": len(occupes),
        # ⚠ « en vie » et « occupe » sont deux choses : un Pokemon K.O. reste
        # dans l'equipe. Les compter ensemble ferait disparaitre un membre au
        # moment ou il tombe.
        "en_vie": sum(1 for f in occupes if not f["ko"]),
        "actif": equipe[0] if equipe[0]["occupe"] else None,
    }


def _principal():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lisible", action="store_true")
    ap.add_argument("--adverse", action="store_true",
                    help="lire l'equipe D'EN FACE au lieu de la sienne "
                         "-- ⚠ elle SURVIT a la fin d'un combat")
    args = ap.parse_args()

    # ⚠ `Probe.__init__` OUVRE la connexion -- il n'y a pas de `connect()`.
    # C'est pour ca que la construction est DANS le `try` : une sonde
    # injoignable leve ici, pas plus loin.
    sonde = None
    try:
        sonde = Probe(DEFAULT_HOST, DEFAULT_PORT)
        lu = lire_equipe(sonde, adverse=args.adverse)
    except Exception as erreur:            # noqa: BLE001
        # ⚠ L'echec sort en JSON lui aussi : un appelant qui parse la sortie n'a
        # pas a distinguer « du JSON » d'« un message d'erreur ». Deux formes
        # obligeraient a deux chemins de lecture, et c'est le second qu'on
        # oublie d'ecrire.
        print(json.dumps({"sonde": "injoignable", "pourquoi": str(erreur)}))
        raise SystemExit(2)
    finally:
        if sonde is not None:
            sonde.close()

    if not args.lisible:
        print(json.dumps(lu, ensure_ascii=False))
        return

    print(f"{lu['occupes']} occupe(s), {lu['en_vie']} en vie")
    for f in lu["equipe"]:
        if not f["occupe"]:
            print(f"  {f['emplacement']}  (vide)")
            continue
        att = " ".join(f"{a['id']}({a['pp']})" for a in f["attaques"])
        etat = " K.O." if f["ko"] else ""
        print(f"  {f['emplacement']}  espece {f['espece']:<4d} N.{f['niveau']:<3d}"
              f" {f['pv']:>3d}/{f['pv_max']:<4d} pid 0x{f['pid']:08X}  {att}{etat}")


if __name__ == "__main__":
    _principal()
