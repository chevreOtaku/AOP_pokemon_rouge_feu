"""Les verrous du coeur de la veille -- sans emulateur, sans partie.

    python -m pytest test_veilleur.py -q

⚠ `differences()` est PURE : elle prend deux releves et rend des evenements.

⚠⚠⚠ AUCUN CHIFFRE ICI NE VIENT D'UNE PARTIE. Les identifiants, especes et
niveaux sont FABRIQUES et manifestement hors domaine (especes 101-103,
attaques 201-205, PID 0xAAAA000x). C'est deliberé et ce n'est pas du
scrupule : un depot public ne porte aucun extrait de sauvegarde, MEME comme
fixture -- et illustrer une table avec les valeurs qu'on a sous la main est
exactement comme une fuite de onze jours est nee sur ce chantier.

Ce que les cas exercent, ce sont des RELATIONS (l'espece change a PID
constant, un identifiant d'attaque en remplace un autre), et une relation
n'a pas besoin des vraies valeurs pour etre vraie.

Chaque cas vient d'un defaut MESURE sur ce chantier, et le dit.
"""

from veilleur import differences


def _releve(**champs):
    """Un releve complet, tous les champs lus, sauf ce qu'on precise."""
    base = {"drapeau": 4, "position": (1, 1, 3, 1), "xp": 1000, "argent": 500,
            "equipe": [], "adverse": None, "image": 12345}
    base.update(champs)
    return base


def test_le_premier_releve_n_est_pas_un_changement():
    """⚠ Sans releve precedent, tout aurait l'air neuf. Une veille qui emet
    six evenements a l'ouverture noie ceux qui comptent."""
    assert differences({}, _releve()) == []


def test_une_lecture_ILLISIBLE_ne_produit_jamais_d_evenement():
    """⚠⚠ « je n'ai pas su lire » n'est pas « ca a change ». Les confondre
    ferait naitre une evolution a chaque coupure de socket -- et le canal
    coupe, c'est mesure."""
    plein = _releve(xp=1000, equipe=[[1, 101, 5, [10]]])
    creux = _releve(xp=None, equipe=None, drapeau=None, argent=None,
                    position=None)
    assert differences(plein, creux) == []
    assert differences(creux, plein) == []


def test_une_hausse_d_xp_est_portee_PAR_POKEMON():
    """⚠⚠⚠ L'experience est un cumul PAR POKEMON -- c'est ce qui rend une
    baisse impossible (D-W). Une SOMME D'EQUIPE n'a pas cette propriete.

    Un rang porte `[pid, espece, niveau, attaques, experience]`.
    """
    avant = _releve(equipe=[[1, 101, 5, [10], 1000]])
    apres = _releve(equipe=[[1, 101, 5, [10], 1348]])
    vus = differences(avant, apres)
    assert {"quoi": "xp", "pid": 1, "de": 1000, "a": 1348, "delta": 348} in vus


def test_un_POKEMON_QUI_SORT_de_l_equipe_ne_fait_PAS_baisser_l_xp():
    """⚠⚠⚠ LE FAUX POSITIF MESURE LE 2026-09-07, EN DIRECT.

    La version d'avant sommait l'experience des six emplacements. Sortir un
    Pokemon faisait chuter cette somme, ce qui declenchait « l'experience a
    BAISSE, donc chargement de sauvegarde » -- puis une fausse ARETE quand il
    revenait, une seconde plus tard.

        Une agregation peut detruire la propriete sur laquelle la regle repose.

    Ici : une sortie se nomme « sortie », et RIEN d'autre.
    """
    avant = _releve(equipe=[[1, 101, 5, [10], 1000],
                            [2, 102, 50, [20], 900000]])
    apres = _releve(equipe=[[1, 101, 5, [10], 1000]])
    vus = differences(avant, apres)

    assert [e["quoi"] for e in vus] == ["sortie"]
    assert not [e for e in vus if e["quoi"] == "xp"]


def test_une_baisse_d_xp_A_PID_CONSTANT_reste_un_signal():
    """⚠ La regle de D-W survit -- elle s'applique la ou elle est vraie : un
    Pokemon present AVANT et APRES ne peut pas avoir moins d'experience."""
    avant = _releve(equipe=[[1, 101, 5, [10], 1348]])
    apres = _releve(equipe=[[1, 101, 5, [10], 1000]])
    vus = differences(avant, apres)
    assert vus[0]["quoi"] == "xp" and vus[0]["delta"] == -348


