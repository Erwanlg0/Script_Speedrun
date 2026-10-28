# Vérification du nouvel habillage vidéo

final result: passed

## Références et état comparé

- Cible : `preview/redesign/design-target.png`, maquette déterministe du compositeur Pillow avec la nouvelle direction visuelle.
- Export réel : `preview/redesign/encoded-frame.png`, image extraite à 10 secondes du MP4 encodé par FFmpeg.
- Vidéo : `preview/redesign/video/run-y8o1n4wm/y8o1n4wm-part-01.mp4`.
- Référence précédente : `preview/social-ready-preview.png`, utilisée pour identifier les changements souhaités, pas comme cible à reproduire.
- État : même run Mario, joueur Cads, rang 1, drapeau canadien, chrono officiel 31 secondes, partie 1/1.
- Dimensions source et export : 1080 × 1920 pixels, densité 1:1. Les notions de viewport CSS et de navigateur ne s'appliquent pas à cet export vidéo.
- La fenêtre du gameplay utilise des dimensions paires pour l'encodage. Les différences de sélection d'une image de la source à 60 images/s vers l'export à 30 images/s sont attendues.

## Preuves visuelles

- Vue complète comparée dans une même image : `preview/redesign/design-comparison.png` ; chaque colonne est réduite à 540 × 960 avec le même facteur.
- Région détaillée comparée à la même échelle : `preview/redesign/detail-comparison.png` ; joueur, drapeau, chrono et numéro de partie.
- Mesure complémentaire : `preview/redesign/comparison-metrics.json`. Écart moyen par canal RGB hors gameplay inférieur à 1,5 sur 255, compatible avec la conversion et la compression vidéo.

## Constats

Aucun écart P0, P1 ou P2 constaté entre la cible et l'export.

- Typographie : titre Segoe UI gras sur deux lignes, corps lisible et chrono Consolas gras. Les textes longs, accents et noms coopératifs sont testés à 1080p et 720p.
- Espacement : alignements cohérents, informations en dehors de toute la fenêtre gameplay, réserve basse de 148 pixels et marge droite de 116 pixels pour les informations.
- Couleurs : fond `#0D0F12` partagé par Pillow et FFmpeg ; accent `#DFFF00`, texte clair et libellés secondaires contrastés. Le chrono noir sur citron reste lisible après encodage.
- Images : drapeau réel conservé ; gameplay complet, sans recadrage ni étirement. Le grand cadre vide a été supprimé et la largeur de gameplay passe de 85 % à 90 % du cadre.
- Contenu : titre, catégorie, joueur, classement, chrono, date et partie correspondent aux métadonnées du run. Aucun crédit original de la vidéo n'est masqué par l'habillage.

## Historique de comparaison

La première comparaison maquette/export, après normalisation des dimensions paires du gameplay, ne relève aucun écart visuel nécessitant une correction. Aucune boucle de correction P0/P1/P2 n'a été nécessaire.

## Vérifications techniques

- 23 tests ciblés du rendu et de la mise en page passent.
- 2 tests d'intégration natifs passent : découpage réel, source avec ou sans audio et plafond de trois minutes.
- Le MP4 réel de 38,2 secondes a été décodé intégralement sans erreur.
- L'identité de l'habillage et le fichier de police sont enregistrés dans les paramètres de rendu pour empêcher la réutilisation silencieuse d'un ancien style.
- Les anciens exports sont conservés. Le nouveau style s'applique aux nouveaux rendus.

## Limites

Les emplacements exacts des contrôles des réseaux sociaux dépendent de leurs applications. Leur superposition réelle n'est pas simulée. Les réglages de durée et les règles de sélection des runs n'ont pas été modifiés dans cette refonte.
