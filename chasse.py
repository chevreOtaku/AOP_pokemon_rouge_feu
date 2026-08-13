"""Chasse aux adresses -- capturer, comparer, reduire.

Aucune carte memoire n'existe pour Pokemon Rouge Feu (FR). Le pointeur de
position a ete trouve en juillet par scan et correlation ; les adresses de
combat, d'equipe et de curseur se trouveront pareil. Cet outil ne cherche rien
tout seul : il capture la memoire a des instants que TU choisis, et il reduit
la liste des candidats en comparant ces instants.

LA METHODE, et elle tient en une phrase :
    tu sais ce qui a change dans le jeu ; la memoire, elle, a beaucoup change.
    On garde les adresses dont le changement RESSEMBLE au tien, et on repete
    jusqu'a ce qu'il en reste peu.

USAGE TYPIQUE -- trouver le drapeau « en combat » :

    python chasse.py capture hors_combat_1
    (declencher un combat)
    python chasse.py capture en_combat_1
    python chasse.py diff hors_combat_1 en_combat_1 --sortie c.txt
    (fuir le combat)
    python chasse.py capture hors_combat_2
    python chasse.py egal hors_combat_1 hors_combat_2 --parmi c.txt --sortie c.txt
    -> il reste les adresses qui ont bouge PUIS sont revenues.

USAGE TYPIQUE -- trouver les PV, quand tu LIS le nombre a l'ecran :

    python chasse.py capture combat_1
    python chasse.py valeur combat_1 --egale 23 --taille 2 --sortie c.txt
    (encaisser des degats, relire les PV a l'ecran)
    python chasse.py capture combat_2
    python chasse.py valeur combat_2 --egale 17 --taille 2 --parmi c.txt --sortie c.txt

⚠⚠ NE METS JAMAIS L'EMULATEUR EN PAUSE POUR CAPTURER.

Cette consigne disait l'inverse jusqu'au 2026-08-12, et elle etait FAUSSE :
en pause, mGBA suspend les rappels du script Lua, donc la sonde ne repond plus.
Mesure -- capture sans pause : reussie ; capture en pause : delai depasse ;
capture suivante : connexion refusee, la sonde ne revient pas d'elle-meme.

⚠ Une capture n'est donc PAS un instant : elle prend ~2 s pendant que le jeu
tourne, et des compteurs d'animation bougeront en cours de route. Ce n'est pas
grave -- ils ne survivront pas aux croisements, parce qu'ils ne respectent
aucune des contraintes qu'on impose. La parade est de choisir un moment
TRANQUILLE : en combat, le menu d'attaques affiche, quand le jeu attend une
entree et que rien ne s'anime.
"""

import argparse
import struct
import sys
from pathlib import Path

from probe import DEFAULT_HOST, DEFAULT_PORT, EWRAM, IWRAM, Probe

ICI = Path(__file__).resolve().parent
DOSSIER = ICI / "chasse"
MORCEAU = 1024   # taille maximale d'un `dump`, cote sonde -- doit rester <= DUMP_MAX

# On balaye les deux regions ou vit l'etat de partie. La ROM est exclue : elle
# ne change jamais, donc elle ne peut rien nous apprendre par comparaison.
PLAGES = [("EWRAM", *EWRAM), ("IWRAM", *IWRAM)]


def capturer(sonde, etiquette: str) -> Path:
    DOSSIER.mkdir(exist_ok=True)
    chemin = DOSSIER / f"{etiquette}.bin"
    with chemin.open("wb") as f:
        for nom, base, longueur in PLAGES:
            f.write(struct.pack("<II", base, longueur))
            lus = 0
            while lus < longueur:
                n = min(MORCEAU, longueur - lus)
                octets = sonde.dump(base + lus, n)
                if octets is None or len(octets) != n:
                    raise RuntimeError(
                        f"{nom} 0x{base + lus:08X} : {sonde.last_reply}")
                f.write(octets)
                lus += n
            print(f"  {nom}  0x{base:08X}  {longueur} octets")
    return chemin


