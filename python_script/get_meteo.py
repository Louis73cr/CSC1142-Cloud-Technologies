import json
import requests_cache
from retry_requests import retry
import openmeteo_requests
import pandas as pd
from datetime import datetime
import time

with open("remontees_mecaniques.json", "r", encoding="utf-8") as f:
    remontees = json.load(f)

def calculer_point_moyen(remontee):
    try:
        lat_amont = remontee["coordonnees"]["amont"]["lat"]
        lng_amont = remontee["coordonnees"]["amont"]["lng"]
        lat_aval = remontee["coordonnees"]["aval"]["lat"]
        lng_aval = remontee["coordonnees"]["aval"]["lng"]
        return {"lat": (lat_amont + lat_aval)/2, "lng": (lng_amont + lng_aval)/2}
    except (KeyError, TypeError):
        return None

def recuperer_neige(lat, lng):
    try:
        print(f"\n🔍 Récupération données pour lat={lat:.4f}, lng={lng:.4f}")
        
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
            {"date": str(row["date"]), "snowfall_cm": round(float(row["snowfall"]), 1) if not pd.isna(row["snowfall"]) else None}
            for _, row in df.iterrows()
        ]

        return historique_neige

    except Exception as e:
        print(f"❌ Erreur récupération neige pour ({lat}, {lng}): {e}")
        return None

resultats = []
for idx, remontee in enumerate(remontees, 1):
    print(f"Traitement {idx}/{len(remontees)}: {remontee.get('appareil','Inconnu')}...")
    if not remontee.get("en_service", False):
        continue
    point_moyen = calculer_point_moyen(remontee)
    if not point_moyen:
        continue
    historique_neige = recuperer_neige(point_moyen["lat"], point_moyen["lng"])
    if historique_neige is None:
        continue
    resultats.append({
        "nom": remontee.get("appareil","Inconnu"),
        "station": remontee.get("station","Inconnue"),
        "coordonnees_moyennes": point_moyen,
        "historique_neige": historique_neige
    })

with open("remontees_avec_snowfall.json", "w", encoding="utf-8") as f:
    json.dump(resultats, f, indent=2, ensure_ascii=False)

print(f"Fin du traitement {len(resultats)} remontées sauvegardées.")