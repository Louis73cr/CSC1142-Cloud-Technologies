import json
import os
import requests_cache
from retry_requests import retry
import openmeteo_requests
import pandas as pd
from datetime import datetime
import time

INPUT_FILE = "../ski-lift.json"
OUTPUT_FILE = "../ski-lift-with-snow.json"

def calculer_point_moyen(remontee):
    """Calculates the average coordinates of the downhill and uphill stations"""
    try:
        coordonnees = remontee.get("coordonnees", {})
        amont = coordonnees.get("amont", {})
        aval = coordonnees.get("aval", {})
        
        lat_amont = amont.get("lat")
        lng_amont = amont.get("lng")
        lat_aval = aval.get("lat")
        lng_aval = aval.get("lng")
        
        if lat_amont and lng_amont and lat_aval and lng_aval:
            return {
                "lat": (lat_amont + lat_aval) / 2,
                "lng": (lng_amont + lng_aval) / 2
            }
        elif lat_amont and lng_amont:
            return {"lat": lat_amont, "lng": lng_amont}
        elif lat_aval and lng_aval:
            return {"lat": lat_aval, "lng": lng_aval}
        else:
            return None
    except (KeyError, TypeError, AttributeError) as e:
        print(f"  ⚠️ Erreur calcul point moyen: {e}")
        return None

def creer_index_donnees_existantes(resultats_existants):
    """Crée un index des données existantes par station"""
    index = {}
    for resultat in resultats_existants:
        station = resultat.get("station", "")
        nom = resultat.get("nom", "")
        cle = (station, nom)
        historique = resultat.get("historique_neige", [])
        if historique and len(historique) > 0:
            index[cle] = resultat
    return index

def recuperer_neige(lat, lng, station_nom=""):
    """Récupère les données de neige depuis Open Meteo"""
    try:
        print(f"  Fetching snow data for lat={lat:.4f}, lng={lng:.4f}")
        
        cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        params = {
            "latitude": lat,
            "longitude": lng,
            "start_date": "2024-11-01",
            "end_date": "2025-04-30",
            "daily": "snowfall_sum"
        }

        responses = openmeteo.weather_api(
            "https://archive-api.open-meteo.com/v1/archive",
            params=params
        )
        response = responses[0]
        
        daily = response.Daily()
        snowfall_values = daily.Variables(0).ValuesAsNumpy()
        
        times = pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left"
        )

        df = pd.DataFrame({"date": times.date, "snowfall": snowfall_values})
        
        historique_neige = [
            {
                "date": str(row["date"]),
                "snowfall_cm": round(float(row["snowfall"]), 1) if not pd.isna(row["snowfall"]) else 0.0
            }
            for _, row in df.iterrows()
        ]

        print(f"  OK {len(historique_neige)} days of snow data retrieved")
        return historique_neige

    except Exception as e:
        print(f"  NOK Error retrieving snow data for ({lat}, {lng}): {e}")
        return None

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        remontees = json.load(f)
    print(f"{len(remontees)} lifts loaded\n")

    resultats_existants = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                resultats_existants = json.load(f)
            print(f"{len(resultats_existants)}  ski lifts with existing data\n")
        except Exception as e:
            print(f"Error loading existing data: {e}")
    
    index_existantes = creer_index_donnees_existantes(resultats_existants)
    
    resultats_dict = {cle: resultat for cle, resultat in index_existantes.items()}
    
    stats = {
        "total": 0,
        "en_service": 0,
        "sans_coordonnees": 0,
        "deja_presentes": 0,
        "nouvelles_requetes": 0,
        "requetes_ok": 0,
        "requetes_erreur": 0
    }
    
    for idx, remontee in enumerate(remontees, 1):
        appareil = remontee.get("appareil", "Inconnu")
        station = remontee.get("station", "Inconnue")
        cle = (station, appareil)
        
        stats["total"] += 1
        
        if idx % 50 == 0 or idx == len(remontees):
            print(f"Progress: {idx}/{len(remontees)} ({100*idx/len(remontees):.1f}%)")
        
        if not remontee.get("en_service", False):
            continue
        
        stats["en_service"] += 1
        
        point_moyen = calculer_point_moyen(remontee)
        if not point_moyen:
            stats["sans_coordonnees"] += 1
            continue
        
        if cle in resultats_dict:
            stats["deja_presentes"] += 1
            continue
        
        stats["nouvelles_requetes"] += 1
        print(f"\n[{idx}/{len(remontees)}] New lift: {appareil}")
        print(f"  Station: {station}")
        
        historique_neige = recuperer_neige(
            point_moyen["lat"],
            point_moyen["lng"],
            f"{station} - {appareil}"
        )
        
        if historique_neige is None:
            stats["requetes_erreur"] += 1
            continue
        
        stats["requetes_ok"] += 1
        
        resultats_dict[cle] = {
            "nom": appareil,
            "station": station,
            "coordonnees_moyennes": point_moyen,
            "historique_neige": historique_neige
        }
        
        time.sleep(0.5)
    
    resultats_finaux = list(resultats_dict.values())
    
    print(f"\nSaving results to {OUTPUT_FILE}...")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultats_finaux, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
