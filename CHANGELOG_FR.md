# Trichr-o-matic — Journal des modifications (Français)

Ce fichier retrace ce qui a changé pour les utilisateurs entre les
différentes versions, à partir de la v0.4.0. C'est le pendant "notes de
version" de `CLAUDE.md` (qui couvre *comment* les choses sont
implémentées, pour le développement) — celui-ci couvre *ce qui a changé et
pourquoi c'est utile pour quelqu'un qui utilise l'application*.

Une version anglaise se trouve dans `CHANGELOG_EN.md`. Une copie PDF de
chacune (`CHANGELOG_EN.pdf` / `CHANGELOG_FR.pdf`) est régénérée
automatiquement par `build_mac.sh` à chaque compilation
(`scripts/generate_changelog_pdf.py`), pour qu'elles restent toujours
synchronisées avec l'`.app` que vous avez entre les mains.

La section **Non publié** en haut liste toujours ce qui a changé depuis la
dernière version réellement compilée, plus une liste courante de ce qui
est prévu ensuite — elle sert donc aussi de résumé de feuille de route,
pas seulement d'historique.

---

## Non publié

### Tâches restantes pour les prochaines versions
- **v0.6.0** : un **panneau de métadonnées** - pas encore spécifié.
- **Prise en charge des fichiers RAW** - pas encore commencée ; cadrée en
  discussion, pas encore prototypée.
- Quelques anciennes fenêtres d'erreur (erreur de chargement d'image,
  échec de l'alignement automatique, erreurs de chargement de session)
  utilisent encore l'ancien style de fenêtre système et n'ont pas encore
  été basculées vers le style d'alerte propre à l'application.

---

## v0.5.0 — 2026-09-08

### Ajouté
- **Un sélecteur de Mode clair** pour chaque photo (bloc Fichiers) :
  **Solo** (une seule photo déjà composée, éditée telle quelle),
  **Trichromie N&B** (le cas classique - 3 clichés noir et blanc
  recomposés en couleur), ou **Trichromie Couleur** (3 vraies photos
  couleur, chacune conservant son propre canal R/V/B, pour un véritable
  effet « Harris Shutter ») - chacun avec sa propre icône. La fenêtre
  d'Import par lot dispose désormais du même choix à 3 options pour
  importer plusieurs photos à la fois, avec un vocabulaire plus clair dans
  toute la fenêtre (sections renommées, et boutons d'info « ? »
  expliquant précisément comment fonctionne l'appariement automatique des
  fichiers).
- **Glissez-déposez des photos depuis le Finder** directement sur le
  bandeau de vignettes - chacune est ajoutée à la session comme une
  nouvelle photo Solo.
- **Courbes** : un nouveau bloc outil pour retoucher directement le ton de
  l'image via une courbe, avec des courbes Y (globale), R, V et B
  indépendantes - cliquez sur la ligne diagonale pour ajouter un point,
  glissez-le pour redessiner la courbe (y compris les deux extrémités, qui
  peuvent désormais se déplacer dans les deux sens pour un vrai point
  noir/blanc), double-cliquez sur un point pour le supprimer. La ligne de
  la courbe ainsi qu'un histogramme en transparence affiché derrière elle
  correspondent tous deux au canal en cours d'édition ; cet histogramme
  montre toujours l'image *avant* vos modifications de courbe, pour que
  vous voyiez exactement votre point de départ - le panneau Histogramme
  principal continue d'afficher le résultat final, corrigé.
- **L'outil Scan intégré à l'application** comme un bloc à part entière,
  aux côtés de Traitement Trichrome/Lumière/Couleur/Recadrage/Courbes -
  capture avec un appareil photo relié par câble, statut de connexion en
  direct, 3 types de film (Noir et Blanc / Couleur / Couleur Inversible),
  un rétroéclairage RVB à l'écran en option (avec une séquence
  automatique de 3 prises rouge/vert/bleu pour scanner directement un
  triplet trichrome), et une **correction de la couleur de base du
  film** pour les négatifs couleur (échantillonnez la base transparente
  du film, ou pointez-la directement sur une photo déjà importée, pour
  supprimer le masque de couleur orange). Les captures terminées sont
  désormais ajoutées automatiquement à la session en cours - plus besoin
  de l'étape manuelle « Ajouter à la session ».
- **Un vrai bouton Noir et Blanc** dans le panneau Couleur - une véritable
  conversion en niveaux de gris pondérée par la luminance, disponible dans
  tous les modes, plutôt qu'une simple mise à zéro de la saturation (qui
  pouvait faire lire des couleurs différentes à la même luminosité comme
  la même nuance de gris).
- Tous les boutons d'info « ? » de l'application s'ouvrent désormais aussi
  après une demi-seconde de survol, pas seulement au clic.

