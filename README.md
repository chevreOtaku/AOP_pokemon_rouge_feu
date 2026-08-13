# AOP -- Pokemon Rouge Feu

Une brique : elle sait lire l'etat du jeu et appuyer sur les boutons.
**Elle ne sait pas qui joue, et c'est voulu.**

> **Statut : etape 3 + lecture memoire.** La sonde, le marcheur manuel et le
> client de protocole existent ; le protocole est branche et verifie contre un
> moteur reel. Depuis le 2026-08-13 la sonde lit aussi la memoire arbitraire, et
> les PV des deux combattants sont trouves ([`adresses.py`](adresses.py)).

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

### Format de la trace

`traces/walk_<horodatage>.jsonl` -- une ligne JSON par evenement, champ `type` :

| `type` | quand | ce qu'il porte |
|---|---|---|
| `session` | **premiere ligne**, une seule | pilote declare, jeu, URL, mode de relance, depart, cible, et tous les seuils |
| `action` | une par action executee | action, `pilote`, avant, apres, `dx`/`dy`, distances, `moved` |

⚠ **Un lecteur doit filtrer sur `type`.** Une trace anterieure au 2026-08-11 n'a ni
en-tete ni champ `type` : la traiter comme les nouvelles compterait l'en-tete pour une
action.

**Pourquoi un en-tete** : sans lui, deux traces produites dans des conditions opposees
sont indiscernables -- celle d'un pilote aleatoire et celle d'un modele se ressemblent
trait pour trait. Un nombre sans ses conditions n'est pas une mesure.

**Pourquoi `pilote` sur CHAQUE action** et pas seulement dans l'en-tete : le jour ou un
humain prend le relais sur une portion du trajet, une trace sans ce champ melangerait les
deux et **tous les agregats deviendraient faux sans que rien ne le signale**. Il ne coute
rien aujourd'hui -- une seule source agit -- et il evite d'avoir a jeter des mesures plus
tard.

⚠ **`--pilote` est une etiquette DECLAREE, pas une mesure.** La brique ne voit que des
messages de protocole ; elle ne peut pas savoir quel moteur les produit. Une etiquette
declaree peut mentir -- mais une trace sans etiquette ne peut meme pas etre comparee.

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

Aucun contexte accumule, aucun etat conserve entre deux tours. Elle envoie des
differentiels et oublie. L'accuse de session du moteur porte un `characterId` :
**il n'est pas lu** -- un pont sans etat rend une mesure reproductible, un pont
qui se souvient rend une mesure qui depend de son passe.

## Chercher une adresse -- `chasse.py`

**Aucune carte memoire n'existe pour la version FR.** Chaque adresse se trouve
par scan et correlation. `chasse.py` ne cherche rien tout seul : il capture la
memoire a des instants que **vous** choisissez, et reduit les candidats en
comparant ces instants.

```
python chasse.py verifier                    # l'auto-test, apres CHAQUE rechargement du Lua
python chasse.py capture <etiquette>         # EWRAM + IWRAM -> chasse/<etiquette>.bin
python chasse.py diff  <a> <b>  [--taille 1|2|4] [--parmi c.txt] [--sortie c.txt]
python chasse.py egal  <a> <b>  [...]        # l'inverse : ce qui n'a PAS bouge
python chasse.py valeur <capture> --egale 22 # les adresses portant une valeur connue
python chasse.py montrer <captures...> --adresses 0x... --parmi c.txt
python chasse.py lire 0x020242DA --taille 2  # en direct, sans capture
```

### ⚠⚠ Chercher une SIGNATURE, pas un nombre

C'est la lecon la plus rentable de la premiere chasse, et elle est generale.

| approche | resultat mesure |
|---|---|
| chercher **un nombre** (les PV lus a l'ecran) | **40 adresses** dans une seule capture, la bonne noyee |
| chercher une **forme** -- `<niveau 1..100> <0xFF> <PV> <max>` + 5 stats plausibles | **une paire par equipe et par capture** |

⚠ Et la comparaison d'etats (« ce qui change entre en-combat et hors-combat »)
**ne converge pas** : 53 240 -> 49 293 candidats en trois croisements. La raison
est structurelle -- *deux captures ne different jamais par UNE chose*, mais par
une dizaine a la fois.

Les adresses trouvees, avec la mesure qui les etablit, vivent dans
[`adresses.py`](adresses.py). Les nombres et le recit complet sont dans les
notes de terrain gaming (`mesures/`).

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
| `version` | `ok <version de la sonde>` |
| `state` | `ok x=<n> y=<n> g=<n> n=<n>` |
| `press <KEY> [frames]` | `ok x=<n> y=<n> g=<n> n=<n>` -- l'etat **apres stabilisation** |
| `read8｜read16｜read32 <addr>` | `ok <valeur decimale>` |
| `dump <addr> <len>` | `ok <hexa majuscule>` -- `len` <= 1024 |
| `blocks <addr> <len> [taille]` | `ok <une somme par bloc>` -- `len` <= 262144 |
| (erreur) | `err <message>` |

`KEY` : `A B SELECT START RIGHT LEFT UP DOWN R L`
Les adresses acceptent `0x02024082` comme `33702018`.

⚠ **`version` n'est pas decoratif.** Charger un script pendant qu'un autre tient
deja le port ne remplace rien : le nouveau echoue a s'installer (port fixe, echec
bruyant -- voir plus haut) et **l'ancien continue de repondre**. Symptome :
`ping` marche, les commandes recentes sont « inconnues ». Sans numero de version,
c'est indiscernable d'une faute de frappe.

**Pourquoi la reponse arrive apres coup** : un pas prend une quinzaine de frames.
Lire immediatement apres le relachement rendrait une position prise au milieu du
mouvement, et l'avant/apres ne voudrait plus rien dire.

## Pieges connus

- ⚠⚠ **NE JAMAIS METTRE L'EMULATEUR EN PAUSE POUR LIRE.** mGBA suspend les
  rappels du script : la sonde cesse de repondre, le client expire, et **elle ne
  s'en remet pas** -- il faut relancer mGBA. Mesure du 2026-08-13 : capture sans
  pause reussie · capture en pause expiree · capture suivante refusee.
  Pour un moment tranquille, prendre le menu d'attaques d'un combat : le jeu
  tourne, mais rien ne s'anime.
- ⚠⚠ **La sonde ne survit pas a un client qui abandonne** -- defaut connu, non
  corrige. Apres un delai depasse cote client, le port cesse d'accepter des
  connexions et seul un redemarrage de mGBA la remet en service. Elle devrait
  se remettre a ecouter ; elle ne le fait pas.
- **Charger un script pendant qu'un autre tient le port ne remplace rien** (voir
  `version` plus haut).
- **Un dialogue ouvert avale les pas.** Ils ne changent rien. Le fermer par `A`
  avant de marcher.
- **Un mur se lit comme une coordonnee inchangee** apres l'appui. C'est aussi la
  signature d'un pas avale : les deux se ressemblent, seul le contexte les
  separe.
- **`mapGroup == 255`** signale une transition de porte : l'etat est instable, il
  ne faut pas conclure dessus.
- ⚠ **Une capture prise pendant une TRANSITION rend des zeros qui ressemblent a
  une absence.** Une capture du 2026-08-13, prise pendant le fondu de fin de
  combat, ne contenait aucune fiche de Pokemon ; les memes adresses, quelques
  secondes plus tard, les portaient intactes. **Un zero se verifie a un second
  instant avant d'etre cru.**

## Licence

MIT -- voir [LICENSE](LICENSE).
