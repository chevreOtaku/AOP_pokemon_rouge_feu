"""Il regarde jouer et n'ecrit que ce qui CHANGE. Il ne presse rien.

    python veilleur.py                  # une ligne JSON par changement
    python veilleur.py --duree 600      # dix minutes puis il ferme
    python veilleur.py --lisible        # pour un humain, pas pour un programme

=== POURQUOI UN PROCESSUS QUI DURE, ET PAS UN APPEL PAR LECTURE ===

Chaque script de ce pont ouvre une connexion, lit, et meurt. C'est juste pour
une question ponctuelle, et c'est INTENABLE pour une surveillance : le
lancement d'un interpreteur coute a lui seul 0,13 s (mesure du 2026-09-07,
imports compris, hors reseau), et quatre lectures en coutent 0,49 avant meme
d'avoir parle a l'emulateur.

Ce module tient UNE socket ouverte et lit en boucle. Le cout par tour retombe
a un aller-retour.

=== IL N'EMET QUE DES CHANGEMENTS, ET UN BATTEMENT ===

⚠⚠ Un journal qui ne parle que quand ca bouge a un silence AMBIGU : « rien n'a
change » et « je suis mort » s'y ecrivent pareil. Un premier journal a ete
perdu comme ca. ➜ Un battement periodique dit « je suis vivant, et voici ce que
je vois », meme quand rien ne bouge.

=== L'ESTAMPILLE EST DOUBLE, ET C'EST LE POINT ===

Chaque ligne porte l'heure de la MONTRE et le numero d'IMAGE du jeu.

⚠⚠⚠ Les deux ne mesurent pas la meme chose des que l'avance rapide entre en
jeu : a 240 images/s, une animation de 300 images dure 1,25 s de montre au lieu
de 5 s. Un delai mesure en secondes ne voyage donc pas d'une vitesse a l'autre
-- exactement ce que le seuil de repetition a montre (21 IMAGES, identiques a
60 et a 240 images/s).

    « l'evolution arrive 5 a 7 s apres la hausse d'xp » -- a quelle VITESSE ?
    Personne ne l'a note. Ce module fait en sorte que la question ne se repose
    plus : l'ecart en images est dans le journal.

=== CE QU'IL NE FAIT PAS ===

Il ne regarde PAS l'ecran. L'oeil (OCR) vit du cote qui decide, pas ici : ce
pont lit de la memoire et rend des nombres. ⚠ Consequence assumee -- il ne peut
pas voir l'invite « X veut apprendre Y », qui est le seul signal ARRIVANT AVANT
une decision humaine. C'est au consommateur de ce flux d'ajouter cet oeil.

Il ne NOMME aucune cause. Une hausse d'experience vient d'un combat gagne OU
d'un objet ; ecrire « combat gagne » ferait dire au journal ce qu'il n'a pas
mesure. C'est la COINCIDENCE de plusieurs lignes qui tranche, et c'est le
travail du lecteur.

⚠⚠⚠ LES SURNOMS SONT RELEVES DEPUIS LE 2026-09-09, et la regle d'avant est
REMPLACEE, pas contournee. Elle disait : « il ne releve AUCUN surnom -- ils
viennent de la sauvegarde, ils sont arbitraires, et un journal se recopie ».

CE QUI L'A FAIT TOMBER, mesure le meme jour : sans eux, une evolution se lit
« un de tes Pokemon evolue » -- sans dire QUI, ni EN QUOI. Verbatim du
proprietaire de la partie : *« si un Pokemon a evolue et on ne sait pas en quoi
ou qui, c'est un probleme »*. L'asymetrie etait pire que le risque : la fiche
d'en face etait nommee, les siennes non.

⚠ LE RISQUE RESTE REEL ET IL A DEJA COUTE. Le 26/08, deux surnoms d'une partie
sont partis dans un message de commit public ; la decision du 06/09 a ete de ne
PAS reecrire l'historique. Ce que la regle protegeait n'a pas disparu -- c'est
la DISCIPLINE qui doit tenir, et le garde du depot public la tient : il lit les
surnoms de la partie en cours et refuse un commit qui les porterait.

➜ La regle devient donc : **les surnoms circulent dans le FLUX, jamais dans le
DEPOT.** Un journal colle dans un message de commit reste une fuite, et le
garde est ce qui l'arrete.

⚠⚠ POURQUOI CE N'EST PAS UNE TABLE. Le surnom par defaut EST le nom d'espece :
un adversaire nomme, une evolution nommee, tout cela sort du jeu. Sans lui, un
consommateur devrait maintenir 386 entrees pour retrouver un nom que la
cartouche porte deja -- et une table recopiee rendrait des noms ANGLAIS pour
une cartouche francaise.

Cas de l'adversaire, ou le risque est nul :

    un Pokemon sauvage   son surnom EST son nom d'espece, identique dans
                         toutes les copies du jeu
    celui d'un dresseur  meme chose -- le jeu ne les renomme pas

Ce n'est donc pas un extrait de sauvegarde : c'est une chaine que porte
n'importe quelle cartouche. Le garde du depot public avait deja tranche ce cas
exact, en le classant faux positif : « le terme est un nom d'ESPECE, present
dans toutes les copies du jeu ; il coincide avec un surnom parce que le surnom
par defaut EST le nom d'espece ».

➜ Et sans lui, un consommateur devrait maintenir une table de 386 especes pour
retrouver un nom que le jeu porte deja -- ce que `equipe.py` dit explicitement
de ne pas faire. La regle de l'equipe reste INTACTE.
"""

