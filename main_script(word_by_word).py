import pandas as pd
import os
import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from wakepy import keep
from anki_exporter import generate_anki_package 
import warnings
warnings.filterwarnings("ignore", module="genanki.note")

from scraper_functions import (
    scrape_and_process_fastdic,
    scrape_and_process_faraazin_with_selenium,
    scrape_and_process_google_translate,
    download_images,
    scrape_and_process_google_define_with_selenium,
    scrape_and_process_cambridge_define_with_selenium,
    scrape_and_process_dictionary_com,
    scrape_and_process_thesaurus_com,
    scrape_and_process_fastdic_audio,
    scrape_and_process_b_amooz,
    scrape_and_process_google_tts_audio
)

# =================================================
# CONFIGURATION
# =================================================
AUTOSAVE_EVERY = 5          # 💾 autosave every N words
ENABLE_PARALLEL = False     # ⚡ turn parallel ON/OFF
MAX_WORKERS = 3            # threads for non-selenium tasks
#TIMEOUT_SECONDS = 30       # ⏱ timeout for non-selenium tasks   

# =================================================
# PATHS
# =================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "Output")
os.makedirs(output_dir, exist_ok=True)

# =================================================
# INFO
# =================================================
info_text = """
<div class="container text-center" style="max-width: 800px; margin: 40px auto; padding: 20px;">
    <div class="card">
        <div class="card-body">
            <p style="font-size: 1.1rem; margin-bottom: 1rem;">
                This deck was created using <strong>Anki Automatic Word Generator</strong>.
            </p>
            <div style="margin: 1.5rem 0;">
                <a href="https://github.com/mjbahonar/Meaning-Ankidroid" 
                   target="_blank" 
                   class="tappable"
                   ontouchstart=""
                   style="display: inline-block; padding: .6rem 1.2rem; background: #007bff; color: #fff; border-radius: .35rem; text-decoration: none; font-size: 1.1rem;">
                    Create your own deck → Just give the app your word list
                </a>
            </div>
        </div>
    </div>
</div>
"""

# =================================================
# INPUT FILE
# =================================================
baseName = "New Words"
excel_file_path = os.path.join(script_dir, baseName + ".xlsx")
df = pd.read_excel(excel_file_path, header=None, names=["Words"])

# =================================================
# OUTPUT COLUMNS
# =================================================
COLUMNS = [
    #"Fastdic_Audio",
    #"Processed_Content_Google_Translate",
    #"Downloaded_Images_HTML",
    #"Processed_Content_Faraazin_Selenium",
    #"Processed_Content_B_Amooz",          
    #"Processed_Content_Fastdic",
    #"Dictionary_com",
    #"Thesaurus_com",
    #"Processed_Content_Google_Define_Selenium_processed",
    #"Processed_Content_Cambridge_Define_Selenium",
    "Anki_US_Sound_Tag",       
    "Anki_NO_Sound_Tag",
    "Anki_Front_Field" ,
    "Info"       

]

for col in COLUMNS:
    df[col] = ""

# =================================================
# AUTOSAVE FUNCTION (Updated to include CSV)
# =================================================
def autosave(df, suffix="autosave"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Save Excel for human review
    excel_path = os.path.join(output_dir, f"{suffix}_{timestamp}_{baseName}.xlsx")
    df.to_excel(excel_path, index=False)
    
    # Save CSV for Anki/Recovery (UTF-8 with BOM for Persian/Special chars)
    csv_path = os.path.join(output_dir, f"{suffix}_{timestamp}_{baseName}.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    
    print(f"\n💾 Autosaved (Excel & CSV): {timestamp}")

# =================================================
# NON-SELENIUM TASK MAP
# =================================================
def run_non_selenium_tasks(word, word_number):
    # Only use Google Translate (Norwegian -> English) and Info
    return {
        "Processed_Content_Google_Translate": scrape_and_process_google_translate(word, word_number),
        # Generate Norwegian TTS and return HTML audio tag (also saves files)
        "gTTS Audio": scrape_and_process_google_tts_audio(word, word_number),
        "Info": info_text
    }

# =================================================
# MAIN LOOP (WORD BY WORD)
# =================================================


# The 'keep.running()' context manager prevents the PC from sleeping
with keep.running():
    print("🚀 Keep-awake mode activated. Starting process...")
    processed_count = 0

    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing words"):
        word = str(row["Words"]).strip()
        word_number = idx + 1

        if not word or word.lower() == "nan":
            continue

        print(f"\n▶ WORD {word_number}: {word}")

        # -------------------------------
        # NON-SELENIUM (PARALLEL OPTIONAL)
        # -------------------------------
        if ENABLE_PARALLEL:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future = executor.submit(run_non_selenium_tasks, word, word_number)
                results = future.result()
        else:
            results = run_non_selenium_tasks(word, word_number)
 
        for col, value in results.items():
            df.at[idx, col] = value

        # -------------------------------
        # POST-PROCESSING FOR ANKI (NEW STEP)
        # -------------------------------
        # 1. Manually construct the sound tag for US pronunciation.
        #    We rely on the scraper function having already downloaded the file.
        
        # Construct the filename structure: fastdic_word_us.mp3
        safe_word = word.replace(' ', '_') # Filename should use underscores if it has spaces
        filename = f"google_no_{safe_word}.mp3"
        
        # Construct the Anki sound tag: [sound:filename]
        anki_sound_tag = f"[sound:{filename}]"
        
        # 2. Store the sound tag in the new dedicated column
        df.at[idx, "Anki_US_Sound_Tag"] = anki_sound_tag
        
        # 3. Create the final Anki Front Field (Sound Tag + Word)
        # This column will be mapped to the Front Field of your Anki card.
        df.at[idx, "Anki_Front_Field"] = f"{word} {anki_sound_tag}"    

        # Selenium-based scrapers are disabled; only Google Translate is used.
        #df.at[idx, "Processed_Content_Google_Define_Selenium_processed"] = (scrape_and_process_google_define_with_selenium(word, word_number))
        #df.at[idx, "Processed_Content_Cambridge_Define_Selenium"] = (scrape_and_process_cambridge_define_with_selenium(word, word_number))

        processed_count += 1

        # -------------------------------
        # AUTOSAVE CHECK
        # -------------------------------
        if processed_count % AUTOSAVE_EVERY == 0:
            autosave(df)
        
    print("✅ Process complete. PC is now allowed to sleep again.")

# =================================================
# FINAL SAVE
# =================================================
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

final_excel = os.path.join(
    output_dir,
    f"output_{timestamp}_{baseName}.xlsx"
)

final_csv = os.path.join(
    output_dir,
    f"output_{timestamp}_{baseName}.csv"
)

df.to_excel(final_excel, index=False)
df.to_csv(final_csv, index=False, encoding="utf-8-sig")


print("\n" + "=" * 60)
print("✅ PROCESS COMPLETED SUCCESSFULLY")
print(f"Excel saved to: {final_excel}")
print(f"CSV saved to  : {final_csv}")
print("=" * 60)


# Define paths for the Anki function
media_folders = [
    os.path.join(script_dir, "Images"), #
    os.path.join(script_dir, "Audio")   #
]
css_file = os.path.join(script_dir, "Styles", "all.css")
apkg_output = os.path.join(output_dir, f"output_{timestamp}_{baseName}.apkg") #

# Call the function from the new file
generate_anki_package(df, apkg_output, media_folders, css_file)