### Modifié
- Les deux graphiques d'histogramme (le panneau Histogramme et l'aperçu
  de l'outil Courbes) affichent désormais la hauteur des barres sur une
  échelle linéaire - les pics hauts et bas reflètent leurs tailles
  relatives réelles. Un pic très dominant (par exemple une grande zone en
  noir ou blanc pur) peut toujours écraser le reste du graphique - les
  petites barres d'avertissement d'écrêtage sur les bords du graphique
  sont justement là pour signaler ce cas.
- « Canaux RVB » renommé **Traitement Trichrome**, et ce bloc (avec
  l'Alignement automatique et la Position verrouillée, désormais à
  l'intérieur) grise désormais complètement avec un message clair
  lorsqu'il ne s'applique pas à la photo active (mode Solo) - comme tous
  les autres blocs outils lorsqu'ils ne sont pas utilisables, plutôt que
  de simplement désactiver discrètement quelques contrôles.
- Dans la fenêtre d'Import par lot, la section « Options avancées »
  renommée **Règles d'Import**, « Dossier d'entrée » renommé
  **Sélection des fichiers**, et « Semi-automatique » renommé
  **Séquentiel** ; la liste des fichiers non appariés est désormais un
  simple compteur avec la liste complète disponible au survol, au lieu
  d'une longue ligne de noms de fichiers toujours affichée.

### Retiré
- L'option de test webcam/iPhone temporaire de l'outil Scan, qui ne
  servait qu'à remplacer un véritable appareil photo relié par câble
  pendant le développement.

---

## v0.4.5 — 2026-09-04

### Ajouté
- **Disposition entièrement personnalisable** : chaque panneau - Fichiers,
  Canaux RVB, Histogramme, Lumière, Couleur, Recadrage et Scan - est
  désormais un bloc indépendant. Glissez un bloc par sa poignée pour le
  réordonner, le déplacer vers l'autre panneau latéral, le réduire à son
  seul en-tête, ou le fermer complètement ; un nouveau menu **Outils**
  liste tous les blocs avec une case à cocher pour faire réapparaître
  ceux qui sont fermés.
- **Préréglages de disposition** (menu Window ▸ Préréglage de
  disposition) : enregistrez vos propres arrangements de panneaux sous
  un nom, puis chargez-les, mettez-les à jour ou supprimez-les à tout
  moment.
- **Raccourcis de disposition rapides** : les boutons Trichrome /
  Correction Couleur / Recadrage / Scan de la barre d'outils (et leurs
  raccourcis T/E/C/S) basculent désormais directement vers votre propre
  disposition enregistrée pour cette tâche - un seul est actif à la fois.
  Ces 4 raccourcis figurent aussi directement dans le menu Window, avec
  la possibilité de les mettre à jour sur place.
- **Réinitialiser la disposition** (menu Window) restaure l'arrangement
  par défaut en un clic.
- La Correction Globale est désormais scindée en deux panneaux séparés,
  **Lumière** (exposition, luminosité, contraste, hautes/basses lumières,
  points noir/blanc, gamma, et Négatif) et **Couleur** (température,
  teinte, saturation, pipette de balance des blancs) - chacun peut être
  placé indépendamment d'un côté ou de l'autre de l'écran.

### Modifié
- Le mode actif de l'outil de recadrage est désormais un bouton dédié
  dans son propre panneau, indépendant du fait que le panneau soit
  simplement visible - il ne s'active/désactive plus de façon inattendue
  lorsque vous réorganisez votre disposition. Échap ne fait plus que
  quitter le mode recadrage sans changer votre disposition ; passer à une
  autre disposition enregistrée désactive automatiquement le mode
  recadrage, et activer la disposition Recadrage le réactive.
- « Canaux Indépendants » renommé en **Canaux RVB**.
- En-têtes de bloc plus compacts et cohérents dans toute l'application,
  avec des tailles d'icônes harmonisées.
- Le choix de la langue a été déplacé dans le menu **Aide** (Aide ▸
  Langue).
- Une version nouvellement installée ou mise à jour ne rouvre plus la
  session qui était ouverte auparavant - le premier lancement démarre
  toujours à vide, il faut donc ouvrir une session existante ou en
  créer une nouvelle.

### Retiré
- Le bouton Copier du panneau Recadrage (redondant avec ⌘C / le Copier
  et le Coller le recadrage du bandeau de vignettes).

---

## v0.4.4 — 2026-09-02

### Ajouté
- **Menu Fenêtre** : Fermer la fenêtre, et des interrupteurs pour le
  panneau de gauche, le panneau de droite et le bandeau de vignettes -
  chacun avec son propre raccourci clavier (⌘W, I, O, P).
