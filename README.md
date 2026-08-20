# AOP -- Pokemon Rouge Feu

Une brique : elle sait lire l'etat du jeu et appuyer sur les boutons.
**Elle ne sait pas qui joue, et c'est voulu.**

> **Statut : etape 3 + lecture memoire + etat de combat.** La sonde, le marcheur
> manuel et le client de protocole existent ; le protocole est branche et verifie
> contre un moteur reel. Depuis le 2026-08-13 la sonde lit la memoire arbitraire
> et les PV des deux combattants sont trouves ([`adresses.py`](adresses.py)).
> Depuis le 2026-08-15, [`etat.py`](etat.py) expose l'**etat de combat** en JSON,
> et les adresses sont **revalidees** a travers un redemarrage de mGBA et un
> changement de sauvegarde.

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

## Lire l'EQUIPE -- `equipe.py`

```
python equipe.py              # JSON
python equipe.py --lisible    # pour un humain
```

```
2 occupe(s), 2 en vie
  0  espece 7    N.9    15/27   pid 0xBBD4B988  33(32) 39(29) 145(28)
  1  espece 1    N.7    24/24   pid 0x1B1708A5  33(35) 45(40) 73(10)
  2  (vide)
```

Espece, niveau, PV, **les quatre attaques avec leurs PP**, les cinq statistiques
et le **PID** -- pour les six emplacements. Aucun OCR.

⚠⚠ **LE PID EST L'IDENTITE, ET RIEN D'AUTRE NE L'EST.** Un `u32` unique par
Pokemon. `pv_max` et le niveau se repetent d'un Pokemon a l'autre : un appelant
qui s'en sert pour reconnaitre « le meme combattant » se trompera un jour sans
le savoir. L'integration Pokemon officielle a fait ce chemin avant nous (son
issue #23).

⚠ **Les identifiants ne sont pas des noms.** `33` ne dit pas « Charge ». La
table espece/attaque est de la **donnee de jeu** et n'est pas ici -- ce module
rend ce qu'il LIT, il ne traduit pas.

### Le chiffrement, et il se franchit sans secret

Les 48 octets qui portent l'espece, les attaques et les PP sont chiffres :

```
cle = personality XOR otId       (deux u32, lisibles en clair aux offsets 0 et 4)
```

Chaque `u32` du bloc est XORe par cette cle, puis les quatre sous-blocs de 12
octets sont **melanges** selon `personality % 24`.

⚠ **La signature qui met sur la voie** : dans un dump brut, un motif se repete
tous les QUATRE octets. C'est la marque d'un XOR par une cle `u32`, pas du bruit.
⚠⚠ **Se tromper d'ordre de melange rend des nombres PLAUSIBLES et faux** -- donc
pire qu'une erreur bruyante.

### ⚠⚠⚠ Trois absences a ne pas confondre

```
personality == 0       l'emplacement est VIDE
dump rend None         la sonde a REFUSE -- c'est une panne
identifiant d'attaque 0  l'emplacement d'attaque est vide, pas une attaque « 0 »
```

Les trois produisent la meme absence de donnees et appellent trois gestes
differents. Une equipe **amputee** par un refus de sonde, presentee comme
complete, se lit exactement comme une equipe de deux.

⚠ Et « occupe » n'est pas « en vie » : un Pokemon K.O. reste dans l'equipe. Les
compter ensemble ferait disparaitre un membre au moment ou il tombe.

### ⚠⚠ L'ERREUR DE LECTURE QUI A COUTE UNE FAUSSE CONCLUSION

Le premier dechiffrement n'a porte que sur **l'emplacement 0** -- le Pokemon
ACTIF. Une conclusion en a ete tiree sur le **starter**. L'emplacement 1 portait
une autre espece, presente depuis le debut.

> **Le Pokemon actif n'est pas le starter.** Lire un emplacement et conclure sur
> l'equipe, c'est fabriquer une troncature puis la lire comme un fait.

➜ Six emplacements coutent six dumps. Moins cher qu'une retractation.

### ⚠ Ce que ce module ne fait PAS

Il ne dit pas si on est **en combat**. La fiche adverse survit a la fin d'un
combat, donc aucune lecture memoire ne distingue « en combat » de « le combat
vient de finir ». C'est le seul etat qui demande encore de regarder l'ecran.

Il ne rend pas non plus ce que le jeu **ECRIT**. Cette prose n'est nulle part en
memoire -- l'oeil cesse d'etre un verificateur d'etat, il reste le canal du
recit.

## Lire l'etat d'un combat -- `etat.py`

Une lecture, une reponse JSON, et on oublie. C'est l'**ETAT**, la premiere des
trois choses qu'un pont expose ; les ACTIONS et le RESULTAT n'en sont pas.

```
python etat.py              # JSON sur la sortie standard
python etat.py --lisible    # pour un humain
```

```json
{"sonde": "ok",
 "joueur":  {"niveau": 6, "pv": 21, "pv_max": 21, "plausible": true, "pourquoi": ""},
 "adverse": {"niveau": 3, "pv": 14, "pv_max": 14, "plausible": true, "pourquoi": ""}}
```

⚠⚠ **Il ne dit JAMAIS « on est en combat »,** parce qu'il ne peut pas le savoir :
la fiche adverse **survit a la fin du combat**, et une fiche perimee se lit
exactement comme une fiche vivante. Il rend un verdict de **plausibilite** --
« ces octets decrivent un combattant » -- et l'appelant tranche avec ce qu'il
voit par ailleurs.

⚠ **Le controle de fraicheur est du cote de l'appelant, et il est gratuit** : le
niveau figure ici ET sur l'ecran du jeu. S'ils divergent, les octets decrivent un
autre combat.

