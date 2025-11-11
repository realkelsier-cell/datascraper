# api/index.py
from flask import Flask, send_file, request
import pandas as pd, requests, zipfile, io, os
from datetime import datetime

app = Flask(__name__, static_folder='../public')

# === CONFIG ===
NPPES_URL = "https://download.cms.gov/nppes/NPPES_Data_Dissemination_November_2025.zip"
CACHE_FILE = "/tmp/usa_psychiatrists_full.csv"
PSY_TAXONOMY = [
    "2084P0800X","2084P0804X","2084P0802X","2084P0805X",
    "2084P0015X","2084F0202X","2084P2900X","2084S0012X",
    "2084N0400X","2084B0002X"
]

# === BUILD FULL DATASET ONCE ===
def build_full():
    if os.path.exists(CACHE_FILE):
        return CACHE_FILE

    print("Downloading NPPES ZIP...")
    r = requests.get(NPPES_URL, stream=True)
    r.raise_for_status()

    print("Extracting CSV...")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [f for f in z.namelist() if "npidata_pfile" in f][0]
        df = pd.read_csv(z.open(csv_name), dtype=str, low_memory=False)

    print(f"Loaded {len(df):,} providers. Filtering psychiatrists...")

    mask = (
        (df['Entity_Type_Code'] == '1') &
        (df['Healthcare_Provider_Primary_Taxonomy_Switch_1'] == 'Y') &
        (df['Healthcare_Provider_Taxonomy_Code_1'].isin(PSY_TAXONOMY))
    )
    psych = df[mask].copy()

    # Occupation mapping
    occ_map = {
        "2084P0800X":"Psychiatry",
        "2084P0804X":"Child & Adolescent Psychiatry",
        "2084P0802X":"Addiction Psychiatry",
        "2084P0805X":"Geriatric Psychiatry",
        "2084P0015X":"Psychosomatic Medicine",
        "2084F0202X":"Forensic Psychiatry",
        "2084P2900X":"Pain Medicine",
        "2084S0012X":"Sleep Medicine",
    }
    psych['occupation'] = psych['Healthcare_Provider_Taxonomy_Code_1'].map(occ_map).fillna("Psychiatry")

    # Full name
    psych['name'] = (
        psych['Provider_First_Name'].fillna('') + " " +
        psych['Provider_Middle_Name'].fillna('').str[:1] + ". " +
        psych['Provider_Last_Name_(Legal_Business_Name)'].fillna('') + " MD"
    ).str.strip().str.replace(r'\s+', ' ', regex=True).str.upper()

    # Final columns
    out = psych[['name','Provider_NPI','occupation']].rename(columns={'Provider_NPI':'license_id'})
    out['email'] = psych['Provider_Business_Practice_Location_Email_Address'].fillna('')
    out['country'] = 'USA'
    out['source'] = 'CMS NPPES'
    out['state'] = psych['Provider_Business_Practice_Location_Address_State_Name'].fillna('Unknown')
    out = out[['name','country','state','occupation','license_id','source','email']]
    out = out.drop_duplicates(subset='license_id')

    os.makedirs("/tmp", exist_ok=True)
    out.to_csv(CACHE_FILE, index=False)
    print(f"Saved {len(out):,} psychiatrists to cache.")
    return CACHE_FILE

# === ROUTES ===
@app.route('/')
def home():
    return send_file('../public/index.html')

@app.route('/download')
def download():
    state = request.args.get('state', '').strip().upper()
    include_email = request.args.get('email', 'true').lower() == 'true'

    csv_path = build_full()
    df = pd.read_csv(csv_path)

    # Filter by state
    if state and state != 'ALL':
        df = df[df['state'].str.upper() == state]

    # Remove email if not wanted
    if not include_email and 'email' in df.columns:
        df = df.drop(columns=['email'])

    temp_file = "/tmp/usa_psychiatrists_filtered.csv"
    df.to_csv(temp_file, index=False)

    filename = f"usa_psychiatrists_{state.lower() if state != 'ALL' else 'all'}_{datetime.now():%Y%m%d}.csv"
    return send_file(temp_file, as_attachment=True, download_name=filename, mimetype='text/csv')

if __name__ == '__main__':
    app.run()