def charger(etiquette: str):
    """Rend [(base, octets), ...]. Le fichier porte ses propres bornes : une
    capture qui ne dit pas d'ou elle vient ne se compare a rien."""
    chemin = DOSSIER / f"{etiquette}.bin"
    if not chemin.exists():
        disponibles = sorted(p.stem for p in DOSSIER.glob("*.bin")) if DOSSIER.exists() else []
        raise SystemExit(f"Capture inconnue : {etiquette}\n"
                         f"Disponibles : {disponibles or '(aucune)'}")
    blocs, brut = [], chemin.read_bytes()
    pos = 0
    while pos < len(brut):
        base, longueur = struct.unpack_from("<II", brut, pos)
        pos += 8
        blocs.append((base, brut[pos:pos + longueur]))
        pos += longueur
    return blocs


def lire_valeur(octets: bytes, offset: int, taille: int) -> int:
    if taille == 1:
        return octets[offset]
    if taille == 2:
        return int.from_bytes(octets[offset:offset + 2], "little")
    return int.from_bytes(octets[offset:offset + 4], "little")


def parcourir(blocs, taille: int, restreint=None):
    """Rend (adresse, valeur) pour chaque position alignee."""
    for base, octets in blocs:
        for off in range(0, len(octets) - taille + 1, taille):
            addr = base + off
            if restreint is not None and addr not in restreint:
                continue
            yield addr, lire_valeur(octets, off, taille)


def charger_candidats(chemin) -> set:
    if not chemin:
        return None
    texte = Path(chemin).read_text(encoding="utf-8")
    return {int(l.split()[0], 16) for l in texte.splitlines()
            if l.strip() and not l.startswith("#")}


def ecrire_candidats(chemin, trouves, commentaire: str):
    if not chemin:
        return
    # ⚠ UN RESULTAT VIDE N'ECRASE PAS UNE LISTE EXISTANTE. Le 2026-08-12,
    # `--parmi pv.txt --sortie pv.txt` a remplace sept candidats durement
    # obtenus par zero -- et zero ne se defait pas. Un croisement qui ne rend
    # rien dit qu'une HYPOTHESE etait fausse, pas que le travail d'avant l'etait.
    if not trouves and Path(chemin).exists():
        print(f"  ⚠ resultat VIDE : {chemin} n'est PAS ecrase (la liste "
              f"precedente est conservee). Revois la valeur cherchee.")
        return
    lignes = [f"# {commentaire}", f"# {len(trouves)} candidats"]
    lignes += [f"0x{a:08X}  {v}" for a, v in trouves]
    Path(chemin).write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"  ecrit : {chemin}")


def rapporter(trouves, sortie, commentaire, apercu=20):
    print(f"\n{len(trouves)} adresse(s)")
    for a, v in trouves[:apercu]:
        print(f"   0x{a:08X}  {v}")
    if len(trouves) > apercu:
        # ⚠ On DIT ce qu'on n'affiche pas. Une liste coupee en silence se lit
        # comme une liste complete -- et une conclusion tiree dessus est fausse
        # sans que rien ne le signale.
        print(f"   ... et {len(trouves) - apercu} autres, non affichees "
              f"(la liste complete part dans --sortie)")
    ecrire_candidats(sortie, trouves, commentaire)


# Le pointeur du SaveBlock1, trouve par scan et correlation le 2026-07-08.
# Il sert ici de TEMOIN : on sait ce qu'il doit contenir, donc il verifie a la
# fois que les nouvelles commandes marchent et qu'on parle au bon jeu.
PTR_SAVEBLOCK = 0x03004F58


