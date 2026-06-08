# Meaning-Ankidroid : L'Architecte Automatisé de Cartes de Vocabulaire

**Meaning-Ankidroid** est un utilitaire Python de qualité professionnelle conçu pour transformer une simple liste de mots en flashcards riches et enrichies par des fichiers multimédias [1]. L'automatisation de la collecte de données à partir de 7 dictionnaires premium et de sources médiatiques de haute qualité permet aux apprenants de langues de se concentrer sur la mémorisation plutôt que sur la création manuelle de cartes [1].

### Utilisation

La mise en route est simplifiée pour vous permettre de passer moins de temps sur la configuration et plus de temps sur l'apprentissage [1] :

1.  **Préparation de l'entrée** : Créez un fichier Excel et listez vos mots cibles dans la première colonne (colonne A) sans ligne d'en-tête [2].
2.  **Personnalisation** : 
    *   **Langue de traduction** : Ouvrez la configuration pour définir votre langue cible pour Google Translate (par exemple : français, espagnol, persan, etc.) [2].
    *   **Sélection des dictionnaires** : Choisissez parmi les 7 dictionnaires disponibles ceux que vous souhaitez utiliser pour vos données de cartes [2].
3.  **Exécution du script** : Lancez `main_script(word_by_word).py` via votre terminal [2]. Le système utilise une logique mot par mot pour garantir que les définitions, les exemples et les médias sont collectés efficacement [2].
4.  **Importation instantanée via .apkg** : En plus des fichiers .csv et .xlsx, le script génère un fichier **.apkg** [2]. Cela permet une importation en un clic dans Anki sur Windows ou AnkiDroid sur Android, en préservant tous les styles, images et enregistrements audio [2].

### Caractéristiques principales

*   **Sept dictionnaires premium** : L'outil agrège les données de sept sources distinctes, dont Fastdic, Faraazin, Google Dictionary, Cambridge Dictionary et Dictionary.com, pour fournir les définitions les plus complètes [3].
*   **Prononciation à double accent** : Le système récupère des enregistrements audio de haute qualité avec les accents **américain et britannique** pour chaque mot [3].
*   **Apprentissage visuel automatisé** : Il récupère automatiquement des images clipart pertinentes pour chaque mot afin d'améliorer la rétention à long terme [3].
*   **Support de traduction mondiale** : Intégré à Google Translate pour supporter les traductions dans n'importe quelle langue cible [3].
*   **Traitement robuste** : Comprend une sauvegarde automatique intégrée et une capacité multi-threading pour éviter la perte de données et augmenter la vitesse de traitement des listes importantes [3].

### Architecture du système

*   **main_script(word_by_word).py** : Gère la logique centrale, le traitement par lots et l'exécution parallèle [4].
*   **scraper_functions.py** : Une bibliothèque spécialisée pour le scraping spécifique aux sites et le téléchargement de médias [4].
*   **anki_exporter.py** : Gère le formatage des données collectées en fichiers prêts pour Anki et en paquets .apkg [4].

### Prérequis
*   Python 3.x [4].
*   Google Chrome et le ChromeDriver correspondant [4].
*   Bibliothèques requises : pandas, selenium, beautifulsoup4, requests, googletrans, Pillow et python-dotenv [4].

### Clause de non-responsabilité
Cet outil est destiné à un usage personnel et éducatif uniquement. Les utilisateurs doivent respecter les conditions d'utilisation des sites Web consultés [4].
