"""Le Pokedex -- quelles especes sont CAPTUREES, lesquelles sont VUES.

Usage :
    python pokedex.py                 # JSON sur la sortie standard
    python pokedex.py --lisible       # pour un humain
    python pokedex.py --espece 56     # une seule espece

⚠ IL CONSTATE, IL NE JUGE PAS. Il rend des drapeaux et un compte ; savoir si
une capture vaut la peine n'est pas sa question.

=== A QUELLE QUESTION IL REPOND, ET A LAQUELLE IL NE REPOND PAS ===

    « capturee »  cette espece a ete enregistree au moins UNE fois
    ce n'est PAS  « on l'a encore » -- relacher ou echanger ne l'efface pas

Pour decider s'il vaut la peine de depenser une Ball sur un sauvage, c'est le
bon drapeau. Pour savoir ce que porte l'equipe, c'est `equipe.py`.

=== LE CONTROLE, ET IL EST EXTERIEUR ===

⚠⚠ Un drapeau isole ne se verifie pas : une adresse fausse rend `0` ou `1`
comme une adresse juste, et les deux sont plausibles. Le controle qui tient est
le **COMPTE** -- le jeu affiche le nombre d'especes capturees dans son propre
Pokedex. Une adresse fausse ne reproduit presque jamais un compte exact.

C'est la meme methode que pour le sac : l'argent etait le seul nombre a avoir un
temoin visible, et c'est par lui que toute la carte a ete validee.

=== LES DEUX PIEGES DE NUMEROTATION ===

⚠⚠ L'index vaut `numero - 1`. Se tromper d'un decale tout le Pokedex, et le
resultat reste plausible partout -- chaque bit lu vaut toujours 0 ou 1.

⚠⚠⚠ Le numero du Pokedex n'est PAS l'identifiant d'espece rendu par `equipe.py`.
Ils coincident pour les 151 premiers et divergent ensuite. Ce module rend donc
le numero qu'on lui donne SANS conversion, et le dit -- inventer une table
silencieuse serait pire que ne pas en avoir.
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from adresses import (POKEDEX, POKEDEX_CAPTURES, POKEDEX_OCTETS,
                      POKEDEX_PREMIER_DIVERGENT, POKEDEX_VUS, PTR_SAVEBLOCK2)
from probe import DEFAULT_HOST, DEFAULT_PORT, EWRAM, Probe


def _bloc(sonde, pointeur):
    """Resout un pointeur de SaveBlock. None si la valeur ne pointe pas dans
    l'EWRAM -- partie non chargee, ou mauvaise cartouche."""
    adresse = sonde.read(pointeur, 32)
    lo, etendue = EWRAM
    if adresse is None or not lo <= adresse < lo + etendue:
        return None
    return adresse


def marque(octets: bytes, numero: int) -> Optional[bool]:
    """Le drapeau de cette espece. Fonction PURE, testable sans le jeu.

    ⚠ Rend None -- pas False -- si le numero sort du champ de bits. « non
    capture » et « je ne peux pas repondre » ne doivent pas se lire pareil.
    """
    if numero < 1:
        return None
    index = numero - 1
    octet, bit = index // 8, index & 7
    if octet >= len(octets):
        return None
    return bool(octets[octet] >> bit & 1)


def numeros_marques(octets: bytes) -> List[int]:
    """Tous les numeros dont le bit est pose. Fonction PURE."""
    return [i * 8 + b + 1
            for i in range(len(octets))
            for b in range(8)
            if octets[i] >> b & 1]


