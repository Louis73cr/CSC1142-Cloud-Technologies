import pandas as pd
import json
import os
import folium
from folium.plugins import MarkerCluster
from folium import Icon, DivIcon, Element

script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)

csv_path = os.path.join(base_dir, "data", "remontees_a_risque.csv")
json_path = os.path.join(base_dir, "ski-lift.json")
output_path = os.path.join(base_dir, "data", "carte_remontees_interactive.html")

df_risque = pd.read_csv(csv_path)

with open(json_path, "r", encoding="utf-8") as f:
    remontees_json = json.load(f)

coords_dict = {}
remontees_all = []
for remontee in remontees_json:
    station = remontee.get("station")
    appareil = remontee.get("appareil")
    key = f"{appareil}|{station}"
    
    annee_fin_service = remontee.get("annee_fin_service")
    is_hors_service = annee_fin_service and str(annee_fin_service).strip() != ""
    
    lat, lng = None, None
    if "coordonnees" in remontee and remontee["coordonnees"]:
        coords = remontee["coordonnees"]
        if "amont" in coords and "aval" in coords:
            amont = coords.get("amont", {})
            aval = coords.get("aval", {})
            
            lat_amont = amont.get("lat") if amont else None
            lng_amont = amont.get("lng") if amont else None
            lat_aval = aval.get("lat") if aval else None
            lng_aval = aval.get("lng") if aval else None
            
            if lat_amont and lng_amont and lat_aval and lng_aval:
                lat = (lat_amont + lat_aval) / 2
                lng = (lng_amont + lng_aval) / 2
            elif lat_amont and lng_amont:
                lat = lat_amont
                lng = lng_amont
            elif lat_aval and lng_aval:
                lat = lat_aval
                lng = lng_aval
            
            if lat and lng:
                coords_dict[key] = {
                    "lat": lat,
                    "lng": lng,
                    "hors_service": is_hors_service,
                    "annee_fin_service": annee_fin_service
                }
                remontees_all.append({
                    "appareil": appareil,
                    "station": station,
                    "key": key,
                    "lat": lat,
                    "lng": lng,
                    "hors_service": is_hors_service,
                    "annee_fin_service": annee_fin_service,
                    "url_article": remontee.get("lien_reportage", "")
                })


df_all_remontees = pd.DataFrame(remontees_all)
df_hors_service = df_all_remontees[(df_all_remontees["hors_service"] == True) & 
                                    (df_all_remontees["lat"].notna()) & 
                                    (df_all_remontees["lng"].notna())]

df_risque["key"] = df_risque["appareil"] + "|" + df_risque["station"]
df_risque["lat"] = df_risque["key"].map(lambda x: coords_dict.get(x, {}).get("lat"))
df_risque["lng"] = df_risque["key"].map(lambda x: coords_dict.get(x, {}).get("lng"))

df_with_coords = df_risque.dropna(subset=["lat", "lng"])
df_sans_meteo = df_with_coords[(df_with_coords["nb_jours_mesure"].fillna(0) == 0)]
df_avec_meteo = df_with_coords[df_with_coords["nb_jours_mesure"].fillna(0) > 0]


def get_color(ratio):
    if ratio >= 0.8:
        return "red"
    elif ratio >= 0.5:
        return "orange"
    elif ratio >= 0.3:
        return "yellow"
    elif ratio >= 0.1:
        return "lightgreen"
    else:
        return "green"