- **Curseur Exposition**, à la fois dans les canaux indépendants et dans
  la Correction Globale, juste au-dessus de Luminosité. Contrairement à
  Luminosité (une simple retouche d'éclaircissement/assombrissement),
  Exposition est un vrai réglage photographique en diaphragmes (EV) qui se
  comporte comme un changement d'exposition réel - le pousser fort brûle
  les hautes lumières, comme le ferait une vraie surexposition à la prise
  de vue.
- **Pipette de lecture sur l'histogramme** : un nouveau bouton pipette à
  côté du bouton de réinitialisation de l'histogramme. Une fois activé,
  survoler l'aperçu trace un repère en direct montrant exactement où ce
  pixel se situe sur les courbes Y/R/V/B.

### Modifié
- Redesign de l'histogramme : de fines lignes de repère ombres/tons
  moyens/hautes lumières en arrière-plan, et un rendu plus doux façon
  Lightroom pour les courbes de canaux superposées (un remplissage
  translucide avec un contour net par-dessus).
- Les indicateurs d'écrêtage de l'histogramme sont plus précis : une
  fine bordure noire ou blanche, souvent invisible, introduite par un
  léger désalignement entre canaux (ou par l'outil Redresser), n'est plus
  confondue avec une vraie sur- ou sous-exposition, et l'indicateur
  s'ajuste désormais à la quantité réellement écrêtée au lieu de toujours
  sauter à la même taille.
- Activer le mode Solo (aperçu N&B) d'un canal met désormais
  automatiquement en évidence le scope correspondant dans l'histogramme
  (le bouton de réinitialisation de l'histogramme désactive le mode Solo
  en retour), et reflète maintenant aussi les réglages « Lumière » de la
  Correction Globale (Exposition, Luminosité, Contraste, Hautes lumières,
  Ombres, Blancs, Noirs, Gamma) - le mode Solo ignorait auparavant
  totalement la Correction Globale pendant qu'un canal était en solo. Les
  réglages propres à la couleur (Température, Teinte, Saturation) restent
  ignorés, puisqu'ils n'ont aucun sens sur un aperçu noir et blanc.

### Corrigé
- **L'effet Harris Shutter** se souvient désormais correctement du
  réglage propre à chaque photo - auparavant, passer d'une photo à
  l'autre pouvait laisser la case à cocher afficher le mauvais état, et
  dans de rares cas un export par lot pouvait réinterpréter les canaux
  d'une photo sous le mauvais mode. L'effet Harris Shutter et le mode
  Négatif peuvent désormais aussi s'appliquer à plusieurs photos
  sélectionnées en une fois - activer l'un ou l'autre règle toujours
  toutes les photos sélectionnées sur le même nouvel état, au lieu
  d'inverser le réglage propre à chaque photo individuellement.
- Le bouton « Relier… » de la fenêtre de reliaison des fichiers manquants
  ne reste plus bloqué désactivé après avoir résolu une photo alors que
  d'autres lignes du tableau restent à corriger.

---

## v0.4.3 — 2026-09-02

### Ajouté
- **Pipette de balance des blancs.** Un outil « Balance des blancs à la
  pipette » dans la section Couleur : cliquez dessus, puis cliquez sur un
  point de l'aperçu qui devrait être gris neutre - la Température et la
  Teinte sont alors réglées automatiquement pour neutraliser ce point. Un
  bouton « Réinitialiser » juste à côté remet Température, Teinte *et*
  Saturation à zéro.
- **Bouton de réinitialisation de la Lumière.** Réinitialise les 7
  curseurs de la section « Lumière » (Luminosité, Contraste, Hautes
  lumières, Ombres, Blancs, Noirs, Gamma) en une fois, à côté du titre de
  la section.
- **Récupération des photos source manquantes ou déplacées.** Si une
  session est rouverte et que certains fichiers R/G/B d'origine ont été
  déplacés ou supprimés, la ou les photos concernées ne disparaissent plus
  silencieusement du bandeau de photos. L'aperçu affiche désormais
  précisément quel(s) fichier(s) manque(nt) et son/leur dernier emplacement
  connu, avec un bouton **Localiser** qui les relie à nouveau (pour toutes
  les photos sélectionnées en une seule fois) en recherchant dans un
  dossier de votre choix.
  - Si certains fichiers restent introuvables (par exemple parce qu'ils ont
    été renommés plutôt que déplacés), une fenêtre les liste dans un
    tableau - survolez une ligne pour voir le chemin d'origine du fichier,
    ou sélectionnez une ligne et cliquez sur **Relier…** pour choisir
    directement le fichier de remplacement exact, sans avoir besoin
    d'aller le rechercher via le panneau de gauche.
- **Les boutons de réinitialisation grisent désormais** dès qu'il n'y a
  rien à réinitialiser - partout dans l'application : Correction Globale,
  Lumière, Couleur, la réinitialisation propre à chaque canal
  (alignement/couleur), et le panneau de recadrage.
- **Ce journal des modifications**, en anglais et en français, avec une
  copie PDF de chacun générée automatiquement et tenue à jour à chaque
  compilation.

### Modifié
- L'option Négatif/inversion a été déplacée dans l'en-tête du panneau
  Correction Globale, à côté de Réinitialiser, sous forme d'icône (grisée
  quand désactivée, allumée quand activée) au lieu d'une case à cocher
  textuelle plus bas dans le panneau - c'est une option assez importante
  en trichromie (une mauvaise polarité gâche toute l'image) pour figurer
  en haut.
- La petite icône d'avertissement/info qui se trouvait à côté de
  Réinitialiser (indiquant que les corrections propres à chaque canal
  n'étaient pas concernées) a été supprimée de l'en-tête de Correction
  Globale ; le bouton d'info « ? » qui explique la portée du panneau reste
  en place.
- Les fenêtres d'alerte/avertissement ont désormais le même style que le
  reste de l'application, au lieu des fenêtres système génériques de macOS.

---

## v0.4.2 — 2026-09-01

### Ajouté
- **Effet Harris Shutter.** Un mode optionnel (case à cocher sous les
  panneaux de canaux) pour celles et ceux qui importent 3 photos *en
  couleur* plutôt qu'en noir et blanc - il extrait le vrai canal R/V/B de
  chaque source au lieu de convertir en niveaux de gris, pour un véritable
  effet Harris Shutter. Désactivé par défaut ; la trichromie noir et blanc
  classique n'est pas affectée.
- **Curseurs redessinés** dans toute l'application : chaque curseur se
  centre désormais visuellement sur sa propre valeur par défaut, se
  remplissant vers la gauche ou la droite depuis ce point, pour voir d'un
  coup d'œil si une valeur est au-dessus ou en dessous de la normale. Les
  nombres sont désormais une valeur propre, cliquable pour être tapée, au
  lieu d'un compteur ; les curseurs de correction couleur s'affichent en
  -100…+100 (à la manière de Lightroom), tandis que les curseurs ayant une
  vraie unité physique (pixels, degrés, zoom) gardent leur propre unité.
- Fenêtre d'export : option « Afficher dans le Finder après l'export ».
- **⌘W** ferme désormais la fenêtre secondaire active (Export, Import,
  Aide) sans quitter l'application.
- Nouveau préréglage de ratio de recadrage : 7:5.
- Grille de recadrage : 4 styles au choix (3×3, 2×2, Nombre d'or, carrés de
  taille fixe), remplaçant l'ancien choix à 2 options.

### Modifié
- « Étalonnage global » renommé en **Correction Globale**, et divisé en
  deux sections clairement identifiées : **Lumière** et **Couleur**
  (Température, Teinte, Saturation, dans cet ordre).
- Les préréglages de ratio de recadrage ont été réordonnés (du plus carré
  au plus large) et l'icône d'orientation tourne désormais visuellement
  pour correspondre à votre sélection.
- Les panneaux Recadrage et Correction Globale correspondent désormais
  exactement en termes de mise en page, si bien que passer de l'un à
  l'autre ne déplace plus rien à l'écran.

### Corrigé
- Recadrer avec un ratio d'aspect verrouillé près du bord d'une photo ne
  déforme plus le ratio.

---

## v0.4.0 / v0.4.1 — 2026-08-31

*(La v0.4.1 était une passe de correction/polissage le jour même après la
v0.4.0 ; les changements ci-dessous couvrent les deux.)*

### Ajouté
- **Nouvelle Session**, un vrai système de session multi-photos, et le
  menu contextuel (clic droit) du bandeau de photos (Tout réinitialiser,
  Dupliquer).
- Contenu du menu Aide réécrit pour correspondre à tout ce qui précède.

### Modifié
- La fenêtre des raccourcis a été réorganisée en sections Général /
  Navigation / Aperçu / Curseurs ; l'explication du « canal actif » a été
  déplacée dans un bouton d'info « ? » directement à côté de la case
  Actif de chaque canal.
- Polissage de la mise en page de la barre latérale : titres de section
  plus clairs, histogramme séparé dans son propre bloc, boutons de
  réinitialisation agrandis/repositionnés.
- Le sélecteur d'outil (Correction Globale ⇄ Recadrage) a été déplacé dans
  la barre d'outils du haut sous forme de deux boutons, avec les raccourcis
  **E** / **C**.

### Supprimé
- Plusieurs chaînes de traduction inutilisées, nettoyées lors d'un audit
  des textes anglais/français.