def lire_pokedex(sonde) -> Dict[str, Any]:
    """Les deux champs de bits, et leurs comptes."""
    sb2 = _bloc(sonde, PTR_SAVEBLOCK2)
    if sb2 is None:
        return {"lu": False,
                "message": f"SaveBlock2 illisible -- {sonde.last_reply}"}

    resultat: Dict[str, Any] = {"lu": True, "message": ""}
    for nom, decalage in (("captures", POKEDEX_CAPTURES), ("vus", POKEDEX_VUS)):
        adresse = sb2 + POKEDEX + decalage
        octets = sonde.dump(adresse, POKEDEX_OCTETS)
        # ⚠ UN DUMP TRONQUE RESTE DE L'HEXA VALIDE. Sans ce controle de
        # longueur, une reponse coupee se lirait comme un Pokedex plus petit --
        # et des especes manquantes ne ressemblent a rien d'anormal.
        if octets is None or len(octets) != POKEDEX_OCTETS:
            recu = 0 if octets is None else len(octets)
            return {"lu": False,
                    "message": f"{nom} : {recu} octets recus sur "
                               f"{POKEDEX_OCTETS} -- lecture tronquee"}
        numeros = numeros_marques(octets)
        resultat[nom] = {
            "adresse": adresse,
            "compte": len(numeros),
            "numeros": numeros,
            "octets": octets.hex(),
        }

    # ⚠⚠ UN CONTROLE DE COHERENCE INTERNE, GRATUIT : on ne peut pas avoir
    # capture une espece sans l'avoir vue. Si `captures` deborde de `vus`, ce
    # n'est pas une partie etrange -- c'est une adresse fausse.
    debordent = sorted(set(resultat["captures"]["numeros"])
                       - set(resultat["vus"]["numeros"]))
    resultat["captures_non_vues"] = debordent
    resultat["coherent"] = not debordent
    if debordent:
        resultat["message"] = (
            f"⚠ {len(debordent)} espece(s) CAPTUREE(S) mais pas VUE(S) : "
            f"{debordent[:10]}. C'est impossible en jeu -- soupconne les "
            f"adresses avant de soupconner la partie.")
    return resultat


def _principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--lisible", action="store_true")
    ap.add_argument("--espece", type=int, default=None,
                    help="un numero de Pokedex NATIONAL (pas un identifiant "
                         "d'espece au-dela de 251)")
    args = ap.parse_args()

    # ⚠ L'ECHEC DE CONNEXION SORT EN JSON LUI AUSSI : un appelant qui parse la
    # sortie ne doit pas avoir a distinguer « du JSON » d'« un message ».
    try:
        sonde = Probe(args.hote, args.port)
        if sonde.ask("ping") != "ok pong":
            lu = {"lu": False, "message": f"la sonde repond mais pas 'pong' : "
                                          f"{sonde.last_reply}"}
        else:
            lu = lire_pokedex(sonde)
    except (OSError, ConnectionError) as e:
        lu = {"lu": False, "message": f"{type(e).__name__} : {e}"}

    if not args.lisible:
        print(json.dumps(lu, ensure_ascii=False))
        return 0 if lu.get("lu") else 2

    if not lu.get("lu"):
        print(f"⚠ {lu['message']}")
        return 2

    print(f"captures : {lu['captures']['compte']:>3}   "
          f"(0x{lu['captures']['adresse']:08X})")
    print(f"vus      : {lu['vus']['compte']:>3}   "
          f"(0x{lu['vus']['adresse']:08X})")
    print(f"coherent : {lu['coherent']}"
          + (f"   {lu['message']}" if lu["message"] else ""))
    if args.espece is not None:
        c = marque(bytes.fromhex(lu["captures"]["octets"]), args.espece)
        v = marque(bytes.fromhex(lu["vus"]["octets"]), args.espece)
        avert = ("   ⚠ au-dela de 251, le numero du Pokedex differe de "
                 "l'identifiant d'espece"
                 if args.espece >= POKEDEX_PREMIER_DIVERGENT else "")
        print(f"\nnumero {args.espece} : capture={c}  vu={v}{avert}")
    print(f"\n⚠ CONTROLE : compare « captures » au nombre que le jeu affiche "
          f"dans son propre Pokedex.\n  Un desaccord tue l'adresse, un accord "
          f"la tient.")
    return 0


if __name__ == "__main__":
    sys.exit(_principal())