def create_popup(row):
    altitude = f"{row.get('altitude_moyenne', 0):.0f}" if pd.notna(row.get('altitude_moyenne')) else "N/A"
    url_article = row.get('url_article', '')
    lien_html = ""
    if url_article and pd.notna(url_article) and str(url_article).strip() != "":
        lien_html = f"""
        <hr style="margin: 10px 0;">
        <p style="margin: 5px 0;">
            <a href="{url_article}" target="_blank" style="color: #1976d2; text-decoration: none; font-weight: bold;">
                📰 <span class="article-link">View article on Remontées-Mécaniques.net</span> →
            </a>
        </p>
        """
    
    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 280px;">
        <h3 style="margin-top: 0; color: #2c3e50; font-size: 16px; border-bottom: 2px solid #1976d2; padding-bottom: 5px;">
            {row['appareil']}
        </h3>
        <p style="margin: 8px 0; color: #555;">
            <strong>📍 <span class="popup-station">Station</span>:</strong> {row['station']}
        </p>
        <hr style="margin: 10px 0; border-color: #e0e0e0;">
        <div style="background-color: #f5f5f5; padding: 8px; border-radius: 4px; margin: 8px 0;">
            <p style="margin: 4px 0; font-size: 13px;"><strong><span class="popup-ratio">Ratio</span>:</strong> <span style="color: #d32f2f; font-weight: bold;">{row.get('ratio_jours_faible_neige', 0):.1%}</span></p>
            <p style="margin: 4px 0; font-size: 13px;"><strong><span class="popup-snow-avg">Average snow</span>:</strong> {row.get('neige_moyenne_cm', 0):.1f} cm</p>
            <p style="margin: 4px 0; font-size: 13px;"><strong><span class="popup-snow-min">Min snow</span>:</strong> {row.get('neige_min_cm', 0):.1f} cm</p>
            <p style="margin: 4px 0; font-size: 13px;"><strong><span class="popup-snow-max">Max snow</span>:</strong> {row.get('neige_max_cm', 0):.1f} cm</p>
        </div>
        <p style="margin: 5px 0; font-size: 13px;"><strong><span class="popup-altitude">Average altitude</span>:</strong> {altitude} m</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong><span class="popup-days">Low-snow days</span>:</strong> {int(row.get('jours_neige_faible', 0))} / {int(row.get('jours_total', 0))}</p>
        <p style="margin: 5px 0; font-size: 13px;"><strong><span class="popup-periods">Dry periods</span>:</strong> {int(row.get('nombre_periodes_secheresse', 0))}</p>
        {lien_html}
    </div>
    """
    return html

def create_popup_hors_service(row):
    annee = row.get('annee_fin_service', 'N/A')
    url_article = row.get('url_article', '')
    
    if (not url_article or pd.isna(url_article) or str(url_article).strip() == "") and 'key' in row:
        key = row['key']
        remontee_json = next((r for r in remontees_json if f"{r.get('appareil')}|{r.get('station')}" == key), None)
        if remontee_json:
            url_article = remontee_json.get('lien_reportage', '')
    
    lien_html = ""
    if url_article and pd.notna(url_article) and str(url_article).strip() != "":
        lien_html = f"""
        <hr style="margin: 10px 0;">
        <p style="margin: 5px 0;">
            <a href="{url_article}" target="_blank" style="color: #1976d2; text-decoration: none; font-weight: bold;">
                📰 <span class="article-link">View article on Remontées-Mécaniques.net</span> →
            </a>
        </p>
        """
    
    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 280px;">
        <h3 style="margin-top: 0; color: #d32f2f; font-size: 16px; border-bottom: 2px solid #d32f2f; padding-bottom: 5px;">
            🪦 {row['appareil']}
        </h3>
        <p style="margin: 8px 0; color: #d32f2f; font-weight: bold; background-color: #ffebee; padding: 5px; border-radius: 4px;">
            <span class="popup-rip">R.I.P. - No longer in service</span>
        </p>
        <p style="margin: 8px 0; color: #555;">
            <strong>📍 <span class="popup-station">Station</span>:</strong> {row['station']}
        </p>
        <p style="margin: 5px 0; font-size: 13px;">
            <strong><span class="popup-end-year">End of service year</span>:</strong> {annee}
        </p>
        {lien_html}
    </div>
    """
    return html

