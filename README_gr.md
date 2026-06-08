# Meaning-Ankidroid: Der automatisierte Vokabelkarten-Architekt

**Meaning-Ankidroid** ist ein professionelles Python-Dienstprogramm, das entwickelt wurde, um eine einfache Liste von Wörtern in reichhaltige, multimediale Flashcards zu verwandeln [1]. Die Automatisierung der Datenerfassung aus 7 Premium-Wörterbüchern und hochwertigen Medienquellen ermöglicht es Sprachlernenden, sich auf das Auswendiglernen statt auf die Erstellung von Karten zu konzentrieren [1].

### Nutzung

Der Einstieg ist optimiert, damit Sie weniger Zeit mit der Konfiguration und mehr Zeit mit dem Lernen verbringen [1]:

1.  **Eingabe vorbereiten**: Erstellen Sie eine Excel-Datei und listen Sie Ihre Zielwörter in der ersten Spalte (Spalte A) ohne Kopfzeile auf [2].
2.  **Erfahrung anpassen**: 
    *   **Übersetzungssprache**: Öffnen Sie die Konfiguration, um Ihre Zielsprache für Google Translate festzulegen (z. B. Deutsch, Französisch, Spanisch, Persisch usw.) [2].
    *   **Wörterbuch-Auswahl**: Wählen Sie aus, welche der 7 verfügbaren Wörterbücher Sie für Ihre Kartendaten verwenden möchten [2].
3.  **Skript ausführen**: Führen Sie `main_script(word_by_word).py` über Ihr Terminal aus [2]. Das System verwendet eine Wort-für-Wort-Logik, um sicherzustellen, dass Definitionen, Beispiele und Medien effizient gesammelt werden [2].
4.  **Sofort-Import via .apkg**: Zusätzlich zu .csv- und .xlsx-Dateien generiert das Skript eine **.apkg**-Datei [2]. Dies ermöglicht einen Ein-Klick-Import in Anki unter Windows oder AnkiDroid unter Android, wobei alle Stile, Bilder und Audioaufnahmen erhalten bleiben [2].

### Hauptmerkmale

*   **Sieben Premium-Wörterbücher**: Das Tool aggregiert Daten aus sieben verschiedenen Quellen, darunter Fastdic, Faraazin, Google Dictionary, Cambridge Dictionary und Dictionary.com, um die umfassendsten Definitionen bereitzustellen [3].
*   **Aussprache mit doppeltem Akzent**: Das System ruft hochwertige Audioaufnahmen in sowohl **US- als auch UK-Akzenten** für jedes Wort ab [3].
*   **Automatisiertes visuelles Lernen**: Relevante Clipart-Bilder werden automatisch für jedes Wort abgerufen, um die langfristige Merkfähigkeit zu verbessern [3].
*   **Globale Übersetzungsunterstützung**: Integriert in Google Translate, um Übersetzungen in jede Zielsprache zu unterstützen [3].
*   **Robuste Verarbeitung**: Verfügt über eine integrierte automatische Speicherung (Autosave) und Multi-Threading-Funktion, um Datenverlust zu verhindern und die Verarbeitungsgeschwindigkeit für große Wortlisten zu erhöhen [3].

### Systemarchitektur

*   **main_script(word_by_word).py**: Verwalte die Kernlogik, die Stapelverarbeitung und die parallele Ausführung [4].
*   **scraper_functions.py**: Eine spezialisierte Bibliothek für seiten-spezifisches Scraping und Medien-Downloads [4].
*   **anki_exporter.py**: Übernimmt die Formatierung der gesammelten Daten in anki-bereite Dateien und .apkg-Pakete [4].

### Voraussetzungen
*   Python 3.x [4].
*   Google Chrome und passender ChromeDriver [4].
*   Erforderliche Bibliotheken: pandas, selenium, beautifulsoup4, requests, googletrans, Pillow und python-dotenv [4].

### Haftungsausschluss
Dieses Tool ist nur für den persönlichen und pädagogischen Gebrauch bestimmt. Nutzer sollten die Nutzungsbedingungen der aufgerufenen Websites respektieren [4].