import argparse
import datetime
import json
import struct
import sys
import time
from typing import Any, Dict, List, Optional

import adresses as A
import equipe as E
from probe import DEFAULT_HOST, DEFAULT_PORT, Probe

PAS = 0.45
BATTEMENT = 20.0
DUREE_PAR_DEFAUT = 55 * 60
ESSAIS_PAR_TOUR = 2


class Canal:
    """Une socket tenue ouverte -- et rouverte quand elle coupe, en le DISANT.

    ⚠ Mesure du 2026-09-02 : le canal coupe apres une rafale de lectures. Une
    veille qui meurt sur une lecture ratee ne veille plus, et son silence ment.
    """

    def __init__(self, hote: str, port: int) -> None:
        self.hote, self.port = hote, port
        self.sonde: Optional[Probe] = None
        self.coupures = 0

    def _ouvrir(self) -> Probe:
        if self.sonde is None:
            self.sonde = Probe(self.hote, self.port)
        return self.sonde

    def _fermer(self) -> None:
        try:
            if self.sonde is not None:
                self.sonde.close()
        except OSError:
            pass
        self.sonde = None

    def releve(self) -> Dict[str, Any]:
        """Un relevé COMPLET, avec None pour ce qui n'a pas pu etre lu.

        ⚠ Jamais d'exception vers l'appelant. Mais jamais de silence non plus :
        `coupures` compte, et le battement le publie.
        """
        vide = {"drapeau": None, "position": None, "xp": None, "argent": None,
                "equipe": None, "adverse": None, "image": None}
        for essai in range(1, ESSAIS_PAR_TOUR + 1):
            try:
                return self._lire(self._ouvrir())
            except (OSError, ValueError, struct.error):
                self._fermer()
                if essai == ESSAIS_PAR_TOUR:
                    self.coupures += 1
        return vide

    def _lire(self, sonde: Probe) -> Dict[str, Any]:
        etat = sonde.state()
        return {
            "drapeau": sonde.read(A.TYPE_DE_COMBAT, 32),
            "position": None if not etat else (etat.get("x"), etat.get("y"),
                                               etat.get("g"), etat.get("n")),
            "argent": _argent(sonde),
            "image": _image(sonde),
            **_equipe_et_xp(sonde),
        }


def _image(sonde: Probe) -> Optional[int]:
    """Le numero d'image courant. None si la sonde est trop ancienne.

    ⚠⚠⚠ LA PREMIERE VERSION LISAIT `keys`, ET C'ETAIT UN CONTRESENS. `keys`
    rend l'image du DERNIER APPUI, et le lire CONSOMME les compteurs : une
    veille qui l'appelle toutes les 0,45 s mange le signal « un humain a
    touche la manette », qui ne lui appartient pas. Trouve le 2026-09-07 en
    faisant tourner -- la lecture rendait -1, c'est-a-dire « aucun appui »,
    pas « le jeu est fige ».

    ⚠ La sonde DIT sa version, et ce n'est pas decoratif : une copie ancienne
    collee dans mGBA repond a certaines commandes et pas aux autres. Rendre
    None laisse la veille tourner sans estampille -- ce qui vaut mieux que pas
    de veille -- et le battement le publie.
    """
    return sonde.frame()