def create_popup_sans_meteo(row):
    altitude = f"{row.get('altitude_moyenne', 0):.0f}" if pd.notna(row.get('altitude_moyenne')) else "N/A"
    url_article = row.get('url_article', '')
    
    lien_html = ""
    if url_article and pd.notna(url_article) and str(url_article).strip() != "":
        lien_html = f"""
        <hr style="margin: 10px 0;">
        <p style="margin: 5px 0;">
            <a href="{url_article}" target="_blank" style="color: #1976d2; text-decoration: none; font-weight: bold;">
                📰 <span class="article-link">View article on Remontées-Mécaniques.net</span> →
            </a>
        </p>
        """
    
    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 280px;">
        <h3 style="margin-top: 0; color: #ff9800; font-size: 16px; border-bottom: 2px solid #ff9800; padding-bottom: 5px;">
            🌧️ {row['appareil']}
        </h3>
        <p style="margin: 8px 0; color: #ff9800; font-weight: bold; background-color: #fff3e0; padding: 5px; border-radius: 4px;">
            <span class="popup-no-data">No weather data available</span>
        </p>
        <p style="margin: 8px 0; color: #555;">
            <strong>📍 <span class="popup-station">Station</span>:</strong> {row['station']}
        </p>
        <p style="margin: 5px 0; font-size: 13px;">
            <strong><span class="popup-altitude">Average altitude</span>:</strong> {altitude} m
        </p>
        <p style="margin: 5px 0; font-size: 12px; color: #777; font-style: italic;">
            <span class="popup-no-snow">No snow data available for this lift</span>
        </p>
        {lien_html}
    </div>
    """
    return html

all_lats = []
all_lngs = []
if len(df_avec_meteo) > 0:
    all_lats.append(df_avec_meteo["lat"])
    all_lngs.append(df_avec_meteo["lng"])
if len(df_sans_meteo) > 0:
    all_lats.append(df_sans_meteo["lat"])
    all_lngs.append(df_sans_meteo["lng"])
if len(df_hors_service) > 0:
    all_lats.append(df_hors_service["lat"])
    all_lngs.append(df_hors_service["lng"])

if all_lats:
    center_lat = pd.concat(all_lats).mean()
    center_lng = pd.concat(all_lngs).mean()
else:
    center_lat = 46.5
    center_lng = 2.5

m = folium.Map(
    location=[center_lat, center_lng],
    zoom_start=6,
    tiles='OpenStreetMap',
    min_zoom=5,
    max_bounds=[[41.0, -5.5], [51.5, 10.5]],
    max_bounds_options={'padding': [20, 20]}
)

folium.TileLayer(
    tiles='OpenStreetMap',
    name='OpenStreetMap',
    attr='OpenStreetMap',
    overlay=False,
    control=False
).add_to(m)

folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Satellite',
    overlay=False,
    control=False
).add_to(m)

folium.TileLayer(
    tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attr='OpenTopoMap',
    name='Topographic',
    overlay=False,
    control=False
).add_to(m)

feature_groups = {
    "Very high risk (>=80%)": folium.FeatureGroup(name="Very high risk (>=80%)", show=True),
    "High risk (50-80%)": folium.FeatureGroup(name="High risk (50-80%)", show=True),
    "Moderate risk (30-50%)": folium.FeatureGroup(name="Moderate risk (30-50%)", show=True),
    "Low risk (10-30%)": folium.FeatureGroup(name="Low risk (10-30%)", show=True),
    "Very low risk (<10%)": folium.FeatureGroup(name="Very low risk (<10%)", show=True),
    "No weather data": folium.FeatureGroup(name="No weather data", show=True),
    "Out of service (RIP)": folium.FeatureGroup(name="Out of service (RIP)", show=True)
}

for fg in feature_groups.values():
    fg.add_to(m)

marker_clusters = {}
for name, fg in feature_groups.items():
    cluster = MarkerCluster(options={"maxClusterRadius": 50})
    cluster.add_to(fg)
    marker_clusters[name] = cluster

all_cluster_names = list(marker_clusters.keys())

for idx, row in df_avec_meteo.iterrows():
    ratio = row.get('ratio_jours_faible_neige', 0)
    color = get_color(ratio)
    
    if ratio >= 0.8:
        group = "Very high risk (>=80%)"
    elif ratio >= 0.5:
        group = "High risk (50-80%)"
    elif ratio >= 0.3:
        group = "Moderate risk (30-50%)"
    elif ratio >= 0.1:
        group = "Low risk (10-30%)"
    else:
        group = "Very low risk (<10%)"
    
    popup = folium.Popup(create_popup(row), max_width=300)
    
    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=8,
        popup=popup,
        color='black',
        weight=1,
        fill=True,
        fillColor=color,
        fillOpacity=0.7,
        tooltip=f"{row['appareil']} - {ratio:.1%}"
    ).add_to(marker_clusters[group])

for idx, row in df_sans_meteo.iterrows():
    popup = folium.Popup(create_popup_sans_meteo(row), max_width=300)
    
    icon_html = """
    <div style="
        width: 30px; 
        height: 30px; 
        background-color: #ff9800; 
        border-radius: 50%; 
        border: 2px solid white; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
    ">
        🌧️
    </div>
    """
    icon = DivIcon(
        html=icon_html,
        icon_size=(30, 30),
        icon_anchor=(15, 15)
    )
    
    folium.Marker(
        location=[row['lat'], row['lng']],
        popup=popup,
        icon=icon,
        tooltip=f"🌧️ {row['appareil']} - No weather data"
    ).add_to(marker_clusters["No weather data"])

for idx, row in df_hors_service.iterrows():
    popup = folium.Popup(create_popup_hors_service(row), max_width=300)
    
    icon_html = """
    <div style="
        width: 30px; 
        height: 30px; 
        background-color: #d32f2f; 
        border-radius: 50%; 
        border: 2px solid white; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
    ">
        🪦
    </div>
    """
    icon = DivIcon(
        html=icon_html,
        icon_size=(30, 30),
        icon_anchor=(15, 15)
    )
    
    marker = folium.Marker(
        location=[row['lat'], row['lng']],
        popup=popup,
        icon=icon,
        tooltip=f"🪦 {row['appareil']} - R.I.P. (End: {row.get('annee_fin_service', 'N/A')})"
    )
    marker.add_to(marker_clusters["Out of service (RIP)"])

all_markers_data_js = []

for idx, row in df_avec_meteo.iterrows():
    all_markers_data_js.append({
        "appareil": row['appareil'],
        "station": row['station'],
        "lat": float(row['lat']),
        "lng": float(row['lng']),
        "type": "active"
    })

for idx, row in df_sans_meteo.iterrows():
    all_markers_data_js.append({
        "appareil": row['appareil'],
        "station": row['station'],
        "lat": float(row['lat']),
        "lng": float(row['lng']),
        "type": "sans_meteo"
    })

for idx, row in df_hors_service.iterrows():
    all_markers_data_js.append({
        "appareil": row['appareil'],
        "station": row['station'],
        "lat": float(row['lat']),
        "lng": float(row['lng']),
        "type": "hors_service"
    })

markers_json = json.dumps(all_markers_data_js)

custom_html = """
<style>
#map-title {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 9999;
    background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
    color: white;
    padding: 16px 32px 24px 32px;
    border-bottom-left-radius: 18px;
    border-bottom-right-radius: 18px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.35);
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 24px;
    font-weight: 700;
    text-align: center;
    border: none;
}

