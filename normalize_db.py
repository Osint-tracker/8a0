import json
import collections
import re
import shutil
import unicodedata

def clean_text(text):
    if not text:
        return ""
    # Normalize unicode characters (remove accents)
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return text.strip()

def normalize_team_name(name):
    cleaned = clean_text(name)
    lowered = cleaned.lower()
    
    # Common mappings
    if "barcelona" in lowered:
        return "Barcelona"
    if "real madrid" in lowered or lowered == "madrid" or ("madrid" in lowered and "real" in lowered):
        return "Real Madrid"
    if "atletico madrid" in lowered or "atletico de madrid" in lowered:
        return "Atletico Madrid"
    if "milan" in lowered and "inter" not in lowered:
        return "AC Milan"
    if "inter" in lowered and "milan" in lowered or "internazionale" in lowered:
        return "Inter Milan"
    if "bayern" in lowered or "munchen" in lowered:
        return "Bayern Munich"
    if "manchester united" in lowered or "man utd" in lowered or "man united" in lowered:
        return "Manchester United"
    if "manchester city" in lowered or "man city" in lowered:
        return "Manchester City"
    if "chelsea" in lowered:
        return "Chelsea"
    if "arsenal" in lowered:
        return "Arsenal"
    if "liverpool" in lowered:
        return "Liverpool"
    if "juventus" in lowered or "juve" in lowered:
        return "Juventus"
    if "porto" in lowered:
        return "Porto"
    if "benfica" in lowered:
        return "Benfica"
    if "ajax" in lowered:
        return "Ajax"
    if "psv" in lowered:
        return "PSV Eindhoven"
    if "feyenoord" in lowered:
        return "Feyenoord"
    if "galatasaray" in lowered:
        return "Galatasaray"
    if "fenerbahce" in lowered:
        return "Fenerbahce"
    if "besiktas" in lowered:
        return "Besiktas"
    if "celtic" in lowered:
        return "Celtic"
    if "rangers" in lowered:
        return "Rangers"
    if "dynamo k" in lowered or "dinamo k" in lowered:
        return "Dynamo Kyiv"
    if "shakhtar" in lowered:
        return "Shakhtar Donetsk"
    if "zenit" in lowered:
        return "Zenit St. Petersburg"
    if "cska m" in lowered:
        return "CSKA Moscow"
    if "spartak" in lowered:
        return "Spartak Moscow"
    if "red star" in lowered or "crvena zvezda" in lowered or "star belgrade" in lowered:
        return "Red Star Belgrade"
    if "steaua" in lowered:
        return "Steaua Bucuresti"
    if "anderlecht" in lowered:
        return "Anderlecht"
    if "brugge" in lowered:
        return "Club Brugge"
    if "lyon" in lowered or "olympique lyonnais" in lowered:
        return "Lyon"
    if "marseille" in lowered or "olympique de marseille" in lowered:
        return "Marseille"
    if "monaco" in lowered:
        return "Monaco"
    if "valencia" in lowered:
        return "Valencia"
    if "sevilla" in lowered:
        return "Sevilla"
    if "villarreal" in lowered:
        return "Villarreal"
    if "sociedad" in lowered:
        return "Real Sociedad"
    if "bilbao" in lowered or "athletic club" in lowered:
        return "Athletic Bilbao"
    if "rapid w" in lowered or "rapid v" in lowered:
        return "Rapid Vienna"
    if "stade de reims" in lowered or "reims" in lowered:
        return "Stade de Reims"
    if "partizan" in lowered:
        return "Partizan Belgrade"
    if "djurgarden" in lowered or "djurgardens" in lowered:
        return "Djurgardens IF"
    if "hibernian" in lowered:
        return "Hibernian"
    if "mtk" in lowered or "voros lobogo" in lowered:
        return "MTK Budapest"
    if "fiorentina" in lowered:
        return "Fiorentina"
    if "grasshopper" in lowered:
        return "Grasshoppers"
    if "hamburg" in lowered or "hamburger" in lowered:
        return "Hamburg"
    if "dortmund" in lowered or "borussia dortmund" in lowered:
        return "Borussia Dortmund"
    if "leverkusen" in lowered or "bayer leverkusen" in lowered:
        return "Bayer Leverkusen"
    if "schalke" in lowered:
        return "Schalke 04"
    if "st etienne" in lowered or "saint-etienne" in lowered:
        return "Saint-Etienne"
    if "norrkop" in lowered:
        return "IFK Norrkoping"
    
    # Generic cleaning
    name = re.sub(r"\b(fc|cf|fk|if|ff|ifk|sv|as|ac|nk|pfc|ssc|rc|sc|afc|bsc|sl|club|deportivo|sporting|real|athletic)\b", "", lowered)
    name = re.sub(r"\b(de|di|da|du|des|von|van|the)\b", "", name)
    name = re.sub(r"[^a-z0-9 ]", "", name)
    name = " ".join(name.split())
    
    return name.title() if name else cleaned

def main():
    db_path = "database_7a0_rated.json"
    backup_path = "database_7a0_rated_prev.json"
    
    # Backup
    shutil.copyfile(db_path, backup_path)
    print(f"[*] Created backup of database at: {backup_path}")
    
    with open(db_path, "r", encoding="utf-8") as f:
        players = json.load(f)
        
    print(f"[*] Processing {len(players)} players...")
    for p in players:
        original = p.get("team_name")
        normalized = normalize_team_name(original)
        p["team_name"] = normalized

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=4)
        
    print("[OK] Database normalized successfully.")
    
    # Summary of changes
    counts = collections.Counter((p["team_name"], p["year"]) for p in players)
    small = [k for k, v in counts.items() if v < 11]
    print(f"[*] Unique team-years: {len(counts)}")
    print(f"[*] Team-years with < 11 players: {len(small)} (reduced from 489)")

if __name__ == "__main__":
    main()
