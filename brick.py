"""La brique marcheur -- etape 3 du jalon 1.

Elle inscrit quatre deplacements, recoit des actions d'un moteur, les execute
dans mGBA par la sonde, et rend compte du monde.

Elle ne tient AUCUN contexte : elle envoie des differentiels et oublie. Pas de
memoire, pas d'identite, pas de VTuber. C'est voulu -- a ce jalon, l'invariant
d'isolation des sujets n'est meme pas en jeu.

⚠⚠ LA CONVENTION DE RESULTAT -- la seule piece que personne d'autre ne fournit,
et la raison d'etre de ce fichier :

  1. `action/result` part IMMEDIATEMENT, AVANT l'execution. C'est un accuse de
     VALIDITE (SPECIFICATION.md:168), pas un resultat.
  2. Son `success` est un DRAPEAU DE RE-ESSAI, pas une verite (ligne 188).
  3. Le monde revient ENSUITE, par un `context` portant l'etat AVANT et APRES.
     Motif sanctionne par le linter de Gary : « send a "validation" success
     result immediately and follow up later with a `context` message ».
  4. Jamais « j'ai reussi ». La brique CONSTATE, le sujet JUGE. Le succes est
     une relation entre une intention et le monde ; la brique n'a que le monde.

Usage :
    python brick.py                             # sans cible : deltas seuls
    python brick.py --target 17,8               # avec cible : le critere du delta
    python brick.py --drive context             # l'autre facon de relancer le tour
    python brick.py --verbose                   # montre les trames

⚠ Le rapport ne pilote pas. Un `context` silencieux nourrit sans rien
reclamer -- c'est ce qu'un compte rendu doit faire. Ce qui relance le tour,
c'est `actions/force`. Mesure du 2026-08-10 en 15 s : rapport silencieux seul
= 0 action ; rapport silencieux + force = 80.

Prealable : la sonde tourne dans mGBA, et un moteur ecoute sur --url.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time

import probe as probe_mod
import protocol
from probe import Probe

GAME_NAME = "Pokemon Rouge Feu"

# Les quatre deplacements. AUCUN schema : ils ne prennent pas de parametre,
# et un `{}` autoriserait n'importe quoi (voir protocol.action).
#
# ⚠ Nommees par ce qu'elles ACCOMPLISSENT, jamais par ce qu'elles terminent :
# un modele evite les actions qui sonnent comme un abandon d'agentivite
# (observe sur Inscryption -- « she really doesn't like to end her turn »).
MOVES = {
    "move_north": "UP",
    "move_south": "DOWN",
    "move_west": "LEFT",
    "move_east": "RIGHT",
}

# ⚠ Ces libelles partent vers un modele de langue, donc ils sont en anglais.
# Le PIEGE DE LA LANGUE n'est pas arme ici : on n'expose que des nombres lus
# en RAM, aucun nom du jeu. Il s'armera le jour ou l'on traduira `mapNum` en
# nom de lieu -- la ROM est FRANCAISE, et une table ecrite en anglais
# reproduirait l'erreur de Cianwood/Irisia avec l'autorite d'un fichier.
DESCRIPTIONS = {
    "move_north": "Walk one tile north (up).",
    "move_south": "Walk one tile south (down).",
    "move_west": "Walk one tile west (left).",
    "move_east": "Walk one tile east (right).",
}


# --------------------------------------------------------------- coeur pur

def distance(state, target) -> int:
    """Distance de Manhattan en tuiles, ou None si elle n'a pas de sens.

    Manhattan et pas euclidienne : avec quatre directions, c'est litteralement
    le nombre de pas restants. Rendre None sur une autre carte est deliberé --
    comparer des tuiles entre deux cartes produirait un nombre qui a l'air
    d'une mesure.
    """
    if state is None or target is None:
        return None
    if (state["g"], state["n"]) != (target["g"], target["n"]):
        return None
    return abs(state["x"] - target["x"]) + abs(state["y"] - target["y"])


def describe(name: str, before, after, target) -> str:
    """Rend compte du monde. CONSTAT, jamais jugement."""
    if before is None or after is None:
        return f"{name}: could not read the position."

    if not probe_mod.is_stable(after):
        return (f"{name}: a door transition is in progress, "
                f"the position is not stable yet.")

    dx = after["x"] - before["x"]
    dy = after["y"] - before["y"]
    parts = [f"{name}: ({before['x']},{before['y']}) -> ({after['x']},{after['y']})"]

    if (before["g"], before["n"]) != (after["g"], after["n"]):
        parts.append(f"the map changed from {before['g']}:{before['n']} "
                     f"to {after['g']}:{after['n']}")
    elif dx == 0 and dy == 0:
        # ⚠ « did not move » et PAS « wall ». Un delta nul porte deja DEUX sens
        # -- un mur, ou un pas avale par un dialogue ouvert -- et rien ici ne
        # permet de les separer. Trancher serait inventer un fait.
        parts.append("the position did not change")

    d_before, d_after = distance(before, target), distance(after, target)
    if d_after is None and target is not None:
        parts.append("the target is on another map")
    elif d_after is not None:
        parts.append(f"distance to target: {d_after} tiles (was {d_before})")

    return ". ".join(parts) + "."


def parse_target(raw: str, current):
    """'12,8' -> cible sur la carte COURANTE. La carte n'est pas un argument :
    la deviner serait offrir un moyen de se tromper en silence."""
    if raw is None:
        return None
    try:
        x_str, y_str = raw.split(",")
        x, y = int(x_str), int(y_str)
    except ValueError:
        raise SystemExit(f"--target attend 'x,y', recu : {raw!r}")
    if current is None:
        raise SystemExit("--target exige une position lisible au demarrage")
    return {"x": x, "y": y, "g": current["g"], "n": current["n"]}


# ------------------------------------------------------------------- trace

class Trace:
    """Une ligne JSON par action. C'est la mesure, pas un journal de debug.

    ⚠ La PREMIERE ligne est un en-tete de session, pas une action. Sans elle,
    deux traces produites dans des conditions opposees sont indiscernables --
    celle d'un pilote aleatoire et celle d'un LLM se ressemblent trait pour
    trait. Un nombre sans ses conditions n'est pas une mesure, c'est une
    anecdote qu'on croit comparable.
    """

    def __init__(self, directory: str, session: dict) -> None:
        os.makedirs(directory, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(directory, f"walk_{stamp}.jsonl")
        self._fh = open(self.path, "a", encoding="utf-8")
        self.write({"type": "session", **session})

    def write(self, row: dict) -> None:
        row.setdefault("type", "action")
        row["t"] = dt.datetime.now().isoformat(timespec="seconds")
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()   # une session qui plante ne doit pas perdre sa mesure

    def close(self) -> None:
        self._fh.close()


# ------------------------------------------------------------------ shell

def action_specs():
    return [protocol.action(name, DESCRIPTIONS[name]) for name in MOVES]


def force_query(target) -> str:
    if target is None:
        return "Choose a direction to walk."
    return (f"Walk toward ({target['x']},{target['y']}). "
            f"Choose one direction to move.")


def handle_action(client, sonde, msg, trace, target, frames, silent_report, pilote):
    """Rend (moved, arrived). `moved` vaut None quand il n'y a pas de cible."""
    data = msg.get("data") or {}
    action_id = data.get("id")
    name = data.get("name")

    if name not in MOVES:
        # Refus AVANT execution : c'est exactement le role de ce message.
        client.result(action_id, False, f"Unknown action: {name}")
        return None, False, None

    # 1. VALIDITE. Immediat, avant que quoi que ce soit touche le monde.
    #    Le moteur attend ce message pour reprendre la main -- la spec :
    #    « Until you send an action result, Neuro will just be waiting. »
    client.result(action_id, True)

    # 2. Le monde.
    before = sonde.state()
    after = sonde.press(MOVES[name], frames)
    if after is None:
        # ⚠ On REMONTE ce que la sonde a dit. Un pointeur RAM invalide et une
        # collision de pilotes (« une pression est deja en cours », quand un
        # second client parle a la meme sonde) sont deux pannes differentes
        # qui exigent deux gestes opposes -- et elles s'affichaient pareil.
        print(f"  !! la sonde a refuse : {sonde.last_reply!r}")

    # 3. Le compte rendu, separe et posterieur. SILENCIEUX en mode `force` :
    #    un rapport nourrit le contexte, il ne reclame rien. C'est la
    #    conclusion du registre de protocole, §4.
    #
    # ⚠ Consequence mesuree le 2026-08-10 : un rapport silencieux ne relance
    #    RIEN. Il faut donc un pilote separe (`actions/force`). Le registre
    #    avait la bonne forme du rapport, la mesure a montre la piece qui
    #    manquait autour.
    client.context(describe(name, before, after, target), silent=silent_report)

    d_before, d_after = distance(before, target), distance(after, target)
    trace.write({
        "action": name,
        # Qui a decide ce pas. Constant aujourd'hui -- une seule source agit --
        # mais pose des maintenant : le jour ou un humain prendra le relais sur
        # une portion, une trace sans ce champ melangerait les deux et tous les
        # agregats deviendraient faux SANS que rien ne le signale.
        "pilote": pilote,
        "id": action_id,
        "before": before,
        "after": after,
        "dx": None if (before is None or after is None) else after["x"] - before["x"],
        "dy": None if (before is None or after is None) else after["y"] - before["y"],
        "distance_before": d_before,
        "distance_after": d_after,
        # Le CRITERE DU DELTA : positif = elle s'est rapprochee. C'est
        # l'amendement P2 du 2026-07-06, et c'est ce que fait le code de
        # NVIDIA (moved = norm(pos_after - pos_before)).
        "moved": None if (d_before is None or d_after is None) else d_before - d_after,
    })
    print(f"  {describe(name, before, after, target)}")

    moved = None if (d_before is None or d_after is None) else d_before - d_after
    return moved, (d_after == 0), d_after


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=protocol.DEFAULT_URL,
                    help="le moteur (Gary au jalon 1)")
    ap.add_argument("--game", default=GAME_NAME)
    ap.add_argument("--host", default=probe_mod.DEFAULT_HOST, help="la sonde")
    ap.add_argument("--port", type=int, default=probe_mod.DEFAULT_PORT)
    ap.add_argument("--frames", type=int, default=probe_mod.PRESS_FRAMES)
    ap.add_argument("--target", default=None, metavar="X,Y",
                    help="point B sur la carte courante ; sans lui, deltas seuls")
    ap.add_argument("--trace-dir", default="traces")
    ap.add_argument("--drive", choices=("force", "context"), default="force",
                    help="ce qui relance le tour. 'force' = rapport silencieux "
                         "puis actions/force (conforme au registre) ; 'context' "
                         "= rapport non silencieux qui sollicite au passage")
    ap.add_argument("--max-stuck", type=int, default=5, metavar="N",
                    help="tours CONSECUTIFS sans progres avant de declarer un "
                         "blocage (defaut 5). Sans cible, sans effet")
    ap.add_argument("--turn-budget", type=float, default=3.0, metavar="K",
                    help="budget de tours = K x la distance de depart (defaut "
                         "3). Au-dela sans arriver : ERRANCE. Sans cible, "
                         "sans effet -- la boucle tourne alors indefiniment")
    ap.add_argument("--pilote", default="inconnu", metavar="NOM",
                    help="qui decide -- 'randy', 'openrouter/free', un nom de "
                         "modele, 'humain'. ⚠ ETIQUETTE DECLAREE, pas mesuree : "
                         "la brique ne peut pas savoir ce que le moteur execute")
    ap.add_argument("--stall", type=float, default=60.0, metavar="S",
                    help="secondes sans action, force en attente, avant de "
                         "declarer un silence du moteur (defaut 60)")
    ap.add_argument("--verbose", action="store_true", help="montre les trames")
    args = ap.parse_args()

    try:
        sonde = Probe(args.host, args.port)
    except OSError as exc:
        print(f"Sonde injoignable sur {args.host}:{args.port} -- {exc}")
        print("La sonde tourne-t-elle ? (mGBA > Outils > Scripting > probe.lua)")
        return 1

    start = sonde.state()
    if start is None:
        print("La sonde repond mais l'etat est illisible (SaveBlock non resolu).")
        print("Une partie est-elle chargee et hors menu ?")
        sonde.close()
        return 1
    target = parse_target(args.target, start)

    # ⚠ L'arrivee ne se testait QU'APRES une action. Depart (12,10) pour une
    # cible (12,10) faisait donc demander au moteur de marcher la ou il etait
    # deja -- une consigne absurde envoyee a un modele, et un budget de tours
    # calcule sur une distance nulle. Mesure du 2026-08-11.
    if target is not None and distance(start, target) == 0:
        print(f"Depart et cible confondus en ({start['x']},{start['y']}).")
        print("Rien a parcourir -- choisis une autre cible.")
        sonde.close()
        return 0

    client = protocol.Client(args.url, args.game, verbose=args.verbose)
    try:
        client.connect()
    except OSError as exc:
        print(f"Moteur injoignable sur {args.url} -- {exc}")
        print("Gary tourne-t-il, et sur le bon port ?")
        sonde.close()
        return 1

    # L'en-tete de session. ⚠ `pilote` est DECLARE : la brique ne voit que des
    # messages de protocole, jamais quel moteur les produit. Une etiquette
    # declaree peut mentir -- mais une trace sans etiquette ne peut meme pas
    # etre comparee, et c'est pire.
    trace = Trace(args.trace_dir, {
        "pilote": args.pilote,
        "jeu": args.game,
        "url": args.url,
        "drive": args.drive,
        "depart": start,
        "cible": target,
        "frames": args.frames,
        "max_stuck": args.max_stuck,
        "turn_budget": args.turn_budget,
        "stall": args.stall,
    })
    print(f"Sonde   : {args.host}:{args.port}  -- depart ({start['x']},{start['y']}) "
          f"carte {start['g']}:{start['n']}")
    print(f"Moteur  : {args.url}")
    cible_txt = ("aucune -- deltas seuls" if target is None
                 else f"({target['x']},{target['y']}) sur la carte de depart")
    print(f"Cible   : {cible_txt}")
    print(f"Trace   : {trace.path}")

    client.startup()
    client.register(action_specs())

    # En mode `force`, le rapport est SILENCIEUX (c'est un compte rendu, il ne
    # reclame rien) et c'est `actions/force` qui pilote. En mode `context`, le
    # rapport porte les deux roles a la fois -- plus simple, moins fidele.
    silent_report = (args.drive == "force")

    opening = f"You are at ({start['x']},{start['y']})."
    if target is not None:
        opening += f" Walk to ({target['x']},{target['y']})."
    client.context(opening, silent=silent_report)

    # ⚠⚠ LA PREMIERE FORCE NE PART PAS ICI, ET C'EST UN CORRECTIF.
    #
    # Le moteur demande une REINSCRIPTION juste apres la connexion. Forcer
    # avant que sa liste d'actions soit stable fabrique la course de l'issue
    # #14 : la force reference des actions reinscrites sous elle.
    # Diagnostic recu le 2026-08-11 : « Multiple actions/force at once --
    # Neuro can only handle one action force at a time ».
    #
    # Elle part donc au premier tour de boucle A VIDE, quand la poignee de
    # main s'est tue. Et `pending_force` garantit qu'il n'y en a JAMAIS deux :
    # une force se consomme par l'action qu'elle provoque.
    pending_force = False
    forced_at = 0.0

    turns = 0
    stuck = 0
    worst_stuck = 0
    d_start = distance(start, target)
    d_last = d_start
    # Un appui = une case, donc la distance de depart EST le nombre minimal de
    # tours. Le budget est un multiple de ce minimum, jamais une constante :
    # un nombre fixe mesurerait la longueur du trajet, pas le pilote.
    budget = None if d_start is None else max(1, int(args.turn_budget * d_start))

    try:
        while True:
            msg = client.receive(timeout=1.0)
            if msg is None:
                # Silence du moteur = la poignee de main s'est tue. C'est le
                # seul moment sur pour poser la premiere force.
                if args.drive == "force" and not pending_force:
                    client.force(force_query(target), list(MOVES),
                                 ephemeral_context=True)
                    pending_force = True
                    forced_at = time.monotonic()
                # ⚠ Une force sans reponse n'autorise PAS d'en renvoyer une
                # (c'est le defaut qu'on vient de corriger). Mais attendre en
                # silence pour toujours n'est pas mieux : il faut le DIRE.
                elif pending_force and time.monotonic() - forced_at > args.stall:
                    print(f"  SILENCE : aucune action depuis {args.stall:.0f} s "
                          f"malgre une force en attente.")
                    print("  Regarde le journal du moteur -- la panne est de "
                          "son cote, pas ici.")
                    break
                continue
            command = msg.get("command")

            if command == "action":
                # L'action CONSOMME la force qui l'a provoquee.
                pending_force = False
                turns += 1
                moved, arrived, d_now = handle_action(
                    client, sonde, msg, trace, target, args.frames,
                    silent_report, args.pilote)
                if d_now is not None:
                    d_last = d_now
                if arrived:
                    print(f"  ARRIVEE en {turns} tours.")
                    break
                if moved is not None:
                    # Un progres nul OU negatif compte comme un tour sans
                    # progres : le yo-yo est un echec au meme titre que le mur.
                    stuck = 0 if moved > 0 else stuck + 1
                    worst_stuck = max(worst_stuck, stuck)
                    if stuck >= args.max_stuck:
                        print(f"  BLOCAGE : {stuck} tours consecutifs sans "
                              f"progres, arret au tour {turns}.")
                        break
                # ⚠ L'ERRANCE est un echec DISTINCT du blocage, et le blocage
                # ne l'attrape pas : une marche au hasard ne se coince jamais,
                # elle tourne. Mesure du 2026-08-10 -- 23 tours, progres net
                # nul, pire serie de blocage 4 : rien ne l'aurait arretee.
                if budget is not None and turns >= budget:
                    print(f"  ERRANCE : {turns} tours pour une distance de "
                          f"depart de {d_start}, sans arriver.")
                    break
                if args.drive == "force":
                    client.force(force_query(target), list(MOVES),
                                 ephemeral_context=True)
                    pending_force = True
                    forced_at = time.monotonic()

            elif command == "actions/reregister_all":
                # ⚠ La spec dit que ce message n'existe pas ; Randy l'ENVOIE a
                # chaque connexion, et Gary aussi quand la compatibilite est
                # active. Une brique qui l'ignore verra le moteur a zero
                # action, indefiniment, SANS erreur.
                print("  (reinscription demandee)")
                client.register(action_specs())

            elif command == "startup":
                # Accuse de session. Il porte un `characterId` -- on ne le lit
                # PAS : la brique ne sait pas qui joue, et c'est une des trois
                # ignorances qu'on tient volontairement.
                print("  (session ouverte par le moteur)")

            else:
                print(f"  (message ignore : {command})")

    except KeyboardInterrupt:
        print()
    except (ConnectionError, OSError) as exc:
        print(f"Connexion perdue : {exc}")
        return 1
    finally:
        trace.close()
        client.close()
        sonde.close()
        print()
        print("--- fin de session ---")
        print(f"pilote declare         : {args.pilote}")
        print(f"tours joues            : {turns}")
        if target is not None:
            print(f"budget de tours        : {budget} ({args.turn_budget}x "
                  f"la distance de depart)")
            print(f"distance au depart     : {d_start} tuiles")
            print(f"distance a la fin      : {d_last} tuiles")
            if d_start is not None and d_last is not None:
                net = d_start - d_last
                print(f"progres net            : {net:+d} tuiles")
            print(f"pire serie sans progres: {worst_stuck} tours")
        else:
            print("distance               : pas de cible -- deltas seuls")
        print(f"trace                  : {trace.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
