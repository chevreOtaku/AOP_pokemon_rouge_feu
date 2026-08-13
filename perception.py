"""Ce qui est LU n'est pas ce qui est MONTRE.

⚠⚠ LA REGLE, ET ELLE N'EST PAS UN REGLAGE.

    On LIT les PV adverses exactement -- c'est le critere de delta, donc la
    mesure. On ne les EXPOSE jamais : ce qui arrive au sujet est une IMPRESSION.

Deux raisons, et la seconde est la plus forte :

1. Le jeu lui-meme ne montre au joueur qu'une BARRE pour l'adversaire, jamais
   un nombre. Donner l'entier serait donner PLUS qu'a un humain -- c'est la
   doctrine d'accessibilite du projet : un lecteur d'ecran, pas un chien-guide
   qui choisit a votre place.
2. Une decision prise sur un chiffre exact n'est pas la meme decision. « Il
   lui reste 5 PV » se calcule ; « il est presque a terre » se juge. Le second
   laisse la place a l'erreur, et donc a quelqu'un.

⚠ CONSEQUENCE D'ARCHITECTURE : la valeur exacte NE TRAVERSE PAS le fil. Ce
module rend une BANDE, pas un nombre -- le filtre est ainsi tenu par
construction, et non par la discipline de celui qui cablera ensuite.

⚠ CE QUI VIT ICI ET CE QUI N'Y VIT PAS. La bande est du savoir de JEU : elle
sort des seuils du jeu lui-meme. Les MOTS, eux, appartiennent au sujet -- deux
VTubers ne disent pas « il est mal en point » de la meme facon, et c'est
exactement la ou une identite se voit. Le dictionnaire ci-dessous est un repli
lisible, pas la voix de quelqu'un : le cote cultivation doit le remplacer.
"""

# Seuils repris du JEU, pas inventes : la barre de PV de Pokemon change de
# couleur a 50 % (vert -> jaune) et a 20 % (jaune -> rouge). S'y aligner, c'est
# donner au sujet ce que la barre donne a un joueur -- ni plus, ni moins.
BANDES = (
    (1.00, "intact"),
    (0.70, "a peine entame"),
    (0.50, "entame"),
    (0.20, "mal en point"),
    (0.01, "presque a terre"),
    (0.00, "a terre"),
)


def bande_pv(pv: int, pv_max: int) -> str:
    """Rend une bande qualitative. JAMAIS le nombre.

    ⚠ Deterministe : la meme fraction rend toujours la meme bande. Un flou
    ALEATOIRE serait pire qu'inutile -- en observant plusieurs fois, on
    moyennerait le bruit et on retrouverait le nombre. Le flou doit venir de
    la GROSSIERETE de l'echelle, pas d'un tirage.
    """
    if pv_max <= 0:
        return "illisible"
    if pv <= 0:
        return "a terre"
    fraction = pv / pv_max
    for seuil, nom in BANDES:
        if fraction >= seuil:
            return nom
    return "a terre"


def perception_adversaire(pv: int, pv_max: int) -> dict:
    """Ce qu'on transmet au sujet a propos d'en face.

    ⚠ Le NOM et le NOMBRE d'adversaires sont autorises (decision chevre du
    2026-08-12) ; les PV ne le sont pas. Cette fonction ne rend donc aucun
    entier de vie -- si un appelant en veut un, c'est qu'il confond la mesure
    et la perception.
    """
    return {"forme": bande_pv(pv, pv_max)}


def mesure_adversaire(pv: int, pv_max: int) -> dict:
    """Ce qu'on ENREGISTRE, et qui ne doit jamais entrer dans un prompt.

    Sert au critere de delta : juger si une decision a fait avancer le combat
    demande les valeurs avant et apres, exactes. C'est de l'instrument.
    """
    return {"pv": pv, "pv_max": pv_max,
            "fraction": (pv / pv_max) if pv_max > 0 else None}
