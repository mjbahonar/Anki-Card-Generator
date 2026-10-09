🌏 Read me in [Farsi](README_fa.md)

# Automatic Anki Card Generator: The Automated Vocabulary Card Architect

### Norwegian edition — V3.6N

The `Norwegian-to-English` branch generates Norwegian cards with Lexin first, Google Translate (Norwegian → Persian) second, and Dict.com third. Lexin retains the first exact Bokmål headword, its definitions, inflection tables, examples, idioms and compounds. The front uses Lexin's synthesized headword pronunciation, with Google TTS as a fallback. Inflection and compound audio is not downloaded.

Run `main_script(word_by_word).py` with a headerless `New Words.xlsx`. Results are saved in `Output` as Excel, CSV and an Anki package with bundled audio. Lexin and Dict.com use Playwright to load their JavaScript content. Install the dependencies in `requirements.txt` and the Playwright Chromium browser (`python -m playwright install chromium`).

See [V3.6N release notes](CHANGELOG.md) for changes, validation and known limitations. The English features described below refer to the earlier English edition.

![](Docs/English.png)

Meaning-Ankidroid is a professional-grade Python utility designed to transform a simple list of words into rich, multimedia-enhanced flashcards. Automating data collection from 7 premium dictionaries and high-quality media sources allows language learners to focus on memorization rather than card creation.

### Usage

Getting started is streamlined to ensure you spend less time on configuration and more time on learning:

1.  **Prepare Your Input**: Create an Excel file and list your target words in the first column (Column A) without a header row.
2.  **Customize Your Experience**: 
    *   **Translation Language**: Open the configuration to set your target language for Google Translate (e.g., Spanish, French, Persian, etc.).
    *   **Dictionary Selection**: Choose which of the 7 available dictionaries you wish to use for your card data.
3.  **Execute the Script**: Run `main_script(word_by_word).py` via your terminal. The system uses word-by-word logic to ensure definitions, examples, and media are gathered efficiently.
4.  **Instant Import via .apkg**: In addition to .csv and .xlsx files, the script generates an **.apkg** file. This allows for a one-click import into Anki on Windows or AnkiDroid on Android, with all styles, images, and audio recordings preserved.

### Key Features

*   **Seven Premium Dictionaries**: The tool aggregates data from seven distinct sources, including Fastdic, Faraazin, Google Dictionary, Cambridge Dictionary, and Dictionary.com, to provide the most comprehensive definitions.
*   **Dual-Accent Pronunciation**: The system retrieves high-quality audio recordings in both **US and UK accents** for every word.
*   **Automated Visual Learning**: It automatically fetches relevant clipart images for each word to improve long-term retention.
*   **Global Translation Support**: Integrated with Google Translate to support translations into any target language.
*   **Robust Processing**: Features an integrated autosave and multi-threading capability to prevent data loss and increase processing speed for large word lists.

### System Architecture

*   **main_script(word_by_word).py**: Manages core logic, batch processing, and parallel execution.
*   **scraper_functions.py**: A specialized library for site-specific scraping and media downloads.
*   **anki_exporter.py**: Handles the formatting of gathered data into Anki-ready files and .apkg packages.

### Prerequisites

*   Python 3.x
*   Google Chrome and matching ChromeDriver.
*   Required Libraries: pandas, selenium, beautifulsoup4, requests, googletrans, Pillow, and python-dotenv.

### Disclaimer

This tool is intended for personal and educational use only. Users should respect the terms of service of the websites being accessed.