def test_une_evolution_se_voit_a_PID_CONSTANT_et_le_niveau_NE_BOUGE_PAS():
    """⚠⚠⚠ Mesure du 2026-09-06, deux fois : l'espece change et le NIVEAU NE
    BOUGE PAS. (Les valeurs relevees vivent dans les notes privees ; elles ne
    sont pas necessaires ici, et une partie reelle n'entre pas dans ce depot.)

    Un detecteur qui exigerait « le niveau change ET l'espece change »
    raterait les DEUX. Ce test echoue si quelqu'un les recouple.
    """
    avant = _releve(equipe=[[0xAAAA0001, 101, 30, [10, 16]]])
    apres = _releve(equipe=[[0xAAAA0001, 102, 30, [10, 16]]])
    vus = differences(avant, apres)

    assert len(vus) == 1
    assert vus[0]["quoi"] == "evolution"
    assert (vus[0]["de"], vus[0]["a"]) == (101, 102)
    assert not [e for e in vus if e["quoi"] == "niveau"]


def test_une_capacite_APPRISE_sur_quatre_attaques_ne_change_pas_le_COMPTE():
    """⚠⚠⚠ LE PIEGE QUI A COUTE UNE MESURE ENTIERE. Un Pokemon qui a deja
    quatre attaques REMPLACE quand il apprend : 4 avant, 4 apres.

        Un COMPTE ne remplace jamais une IDENTITE.

    Le veilleur du 06/09 comptait, et il a rate l'evenement que
    `delta_combat` voyait -- lui compare des ENSEMBLES.
    """
    avant = _releve(equipe=[[0xAAAA0002, 103, 20, [201, 202, 203, 204]]])
    apres = _releve(equipe=[[0xAAAA0002, 103, 20, [201, 202, 205, 204]]])
    vus = differences(avant, apres)

    assert len(avant["equipe"][0][3]) == len(apres["equipe"][0][3]) == 4
    assert len(vus) == 1
    assert vus[0]["quoi"] == "capacite"
    assert vus[0]["apprises"] == [205]
    assert vus[0]["remplacees"] == [203]


def test_un_ordre_d_attaques_different_n_est_PAS_un_apprentissage():
    """⚠ Le jeu peut reordonner ; l'ENSEMBLE est ce qui identifie. Comparer
    des listes brutes emettrait une capacite fantome."""
    avant = _releve(equipe=[[1, 101, 5, [10, 20, 30]]])
    apres = _releve(equipe=[[1, 101, 5, [30, 10, 20]]])
    assert differences(avant, apres) == []


def test_une_entree_et_une_sortie_d_equipe_se_nomment():
    """Une CAPTURE fait apparaitre un PID ; un depot en fait disparaitre un.
    ⚠ Aucun des deux ne se deduit du COMPTE : une capture qui remplace un
    Pokemon depose laisserait le compte inchange."""
    avant = _releve(equipe=[[1, 101, 5, [10]]])
    apres = _releve(equipe=[[2, 102, 3, [33]]])
    quoi = sorted(e["quoi"] for e in differences(avant, apres))
    assert quoi == ["entree", "sortie"]


def test_le_drapeau_dit_le_bit_DRESSEUR_avec_sa_valeur():
    """0x4 sauvage -> 0xC dresseur, verifie par VARIATION le 06/09.
    ⚠ Le champ `dresseur` accompagne la valeur, il ne la remplace pas : le
    drapeau est PERIME hors combat et le lecteur doit voir les deux."""
    vus = differences(_releve(drapeau=0x4), _releve(drapeau=0xC))
    assert len(vus) == 1
    assert vus[0]["dresseur"] is True
    assert (vus[0]["de"], vus[0]["a"]) == (0x4, 0xC)


def test_un_compteur_d_images_qui_RECULE_est_une_rupture():
    """⚠⚠⚠ Un compteur d'images ne recule jamais dans une partie qui tourne.

    C'est une IMPOSSIBILITE, comme une experience qui baisse -- mais elle
    couvre les DEUX SENS : charger une partie plus avancee fait MONTER l'xp,
    et tout ressemble alors a une victoire enorme.

    (Les valeurs sont fabriquees ; la mesure reelle vit dans les notes
    privees.)
    """
    avant = _releve(image=900, xp=1000, argent=500)
    apres = _releve(image=100, xp=90000, argent=40000)
    vus = differences(avant, apres)

    assert vus[0]["quoi"] == "rupture", "la rupture passe AVANT les deltas"
    assert (vus[0]["de"], vus[0]["a"]) == (900, 100)
    # ⚠ Les autres deltas restent VISIBLES : le lecteur doit voir ce qui a
    # change ET savoir que rien de tout cela n'est arrive dans la partie.
    # ⚠ `xp` n'est plus derive de la somme d'equipe : elle bouge quand la
    # COMPOSITION bouge. Ce qui reste visible ici, c'est l'argent -- et il
    # suffit a montrer que les deltas ne sont pas effaces.
    assert {e["quoi"] for e in vus} >= {"rupture", "argent"}


def test_un_compteur_d_images_qui_AVANCE_n_est_pas_une_rupture():
    """⚠ Le cas normal, et il doit rester muet -- sinon le garde crie a chaque
    tour et on apprend a l'ignorer."""
    vus = differences(_releve(image=100), _releve(image=200))
    assert not [e for e in vus if e["quoi"] == "rupture"]
