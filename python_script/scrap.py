import requests
from bs4 import BeautifulSoup
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import logging
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraping.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


base_url = "https://www.remontees-mecaniques.net"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.remontees-mecaniques.net/'
}

departements = [
    ("/bdd/liste-3-1.html", "France"),
]


data_complete = []
data_lock = Lock()

stats = {
    'total': 0,
    'complete': 0,
    'incomplete': 0,
    'errors': 0
}
stats_lock = Lock()

def create_session():
    """Creates a new session for each thread"""
    session = requests.Session()
    session.headers.update(headers)
    return session


def extract_coordinates_from_js(soup):
    """Extracts GPS coordinates from the map JavaScript"""
    coords = {'amont': {}, 'aval': {}}
    
    script_tags = soup.find_all('script', string=re.compile('positionLat'))
    for script in script_tags:
        script_text = script.string
        if not script_text:
            continue
        
        pattern = r'positionLat\s*=\s*([\d.-]+);\s*positionLng\s*=\s*([\d.-]+);.*?message=".*?<span.*?>(.*?)</span>.*?<br/>\((.*?)\)'
        
        matches = re.finditer(pattern, script_text, re.DOTALL)
        
        for match in matches:
            lat = float(match.group(1))
            lng = float(match.group(2))
            gare_type = match.group(4).strip()
            
            if 'Amont' in gare_type:
                coords['amont'] = {'lat': lat, 'lng': lng}
            elif 'Aval' in gare_type:
                coords['aval'] = {'lat': lat, 'lng': lng}
    
    return coords if (coords['amont'] or coords['aval']) else None


def extract_banniere(soup):
    """Extracts the banner image name"""
    banniere_img = soup.find('img', src=re.compile(r'banniere-'))
    if banniere_img:
        src = banniere_img.get('data-original') or banniere_img.get('src')
        if src:
            match = re.search(r'banniere-([^/]+\.(?:jpg|JPG|png|PNG))', src)
            if match:
                return match.group(0)
    return None


