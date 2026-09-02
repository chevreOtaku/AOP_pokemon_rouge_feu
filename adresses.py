"""Les adresses memoire trouvees, avec la mesure qui les etablit.

⚠ AUCUNE DOCUMENTATION FR N'EXISTE pour Pokemon Version Rouge Feu (France).
Chaque adresse ici a ete trouvee par scan et correlation avec `chasse.py`, et
chacune porte la mesure qui l'a confirmee. Une adresse sans sa methode est
invérifiable : le jour ou elle cesse d'etre juste, on ne saurait ni pourquoi
ni comment la retrouver.

⚠ CE FICHIER DECRIT UN JEU, rien d'autre. Aucun etat de moteur, aucune memoire :
ce pont reste sans etat pour qu'une mesure soit reproductible.
"""

# --------------------------------------------------------------- position
#
# Pointeur du SaveBlock1. Trouve le 2026-07-08 par scan de l'IWRAM (tout mot
# de 32 bits pointant dans l'EWRAM), puis marche d'un nombre connu de pas en
# retenant le candidat dont la coordonnee bougeait d'autant.
#
# ⚠ RELIRE LE POINTEUR A CHAQUE LECTURE, ne JAMAIS cacher l'adresse resolue :
# Rouge Feu DEMENAGE ses SaveBlocks en cours de partie.
PTR_SAVEBLOCK1 = 0x03004F58
#   +0 x (u16) · +2 y (u16) · +4 mapGroup (u8, 255 = transition de porte)
#   +5 mapNum (u8)

# Pointeur du SaveBlock2, colle au premier. PREDIT le 2026-09-01 par adjacence
# (elle tient sur la carte USA), puis CONFIRME : il pointe dans l'EWRAM, et la
# cle qu'il porte dechiffre l'argent a une valeur lue a l'ecran.
PTR_SAVEBLOCK2 = 0x03004F5C

# ------------------------------------------------------------------- le sac
#
# Trouve le 2026-09-01, et pas par une chasse : la carte memoire de la
# cartouche USA a ete TRANSFEREE, puis verifiee ici. Ce qui a autorise le
# transfert est une comparaison sur des adresses deja connues des deux cotes --
# EWRAM identique sur 3 cas sur 3, IWRAM differente sur 1 sur 1.
#
# ⚠ CE SONT DES DECALAGES DANS UNE STRUCTURE, pas des adresses. Ils traversent
# la localisation par construction : la disposition d'une sauvegarde ne depend
# pas de la langue des textes.
#
# Une entree fait QUATRE octets : {u16 identifiant, u16 quantite XOR cle16}.
# Un identifiant nul = emplacement vide -- et sa quantite brute vaut alors la
# cle elle-meme (0 XOR cle = cle). C'est ce detail qui a confirme le
# chiffrement : une quantite brute egale a la cle au bit pres ne s'invente pas.
POCHES = (
    ("objets",     0x0310, 42),
    ("objets_rares", 0x03B8, 30),
    ("pokeballs",  0x0430, 13),
    ("ct_cs",      0x0464, 58),
    ("baies",      0x054C, 43),
)
#
# La cle chiffre AUSSI l'argent, et c'est par l'argent qu'elle se controle :
# une cle fausse rend un entier arbitraire, une cle juste rend le nombre que le
# jeu affiche. Verification du 2026-09-01 : 2000.
CLE_CHIFFREMENT = 0x0F20   # dans le SaveBlock2
ARGENT          = 0x0290   # dans le SaveBlock1
#
# ------------------------------------------------- le sac, quand il est OUVERT
#
# Transferees de la carte USA le 2026-09-01, puis VERIFIEES ici par correlation.
# Critere ecrit AVANT la mesure, et tenu deux fois :
#   la poche : 0 sur OBJETS, 1 sur OBJ. RARES, 2 sur POKe BALLS
#   la ligne : 0 sur POTION, 1 sur SUPER BONBON, 2 sur SORTIR
#
# ⚠⚠ CES ADRESSES N'ONT DE SENS QUE LE SAC OUVERT. C'est un etat de MENU, pas
# un etat de partie. Lu sac ferme, il rend une valeur qui RESSEMBLE a une
# lecture sans en etre une -- premiere tentative du 2026-09-01, sac ferme : 0,
# ininterpretable et non pas faux. Meme piege que la fiche adverse qui survit
# a la fin d'un combat.
SAC_POCHE       = 0x0203AD02   # u16 -- indexe POCHES ci-dessus. VERIFIE 2026-09-01
SAC_LIGNE       = 0x0203AD04   # u16[3] -- UNE PAR POCHE. VERIFIE 2026-09-01
SAC_DEFILEMENT  = 0x0203AD0A   # u16[3] -- ⚠ NON VERIFIE
SAC_PAS_TABLEAU = 2            # MESURE le 2026-09-01


