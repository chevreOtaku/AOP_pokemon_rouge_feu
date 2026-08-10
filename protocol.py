"""Le protocole -- le tuyau et les six messages, rien d'autre.

Ce module ne sait RIEN du jeu : ni Pokemon, ni sonde, ni RAM. Il ouvre une
WebSocket vers un moteur (Gary au jalon 1) et transporte des messages.

La CONVENTION DE RESULTAT ne vit pas ici, et c'est deliberé : elle depend de
ce que le monde renvoie, donc elle appartient a la brique. Ce fichier fournit
seulement `result()` et `context()` -- les deux moities du motif -- sans
imposer comment on s'en sert.

Reference : neuro-sdk/API/SPECIFICATION.md, lu le 2026-08-10.

⚠ GARY VALIDE EN `strictObject` (src/lib/api/v1/spec.ts) : tout champ
supplementaire fait echouer le message. On n'envoie QUE ce qui est specifie.
Corollaire du plan : sur Gary, « ca casse » est fiable, « ca marche » ne
garantit rien -- il est plus strict que la production.
"""

import json

import websocket

DEFAULT_URL = "ws://127.0.0.1:9600"

# Messages que le moteur peut nous envoyer (spec.ts, zNeuroMessage).
# Il n'y en a que trois.
INCOMING = ("startup", "action", "actions/reregister_all")


def action(name: str, description: str, schema=None) -> dict:
    """Construit une action a inscrire.

    ⚠ Le schema est OMIS quand il n'y en a pas -- JAMAIS `{}`. Un objet vide
    est un JSON Schema qui autorise tout : le modele le remplit de dechets.
    Et Randy ne se comporte pas pareil selon les deux formes (issue #51).
    """
    out = {"name": name, "description": description}
    if schema is not None:
        out["schema"] = schema
    return out


class Client:
    """Client du protocole. Synchrone, un seul fil, comme la sonde."""

    def __init__(self, url: str = DEFAULT_URL, game: str = "", verbose: bool = False) -> None:
        if not game:
            raise ValueError("le nom du jeu est obligatoire (champ `game`)")
        self.url = url
        self.game = game
        self.verbose = verbose
        self._ws = None

    # ------------------------------------------------------------ connexion

    def connect(self, timeout: float = 10.0) -> None:
        self._ws = websocket.create_connection(self.url, timeout=timeout)

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None

    # ------------------------------------------------------------ sortants

    def _send(self, command: str, data=None) -> None:
        if self._ws is None:
            raise ConnectionError("pas connecte")
        msg = {"command": command, "game": self.game}
        # `data` absent plutot que null : la spec le declare optionnel sur les
        # messages qui n'en portent pas, et un champ en trop est refuse.
        if data is not None:
            msg["data"] = data
        raw = json.dumps(msg)
        if self.verbose:
            print(f"  -> {raw}")
        self._ws.send(raw)

    def startup(self) -> None:
        """Annonce la session. A envoyer une fois, en premier."""
        self._send("startup")

    def register(self, actions) -> None:
        self._send("actions/register", {"actions": list(actions)})

    def unregister(self, names) -> None:
        self._send("actions/unregister", {"action_names": list(names)})

    def result(self, action_id: str, success: bool, message: str = None) -> None:
        """Accuse de VALIDITE de l'action -- pas son resultat.

        SPECIFICATION.md:168 : « It should usually be sent after validating the
        action parameters, BEFORE it is actually executed in-game. »

        ⚠ `success` est un DRAPEAU DE RE-ESSAI, pas une verite. La spec
        (ligne 188) le dit sans detour : si l'action a echoue mais qu'on ne
        veut PAS qu'elle soit rejouee, il faut mettre `true` quand meme et
        expliquer dans `message`. Le monde se raconte par `context()`.
        """
        data = {"id": action_id, "success": success}
        if message is not None:
            data["message"] = message
        self._send("action/result", data)

    def context(self, message: str, silent: bool = True) -> None:
        """Raconte le monde. `silent` est obligatoire dans le schema de Gary.

        ⚠ `silent: True` NOURRIT le contexte sans rien reclamer. Un rapport est
        un compte rendu, pas une sollicitation -- c'est pour ca qu'il est
        silencieux. Ce qui relance le tour, c'est `force()`, pas ceci.
        Mesure du 2026-08-10 : avec des rapports silencieux SEULS, aucune
        action n'arrive jamais.
        """
        self._send("context", {"message": message, "silent": silent})

    def force(self, query: str, action_names, state: str = None,
              ephemeral_context: bool = None) -> None:
        """Exige une action MAINTENANT, choisie parmi celles nommees.

        C'est la piece qui PILOTE le tour. Le rapport dit ce qui s'est passe ;
        ceci dit qu'il faut rejouer.

        `priority` est omis : la spec le donne a `low` par defaut, et un champ
        de moins est une facon de moins de heurter la validation stricte.

        ⚠ REGLE DURE : ne JAMAIS desinscrire une action engagee dans une force
        en attente. Course decrite dans l'issue #14, trois temoins independants.
        La brique n'ayant aucun recalcul d'affordance, elle ne desinscrit rien
        -- mais la regle doit voyager avec le code qui la rend possible.
        """
        data = {"query": query, "action_names": list(action_names)}
        if state is not None:
            data["state"] = state
        if ephemeral_context is not None:
            data["ephemeral_context"] = ephemeral_context
        self._send("actions/force", data)

    # ------------------------------------------------------------ entrant

    def receive(self, timeout: float = 1.0):
        """Rend le prochain message, ou None si rien n'est arrive a temps.

        None ne signale PAS une erreur : c'est le cas normal quand le moteur
        n'a rien a dire. La boucle appelante doit pouvoir tourner a vide.
        """
        if self._ws is None:
            raise ConnectionError("pas connecte")
        self._ws.settimeout(timeout)
        try:
            raw = self._ws.recv()
        except websocket.WebSocketTimeoutException:
            return None
        if not raw:
            return None
        if self.verbose:
            print(f"  <- {raw}")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            # La spec avertit : « data comes directly from Neuro, there is a
            # chance it might be malformed. » On refuse la trame, on ne meurt
            # pas -- une brique qui tombe sur un message tordu emporte la
            # mesure avec elle.
            print(f"  !! trame illisible, ignoree : {raw[:120]!r}")
            return None
        if not isinstance(msg, dict) or "command" not in msg:
            print(f"  !! trame sans commande, ignoree : {raw[:120]!r}")
            return None
        return msg
