"""La table identifiant -> nom d'ATTAQUE, construite PAR ACQUISITION.

⚠⚠ AUCUNE LIGNE N'EST RECOPIEE D'UN DESASSEMBLAGE. Une table copiee rendrait
des noms ANGLAIS pour une cartouche francaise, et 354 attaques dont une partie
n'en verra jamais la plupart. Un nom faux se lit comme un nom vrai -- et il se
lirait dans une phrase adressee a quelqu'un.

Ce fichier est le frere de `objets_connus.py`, et il suit la meme doctrine.

=== COMMENT UNE LIGNE ENTRE ICI ===

    1. lire les attaques d'un Pokemon      -> un ensemble d'identifiants
    2. le jeu affiche « X veut apprendre Y »   <- l'humain lit le NOM
    3. l'humain accepte
    4. relire                              -> exactement UN identifiant neuf

⚠ L'etape 2 est ce qui rend la methode SURE : le jeu NOMME l'attaque a l'ecran
avant de l'ecrire en memoire. Le nom et l'identifiant sont donc lus dans la
meme minute, sur le meme evenement, par deux canaux independants.

⚠⚠ ET LE COMPTE NE SUFFIT PAS. Un Pokemon qui a deja quatre attaques REMPLACE
quand il en apprend une : le compte reste 4. C'est la DIFFERENCE D'ENSEMBLES
qui donne l'identifiant neuf -- et l'ensemble qui part donne, gratuitement,
lequel a ete remplace.

    Un COMPTE ne remplace jamais une IDENTITE.

=== POURQUOI LA CLE EST L'IDENTIFIANT, ET JAMAIS LE JEU ===

Comme pour les objets, les identifiants d'attaques semblent partages entre les
titres de la Generation 3. ⚠ HYPOTHESE non verifiee -- le nom de ce fichier ne
mentionne donc aucun jeu. Si elle tombe, on le saura par un nom qui ne
correspond pas a l'ecran, ce qui se voit tout de suite.

=== CE QUE CETTE TABLE N'EST PAS ===

⚠ Elle n'est pas un catalogue et n'a pas vocation a le devenir. Elle sert a
DIRE un nom a quelqu'un -- pas a raisonner sur des attaques. Neuf entrees
mesurees valent mieux que 354 recopiees dont on ignore laquelle est fausse.
"""

# ⚠ NOMS FRANCAIS, releves A L'ECRAN par l'humain, jamais traduits ni devines.
# Chaque entree porte la date ou elle a ete lue.
NOMS = {
    17: "CRU-AILE",       # 2026-09-06 -- « ... veut apprendre CRU-AILE. »
    # ⚠⚠ LES DEUX SUIVANTES VIENNENT D'UN SEUL EVENEMENT, et c'est neuf. La
    # sequence de remplacement nomme l'attaque APPRISE **et** celle qui est
    # OUBLIEE ; la difference d'ENSEMBLES en memoire donne les deux
    # identifiants du meme instant. Un apprentissage rend donc DEUX paires,
    # pas une -- releve du 2026-09-07 :
    #
    #     « ... apprend POUDRE DODO ! »                        apprises   [79]
    #     « ... ne sait plus comment utiliser DOUX PARFUM. »   remplacees [230]
    #
    # ⚠ Le nom du Pokemon est retire de ces citations A DESSEIN : le surnom
    # par defaut EST le nom d'espece, donc le citer reviendrait a poser un
    # extrait de la partie en cours dans un depot public.
    79: "POUDRE DODO",    # 2026-09-07
    230: "DOUX PARFUM",   # 2026-09-07
}

# ⚠ Les identifiants VUS en memoire mais jamais nommes a l'ecran. Ils ne sont
# pas des inconnues a combler : ils sont la preuve que cette table est
# incomplete, et ils empechent de la croire exhaustive.
#
# Releves le 2026-09-06 sur une equipe de quatre Pokemon :
NON_NOMMES = (10, 16, 18, 22, 28, 33, 39, 43, 45, 73, 98, 110, 145)


def nom(identifiant: int) -> str:
    """Le nom francais de cette attaque, ou une etiquette qui DIT qu'on ne sait pas.

    ⚠ Ne devine JAMAIS. Un identifiant absent rend « attaque <n> » -- une
    etiquette qu'un humain reconnait comme un trou, pas comme un nom.
    """
    return NOMS.get(identifiant, f"attaque {identifiant}")


def est_connue(identifiant: int) -> bool:
    """A-t-on releve le nom de cette attaque a l'ecran. PURE."""
    return identifiant in NOMS
