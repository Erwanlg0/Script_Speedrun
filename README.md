# Script Speedrun

Sélectionne des speedruns vérifiés sur speedrun.com, télécharge leurs vidéos YouTube ou Twitch et prépare des MP4 verticaux pour Instagram, YouTube et TikTok. Le gameplay reste entier, sans recadrage ni étirement. Les panneaux affichent le jeu, la catégorie, le classement, le joueur, son drapeau, le chrono officiel, la date et le numéro de partie.

La publication sur les réseaux reste manuelle. Chaque export contient les crédits et les liens vers le run, le joueur et la vidéo originale.

## Installation sous Windows

Python 3.11 ou plus récent est requis ; le projet est testé ici avec Python 3.15. Depuis Git Bash, dans le dossier du projet :

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Les dépendances directes sont Pillow, requests et `yt-dlp[default]`. MoviePy, OpenCV et NumPy ne sont plus nécessaires. `requirements.in` déclare les dépendances directes ; `requirements.txt` fixe l'environnement obtenu par `pip freeze`.

Les exécutables natifs sont à installer séparément :

- [FFmpeg et FFprobe](https://ffmpeg.org/download.html) : dans le `PATH`, ou sous `.tools/ffmpeg.exe` et `.tools/ffprobe.exe`.
- [ImageMagick](https://imagemagick.org/download/) : facultatif, pour convertir les drapeaux SVG. Placer `magick.exe` dans le `PATH` ou dans `.tools/imagemagick/` avec ses fichiers compagnons. Sans convertisseur, le code du pays remplace le drapeau SVG ; les PNG restent utilisables.
- Node.js ou Deno : recommandé pour les challenges JavaScript de YouTube. Le Node présent dans le `PATH` est détecté automatiquement. Voir les prérequis de [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Les variables `FFMPEG_BINARY`, `FFPROBE_BINARY` et `IMAGEMAGICK_BINARY` permettent d'indiquer d'autres chemins d'exécutables. `SPEEDRUN_FONT` permet de choisir un fichier de police. FFmpeg 9.0.2 et ImageMagick 7.1.2-34 ont été utilisés pour vérifier le rendu.

## Sélection et téléchargement

Renseigner une URL de jeu speedrun.com par ligne dans `game_urls.txt`. Les lignes vides et celles commençant par `#` sont ignorées.

```bash
.venv/Scripts/python.exe Speedrun.py --list-only
.venv/Scripts/python.exe Speedrun.py --max-videos 3
```

`python -m speedrun` utilise le même point d'entrée. `--list-only` affiche les candidats sans téléchargement ni écriture dans l'historique et ne nécessite pas FFmpeg.

Le programme examine les jeux dans un ordre aléatoire, puis les classements disponibles par jeu, niveau et sous-catégorie. Il retient les runs vérifiés du podium, entre 20 et 300 secondes par défaut. Pour chaque jeu, il privilégie les premières places, les runs qui tiennent dans une seule partie, puis les plus récents. Les vidéos déjà utilisées sont écartées.

`game_rules.json` contient les exceptions par jeu. La règle fournie pour Celeste accepte les runs de niveaux individuels jusqu'à une heure, en excluant les classements du jeu complet :

```json
{
  "celeste": {
    "max_duration": 3600,
    "levels_only": true
  }
}
```

Cette exception concerne les maps ou chapitres IL ; les autres jeux gardent la limite générale de 300 secondes. Ajouter `https://www.speedrun.com/celeste` dans le fichier des jeux utilisé si cette URL n'y figure pas : une règle seule n'ajoute pas de jeu à la sélection. `levels_only` sélectionne des classements de niveaux et ne supprime pas les menus ou transitions dans la vidéo.

```bash
.venv/Scripts/python.exe -m speedrun --games game_urls.txt --game-rules game_rules.json --output Video_final --max-videos 3 --min-duration 20 --max-duration 300 --top 3 --segment-duration 59
```

`--top` accepte `1`, `2` ou `3`. `--game-rules` permet d'utiliser un autre fichier de règles. Une exception par jeu remplace `--max-duration` pour ce jeu. Les sources dépassant la limite du jeu plus 120 secondes sont refusées avant téléchargement ; après analyse, leur durée doit aussi être comprise entre la durée officielle moins 2 secondes et cette durée plus 120 secondes.

La longueur du run source et celle de chaque export sont distinctes : un long run de niveau Celeste est découpé en plusieurs fichiers courts. `--max-videos` limite le nombre de runs exportés, pas le nombre de parties.

`--segment-duration` vaut **59 secondes par défaut** et ne peut pas dépasser **180 secondes**. Ce plafond est un choix du logiciel, contrôlé par la commande et le moteur de rendu. YouTube accepte les [Shorts verticaux jusqu'à trois minutes](https://support.google.com/youtube/answer/15424877) ; le [guide de transfert de TikTok](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide) indique également que tous les créateurs peuvent publier des vidéos de trois minutes. Cela ne définit pas une limite universelle d'import pour les trois réseaux. Le réglage de 59 secondes reste le choix conservateur du projet pour préparer une même série destinée à Instagram, YouTube et TikTok.

Les débuts et fins de maps ne sont pas détectés automatiquement dans une VOD. Pour isoler une map et retirer manuellement les séquences entre deux runs, indiquer ses bornes dans le fichier local :

```bash
.venv/Scripts/python.exe -m speedrun --video "Video_download/source.mp4" --metadata "Video_final/run-ID/metadata.json" --start 12.5 --end 87.2 --output "Video_remontees"
```

Les métadonnées proviennent d'un export existant. Le montage ne conserve que l'intervalle entre `--start` et `--end`, exprimés en secondes, puis le découpe selon `--segment-duration`. Sans `--end`, il conserve le reste de la vidéo. Il faut choisir les bornes de la map et les métadonnées correspondantes ; aucun détecteur de transitions ne les détermine. Un autre dossier `--output` permet de refaire un run avec des paramètres différents sans écraser l'export précédent.

## Fichiers produits

Par défaut, les chemins sont ancrés dans le dossier du projet :

- `Video_download/` : vidéos sources, avec reprise des téléchargements par yt-dlp.
- `Video_final/run-ID/` : parties MP4, `metadata.json` et `description.txt` avec crédits.
- `used_runs_db.json` : historique conservant son ancien format ; sauvegarde atomique uniquement après un export complet réussi.
- `game_rules.json` : exceptions de durée et sélection des niveaux par jeu.
- `flags/` : drapeaux PNG ou SVG, sélectionnés depuis le pays du joueur.

Les sorties sont en **1080 × 1920, 30 images/s, H.264/AAC, `yuv420p` et `faststart`**, avec des parties de 59 secondes au maximum par défaut. Les vidéos sans audio sont également prises en charge. Les fichiers sont préparés dans un dossier temporaire ; un échec ne remplace pas un export terminé.

## Organisation du code

- `Speedrun.py`, `speedrun/__main__.py`, `cli.py` : lancement et options.
- `config.py`, `models.py`, `utils.py` : paramètres, données d'un run et fonctions communes.
- `api.py`, `policy.py`, `app.py` : accès à speedrun.com, règles par jeu, sélection et déroulement du traitement.
- `download.py`, `history.py` : téléchargement et détection des vidéos déjà utilisées.
- `layout.py`, `render.py` : panneaux graphiques et export vidéo FFmpeg.
- `publication.py` : métadonnées et description avec crédits.
- `tests/` : tests des modules et des erreurs importantes.

Ces modules sont regroupés dans le paquet `speedrun/`.

## Vérification

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Les tests unitaires utilisent réellement Pillow pour les images et simulent les frontières API, yt-dlp et FFmpeg. Les tests d'intégration utilisent FFmpeg et FFprobe lorsqu'ils sont disponibles : découpage, audio ou silence, fichiers lisibles et plafond réel de trois minutes. Ils ne téléchargent pas de vidéo. La découverte API, le téléchargement YouTube et un rendu complet de 38 secondes ont également été vérifiés sur une vraie source.
