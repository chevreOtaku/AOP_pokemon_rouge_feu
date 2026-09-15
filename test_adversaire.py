"""Qui est EN FACE -- la regle, ecrite avant le code.

    python -m pytest test_adversaire.py -q

⚠⚠⚠ POURQUOI CE MODULE. `equipe.py` rend `actif = emplacement 0`, et cote
ADVERSE c'est faux des le premier K.O. : la fiche reste collee au Pokemon a
terre pendant que le suivant combat (mesure du 2026-09-15). Si les deux sont du
meme niveau, le controle de fraicheur par le niveau ne voit rien -- et un nom
EXACT mais FAUX serait presente comme une certitude.

⚠⚠ ET L'ECRAN NE PEUT PAS DEPARTAGER. Mesure du meme jour : la graphie lue a
l'ecran ressemble autant a l'un qu'a l'autre des deux candidats (ecart 0.036),
et contre toute la table des especes elle designe une espece absente du
combat. L'identite vient donc de la memoire SEULE, et la regle se TAIT quand
la memoire ne suffit pas.

=== LA REGLE ===

    un seul adversaire vivant                    -> lui
    aucun K.O. encore, plusieurs vivants         -> le PREMIER vivant (il ouvre)
    un K.O. a eu lieu ET plusieurs vivants       -> REFUS : on ne sait pas lequel
    aucun vivant, ou un PV illisible             -> REFUS

⚠ HYPOTHESE portee par la 2e ligne : un dresseur ouvre avec son premier
Pokemon et n'en change pas volontairement avant un K.O. La lecture de l'index
du combattant en memoire la remplacera ; d'ici la, elle est ecrite ici pour
qu'on ne l'oublie pas.

⚠⚠ AUCUNE VALEUR ICI NE VIENT D'UNE PARTIE (doctrine de `test_veilleur.py`) :
especes 101-103, niveaux et PV fabriques. Ce qui est teste, ce sont des
RELATIONS -- vivant, a terre, vide, illisible.
"""
from adversaire import adversaire_actif


def _fiche(emplacement, espece, pv, pv_max=30, niveau=9):
    return {"occupe": True, "emplacement": emplacement, "espece": espece,
            "niveau": niveau, "pv": pv, "pv_max": pv_max}


def _vide(emplacement):
    """⚠ La forme REELLE d'`equipe.lire_fiche` pour un emplacement vide."""
    return {"occupe": False, "pourquoi": "emplacement vide",
            "emplacement": emplacement}


def _en_panne(emplacement):
    """⚠ La forme REELLE de `lire_equipe` quand la sonde refuse un `dump`."""
    return {"occupe": False, "pourquoi": "la sonde a refuse la lecture",
            "emplacement": emplacement}


def test_un_seul_adversaire_vivant_c_est_lui():
    rendu = adversaire_actif([_fiche(0, 101, 20), _vide(1)])
    assert rendu["emplacement"] == 0
    assert rendu["espece"] == 101


def test_aucun_KO_et_plusieurs_vivants_c_est_le_PREMIER_qui_ouvre():
    rendu = adversaire_actif([_fiche(0, 101, 26), _fiche(1, 102, 26)])
    assert rendu["emplacement"] == 0
    assert rendu["espece"] == 101


def test_le_premier_se_juge_a_l_EMPLACEMENT_pas_a_l_ordre_de_la_liste():
    """⚠ Une liste reordonnee par un appelant ne doit pas changer qui ouvre."""
    rendu = adversaire_actif([_fiche(1, 102, 26), _fiche(0, 101, 26)])
    assert rendu["emplacement"] == 0


def test_Q4_le_premier_est_A_TERRE_et_le_second_vivant_c_est_le_SECOND():
    """⚠⚠⚠ LE DEFAUT MESURE. `actif = emplacement 0` rendait le Pokemon a terre.
    Meme niveau des deux cotes, expres : c'est le cas que le controle de
    fraicheur par le niveau ne voit pas."""
    rendu = adversaire_actif([_fiche(0, 101, 0, niveau=9),
                              _fiche(1, 102, 26, niveau=9)])
    assert rendu["emplacement"] == 1
    assert rendu["espece"] == 102


def test_un_KO_et_PLUSIEURS_vivants_c_est_un_REFUS_et_pas_une_supposition():
    """⚠⚠ Apres un K.O., un dresseur envoie qui il veut. Deviner reviendrait a
    ecrire un nom exact et peut-etre faux -- celui dont elle n'aurait aucune
    raison de douter."""
    rendu = adversaire_actif([_fiche(0, 101, 0), _fiche(1, 102, 26),
                              _fiche(2, 103, 26)])
    assert "emplacement" not in rendu
    assert "refus" in rendu