def extract_detail_info(soup):
    """Extracts detailed information - CORRECTED VERSION"""
    info = {}
    
    desc_div = soup.find('div', class_='reportage_entete_description')
    if desc_div:
        text = desc_div.get_text()
        
        year_match = re.search(r'Année de construction\s*:\s*(\d{4})', text)
        if year_match:
            info['annee_construction'] = year_match.group(1)
        
        fin_match = re.search(r'Année de fin de service[^:]*:\s*(\d{4})', text)
        if fin_match:
            info['annee_fin_service'] = fin_match.group(1)
        
        destruction_match = re.search(r'Année de destruction\s*:\s*(\d{4})', text)
        if destruction_match:
            info['annee_fin_service'] = destruction_match.group(1)
    
    content_div = soup.find('div', class_='reportage_content')
    if content_div:
        ul_tags = content_div.find_all('ul')
        
        for ul in ul_tags:
            items = ul.find_all('li')
            for item in items:
                full_text = item.get_text()
                
                strong_tag = item.find('strong')
                if strong_tag:
                    key_text = strong_tag.get_text().strip()
                    value_text = full_text.replace(key_text, '').strip()
                    value_text = re.sub(r'^:\s*', '', value_text).strip()
                    
                    if not value_text:
                        continue
                    
                    if 'Saison d\'exploitation' in key_text or 'Saison d\'exploitation' in key_text:
                        info['saison_exploitation'] = value_text
                    elif 'Débit' in key_text and 'montée' not in key_text.lower():
                        info['debit'] = value_text
                    elif 'Vitesse d\'exploitation' in key_text or 'Vitesse d\'exploitation' in key_text:
                        info['vitesse_exploitation'] = value_text
                    elif 'Capacité' in key_text:
                        info['capacite'] = value_text
                    elif 'Altitude aval' in key_text:
                        info['altitude_aval'] = value_text
                    elif 'Altitude amont' in key_text:
                        info['altitude_amont'] = value_text
                    elif 'Longueur développée' in key_text or 'Longueur développée' in key_text:
                        info['longueur_developpee'] = value_text
                    elif 'Dénivelée' in key_text or 'Dénivelée' in key_text:
                        info['denivelee'] = value_text
                    elif 'Pente moyenne' in key_text:
                        info['pente_moyenne'] = value_text
                    elif 'Pente maximale' in key_text:
                        info['pente_max'] = value_text
                    elif 'Puissance développée' in key_text or 'Puissance développée' in key_text:
                        info['puissance_developpee'] = value_text
                    elif 'Type de gare' in key_text:
                        info['type_gare'] = value_text
                    elif 'Emplacement motrice' in key_text:
                        info['emplacement_motrice'] = value_text
                    elif 'Emplacement tension' in key_text:
                        info['emplacement_tension'] = value_text
                    elif 'Type de tension' in key_text:
                        info['type_tension'] = value_text
                    elif 'Sens de montée' in key_text or 'Sens de montée' in key_text:
                        info['sens_montee'] = value_text
                    elif 'Type d\'embarquement' in key_text or 'Type d\'embarquement' in key_text:
                        info['type_embarquement'] = value_text
                    elif 'Nombre de pylônes' in key_text or 'Nombre de pylônes' in key_text:
                        info['nombre_pylones'] = value_text
                    elif 'Particularités' in key_text or 'Particularités' in key_text:
                        info['particularites'] = value_text
                    elif 'Temps de trajet' in key_text:
                        info['temps_trajet'] = value_text
    
    detail_list = soup.find('ul', class_='reportage_detail')
    if detail_list:
        items = detail_list.find_all('li')
        for item in items:
            text = item.get_text()
            
            patterns = {
                'saison_exploitation': r"Saison d['']exploitation\s*:\s*([^\n]+)",
                'debit_montee': r'Débit.*?montée\s*:\s*([^\n]+)',
                'vitesse_exploitation': r'Vitesse.*?exploitation\s*:\s*([^\n]+)',
                'capacite': r'Capacité\s*:\s*([^\n]+)',
                'altitude_aval': r'Altitude aval\s*:\s*([^\n]+)',
                'altitude_amont': r'Altitude amont\s*:\s*([^\n]+)',
                'longueur_developpee': r'Longueur développée\s*:\s*([^\n]+)',
                'puissance_developpee': r'Puissance développée\s*:\s*([^\n]+)'
            }
            
            for key, pattern in patterns.items():
                if key not in info:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        info[key] = match.group(1).strip()
    
    if content_div:
        html_content = str(content_div)
        
        patterns_html = {
            'annee_construction': [
                r'<strong>Année de construction</strong>\s*:\s*(\d{4})',
                r'<strong>Ann&#233;e de construction</strong>\s*:\s*(\d{4})'
            ],
            'annee_fin_service': [
                r'<strong>Année de (?:destruction|fin de service)</strong>\s*:\s*(\d{4})',
                r'<strong>Ann&#233;e de (?:destruction|fin de service)</strong>\s*:\s*(\d{4})'
            ],
            'saison_exploitation': [
                r'<strong>Saison d[\'&#39;]exploitation</strong>\s*:\s*([^<\n]+)',
                r'<strong>Saison d&#39;exploitation</strong>\s*:\s*([^<\n]+)'
            ],
            'capacite': [
                r'<strong>Capacité</strong>\s*:\s*([^<\n]+)',
                r'<strong>Capacit&#233;</strong>\s*:\s*([^<\n]+)'
            ],
            'debit': [
                r'<strong>Débit (?:à la montée|montée|&#224; la mont&#233;e)</strong>\s*:\s*([^<\n]+)',
                r'<strong>D&#233;bit (?:&#224; la mont&#233;e|montée)</strong>\s*:\s*([^<\n]+)'
            ],
            'vitesse_exploitation': [
                r'<strong>Vitesse d[\'&#39;]exploitation</strong>\s*:\s*([^<\n]+)',
                r'<strong>Vitesse d&#39;exploitation</strong>\s*:\s*([^<\n]+)'
            ],
            'denivelee': [
                r'<strong>Dénivel[ée]e</strong>\s*:\s*([^<\n]+)',
                r'<strong>D&#233;nivel[ée]e</strong>\s*:\s*([^<\n]+)'
            ],
            'longueur_developpee': [
                r'<strong>Longueur développée</strong>\s*:\s*([^<\n]+)',
                r'<strong>Longueur d&#233;velopp&#233;e</strong>\s*:\s*([^<\n]+)'
            ],
            'altitude_aval': [
                r'<strong>Altitude (?:de la )?gare aval</strong>\s*:\s*([^<\n]+)',
                r'<strong>Altitude (?:de la )?(?:aval|gare aval)</strong>\s*:\s*([^<\n]+)'
            ],
            'altitude_amont': [
                r'<strong>Altitude (?:de la )?gare amont</strong>\s*:\s*([^<\n]+)',
                r'<strong>Altitude (?:de la )?(?:amont|gare amont)</strong>\s*:\s*([^<\n]+)'
            ],
            'temps_trajet': [
                r'<strong>Temps de trajet</strong>\s*:\s*([^<\n]+)'
            ],
            'puissance_developpee': [
                r'<strong>Puissance développée</strong>\s*:\s*([^<\n]+)',
                r'<strong>Puissance d&#233;velopp&#233;e</strong>\s*:\s*([^<\n]+)'
            ]
        }
        
        for key, pattern_list in patterns_html.items():
            if key not in info:
                for pattern in pattern_list:
                    match = re.search(pattern, html_content, re.IGNORECASE)
                    if match:
                        value = match.group(1).strip()
                        value = value.replace('&#233;', 'é').replace('&#224;', 'à')
                        value = value.replace('&#244;', 'ô').replace('&#39;', "'")
                        value = value.replace('&#232;', 'è').replace('&#8217;', "'")
                        value = value.replace('&nbsp;', ' ').replace('&amp;', '&')
                        value = value.replace('&#234;', 'ê').replace('&#226;', 'â')
                        value = re.sub(r'<br\s*/?>', '', value)
                        value = re.sub(r'\s+', ' ', value).strip()
                        if value:
                            info[key] = value
                            break
    
    return info