def verifier(sonde) -> int:
    """Auto-test apres rechargement du script Lua. Rend 0 si tout passe.

    ⚠ Chaque etape DIT ce qu'elle attendait. Un auto-test qui repond « KO »
    sans dire quoi ne fait que deplacer la question.
    """
    echecs = 0

    def verdict(nom, ok, detail):
        nonlocal echecs
        if not ok:
            echecs += 1
        print(f"  [{'ok ' if ok else 'ECHEC'}] {nom:34s} {detail}")

    verdict("ping", sonde.ask("ping") == "ok pong", sonde.last_reply)

    # ⚠ EN PREMIER, PARCE QUE TOUT LE RESTE EN DEPEND. Sans ce controle, une
    # ancienne copie du script repond `ping` et `state` puis rend « commande
    # inconnue » sur le reste -- et on cherche la faute dans le mauvais fichier.
    version = sonde.ask("version")
    a_la_version = version.startswith("ok ")
    verdict("version de la sonde", a_la_version,
            version[3:] if a_la_version else
            f"{sonde.last_reply}  <- SCRIPT LUA PERIME dans mGBA")
    if not a_la_version:
        print("\n  Le script charge dans mGBA est ANTERIEUR aux lectures memoire.")
        print("  Un « rechargement » ne suffit pas si le script avait ete COLLE :")
        print("  dans mGBA, Outils > Scripting, puis File > Load sur")
        print(f"  {ICI / 'lua' / 'probe.lua'}")
        print("  (et regarde la console : une faute de syntaxe s'y affiche)")
        return 1

    etat = sonde.state()
    verdict("state (commande d'origine)", etat is not None,
            str(etat) if etat else sonde.last_reply)

    ptr = sonde.read(PTR_SAVEBLOCK, 32)
    lo, taille = EWRAM
    plausible = ptr is not None and lo <= ptr < lo + taille
    verdict("read32 du pointeur temoin", plausible,
            f"0x{ptr:08X}" if ptr is not None else sonde.last_reply)
    if ptr is not None and not plausible:
        print("         -> la commande repond, mais la valeur ne pointe pas dans "
              "l'EWRAM : mauvaise cartouche, ou partie non chargee")

    octets = sonde.dump(lo, 64)
    verdict("dump de 64 octets", octets is not None and len(octets) == 64,
            f"{len(octets)} octets" if octets else sonde.last_reply)

    grand = sonde.dump(lo, 1024)
    verdict("dump de 1024 octets (troncature)",
            grand is not None and len(grand) == 1024,
            f"{len(grand)} octets recus sur 1024" if grand else sonde.last_reply)

    sommes = sonde.blocks(lo, 4096, 256)
    verdict("blocks : 4096 / 256 = 16 sommes",
            sommes is not None and len(sommes) == 16,
            f"{len(sommes)} sommes" if sommes else sonde.last_reply)

    # ⚠ ON VERIFIE LA RAISON, PAS SEULEMENT L'ABSENCE DE VALEUR. Ce controle a
    # rendu « ok » le 2026-08-12 face a une sonde qui ne connaissait meme pas la
    # commande : il voyait None et concluait au refus. Un test qui passe pour la
    # mauvaise raison est pire qu'un test absent -- il certifie.
    refus = sonde.read(0x00000000, 32)
    raison = sonde.last_reply
    bien_refuse = refus is None and "region" in raison.lower()
    verdict("refus d'une adresse hors region", bien_refuse,
            raison if bien_refuse
            else f"{raison}  <- rien lu, mais pas pour la bonne raison")

    print()
    if echecs == 0:
        print("Sonde complete : les trois lectures brutes repondent, "
              "et le temoin confirme la bonne partie.")
    else:
        print(f"{echecs} echec(s). Si TOUT echoue y compris `ping`, le script Lua "
              f"n'a pas ete recharge -- ou il a une faute de syntaxe : "
              f"regarde la console de scripting de mGBA.")
    return 1 if echecs else 0