def test_aucun_vivant_c_est_un_refus():
    assert "refus" in adversaire_actif([_fiche(0, 101, 0), _fiche(1, 102, 0)])


def test_un_PV_ILLISIBLE_est_un_refus_meme_si_un_autre_est_vivant():
    """⚠ Un PV qu'on n'a pas su lire n'est ni « vivant » ni « a terre ». Le
    compter d'un cote ou de l'autre changerait la regle en silence."""
    rendu = adversaire_actif([_fiche(0, 101, None), _fiche(1, 102, 26)])
    assert "refus" in rendu


def test_les_emplacements_vides_ne_comptent_pas():
    rendu = adversaire_actif([_vide(0), _fiche(1, 102, 26), _vide(2)])
    assert rendu["emplacement"] == 1


def test_une_equipe_absente_ou_vide_est_un_refus():
    assert "refus" in adversaire_actif(None)
    assert "refus" in adversaire_actif([])
    assert "refus" in adversaire_actif([_vide(0), _vide(1)])


def test_la_raison_est_toujours_dite():
    """⚠ Un nom sans sa raison ne se relit pas : « seul vivant » et « ouvre le
    combat » n'ont pas la meme solidite, et le journal doit le montrer."""
    for equipe in ([_fiche(0, 101, 20)],
                   [_fiche(0, 101, 26), _fiche(1, 102, 26)],
                   [_fiche(0, 101, 0), _fiche(1, 102, 26), _fiche(2, 103, 26)]):
        rendu = adversaire_actif(equipe)
        assert rendu.get("raison") or rendu.get("refus")


def test_un_emplacement_EN_PANNE_n_est_pas_un_emplacement_vide():
    """⚠⚠⚠ TROUVE AVANT LE BRANCHEMENT, en lisant `equipe.py`. Une lecture
    refusee par la sonde rend `occupe: False` -- la meme forme qu'un vide. Si
    l'emplacement 0 (vivant) tombe en panne et que le 1 se lit, une regle qui
    l'ignore conclurait « seul vivant : le 1 » -- un nom exact et FAUX. Une
    equipe amputee ne se presente pas comme une equipe complete."""
    rendu = adversaire_actif([_en_panne(0), _fiche(1, 102, 26)])
    assert "refus" in rendu
    assert "emplacement" not in rendu


def test_CONTRAT_le_libelle_du_vide_est_celui_qu_equipe_rend_VRAIMENT():
    """⚠ Ce module reconnait un vide a son libelle. Si `equipe.py` le change,
    ce test tombe -- au lieu que tous les vides deviennent des pannes en
    silence, ou pire, l'inverse."""
    import equipe
    vide_reel = equipe.lire_fiche(bytes(equipe.TAILLE_FICHE))
    assert vide_reel["pourquoi"] == _vide(0)["pourquoi"]
    assert "refus" not in adversaire_actif([_fiche(0, 101, 20),
                                             vide_reel | {"emplacement": 1}])
    trop_courte = equipe.lire_fiche(b"") | {"emplacement": 1}
    assert "refus" in adversaire_actif([_fiche(0, 101, 20), trop_courte])


# ============================================================================
# LA LECTURE PAR LA SONDE -- la frontiere, pas la regle
# ============================================================================

class _Sonde:
    """`dump` factice : rend `reponse` (des octets, None, ou une exception)."""

    def __init__(self, reponse):
        self.reponse, self.demandes = reponse, 0

    def dump(self, adresse, longueur):
        self.demandes += 1
        if isinstance(self.reponse, Exception):
            raise self.reponse
        return self.reponse if self.reponse is None else self.reponse[:longueur]


def test_LECTURE_une_sonde_qui_refuse_tout_rend_un_refus_de_PANNE():
    from adversaire import lire_adverse_actif
    rendu = lire_adverse_actif(_Sonde(None))
    assert "refus" in rendu and "illisible" in rendu["refus"], rendu


def test_LECTURE_une_equipe_adverse_vide_rend_un_refus():
    import equipe
    from adversaire import lire_adverse_actif
    rendu = lire_adverse_actif(_Sonde(bytes(equipe.TAILLE_FICHE)))
    assert "refus" in rendu, rendu


def test_LECTURE_une_exception_de_la_sonde_ne_REMONTE_pas():
    """⚠⚠ `etat.py` enveloppe TOUT son etat dans un seul `try`. Si la lecture
    de l'adversaire levait, elle emporterait aussi les PV du joueur -- une
    piece ajoutee casserait les pieces qui marchaient. Elle rend un refus."""
    from adversaire import lire_adverse_actif
    rendu = lire_adverse_actif(_Sonde(ConnectionError("sonde coupee")))
    assert "refus" in rendu and "ConnectionError" in rendu["refus"], rendu