def scrape_reportage_details(session, appareil_data):
    """Scrapes reportage details - thread-safe version"""
    url_reportage = appareil_data['lien_reportage']
    
    try:
        resp = session.get(url_reportage, timeout=20)
        
        if resp.status_code != 200:
            logging.warning(f"Error {resp.status_code} for {appareil_data['appareil']}")
            with stats_lock:
                stats['errors'] += 1
            return None
        
        resp.encoding = "windows-1252"
        soup = BeautifulSoup(resp.text, "html.parser")
        
        details = {}
        
        # GPS coordinates
        coords = extract_coordinates_from_js(soup)
        if coords:
            details['coordonnees'] = coords
        
        # Banner
        banniere = extract_banniere(soup)
        if banniere:
            details['banniere'] = banniere
        
        # Detailed information
        info = extract_detail_info(soup)
        details.update(info)
        
        return details
        
    except Exception as e:
        logging.error(f"Error for {appareil_data['appareil']}: {e}")
        with stats_lock:
            stats['errors'] += 1
        return None


def process_appareil(session, appareil_data):
    """Processes a complete device - ALL IN ONE FILE"""
    nom = appareil_data['appareil']
    
    if not appareil_data['lien_reportage']:
        appareil_data['donnees_manquantes'] = ["lien_reportage"]
        appareil_data['statut_complet'] = False
        with data_lock:
            data_complete.append(appareil_data)
        with stats_lock:
            stats['incomplete'] += 1
            stats['total'] += 1
        logging.info(f"[XX] {nom} - No link")
        return
    
    # Scrape details
    details = scrape_reportage_details(session, appareil_data)
    
    if details:
        appareil_data.update(details)
        
        # Check for missing data
        missing = []
        
        # Check coordinates
        if 'coordonnees' not in details:
            missing.append("coordonnées")
        
        # Check construction year (except if end of service year exists)
        if 'annee_construction' not in details and 'annee_fin_service' not in details:
            missing.append("année_construction")
        
        # MANDATORY check for both altitudes
        if 'altitude_aval' not in details:
            missing.append("altitude_aval")
        if 'altitude_amont' not in details:
            missing.append("altitude_amont")
        
        # Add status
        if len(missing) == 0:
            appareil_data['statut_complet'] = True
            with stats_lock:
                stats['complete'] += 1
                stats['total'] += 1
            logging.info(f"[OK] {nom} - Complete")
        else:
            appareil_data['statut_complet'] = False
            appareil_data['donnees_manquantes'] = missing
            with stats_lock:
                stats['incomplete'] += 1
                stats['total'] += 1
            logging.info(f"[!!] {nom} - Incomplete: {', '.join(missing)}")
        
        with data_lock:
            data_complete.append(appareil_data)
    else:
        appareil_data['statut_complet'] = False
        appareil_data['donnees_manquantes'] = ["extraction_failed"]
        with data_lock:
            data_complete.append(appareil_data)
        with stats_lock:
            stats['incomplete'] += 1
            stats['total'] += 1
        logging.warning(f"[XX] {nom} - Extraction failed")


