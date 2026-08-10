# AOP -- Pokemon Rouge Feu

Une brique : elle sait lire l'etat du jeu et appuyer sur les boutons.
**Elle ne sait pas qui joue, et c'est voulu.**

> **Statut : etape 3.** La sonde, le marcheur manuel et le client de protocole
> existent. Le protocole est branche et verifie contre un moteur reel.

---

## Ce que c'est

Un pont entre **Pokemon Version Rouge Feu (FR)** tournant dans **mGBA** et un
programme exterieur. Deux moities :

```
   programme exterieur (Python)          mGBA + lua/probe.lua
        client TCP  ─────────────────►   serveur TCP, port 9601
                                          │
                                          ├─ emu:read*    (position en RAM)
                                          └─ emu:setKeys  (les touches)
```

**Aucune injection de touches au niveau du systeme.** L'entree passe *dans*
l'emulateur, donc la fenetre n'a pas besoin d'etre au premier plan et un
`alt-tab` ne detourne rien.

## Prerequis

- **mGBA 0.10.5** ou plus recent -- une **release taguee**, pas un instantane de
  developpement. Un socle qui bouge sous la mesure ne sert a rien.
- Une cartouche **Pokemon Version Rouge Feu (France)**.
- Python 3.10+.
  - `probe.py` et `walk.py` : **bibliotheque standard seule**.
  - `brick.py` : une seule dependance, `pip install -r requirements.txt`.

## Demarrer

**1. Charger la sonde.** Dans mGBA : `Outils > Scripting`, puis coller le
contenu de `lua/probe.lua` (ou `File > Load`). La console doit afficher :

```
Sonde Rouge Feu FR -- ecoute sur le port 9601
```

Si le port est occupe, le script **echoue bruyamment et n'ecoute pas**. C'est
volontaire : un port qui se decale tout seul, c'est un client qui se connecte
ailleurs -- ou nulle part -- sans que rien ne le dise.

**2. Verifier les yeux.** C'est l'etape que l'on ne saute pas :

```
python walk.py
```

Puis marcher avec `z q s d` et regarder les coordonnees. **Elles doivent bouger
dans le bon sens, et d'un pas a la fois.**

