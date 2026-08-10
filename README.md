# AOP -- Pokemon Rouge Feu

Une brique : elle sait lire l'etat du jeu et appuyer sur les boutons.
**Elle ne sait pas qui joue, et c'est voulu.**

> **Statut : etape 1-2.** La sonde et le marcheur manuel existent. Le protocole
> n'est pas encore branche.

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
- Python 3.11+ (bibliotheque standard uniquement).

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
