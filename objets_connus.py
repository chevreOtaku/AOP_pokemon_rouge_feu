"""La table identifiant -> nom, construite PAR ACQUISITION.

⚠⚠ AUCUNE LIGNE N'EST RECOPIEE D'UN DESASSEMBLAGE. Une table copiee rendrait
`ITEM_POTION` -- des noms ANGLAIS pour une cartouche francaise -- et 377 objets
dont la partie n'en a jamais vu 350. Un nom faux se lit comme un nom vrai.

=== COMMENT UNE LIGNE ENTRE ICI ===

    1. lire le sac en memoire        -> un ensemble d'identifiants
    2. l'humain acquiert UN objet
    3. relire                        -> exactement UN identifiant neuf
    4. l'humain le nomme, en lisant SON ecran

Independant de l'ordre, independant du defilement, auto-verifiant : si deux
identifiants changent, on ne conclut pas, on recommence.

⚠ UNE METHODE PAR POSITION A ETE REFUTEE le 2026-09-01. Apparier la ligne de
l'ecran a l'emplacement de la RAM semble marcher -- et casse des que la poche
depasse la fenetre visible, parce que la liste DEFILE. Elle casse aussi entre
deux parties, l'ordre du sac n'etant pas canonique.

    La position n'est pas une identite. L'identifiant en est une.

=== POURQUOI LA CLE EST L'IDENTIFIANT, ET JAMAIS LE JEU ===

Les identifiants d'objets semblent partages entre les titres de la Generation 3
-- Rouge Feu, Vert Feuille, Rubis, Saphir, Emeraude. ⚠ HYPOTHESE non verifiee.
Si elle tient, cette table sert aussi ailleurs ; c'est pourquoi son nom ne
mentionne aucun jeu. Si elle tombe, il faudra la scinder -- et on le saura par
un nom qui ne correspond pas a l'ecran, ce qui se voit tout de suite.
"""

# ⚠ NOMS FRANCAIS, releves a l'ecran par l'humain, jamais traduits ni devines.
# Chaque entree porte la date ou elle a ete lue.
NOMS = {
    4: "POKe BALL",       # 2026-09-01
    13: "POTION",         # 2026-09-01
    14: "ANTIDOTE",       # 2026-09-02
    18: "ANTI-PARA",      # 2026-09-02
    24: "RAPPEL",         # 2026-09-02
    36: "ELIXIR",         # 2026-09-02
    68: "SUPER BONBON",   # 2026-09-01
    366: "TV ABC",        # 2026-09-01
}

# ⚠ VU EN MEMOIRE, JAMAIS A L'ECRAN. L'identifiant 1 occupe un emplacement de la
# poche Pokeballs (x99) et personne n'a regarde cet ecran. On ne le nomme pas :
# une supposition inscrite ici deviendrait un fait au prochain relecteur.
NON_NOMMES = (1,)


def nom(identifiant: int) -> str:
    """Le nom si on le connait, sinon une etiquette qui DIT qu'on ne sait pas.

    ⚠ On ne rend jamais une chaine vide ni le seul nombre : « objet 24 » et
    « RAPPEL » se lisent pareil dans une phrase, et l'un des deux est un aveu.
    """
    connu = NOMS.get(identifiant)
    return connu if connu else f"objet {identifiant} (non nomme)"