def main():
    ap = argparse.ArgumentParser(description="Chasse aux adresses memoire")
    ap.add_argument("--hote", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    sous = ap.add_subparsers(dest="cmd", required=True)

    p = sous.add_parser("capture", help="enregistrer l'etat memoire maintenant")
    p.add_argument("etiquette")

    for nom, aide in (("diff", "adresses dont la valeur A CHANGE"),
                      ("egal", "adresses dont la valeur EST RESTEE la meme")):
        p = sous.add_parser(nom, help=aide)
        p.add_argument("a")
        p.add_argument("b")
        p.add_argument("--taille", type=int, default=1, choices=(1, 2, 4))
        p.add_argument("--parmi")
        p.add_argument("--sortie")

    p = sous.add_parser("valeur", help="adresses portant une valeur connue")
    p.add_argument("capture")
    p.add_argument("--egale", type=int, required=True)
    p.add_argument("--taille", type=int, default=2, choices=(1, 2, 4))
    p.add_argument("--parmi")
    p.add_argument("--sortie")

    p = sous.add_parser("lire", help="lire quelques adresses en direct")
    p.add_argument("adresses", nargs="+")
    p.add_argument("--taille", type=int, default=2, choices=(8, 16, 32, 1, 2, 4))

    p = sous.add_parser("montrer", help="ce que valent des adresses dans chaque capture")
    p.add_argument("captures", nargs="+")
    p.add_argument("--adresses", nargs="*", default=[])
    p.add_argument("--parmi")
    p.add_argument("--taille", type=int, default=2, choices=(1, 2, 4))

    sous.add_parser("verifier", help="l'auto-test de la sonde -- a lancer apres "
                                     "chaque rechargement du script Lua")

    args = ap.parse_args()

    if args.cmd in ("capture", "lire", "verifier"):
        try:
            sonde = Probe(args.hote, args.port)
        except OSError as e:
            raise SystemExit(
                f"Sonde injoignable sur {args.hote}:{args.port} -- {e}\n"
                f"mGBA est-il ouvert avec lua/probe.lua charge ?\n"
                f"⚠ Si la sonde repondait il y a une minute : une capture lancee "
                f"pendant que le jeu etait EN PAUSE la tue (les rappels du script "
                f"sont suspendus, le client expire, la sonde ne revient pas). "
                f"Il faut relancer mGBA et recharger le script.")
        if sonde.ask("ping") != "ok pong":
            raise SystemExit(f"La sonde repond mais pas 'pong' : {sonde.last_reply}")

    if args.cmd == "verifier":
        sys.exit(verifier(sonde))

    if args.cmd == "capture":
        print(f"Capture '{args.etiquette}' -- le jeu doit TOURNER (jamais en pause : "
              f"la sonde ne repond plus) ; choisis un moment ou rien ne s'anime.")
        chemin = capturer(sonde, args.etiquette)
        print(f"-> {chemin}")
        sonde.close()
        return

    if args.cmd == "lire":
        bits = {1: 8, 2: 16, 4: 32}.get(args.taille, args.taille)
        for texte in args.adresses:
            addr = int(texte, 16) if texte.lower().startswith("0x") else int(texte)
            v = sonde.read(addr, bits)
            print(f"  0x{addr:08X}  {v if v is not None else sonde.last_reply}")
        sonde.close()
        return

    restreint = charger_candidats(getattr(args, "parmi", None))

    if args.cmd == "montrer":
        # ⚠ REGARDER AVANT DE SUPPOSER. Un croisement qui rend zero ne dit pas
        # ou est l'erreur ; la table des valeurs, elle, la montre en une ligne.
        adresses = sorted(restreint or set())
        for texte in args.adresses:
            adresses.append(int(texte, 16) if texte.lower().startswith("0x")
                            else int(texte))
        adresses = sorted(set(adresses))
        if not adresses:
            raise SystemExit("Aucune adresse : donne --parmi <fichier> ou --adresses ...")
        tables = {c: dict(parcourir(charger(c), args.taille, set(adresses)))
                  for c in args.captures}
        largeur = max(9, max(len(c) for c in args.captures) + 1)
        entete = "adresse    " + "".join(f"{c:>{largeur}s}" for c in args.captures)
        print(entete)
        print("-" * len(entete))
        for addr in adresses:
            ligne = f"0x{addr:08X}"
            for c in args.captures:
                v = tables[c].get(addr)
                ligne += f"{('-' if v is None else str(v)):>{largeur}s}"
            print(ligne)
        return

    if args.cmd == "valeur":
        blocs = charger(args.capture)
        trouves = [(a, v) for a, v in parcourir(blocs, args.taille, restreint)
                   if v == args.egale]
        rapporter(trouves, args.sortie,
                  f"{args.capture} : valeur == {args.egale} ({args.taille} octets)")
        return

    ba, bb = charger(args.a), charger(args.b)
    va = dict(parcourir(ba, args.taille, restreint))
    trouves = []
    for addr, valeur in parcourir(bb, args.taille, restreint):
        avant = va.get(addr)
        if avant is None:
            continue
        if (args.cmd == "diff") == (avant != valeur):
            trouves.append((addr, valeur if args.cmd == "diff" else avant))
    rapporter(trouves, args.sortie,
              f"{args.a} -> {args.b} : {args.cmd} ({args.taille} octets)")


if __name__ == "__main__":
    main()