**3. Brancher un moteur.** Un moteur ecoute en WebSocket ; la brique s'y
connecte (c'est le jeu qui est CLIENT, le moteur qui est SERVEUR).

```
python brick.py                      # sans cible : deltas seuls
python brick.py --target 12,8        # cible sur la carte courante
python brick.py --verbose            # montre les trames envoyees et recues
```

Chaque action produit une ligne dans `traces/walk_<horodatage>.jsonl`.

### L'ordre des pilotes n'est pas negociable

**aleatoire -> manuel deterministe -> LLM.** Sauter au LLM rend la mesure
ininterpretable : on ne peut plus distinguer *« le modele erre »* de *« mon
capteur de position est faux »*.

Le pilote aleatoire n'est pas une formalite, c'est le **plancher** : il donne
le ratio qu'on obtient sans rien comprendre au jeu, et tout chiffre ulterieur
se lit contre lui.

> **Les nombres ne sont pas dans ce fichier.** Baselines, montages et versions
> vivent dans les notes de terrain gaming (`mesures/`). Un README dit comment
> on s'en sert ; une mesure est un resultat a une date, et les deux ne
> vieillissent pas a la meme vitesse.

### La convention de resultat

C'est la piece que la brique existe pour porter, et qu'aucun SDK ne fournit.

| message | ce qu'il dit | quand |
|---|---|---|
| `action/result` | l'action est **VALIDE** | **immediatement, AVANT execution** |
| `context` | ce que le monde a fait -- etat avant et apres | apres l'execution |

Deux consequences qui se lisent mal si on ne les ecrit pas :

1. **`success` n'est pas une verite, c'est un drapeau de re-essai.** La
   specification est explicite : si l'action a echoue mais qu'on ne veut *pas*
   qu'elle soit rejouee, il faut envoyer `true` et expliquer dans `message`.
2. **La brique ne dit jamais « j'ai reussi ».** Elle constate un delta ; juger
   si c'etait un succes suppose de connaitre l'intention, et la brique ne la
   connait pas.

⚠ **Un delta nul n'est jamais rapporte comme « un mur ».** Il porte deja deux
sens -- un mur, ou un pas avale par un dialogue -- et rien dans la brique ne
permet de les separer. Elle ecrit *« the position did not change »*.

### ⚠ Le rapport ne pilote pas -- c'est `actions/force` qui pilote

Un `context` en `silent: true` **nourrit** le contexte sans rien reclamer.
C'est ce qu'un rapport doit faire : c'est un compte rendu, pas une question.
Mais alors **rien ne relance le tour suivant**, et la boucle s'arrete au
premier pas.

Mesure a l'appui, trois configurations comparees, une seule variable changee
a la fois : un rapport silencieux seul ne produit **aucune** action ; le meme
rapport suivi d'une force en produit en continu. Les chiffres sont dans les
notes de terrain gaming.

➜ Defaut : **`--drive force`**. Le rapport reste silencieux, et
`actions/force` demande explicitement une direction a chaque tour. Chaque
role a son message.

`--drive context` garde l'autre voie : le rapport porte les deux roles a la
fois. Plus simple, mais il invite aussi la narration -- prive d'affordances,
un modele ne se tait pas, il raconte.

⚠ **Sous une force, le « Chance to skip acting » d'un moteur aleatoire ne
s'applique pas** (« when prompted to act but *not forced* »). Le meme reglage
n'a donc pas le meme effet selon `--drive`.

### Quand une session s'arrete

| condition | ce qui la declenche |
|---|---|
| **arrivee** | la distance a la cible atteint 0 |
| **blocage** | `--max-stuck` tours CONSECUTIFS sans progres (defaut 5) |
| **errance** | plus de `--turn-budget` x distance de depart tours (defaut 3x) |
| interruption | `Ctrl-C` |

⚠ **Le blocage n'attrape PAS l'errance, et c'est pour ca qu'il en faut deux.**
Une marche au hasard ne se coince jamais : elle tourne. Verifie sur une
session reelle, ou la pire serie sans progres est restee sous le seuil de
blocage du debut a la fin -- rien ne l'aurait arretee.

Le budget est un **multiple de la distance de depart**, jamais une constante :
un nombre fixe mesurerait la longueur du trajet et pas le pilote.

⚠ Un progres **nul ou negatif** compte comme un tour sans progres : le yo-yo
est un echec au meme titre que le mur. Un pas dans le bon sens remet le
compteur a zero.

⚠ **`--max-stuck` n'est pas un budget de tours.** Un appui = une case, donc
une cible a N cases demande au moins N actions. Confondre les deux ferait
mesurer l'arithmetique et pas le deplacement.

### Ce que la brique ne fait pas, et ne fera pas ici

Aucun contexte accumule, aucune memoire, aucune identite. Elle envoie des
differentiels et oublie. L'accuse de session du moteur porte un `characterId` :
**il n'est pas lu.** La brique ne sait pas qui joue.

## Comment la position est lue

| | |
|---|---|
| pointeur IWRAM | `0x03004F58` |
| x | `u16 @ +0` |
| y | `u16 @ +2` |
| mapGroup | `u8 @ +4` (**255 = transition de porte**) |
| mapNum | `u8 @ +5` |

**Le pointeur est relu a chaque lecture** et l'adresse resolue n'est jamais mise
en cache : Rouge Feu **demenage ses SaveBlocks** en cours de partie.

> **Ce pointeur a ete trouve par scan et correlation, pas dans une
> documentation.** Aucune documentation FR n'existait. La methode : scanner
> l'IWRAM pour tout mot de 32 bits pointant dans l'EWRAM, puis marcher un nombre
> connu de pas et retenir le candidat dont la bonne coordonnee bouge d'autant.

⚠ **Il se verifie, il ne se suppose pas.** Une adresse valable sur une version du
jeu ne l'est pas forcement sur une autre -- le script `pokemon.lua` livre avec
mGBA, par exemple, ne reconnait **aucune** cartouche non anglophone.

## Protocole de la sonde

Une ligne par requete, une ligne par reponse.

| requete | reponse |
|---|---|
| `ping` | `ok pong` |
| `state` | `ok x=<n> y=<n> g=<n> n=<n>` |
| `press <KEY> [frames]` | `ok x=<n> y=<n> g=<n> n=<n>` -- l'etat **apres stabilisation** |
| (erreur) | `err <message>` |

`KEY` : `A B SELECT START RIGHT LEFT UP DOWN R L`

**Pourquoi la reponse arrive apres coup** : un pas prend une quinzaine de frames.
Lire immediatement apres le relachement rendrait une position prise au milieu du
mouvement, et l'avant/apres ne voudrait plus rien dire.

## Pieges connus

- **Un dialogue ouvert avale les pas.** Ils ne changent rien. Le fermer par `A`
  avant de marcher.
- **Un mur se lit comme une coordonnee inchangee** apres l'appui. C'est aussi la
  signature d'un pas avale : les deux se ressemblent, seul le contexte les
  separe.
- **`mapGroup == 255`** signale une transition de porte : l'etat est instable, il
  ne faut pas conclure dessus.

## Licence

MIT -- voir [LICENSE](LICENSE).
