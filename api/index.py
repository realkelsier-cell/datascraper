# api/index.py
from flask import Flask, send_file, request
import pandas as pd, requests, zipfile, io, os
from datetime import datetime

app = Flask(__name__, static_folder='../public')

# Config
NPPES_URL = "https://download.cms.gov/nppes/NPPES_Data_Dissemination_November_2025.zip"
CACHE_FILE = "/tmp/usa_psychiatrists.csv"
PSY_TAXONOMY = [
    "2084P0800X","2084P0804X","2084P0802X","2084P0805X",
    "2084P0015X","2084F0202X","2084P2900X","2084S0012X",
    "2084N0400X","2084B0002X"
]

def build_csv():
    if os.path.exists(CACHE_FILE):
        return CACHE_FILE

    r = requests.get(NPPES_URL, stream=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [f for f in z.namelist() if "npidata_pfile" in f][0]
        df = pd.read_csv(z.open(csv_name), dtype=str, low_memory=False)

    mask = (
        (df['Entity_Type_Code'] == '1') &
        (df['Healthcare_Provider_Primary_Taxonomy_Switch_1'] == 'Y') &
        (df['Healthcare_Provider_Taxonomy_Code_1'].isin(PSY_TAXONOMY))
    )
    psych = df[mask].copy()

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

    psych['name'] = (
        psych['Provider_First_Name'].fillna('') + " " +
        psych['Provider_Middle_Name'].fillna('').str[0] + ". " +
        psych['Provider_Last_Name_(Legal_Business_Name)'].fillna('') + " MD"
    ).str.strip().str.upper()

    out = psych[['name','Provider_NPI','occupation']].rename(columns={'Provider_NPI':'license_id'})
    out['email'] = psych['Provider_Business_Practice_Location_Email_Address'].fillna('')
    out['country'] = 'USA'
    out['source'] = 'CMS NPPES'
    out = out[['name','country','occupation','license_id','source','email']]
    out = out.drop_duplicates(subset='license_id')

    os.makedirs("/tmp", exist_ok=True)
    out.to_csv(CACHE_FILE, index=False)
    return CACHE_FILE

@app.route('/')
def home():
    return send_file('../public/index.html')

@app.route('/download')
def download():
    include_email = request.args.get('email', 'true').lower() == 'true'
    csv_path = build_csv()
    df = pd.read_csv(csv_path)
    if not include_email:
        df = df.drop(columns=['email'])
    temp = "/tmp/usa_psychiatrists_temp.csv"
    df.to_csv(temp, index=False)
    return send_file(
        temp,
        as_attachment=True,
        download_name=f"usa_psychiatrists_{datetime.now():%Y%m%d}.csv",
        mimetype='text/csv'
    )

if __name__ == '__main__':
    app.run()
