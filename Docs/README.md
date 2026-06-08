# Documentation: Automatic Anki Card Generator

# How to use **Automatic Anki Card Generator**

This documentation provides a technical guide for the **Automatic Anki Card Generator**, detailing its structure, configuration, and customization options.

---

## Index
- [Documentation: Automatic Anki Card Generator](#documentation-automatic-anki-card-generator)
- [How to use **Automatic Anki Card Generator**](#how-to-use-automatic-anki-card-generator)
  - [Index](#index)
  - [1. Project Architecture](#1-project-architecture)
  - [2. Environment Setup (.env \& ADDRESS)](#2-environment-setup-env--address)
  - [3. Core Configuration \& Performance](#3-core-configuration--performance)
  - [4. Customizing Scrapers \& Translation](#4-customizing-scrapers--translation)
  - [5. Anki Model \& Export Customization](#5-anki-model--export-customization)
  - [6. Troubleshooting \& Maintenance](#6-troubleshooting--maintenance)

---

## 1. Project Architecture
The software is divided into three primary modules:
* **`main_script(word_by_word).py`**: The central orchestrator that manages the input Excel file, handles the processing loop, and triggers autosaves.
* **`scraper_functions.py`**: The scraping engine containing logic for network requests, HTML parsing (BeautifulSoup), and browser automation (Selenium).
* **`anki_exporter.py`**: The export module that defines the Anki card layout (HTML/CSS) and bundles media into a final `.apkg` file.

## 2. Environment Setup (.env & ADDRESS)
The system uses a `.env` file to manage machine-specific paths and sensitive data.
* **The `ADDRESS` Variable**: This variable defines the destination directory for media syncing.
* **Media Storage**: Images and audio files are saved both to a local `Images/` or `Audio/` folder and to the path specified in the `ADDRESS` environment variable.
* **Where to modify**: Create a `.env` file in the project root and define your path: `ADDRESS=C:/Your/Anki/Media/Path`.

## 3. Core Configuration & Performance
Global settings are located at the top of `main_script(word_by_word).py`:
* **`AUTOSAVE_EVERY`**: Controls how often (in number of words) the script saves progress to CSV and Excel.
* **`ENABLE_PARALLEL`**: A boolean flag to toggle multi-threaded processing for non-Selenium scrapers.
* **`MAX_WORKERS`**: Defines the number of threads used when parallel processing is enabled.
* **`baseName`**: Specifies the name of the input Excel file the script will process.

## 4. Customizing Scrapers & Translation
Users can modify the data sources and translation logic within `scraper_functions.py`.
* **Changing Google Translate**: To change the target language, edit the `scrape_and_process_google_translate` function. Locate the `GoogleTranslator(source='en', target='fa')` line and change `'fa'` to your desired language code (e.g., `'es'` for Spanish).
* **Image Settings**: The `download_images` function uses a search query that includes the word plus the suffix "+clipart" to find relevant visuals.
* **Enabling/Disabling Sources**: In `main_script(word_by_word).py`, you can comment out specific functions inside `run_non_selenium_tasks` to skip those data sources.

## 5. Anki Model & Export Customization
The final look and feel of the flashcards are defined in `anki_exporter.py`.
* **Unique IDs**: The `MODEL_ID` and `DECK_ID` must remain constant to update existing decks, or be changed to create entirely new, separate decks in Anki.
* **Card Fields**: The model includes specific fields like `FrontField`, `Audios`, `GoogleTrans`, `Images`, and `Thesaurus`.
* **HTML Templates**: You can modify the `qfmt` (Question Format) and `afmt` (Answer Format) within the `anki_model` to rearrange how data appears on your cards.
* **CSS Styling**: The script imports styling from `Styles/all.css` to manage the visual presentation.

## 6. Troubleshooting & Maintenance
* **ChromeDriver**: Selenium functions (like Faraazin) require `chromedriver.exe` to be located in a `chromedriver-win64` folder within the script directory.
* **Network Safety**: The `safe_get` function implements a random delay (3-6 seconds) and a retry policy to prevent IP blocking.
* **Empty Folders**: Note that while the script creates folders, Anki generally requires them to contain files to be included in the package.