def _argent(sonde: Probe) -> Optional[int]:
    """L'argent, dechiffre. ⚠ Le SaveBlock1 DEMENAGE : on relit le pointeur."""
    base = sonde.read(A.PTR_SAVEBLOCK1, 32)
    if not base:
        return None
    cle = sonde.read(base + A.CLE_CHIFFREMENT, 32)
    brut = sonde.read(base + A.ARGENT, 32)
    if cle is None or brut is None:
        return None
    return (int(brut) ^ int(cle)) & 0xFFFFFFFF


def _equipe_et_xp(sonde: Probe) -> Dict[str, Any]:
    """L'equipe reduite a ce qui IDENTIFIE, l'experience DE CHACUN comprise.

    ⚠⚠ LES IDENTIFIANTS D'ATTAQUES, PAS LEUR COMPTE. Un Pokemon qui a deja
    quatre attaques et qui en apprend une la REMPLACE : le compte reste 4 et la
    capacite devient invisible. Ce veilleur a rate exactement ca le 06/09.

    ⚠⚠⚠ ET L'EXPERIENCE EST PORTEE PAR CHAQUE POKEMON, PAS PAR L'EQUIPE. La
    version d'avant rendait une SOMME. Mesure du 2026-09-07 : sortir un Pokemon
    de l'equipe faisait baisser cette somme, ce qui declenchait la regle
    « l'experience a BAISSE, donc chargement de sauvegarde » -- fausse -- puis
    une fausse hausse quand il revenait.

        « l'experience ne peut que monter » est vrai POUR UN POKEMON.
        Une somme d'equipe n'a pas cette propriete.

    Le total reste rendu pour l'affichage, mais AUCUN evenement n'en derive.
    """
    base = A.PV_EQUIPE - E.DECALAGE_PV
    total, rangs = 0, []
    for rang in range(6):
        octets = sonde.dump(base + E.PAS_EQUIPE * rang, E.TAILLE_FICHE)
        if octets is None:
            return {"equipe": None, "xp": None, "adverse": _adverse(sonde)}
        blocs = E.dechiffrer(octets)
        if blocs is None:
            continue
        # ⚠⚠⚠ UNE LECTURE DECHIREE NE PRODUIT AUCUN EVENEMENT -- ni partiel,
        # ni « probablement bon ». Si UN emplacement est incoherent, c'est
        # tout l'instantane qui est suspect : on rend `None`, ce qui veut deja
        # dire « pas lu » et n'emet rien.
        #
        # Mesure du 2026-09-07 : une lecture prise pendant une montee de niveau
        # a produit une fausse evolution, une fausse capacite apprise, et une
        # fausse baisse d'experience -- laquelle a declenche la regle du
        # chargement de sauvegarde. Trois faux positifs d'un seul octet mal
        # tombe.
        if E.somme_de_controle_ok(octets) is False:
            return {"equipe": None, "xp": None, "adverse": _adverse(sonde)}
        experience = struct.unpack_from("<I", blocs["G"], 4)[0]
        total += experience
        fiche = E.lire_fiche(octets)
        rangs.append([fiche["pid"], fiche["espece"], fiche["niveau"],
                      sorted(a["id"] for a in fiche["attaques"]), experience,
                      fiche["surnom"]])
    return {"equipe": rangs, "xp": total, "adverse": _adverse(sonde)}


