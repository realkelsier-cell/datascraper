# api/index.py
from flask import Flask, send_file, request, jsonify
import pandas as pd
import requests
import zipfile
import io
import os
from datetime import datetime

app = Flask(__name__, static_folder='../public')

# === CONFIG ===
NPPES_URL = "https://download.cms.gov/nppes/NPPES_Data_Dissemination_November_2025.zip"
CSV_CACHE = "/tmp/psychiatrists_global.csv"
CACHE_TIME = 24 * 60 * 60  # 24 hours

# Psychiatry taxonomy codes (USA)
PSY_CODES = [
    "2084P0800X", "2084P0804X", "2084P0802X", "2084P0805X",
    "2084P0015X", "2084F0202X", "2084P2900X", "2084S0012X",
    "2084N0400X", "2084B0002X"
]

# Country data sources (only real open bulk)
COUNTRIES = {
    "USA": {
        "url": NPPES_URL,
        "type": "nppes",
        "enabled": True
    },
    "UK": {
        "enabled": False,
        "note": "GMC: No free bulk CSV. Manual export: https://www.gmc-uk.org/registration-and-licensing/the-medical-register"
    },
    "Australia": {
        "enabled": False,
        "note": "AHPRA: Public register search only. No bulk CSV."
    },
    "France": {
        "enabled": False,
        "note": "Ordre des Médecins: No open bulk data."
    },
    "Germany": {
        "enabled": False,
        "note": "KBV/Ärztekammer: No open bulk CSV."
    }
}

def generate_usa():
    resp = requests.get(NPPES_URL, stream=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_file = [f for f in z.namelist() if "npidata_pfile" in f][0]
        df = pd.read_csv(z.open(csv_file), dtype=str, low_memory=False)
    
    mask = (
        (df['Entity_Type_Code'] == '1') &
        (df['Healthcare_Provider_Primary_Taxonomy_Switch_1'] == 'Y') &
        (df['Healthcare_Provider_Taxonomy_Code_1'].isin(PSY_CODES))
    )
    psych = df[mask].copy()

    tax_map = {
        "2084P0800X": "Psychiatry",
        "2084P0804X": "Child & Adolescent Psychiatry",
        "2084P0802X": "Addiction Psychiatry",
        "2084P0805X": "Geriatric Psychiatry",
        "2084P0015X": "Psychosomatic Medicine",
        "2084F0202X": "Forensic Psychiatry",
        "2084P2900X": "Pain Medicine",
        "2084S0012X": "Sleep Medicine",
    }
    psych['occupation'] = psych['Healthcare_Provider_Taxonomy_Code_1'].map(tax_map).fillna("Psychiatry")
    psych['name'] = (
        psych['Provider_First_Name'].fillna('') + " " +
        psych['Provider_Middle_Name'].fillna('').str[0] + ". " +
        psych['Provider_Last_Name_(Legal_Business_Name)'].fillna('') + " MD"
    ).str.strip().str.upper()
    
    result = psych[['name', 'Provider_NPI', 'occupation']].rename(columns={'Provider_NPI': 'license_id'})
    result['email'] = psych['Provider_Business_Practice_Location_Email_Address'].fillna('')
    result['country'] = 'USA'
    result['source'] = 'CMS NPPES'
    return result[['name', 'country', 'occupation', 'license_id', 'source', 'email']]

@app.route('/')
def home():
    return send_file('../public/index.html')

@app.route('/api/countries')
def get_countries():
    return jsonify(COUNTRIES)

@app.route('/api/generate')
def generate():
    include_email = request.args.get('email', 'true').lower() == 'true'
    selected = request.args.get('countries', 'USA').split(',')

    if not any(c in COUNTRIES and COUNTRIES[c]['enabled'] for c in selected):
        return jsonify({"error": "No valid countries selected"}), 400

    dfs = []
    if 'USA' in selected and COUNTRIES['USA']['enabled']:
        df = generate_usa()
        if not include_email:
            df = df.drop(columns=['email'])
        dfs.append(df)

    final = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    final = final.drop_duplicates(subset='license_id')

    # Cache
    os.makedirs("/tmp", exist_ok=True)
    final.to_csv(CSV_CACHE, index=False)

    return send_file(
        CSV_CACHE,
        as_attachment=True,
        download_name=f"psychiatrists_global_{datetime.now().strftime('%Y%m%d')}.csv",
        mimetype='text/csv'
    )

if __name__ == '__main__':
    app.run()