def sac_ligne(poche: int) -> int:
    """L'adresse du curseur de CETTE poche. Il y en a un par poche."""
    return SAC_LIGNE + SAC_PAS_TABLEAU * poche


def sac_defilement(poche: int) -> int:
    """⚠ Le pas est MESURE sur les curseurs, INFERE par symetrie ici."""
    return SAC_DEFILEMENT + SAC_PAS_TABLEAU * poche

# ⚠⚠⚠ LE SAC SE SOUVIENT DE LA LIGNE, PAS SEULEMENT DE LA POCHE -- et il peut
# rouvrir SUR « SORTIR ». Mesure de chevre, 2026-09-01 : « si la derniere
# position est SORTIR, il est directement a la position SORTIR ».
# ➜ Un « A » aveugle a la reouverture FERME LE SAC. Le geste rapporte « j'ai
# presse A », et rien ne s'est passe. C'est le meme symptome silencieux que le
# defilement non lu -- deux causes, une seule apparence.
# ➜ Le curseur se LIT avant de presser, et la cible se borne a 0..n-1.
#
# ⚠⚠ QUASI-RATE A GARDER EN MEMOIRE. Le test qui a valide `SAC_LIGNE` avait
# navigue dans la poche OBJETS -- l'indice 0. L'adresse etait donc juste PAR LA
# POCHE, pas par conception. Le meme test dans POKe BALLS n'aurait rien vu
# bouger a 0x0203AD04, et aurait condamne une adresse correcte.
# ➜ Un tableau teste sur son PREMIER element ne se distingue pas d'un scalaire.
#
# Structure confirmee par contiguite : 0x0203AD04 + 3*2 = 0x0203AD0A, sans trou.
#   AD02 poche · AD04/AD06/AD08 curseurs · AD0A/AD0C/AD0E defilements
#
# ⚠⚠⚠ LA SELECTION VRAIE = SAC_LIGNE + SAC_DEFILEMENT.
#
# Et le second n'a PAS pu etre verifie le 2026-09-01 : il ne bouge que si une
# poche depasse la fenetre visible, et la plus remplie en contenait DEUX. Une
# adresse fausse et une adresse juste rendent donc le meme zero aujourd'hui --
# le controle est impossible, pas negatif.
# ➜ Le defaut ne mordra que le jour ou une poche debordera, et il mordra en
# SILENCE : c'est exactement ce qui a coute a l'integration de reference un
# ANNULER selectionne a la place d'un objet, ligne lue 5, objet non consomme.
# ➜ A RETESTER des qu'une poche depasse six objets. Tant que ce n'est pas fait,
# additionner les deux quand meme -- l'addition est juste dans les deux cas.
#
# ⚠ LA DERNIERE LIGNE EST « SORTIR », PAS UN OBJET. Sur une poche de n objets,
# les indices valides pour un objet sont 0..n-1 ; n vaut SORTIR. Une selection
# calculee sans cette borne choisit d'annuler en croyant choisir un objet.

# ⚠ VERIFIE CONTRE L'ECRAN le 2026-09-01, trois poches :
#   POTION x1 (id 13) · SUPER BONBON x99 (id 68) · POKe BALL x107 (id 4)
# Les trois quantites tombent juste. C'est la seule verite terrain qui vaille
# ici -- les quantites du sac n'ont pas d'autre temoin que l'affichage.

