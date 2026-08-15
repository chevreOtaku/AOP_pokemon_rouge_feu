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
# ⚠ HYPOTHESE NON VERIFIEE : le membre N serait a +100*N. Personne ne l'a
# teste -- il faudra un combat avec plusieurs Pokemon vivants pour le dire.
PAS_EQUIPE = 100

NIVEAU = -2
PV_MAX = +2

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