def scrape_departement(url_dep, dep_name):
    """Scrapes a department and returns the list of devices"""
    session = create_session()
    appareils_list = []
    
    try:
        logging.info(f"Starting scraping {dep_name}")
        resp = session.get(base_url + url_dep, timeout=15)
        resp.encoding = "windows-1252"
        
        if resp.status_code != 200:
            logging.error(f"Error {resp.status_code} for {dep_name}")
            return appareils_list
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for station_li in soup.select("ul.liste_station > li"):
            station_tag = station_li.select_one("span.station_name")
            if not station_tag:
                continue
            nom_station = station_tag.text.strip()
            
            for app_div in station_li.select("div.tableRow"):
                nom_appareil_tag = app_div.select_one("a.appareil")
                if not nom_appareil_tag:
                    continue
                
                nom_appareil = nom_appareil_tag.text.strip()
                href = nom_appareil_tag.get("href", "")
                lien_reportage = base_url + href if href else ""
                
                # Status
                imgs = app_div.find_all("img")
                en_service = True
                if len(imgs) > 1:
                    src = imgs[1].get("src", "")
                    if "icon_hs_on" in src:
                        en_service = False
                
                # Manufacturer
                constructeur = ""
                cellules = app_div.select("div.tableCell")
                for cell in reversed(cellules):
                    link = cell.select_one("a[href*='liste-6']")
                    if link:
                        constructeur = link.text.strip()
                        break
                
                appareil_data = {
                    "departement": dep_name,
                    "station": nom_station,
                    "appareil": nom_appareil,
                    "constructeur": constructeur,
                    "en_service": en_service,
                    "lien_reportage": lien_reportage
                }
                
                appareils_list.append(appareil_data)
        
        logging.info(f"{dep_name}: {len(appareils_list)} devices found")
        
    except Exception as e:
        logging.error(f"Error scraping {dep_name}: {e}")
    
    return appareils_list


def main():
    all_appareils = []
    for url_dep, dep_name in departements:
        appareils = scrape_departement(url_dep, dep_name)
        all_appareils.extend(appareils)
        time.sleep(1)
    
    logging.info(f"\n{len(all_appareils)} devices to process")
    
    # Number of parallel workers
    MAX_WORKERS = 10
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Create a session per worker
        sessions = [create_session() for _ in range(MAX_WORKERS)]
        
        # Submit all tasks
        futures = []
        for i, appareil in enumerate(all_appareils):
            session = sessions[i % MAX_WORKERS]
            future = executor.submit(process_appareil, session, appareil)
            futures.append(future)
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error in thread: {e}")
    
    with open("remontees_mecaniques.json", "w", encoding="utf-8") as f:
        json.dump(data_complete, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()