#controls-panel {
    position: fixed;
    top: 110px;
    right: 12px;
    width: 260px;
    z-index: 9999;
    background: rgba(255, 255, 255, 0.95);
    border-radius: 14px;
    border: 1px solid #dfe3e8;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.2);
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    padding: 16px;
}

.panel-section {
    margin-bottom: 16px;
}

.panel-label {
    display: block;
    font-weight: 600;
    color: #0f172a;
    margin-bottom: 8px;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}

#lang-selector,
#map-type-selector {
    width: 100%;
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid #cbd5f5;
    font-size: 13px;
    color: #0f172a;
    background: white;
}

.legend {
    border-top: 1px solid #e5e7eb;
    padding-top: 12px;
}

.legend h4 {
    margin: 0 0 10px 0;
    font-size: 14px;
    color: #0f172a;
}

.legend-item {
    display: flex;
    align-items: center;
    margin: 6px 0;
    font-size: 13px;
    color: #1f2937;
}

.legend-color {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    margin-right: 10px;
    border: 1px solid rgba(0,0,0,0.2);
}

.legend-icon {
    font-size: 16px;
    margin-right: 10px;
}

#project-footer {
    position: fixed;
    bottom: 10px;
    right: 10px;
    z-index: 10000;
    background: rgba(15, 23, 42, 0.9);
    color: #e2e8f0;
    padding: 10px 22px;
    border-radius: 14px;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 13px;
    letter-spacing: 0.4px;
    box-shadow: 0 6px 25px rgba(0,0,0,0.35);
}
</style>