def _adverse(sonde: Probe) -> Optional[List[int]]:
    """La derniere fiche adverse lue.

    ⚠⚠ Elle SURVIT a la fin du combat, comme le drapeau. Ce champ ne dit donc
    pas « il y a un adversaire » : il dit « la derniere fiche adverse dit
    ceci ». C'est elle qui a produit un faux positif de capture le 06/09.
    """
    octets = sonde.dump(A.PV_ADVERSE - E.DECALAGE_PV, E.TAILLE_FICHE)
    if not octets:
        return None
    fiche = E.lire_fiche(octets)
    if not fiche.get("occupe"):
        return None
    # ⚠ Le surnom en dernier : ajouter en QUEUE ne deplace aucun indice
    # existant. Un consommateur qui lit `[0]` continue de lire le PID.
    return [fiche["pid"], fiche["espece"], fiche["niveau"],
            fiche["stats"]["vitesse"], fiche["surnom"]]


def differences(avant: Dict[str, Any], apres: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Les changements entre deux releves. Fonction PURE, et c'est le coeur.

    ⚠ Une valeur illisible (None) ne produit JAMAIS d'evenement : « je n'ai pas
    su lire » n'est pas « ca a change ». Confondre les deux ferait naitre une
    evolution a chaque coupure de socket.
    """
    evenements: List[Dict[str, Any]] = []

    # ⚠⚠⚠ LE COMPTEUR D'IMAGES NE RECULE JAMAIS. Il ne compte pas le temps, il
    # compte les images emulees : rien, dans une partie qui tourne, ne peut le
    # faire diminuer. Une baisse est donc une IMPOSSIBILITE, et elle ne signale
    # qu'une chose -- un etat sauvegarde recharge, ou l'emulateur relance.
    #
    # ⚠⚠ POURQUOI ELLE VAUT MIEUX QUE LA REGLE DE L'XP. « l'experience baisse »
    # (D-W) est aussi une impossibilite, mais elle ne couvre qu'UN SENS :
    # charger une partie PLUS avancee fait MONTER l'xp, et tout ressemble alors
    # a une victoire enorme.
    #
    #   Mesure du 2026-09-07, en direct : img 11 652 940 -> 4 383 298, avec
    #   +350 812 d'xp, +37 698 d'argent, six PID entrants. La regle de l'xp
    #   n'a pas pu tirer ; le recul d'images, si.
    #
    # ⚠ Elle est emise EN PREMIER et les autres deltas du meme tour suivent :
    # le lecteur doit pouvoir voir ce qui a change ET savoir que rien de tout
    # cela n'est arrive dans la partie.
    a, b = avant.get("image"), apres.get("image")
    if a is not None and b is not None and b < a:
        evenements.append({"quoi": "rupture", "de": a, "a": b,
                           "pourquoi": "le compteur d'images a RECULE -- etat "
                                       "recharge ou emulateur relance ; les "
                                       "deltas de ce tour ne sont pas des "
                                       "evenements de jeu"})

    # ⚠⚠⚠ `xp` N'EST PLUS UNE SOURCE D'EVENEMENT. C'est une somme d'equipe :
    # elle bouge quand la COMPOSITION bouge, sans qu'aucun Pokemon n'ait gagne
    # ni perdu quoi que ce soit. Elle reste dans le releve pour l'affichage.
    # L'experience qui compte est celle de chaque PID, plus bas.
    for champ in ("position", "drapeau", "argent"):
        a, b = avant.get(champ), apres.get(champ)
        if b is None or a is None or a == b:
            continue
        evenement = {"quoi": champ, "de": a, "a": b}
        if champ == "argent":
            evenement["delta"] = b - a
        if champ == "drapeau":
            evenement["dresseur"] = bool(b & A.COMBAT_DRESSEUR)
        evenements.append(evenement)

    evenements.extend(_rencontre(avant.get("adverse"), apres.get("adverse")))

    evenements.extend(_differences_equipe(avant.get("equipe"),
                                          apres.get("equipe")))
    return evenements


def _rencontre(avant: Optional[List[int]],
               apres: Optional[List[int]]) -> List[Dict[str, Any]]:
    """Un adversaire NEUF s'est presente. Fonction PURE.

    ⚠⚠⚠ ON NE REGARDE PAS SI UNE FICHE EST LA -- ELLE Y EST TOUJOURS. Mesure
    du 2026-09-09, trois lectures d'affilee : apres un combat gagne, la fiche
    adverse garde les memes PID avec des PV a zero. Elle ne se vide ni apres
    un sauvage ni apres un dresseur. Une fiche perimee se lit exactement comme
    une fiche vivante -- c'est elle qui a produit le faux positif de capture
    du 06/09.

    ➜ Le seul signal honnete est le PID QUI CHANGE. Deux Rattata d'affilee
    portent des PID differents : un changement veut dire qu'un autre Pokemon a
    ete charge, donc qu'une rencontre commence. Meme discipline que l'xp par
    PID, pour la meme raison.

    ⚠⚠ LA PREMIERE LECTURE N'EMET RIEN. Au demarrage, `avant` est absent et la
    fiche presente est celle du DERNIER combat -- souvent termine depuis
    longtemps. Annoncer une rencontre a l'ouverture ferait naitre un combat qui
    n'a pas lieu. Meme regle que les champs scalaires plus haut : sans un
    « avant », il n'y a pas de changement.
    """
    if not avant or not apres:
        return []
    if avant[0] == apres[0]:
        return []
    rencontre = {"quoi": "rencontre", "pid": apres[0], "espece": apres[1],
                 "niveau": apres[2]}
    # ⚠ Le nom n'est ajoute que s'il a ete lu. Un surnom illisible ne doit pas
    # devenir une chaine vide qui se lirait comme « il n'a pas de nom ».
    if len(apres) > 4 and apres[4]:
        rencontre["nom"] = apres[4]
    return [rencontre]


def _differences_equipe(avant, apres) -> List[Dict[str, Any]]:
    """Evolution, niveau, capacite -- trois deltas d'une meme lecture.

    ⚠⚠ Indexes par PID, la SEULE identite. Deux Pokemon de meme espece, meme
    niveau et memes PV existent (mesure du 06/09) : comparer par rang ou par
    espece les melangerait un jour, sans le dire.
    ⚠⚠⚠ Une EVOLUTION change l'espece a PID CONSTANT, et le NIVEAU NE BOUGE
    PAS. Un detecteur qui exigerait les deux raterait toutes les evolutions.
    """
    # ⚠⚠⚠ `None` ET `[]` NE SONT PAS LA MEME CHOSE, et ce test les
    # confondait. `None` veut dire « je n'ai pas su lire » -- somme de controle
    # mauvaise, sonde muette -- et il ne doit rien produire. `[]` veut dire
    # « lu, et l'equipe est vide » : c'est un ETAT, et les depots qui l'ont
    # videe sont de vrais evenements de sortie.
    #   Trouve le 2026-09-09 par un test qui vidait l'equipe : aucune sortie
    # n'etait emise. Meme famille que le defaut que ce module repare partout --
    # une absence de lecture prise pour une absence de chose.
    if avant is None or apres is None:
        return []
    connus = {rang[0]: rang for rang in avant}
    evenements = []
    for rang in apres:
        pid, espece, niveau, attaques = rang[0], rang[1], rang[2], rang[3]
        experience = rang[4] if len(rang) > 4 else None
        # ⚠ Un surnom illisible reste ABSENT, jamais une chaine vide -- elle se
        # lirait comme « il n'a pas de nom ». Meme regle que pour l'adversaire.
        nom = rang[5] if len(rang) > 5 and rang[5] else None
        if pid not in connus:
            entree = {"quoi": "entree", "pid": pid, "espece": espece,
                      "niveau": niveau}
            if nom:
                entree["nom"] = nom
            evenements.append(entree)
            continue
        ancien = connus[pid]
        espece0, niveau0, attaques0 = ancien[1], ancien[2], ancien[3]
        experience0 = ancien[4] if len(ancien) > 4 else None
        # ⚠⚠ L'EXPERIENCE D'UN POKEMON DONNE : la voila, l'impossibilite. Un
        # Pokemon present AVANT et APRES ne peut pas avoir moins d'experience
        # qu'avant. Une baisse ici est un vrai signal de rupture, la ou une
        # baisse de la SOMME n'en etait pas un.
        if (experience is not None and experience0 is not None
                and experience != experience0):
            evenements.append({"quoi": "xp", "pid": pid, "de": experience0,
                               "a": experience, "delta": experience - experience0})
        nom0 = ancien[5] if len(ancien) > 5 and ancien[5] else None
        if espece != espece0:
            # ⚠⚠ LES DEUX NOMS, et c'est tout l'interet. Un Pokemon au nom par
            # defaut change de nom en evoluant : `de_nom` et `a_nom` donnent
            # « X est devenu Y ». Un Pokemon SURNOMME garde son nom -- les deux
            # champs sont alors egaux, et c'est la verite du jeu, pas un bug.
            evolution = {"quoi": "evolution", "pid": pid,
                         "de": espece0, "a": espece, "niveau": niveau}
            if nom0:
                evolution["de_nom"] = nom0
            if nom:
                evolution["a_nom"] = nom
            evenements.append(evolution)
        if niveau != niveau0:
            monte = {"quoi": "niveau", "pid": pid, "de": niveau0, "a": niveau}
            if nom:
                monte["nom"] = nom
            evenements.append(monte)
        if sorted(attaques) != sorted(attaques0):
            capacite = {
                "quoi": "capacite", "pid": pid,
                "apprises": sorted(set(attaques) - set(attaques0)),
                "remplacees": sorted(set(attaques0) - set(attaques))}
            if nom:
                capacite["nom"] = nom
            evenements.append(capacite)
    partis = set(connus) - {rang[0] for rang in apres}
    for pid in sorted(partis):
        # ⚠ Le nom vient du releve d'AVANT : celui qui part n'est plus dans le
        # releve d'apres, par definition.
        ancien = connus[pid]
        sortie = {"quoi": "sortie", "pid": pid}
        if len(ancien) > 5 and ancien[5]:
            sortie["nom"] = ancien[5]
        evenements.append(sortie)
    return evenements


def _emettre(objet: Dict[str, Any], lisible: bool) -> None:
    if lisible:
        heure = objet.get("heure", "")
        image = objet.get("image")
        reste = {c: v for c, v in objet.items()
                 if c not in ("heure", "image", "quoi")}
        print(f"{heure}  img {image if image is not None else '?':>10}  "
              f"{objet.get('quoi', ''):<10} {reste}", flush=True)
    else:
        print(json.dumps(objet, ensure_ascii=True), flush=True)


def _principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--duree", type=float, default=DUREE_PAR_DEFAUT)
    ap.add_argument("--pas", type=float, default=PAS)
    ap.add_argument("--battement", type=float, default=BATTEMENT)
    ap.add_argument("--lisible", action="store_true",
                    help="pour un humain ; par defaut c'est du JSON par ligne")
    args = ap.parse_args()

    canal = Canal(args.hote, args.port)
    precedent: Dict[str, Any] = {}
    debut = time.time()
    dernier_battement = 0.0
    tours = 0

    _emettre({"heure": _heure(), "quoi": "ouverture", "pas": args.pas,
              "battement": args.battement, "image": None,
              "note": "RAM seule -- cette veille ne regarde pas l'ecran"},
             args.lisible)

    try:
        while time.time() - debut < args.duree:
            tours += 1
            t0 = time.time()
            courant = canal.releve()
            for evenement in differences(precedent, courant):
                _emettre({"heure": _heure(), "image": courant["image"],
                          **evenement}, args.lisible)
            # ⚠ On ne remplace QUE ce qui a ete lu : garder un None ecraserait
            # la derniere valeur connue et ferait re-emettre le meme changement
            # au tour suivant.
            for champ, valeur in courant.items():
                if valeur is not None:
                    precedent[champ] = valeur

            if time.time() - dernier_battement >= args.battement:
                _emettre({"heure": _heure(), "quoi": "battement",
                          "image": courant["image"], "tour": tours,
                          "ms": round((time.time() - t0) * 1000),
                          "coupures": canal.coupures,
                          "drapeau": courant["drapeau"],
                          "xp": courant["xp"], "argent": courant["argent"]},
                         args.lisible)
                dernier_battement = time.time()
            time.sleep(args.pas)
    except KeyboardInterrupt:
        _emettre({"heure": _heure(), "quoi": "fermeture", "image": None,
                  "raison": "interrompue"}, args.lisible)
        return 0

    _emettre({"heure": _heure(), "quoi": "fermeture", "image": None,
              "raison": "duree atteinte", "tours": tours}, args.lisible)
    return 0


def _heure() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    sys.exit(_principal())
