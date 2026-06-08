import genanki
import os

# =================================================
# UNIQUE IDS (MUST REMAIN CONSTANT)
# =================================================
# These identify your model and deck in Anki. 
# If they change, Anki will create duplicates instead of updating.
MODEL_ID = 1559328410
DECK_ID = 2059400110


#####################################################################
### Name of the Deck ###
#####################################################################
name_of_the_deck = "MJB-Norwegian Words"  ### Name of the Deck ###

def generate_anki_package(df, output_path, media_folders, css_path):
    print("📦 Generating Anki Package...")
    
    # 1. Load CSS from Styles/all.css
    css_content = ""
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
    else:
        print(f"⚠️ Warning: CSS file not found at {css_path}")

    # 2. Define Model (Fields must match the order in genanki.Note)
    anki_model = genanki.Model(
        MODEL_ID,
        'Advanced Scraper Model',
        fields=[
            {'name': 'FrontField'},   # Word + Sound Tag
            #{'name': 'Audios'},       # Audio Field
            {'name': 'GoogleTrans'},  #
            #{'name': 'Images'},       #
            #{'name': 'Faraazin'},     #
            #{'name': 'BAmooz'},       #
            #{'name': 'Fastdic'},      #
            #{'name': 'Thesaurus'},
            {'name': 'Info'}    #
        ],
        #######################################################################
        ### This is where you define how the card looks in Anki. You can customize  ###
        ### the HTML structure and include/exclude fields as needed.                ###
        #######################################################################
        templates=[{
            'name': 'Norwegian Words',
            'qfmt': '<div class="front">{{FrontField}}</div>',
            'afmt': '''
                {{FrontSide}}
                <hr id=answer>
                {{GoogleTrans}}
                <hr>
                {{Info}}
            ''',
        }],
        css=css_content
    )

    # 3. Create Deck
    anki_deck = genanki.Deck(DECK_ID, name_of_the_deck) ### Name of the Deck ###

    # 4. Add Notes from DataFrame using your existing column names
    for _, row in df.iterrows():
        note = genanki.Note(
            model=anki_model,
            fields=[
                str(row['Anki_Front_Field']),                   #
                #str(row['Fastdic_Audio']),                      #
                str(row['Processed_Content_Google_Translate']), #
                #str(row['Downloaded_Images_HTML']),             #
                #str(row['Processed_Content_Faraazin_Selenium']),#
                #str(row['Processed_Content_B_Amooz']),          #
                #str(row['Processed_Content_Fastdic']),          #
                #str(row['Thesaurus_com']),                       #
                str(row['Info'])
            ]
        )
        anki_deck.add_note(note)

    # 5. Collect Media Paths (Images & Audio)
    media_files = []
    for folder in media_folders:
        if os.path.exists(folder):
            for file in os.listdir(folder):
                # Anki needs absolute paths to bundle files
                full_path = os.path.abspath(os.path.join(folder, file))
                if os.path.isfile(full_path):
                    media_files.append(full_path)

    # 6. Build and Save
    package = genanki.Package(anki_deck)
    package.media_files = media_files
    package.write_to_file(output_path)
    print(f"✅ APKG Created at: {output_path}")