<div id='map-title'>
    <span id='title-text'>French Ski Lifts Risk Map</span>
</div>

<div id='controls-panel'>
    <div class='panel-section'>
        <label id='label-map-type' class='panel-label'>Map Type</label>
        <select id='map-type-selector'>
            <option value='OpenStreetMap' id='option-map-osm'>OpenStreetMap</option>
            <option value='Satellite' id='option-map-sat'>Satellite</option>
        </select>
    </div>
    <div class='legend'>
        <h4 id='legend-title'>Legend</h4>
        <p id='legend-ratio-definition' style='font-size: 12px; color: #666; margin: 8px 0 12px 0; line-height: 1.4; font-style: italic;'>
            Ratio: percentage of days in the operating season (11/01/2024 to 04/30/2025) when there was less than 50 cm of snow
        </p>
        <div class='legend-item'>
            <span class='legend-color' style='background:#c53030;'></span>
            <span id='legend-risk-very-high'>Very high risk (≥ 80%)</span>
        </div>
        <div class='legend-item'>
            <span class='legend-color' style='background:#d97706;'></span>
            <span id='legend-risk-high'>High risk (50-80%)</span>
        </div>
        <div class='legend-item'>
            <span class='legend-color' style='background:#facc15;'></span>
            <span id='legend-risk-medium'>Moderate risk (30-50%)</span>
        </div>
        <div class='legend-item'>
            <span class='legend-color' style='background:#a3e635;'></span>
            <span id='legend-risk-low'>Low risk (10-30%)</span>
        </div>
        <div class='legend-item'>
            <span class='legend-color' style='background:#4ade80;'></span>
            <span id='legend-risk-very-low'>Very low risk (&lt;10%)</span>
        </div>
        <div class='legend-item'>
            <span class='legend-icon'>🌧️</span>
            <span id='legend-no-meteo'>No weather data</span>
        </div>
        <div class='legend-item'>
            <span class='legend-icon'>🪦</span>
            <span id='legend-rip'>Out of service</span>
        </div>
    </div>
</div>

<div id='project-footer'>
    <span id='footer-text'>Made by Louis CROCI et Quentin LOUYOT DOSSAT | <a href='https://github.com/Louis73cr/CSC1142-Cloud-Technologies' target='_blank' style='color: #e2e8f0; text-decoration: underline;'>GitHub</a></span>
</div>

<script>
const baseLayersConfig = {
    OpenStreetMap: {
        url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: 'OpenStreetMap',
        maxZoom: 19
    },
    Satellite: {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attribution: 'Esri',
        maxZoom: 19
    }
};

function getLeafletMap() {
    if (window.map && window.map instanceof L.Map) {
        return window.map;
    }
    if (typeof map !== 'undefined' && map instanceof L.Map) {
        window.map = map;
        return window.map;
    }
    for (const key in window) {
        if (window[key] instanceof L.Map) {
            window.map = window[key];
            return window.map;
        }
    }
    return null;
}

function setBaseLayer(mapType) {
    const map = getLeafletMap();
    if (!map) return;
    const config = baseLayersConfig[mapType] || baseLayersConfig.OpenStreetMap;
    const baseLayers = [];
    map.eachLayer(function(layer) {
        if (layer instanceof L.TileLayer && !layer.options.overlay) {
            baseLayers.push(layer);
        }
    });
    baseLayers.forEach(layer => map.removeLayer(layer));
    const tileLayer = L.tileLayer(config.url, {
        attribution: config.attribution,
        maxZoom: config.maxZoom
    });
    tileLayer.addTo(map);
}

window.addEventListener('load', function() {
    setBaseLayer('OpenStreetMap');
    const mapSelector = document.getElementById('map-type-selector');
    if (mapSelector) {
        mapSelector.addEventListener('change', function() {
            setBaseLayer(mapSelector.value);
        });
    }
});
</script>
"""

m.get_root().html.add_child(Element(custom_html))

m.save(output_path)