# ------------------------------------------------------- fiches de combat
#
# Trouvees le 2026-08-13. METHODE : capturer la memoire a plusieurs instants,
# puis chercher non pas un nombre isole mais une SIGNATURE STRUCTURELLE --
# <niveau 1..100> <0xFF> <PV> <PV max> puis cinq statistiques plausibles.
#
# ⚠ Un nombre isole se trouve par dizaines et ne prouve rien : la premiere
# tentative a cherche une valeur unique et rendu sept adresses, toutes fausses
# (dont une table d'index qui contenait 20,21,22,23,24,25 -- le nombre cherche
# etait simplement dedans). La PAIRE coherente, elle, n'est apparue qu'une fois
# par equipe et par capture.
#
# CONFIRMATION -- trois predictions posees AVANT lecture, les trois tombees :
# apres un soin et une montee de niveau, PV == max, max > 22, niveau = 7.
# Lu en direct : 24, 24, 7.
#
# Disposition, mesuree octet par octet :
#     -2  niveau        (u8)      +1 = 0xFF
#      0  PV courants   (u16)
#     +2  PV max        (u16)
#     +4  attaque · +6 defense · +8 vitesse · +10 atq.spe · +12 def.spe (u16)
PV_EQUIPE  = 0x020242DA   # le Pokemon actif du joueur
PV_ADVERSE = 0x02024082   # celui d'en face
#
# L'ecart est de 600 octets = 6 x 100 : le pas d'une equipe de six.
# ✅ VERIFIE le 2026-08-19. Cette ligne a porte « HYPOTHESE NON VERIFIEE :
# personne ne l'a teste » pendant six jours. Les six emplacements ont ete lus
# d'affilee : deux occupes, quatre vides, especes et attaques coherentes avec
# l'ecran. Voir `equipe.py`.
PAS_EQUIPE = 100

# ⚠⚠ LA FICHE COMPLETE COMMENCE 86 OCTETS AVANT LES PV. `struct Pokemon` fait
# 100 octets et place `hp` a l'offset 86 -- ce qui relie l'adresse ci-dessus au
# DEBUT de la fiche, et donne acces a l'espece, aux quatre attaques, a leurs PP
# et au PID. Les 48 octets qui les portent sont CHIFFRES ; la cle
# (`personality XOR otId`) est lisible en clair aux offsets 0 et 4.
# ➜ Tout le detail, la methode et ses pieges : `equipe.py`.
DEBUT_FICHE = -86

NIVEAU = -2
PV_MAX = +2

# ------------------------------------------- modificateurs de statistiques
#
# Trouves le 2026-08-16. ⚠ PAS dans les fiches d'equipe ci-dessus : celles-ci
# sont espacees de 600 = 6 x 100, le pas d'une EQUIPE. Les modificateurs vivent
# dans une structure de COMBAT separee, qui n'existe que pendant un combat.
# Une premiere recherche a echoue en scrutant le voisinage des fiches d'equipe :
# l'hypothese « les modificateurs sont pres d'elles » etait fausse.
#
# METHODE -- signature structurelle, encore, et une prediction posee d'avance :
# les sept modificateurs (attaque, defense, vitesse, atq.spe, def.spe,
# precision, esquive) sont contigus, neutres a 6, bornes 0..12. Un tableau
# intact est donc une suite de HUIT octets valant exactement 6 (le premier
# emplacement, prevu pour les PV, ne sert pas).
#
# RESULTAT : sur 262 144 octets d'EWRAM, **une seule** suite de 8 x 0x06.
# Et a exactement +88 -- le pas d'une entree de structure de combat -- un second
# tableau portant `06 06 05 06 06 06 06 06`.
#
# ⚠⚠ CE N'EST PAS UNE COINCIDENCE NUMERIQUE : le 5 est en position DEFENSE, et
# la capacite qui venait d'etre utilisee etait MIMI-QUEUE, qui baisse la
# defense adverse. C'est le geste du joueur qui a ecrit cet octet.
STAGES_EQUIPE  = 0x02023BFC   # le combattant du joueur
STAGES_ADVERSE = 0x02023C54   # celui d'en face
PAS_COMBATTANT = 88
#
#   +0 (inutilise) · +1 attaque · +2 defense · +3 vitesse
#   +4 atq.spe · +5 def.spe · +6 precision · +7 esquive
#   valeur 6 = neutre ; 0..12 ; (valeur - 6) = le nombre de crans
STAGE_NEUTRE = 6
#
# ⚠ CES ADRESSES N'ONT DE SENS QU'EN COMBAT. Hors combat elles portent des
# restes -- meme piege que la fiche adverse, et meme garde : la boite affichee
# a l'ecran est la seule preuve qu'un combat a lieu.
#
# ⚠ RESERVE : une prediction de confirmation supplementaire -- reutiliser
# MIMI-QUEUE et voir l'octet passer de 5 a 4 -- n'a PAS ete executee. Ce qui
# precede tient sur la structure, l'unicite de la suite, et le mecanisme ; pas
# sur une seconde variation observee.