⚠ **`plausible: false` n'est pas une panne.** Une lecture prise pendant un fondu
de transition rend des structures vides. Ce module ne relit pas de lui-meme -- il
declare, et laisse l'appelant decider d'attendre, parce qu'attendre ici bloquerait
sa boucle.

⚠ **L'echec de connexion sort en JSON lui aussi** (code 2). Un appelant qui parse
la sortie n'a pas a distinguer « du JSON » d'« un message d'erreur » : deux formes
obligeraient a deux chemins de lecture, et c'est le second qu'on oublie d'ecrire.

## Appuyer sur un bouton -- `presser.py`

```
python presser.py A
python presser.py DOWN --frames 6
```

```json
{"presse": true, "touche": "DOWN", "position_apres": {"x": 12, "y": 37, "g": 3, "n": 19},
 "note": "la position n'a aucun sens en menu -- relire l'ecran"}
```

⚠⚠ **`presse: true` veut dire « la sonde a accepte la pression », PAS « ca a
marche ».** `position_apres` est la position du PERSONNAGE : utile pour marcher,
sans aucun sens dans un menu ou elle ne bouge pas. **Un appelant qui veut savoir
ce que la pression a fait doit RELIRE l'ecran.**

⚠ Une touche inconnue est refusee **avant** d'ouvrir la connexion : c'est une
faute d'appelant, pas une panne de sonde.

### ⚠⚠⚠ Trois etats, jamais deux -- une sonde morte se lit comme un mur

Mesure du 2026-08-15. La sonde est morte en pleine sequence de pressions (voir
« Pieges connus »), et le client a alors observe, a chaque appel, que **le
curseur n'avait pas bouge** -- exactement ce qu'il observerait devant une butee.

> Un navigateur qui ne distingue pas les deux conclut « je suis arrive » et
> valide le mauvais choix, en silence.

Un client qui presse doit donc separer :

```
deplacement   la pression a porte, l'ecran a change
butee         la pression a porte, l'ecran n'a pas change
echec         la pression n'a PAS eu lieu -- rien n'est conclu
```

⚠ **Et le cout est structurel** : presser plusieurs fois par tour exerce
beaucoup plus fort la fragilite decrite plus bas qu'une simple lecture. Chaque
mort coute un redemarrage de mGBA. **Le correctif de fond est cote sonde.**

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
| `keys` | `ok humain=<n> moi=<n> dernier=<masque> frame=<n>` |
| (erreur) | `err <message>` |

### ⚠⚠ `keys` -- la sonde voit les appuis de l'humain

Un changement d'ecran est un **effet** ; un appui est la **cause**. Surveiller la
cause dit **quand regarder**, a la frame pres -- ce qu'aucune comparaison de
texte ne peut donner. Mesure : les messages de resultat du jeu durent ~2 s, donc
un scrutin toutes les 3 s en rate la moitie, seuil parfait ou non.

⚠ **Comment c'est possible** : `emu:setKeys` ecrit dans le meme etat que le
clavier. Verifie dans la source de mGBA -- l'interface Qt appelle
`core->setKeys(core, activeKeys)` avec les touches actives
(`src/platform/qt/CoreController.cpp`), et `emu:getKeys()` relit ce meme
`gba->keysActive`.

⚠⚠⚠ **`humain` et `moi` sont comptes SEPAREMENT.** La sonde voit ses propres
pressions -- celles qu'un client envoie via `press` -- exactement comme celles
d'un humain. Sans cette separation, un navigateur automatique se declencherait
**sur lui-meme, en boucle**.

⚠ **Semantique de VIDANGE** : chaque appui n'est rendu qu'une fois ; lire
consomme. Un compteur cumulatif obligerait l'appelant a garder l'etat precedent
pour calculer une difference -- et c'est exactement l'endroit ou l'on oublie de
le faire.

⚠ **Front montant seulement** : une touche MAINTENUE compte une fois, pas
soixante fois par seconde.

⚠ **Ce que ce canal ne dit PAS** : tout ne vient pas d'un appui. L'adversaire
agit, un niveau monte, une animation se joue. Il repond a « quand regarder »,
jamais a « tout ce qui arrive ».

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
- ✅ **La sonde survit desormais a un client qui abandonne** (correctif du
  2026-08-16). Le defaut etait mesure -- elle tombait entre 20 et 25 abandons --
  et venait de deux fuites sur le chemin d'ERREUR : la case du client etait mise
  a nil **sans que le socket soit ferme**, et `#clients + 1` sur une table a
  trous pouvait ecraser une entree vivante. Verifie apres correctif : **60
  abandons, toujours vivante**, puis confirme en production sur une panne non
  planifiee.
- ⚠⚠⚠ **UNE COMMANDE QUI PLANTE SE LIT COMME UNE SONDE MORTE.** Une erreur Lua
  dans un gestionnaire tue le rappel : aucune reponse ne part, et le client voit
  **un delai depasse** -- exactement ce qu'il verrait devant une sonde morte.
  Mesure du 2026-08-18 : une variable declaree APRES la fonction qui la lit
  (donc `nil`, donc `string.format` qui leve) a produit ce symptome.
  ➜ **Le diagnostic est gratuit, il suffit de le connaitre :**

  ```
  delai depasse, PUIS `ping` repond  ->  c'est la COMMANDE qui a plante
  delai depasse, PUIS `ping` muet    ->  c'est la SONDE qui est morte
  ```

  Un seul `ping` separe les deux, et elles ne se reparent pas au meme endroit.
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