# ------------------------------------------------- ce qui reste a trouver
#
# ⚠ LE DRAPEAU « EN COMBAT » N'EST PAS TROUVE, et l'astuce evidente ECHOUE :
# apres un combat, `PV_ADVERSE` garde la fiche du dernier adversaire (mesure :
# niveau 3, 0/15, hors combat). Une fiche perimee s'y lit exactement comme une
# fiche vivante. « Des PV adverses sains » ne dit donc PAS qu'un combat est en
# cours.
#
# ⚠ La chasse au drapeau par comparaison d'etats a echoue le 2026-08-12 :
# 53 240 -> 53 028 -> 49 293 candidats en trois croisements. Les contraintes
# etaient trop faibles parce que deux captures differaient par une dizaine de
# choses a la fois, pas seulement par « en combat ou non ».
#
# Restent aussi : le curseur de menu (un menu a une position, et « bas, bas, A »
# ne veut pas dire la meme chose selon d'ou l'on part), l'espece du Pokemon,
# le sac.

# ------------------------------------------------------------- avertissements
#
# ⚠ UNE CAPTURE PRISE PENDANT UNE TRANSITION MONTRE DES ZEROS QUI RESSEMBLENT
# A UNE ABSENCE. La capture `hors_1` du 2026-08-13 ne contenait AUCUNE fiche --
# prise pendant le fondu de fin de combat. La meme lecture, quelques secondes
# plus tard, rendait les deux fiches intactes. Un zero se verifie a un second
# instant avant d'etre cru.
#
# ⚠ NE JAMAIS METTRE L'EMULATEUR EN PAUSE POUR LIRE : mGBA suspend les rappels
# du script Lua, la sonde cesse de repondre, et elle ne s'en remet pas -- il
# faut relancer mGBA.
#
# ✅ STABILITE ETABLIE LE 2026-08-15 -- la reserve ci-dessous est LEVEE.
#
# Cette ligne a dit « non etablie » jusqu'au 15/08. Elle disait vrai le 13, et
# elle serait devenue un avertissement perime qui se lit comme un etat present :
# c'est le mode de peremption le plus couteux d'un document, parce qu'il ne se
# voit pas. Elle est donc reecrite le jour meme de la mesure.
#
# CE QUI A ETE VERIFIE, et les deux conditions posees le 13/08 sont couvertes :
#   - mGBA a ete relance entre le 13 et le 15
#   - une AUTRE sauvegarde a ete chargee entre-temps (partie personnelle, puis
#     retour a la sienne)
#
# METHODE : cinq predictions ECRITES AVANT la lecture, tirees d'une source
# INDEPENDANTE de la memoire -- l'OCR de l'ecran de combat, qui rend les noms et
# les niveaux mais pas les PV (mesure : deux lectures des memes pixels rendent
# « 21Z » puis « 20 ZL »).
#
#   attendu : niveau 6 et niveau 3 · PV max plausibles · PV <= max
#   lu      : 6 · 21/21     et     3 · 14/14
#
# ⚠ C'est la CONCORDANCE DES DEUX NIVEAUX qui prouve, pas les PV : une fiche
# perimee porterait le combat precedent, donc un autre couple de niveaux. Deux
# valeurs justes simultanement contre une source qui n'a pas servi a trouver les
# adresses n'est pas une coincidence.
#
# ➜ CE CONTROLE EST DEVENU PERMANENT : `etat.py` rend le niveau, et le
# consommateur le compare a celui lu a l'ecran. Une divergence signale une fiche
# perimee -- c'est le drapeau « en combat » qu'aucune chasse memoire n'a trouve,
# obtenu par redondance au lieu d'une adresse.
