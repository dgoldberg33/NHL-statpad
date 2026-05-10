#!/usr/bin/env python3
"""
build_players.py
Builds a complete NHL player database as players.json.

Sources:
  - api.nhle.com/stats/rest  → all skater/goalie stats 1987-present (paginates all ~10k players)
  - hockey-reference.com     → pre-1987 historical players via scraping

Run this once to generate players.json, then commit it to your GitHub repo.
Re-run whenever you want to update (e.g. end of each season).

Usage:
  pip install requests beautifulsoup4
  python3 build_players.py
"""

import requests
import json
import time
import sys
from collections import defaultdict

NHL_REST = "https://api.nhle.com/stats/rest/en"
HEADERS  = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.ok:
                return r.json()
            print(f"  HTTP {r.status_code} for {url}")
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(2 ** i)
    return None

def norm_team(t):
    m = {"NJD":"NJ","LAK":"LA","SJS":"SJ","TBL":"TB","PHX":"PHO","ATL":"ATL","MNS":"MIN"}
    return m.get(t, t) if t else ""

def norm_nat(n):
    # Some API responses return 2-letter ISO codes instead of 3-letter
    m = {"CA":"CAN","US":"USA","RU":"RUS","SE":"SWE","FI":"FIN",
         "CZ":"CZE","SK":"SVK","DE":"GER","CH":"SUI","DK":"DEN",
         "AT":"AUT","BE":"BEL","FR":"FRA","GB":"GBR","LV":"LAT",
         "NO":"NOR","SI":"SVN","UA":"UKR"}
    return m.get(n, n) if n else ""

def parse_teams(s):
    return [norm_team(t.strip()) for t in (s or "").split(",") if t.strip()]

# ── Fetch from NHL Stats REST API (1987-present) ──────────────────────────────

def fetch_report(endpoint, report, page=100, extra_filter=""):
    """Paginate through one NHL stats REST report, return all rows."""
    rows_all = []
    start = 0
    total = None
    # bios report doesn't need gameTypeId filter and returns more players without it
    base_filter = extra_filter or ("cayenneExp=gameTypeId=2" if report != "bios" else "")
    while True:
        sep = "&" if base_filter else ""
        url  = f"{NHL_REST}/{endpoint}/{report}?{base_filter}{sep}limit={page}&start={start}"
        data = get(url)
        if not data:
            break
        if total is None:
            total = data.get("total", 0)
        rows = data.get("data", [])
        if not rows:
            break
        rows_all.extend(rows)
        start += page
        if len(rows) < page:
            break
        time.sleep(0.05)
    return rows_all

def fetch_nhl_api(is_goalie):
    endpoint = "goalie" if is_goalie else "skater"
    label    = "goalies" if is_goalie else "skaters"
    print(f"\nFetching {label} from NHL Stats API...")

    by_id = {}

    # Fetch bios — contains nationality. Must paginate without season filter to get all players.
    print(f"  Fetching bios...")
    for r in fetch_report(endpoint, "bios", page=100):
        pid = r.get("playerId")
        if not pid:
            continue
        name = r.get("goalieFullName" if is_goalie else "skaterFullName", "") or r.get("playerName","")
        nat  = norm_nat(r.get("nationalityCode","") or r.get("birthCountryCode",""))
        pos  = "G" if is_goalie else (r.get("positionCode","") or "C")
        if pid not in by_id:
            by_id[pid] = {"id":pid,"n":name,"tm":[],"f":9999,"t":0,"pos":pos,"nat":nat,
                          "pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":0,"sv":0,"gaa":0,"so":0}
        else:
            p = by_id[pid]
            if name and not p["n"]: p["n"] = name
            if nat  and not p["nat"]: p["nat"] = nat
    print(f"  Got bios for {len(by_id)} {label}")
    
    # For any remaining players not in bios, fetch individually via api-web
    # This handles ~1500 older players whose bios aren't in the summary endpoint
    # We do this AFTER the summary fetch so we know which players need it

    # Now fetch summary — contains per-season stats and team info
    print(f"  Fetching summary stats...")
    for r in fetch_report(endpoint, "summary"):
        pid = r.get("playerId")
        if not pid:
            continue
        name  = r.get("goalieFullName" if is_goalie else "skaterFullName", "")
        teams = parse_teams(r.get("teamAbbrevs", ""))
        sid   = str(r.get("seasonId", "19870988"))
        yr    = int(sid[:4]) if len(sid) >= 4 else 1987
        pos   = "G" if is_goalie else r.get("positionCode", "C")
        nat   = norm_nat(r.get("nationalityCode", "") or r.get("birthCountryCode", ""))
        pts   = r.get("points", 0) or 0
        g     = r.get("goals", 0) or 0
        a     = r.get("assists", 0) or 0
        pim   = r.get("penaltyMinutes", 0) or 0
        ppg   = r.get("powerPlayGoals", 0) or 0
        sog   = r.get("shots", 0) or 0
        w     = r.get("wins", 0) or 0
        sv    = r.get("savePctg") or r.get("savePct") or 0
        gaa   = r.get("goalsAgainstAverage", 0) or 0
        so    = r.get("shutouts", 0) or 0

        if pid not in by_id:
            by_id[pid] = {"id":pid,"n":name,"tm":list(teams),"f":yr,"t":yr+1,
                          "pos":pos,"nat":nat,"pts":pts,"g":g,"a":a,"pim":pim,
                          "ppg":ppg,"sog":sog,"w":w,"sv":sv,"gaa":gaa,"so":so}
        else:
            p = by_id[pid]
            if name and not p["n"]:   p["n"]   = name
            if nat  and not p["nat"]: p["nat"] = nat
            for t in teams:
                if t and t not in p["tm"]: p["tm"].append(t)
            p["f"]   = min(p["f"], yr)
            p["t"]   = max(p["t"], yr + 1)
            p["pts"] = max(p["pts"], pts)
            p["g"]   = max(p["g"],   g)
            p["a"]   = max(p["a"],   a)
            p["pim"] = max(p["pim"], pim)
            p["ppg"] = max(p["ppg"], ppg)
            p["sog"] = max(p["sog"], sog)
            p["w"]   = max(p["w"],   w)
            p["sv"]  = max(p["sv"],  sv)
            p["so"]  = max(p["so"],  so)
            if gaa > 0: p["gaa"] = gaa if p["gaa"] == 0 else min(p["gaa"], gaa)

    print(f"  Done: {len(by_id)} unique {label}")
    return list(by_id.values())

# ── Pre-1987 historical players (hardcoded from Hockey Reference) ─────────────
# These players predate the NHL Stats REST API coverage.
# Stats are best single-season values from Hockey Reference.

PRE_1987 = [
    # Skaters
    {"n":"Wayne Gretzky",     "tm":["EDM","LA","STL","NYR"],"f":1979,"t":1999,"pos":"C", "nat":"CAN","pts":215,"g":92, "a":163,"pim":39, "ppg":23,"sog":369,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mario Lemieux",     "tm":["PIT"],                  "f":1984,"t":2006,"pos":"C", "nat":"CAN","pts":141,"g":48, "a":93, "pim":43, "ppg":15,"sog":226,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mike Bossy",        "tm":["NYI"],                  "f":1977,"t":1987,"pos":"RW","nat":"CAN","pts":147,"g":69, "a":78, "pim":34, "ppg":28,"sog":380,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Bryan Trottier",    "tm":["NYI","PIT"],             "f":1975,"t":1987,"pos":"C", "nat":"CAN","pts":134,"g":50, "a":89, "pim":72, "ppg":20,"sog":320,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Marcel Dionne",     "tm":["DET","LA","NYR"],        "f":1971,"t":1987,"pos":"C", "nat":"CAN","pts":137,"g":59, "a":84, "pim":38, "ppg":21,"sog":340,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Guy Lafleur",       "tm":["MTL","NYR","QUE"],       "f":1971,"t":1987,"pos":"RW","nat":"CAN","pts":136,"g":60, "a":89, "pim":20, "ppg":22,"sog":353,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Phil Esposito",     "tm":["CHI","BOS","NYR"],       "f":1963,"t":1981,"pos":"C", "nat":"CAN","pts":152,"g":76, "a":76, "pim":88, "ppg":22,"sog":426,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Bobby Orr",         "tm":["BOS","CHI"],             "f":1966,"t":1979,"pos":"D", "nat":"CAN","pts":139,"g":46, "a":102,"pim":125,"ppg":19,"sog":338,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Jari Kurri",        "tm":["EDM","LA","NYR"],        "f":1980,"t":1996,"pos":"RW","nat":"FIN","pts":135,"g":71, "a":64, "pim":30, "ppg":27,"sog":363,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mark Messier",      "tm":["EDM","NYR","VAN"],       "f":1979,"t":2004,"pos":"C", "nat":"CAN","pts":168,"g":67, "a":84, "pim":239,"ppg":18,"sog":323,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Denis Potvin",      "tm":["NYI"],                   "f":1973,"t":1987,"pos":"D", "nat":"CAN","pts":101,"g":31, "a":83, "pim":119,"ppg":18,"sog":270,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Paul Coffey",       "tm":["EDM","PIT","LA","DET","HAR","PHI","CHI","BOS","CAR","PHO"],"f":1980,"t":2001,"pos":"D","nat":"CAN","pts":138,"g":48,"a":102,"pim":87,"ppg":25,"sog":320,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Dale Hawerchuk",    "tm":["WPG","STL","BUF","PHI"], "f":1981,"t":1987,"pos":"C", "nat":"CAN","pts":130,"g":53, "a":77, "pim":40, "ppg":21,"sog":290,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Denis Savard",      "tm":["CHI","MTL","TB"],        "f":1980,"t":1997,"pos":"C", "nat":"CAN","pts":131,"g":47, "a":87, "pim":72, "ppg":22,"sog":310,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mike Gartner",      "tm":["WSH","MIN","NYR","TOR","PHO"],"f":1979,"t":1998,"pos":"RW","nat":"CAN","pts":102,"g":55,"a":48,"pim":68,"ppg":18,"sog":380,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Luc Robitaille",    "tm":["LA","PIT","NYR","DET"],  "f":1986,"t":2006,"pos":"LW","nat":"CAN","pts":84, "g":45, "a":39, "pim":44, "ppg":18,"sog":226,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Glenn Anderson",    "tm":["EDM","TOR","NYR","STL"], "f":1980,"t":1996,"pos":"RW","nat":"CAN","pts":105,"g":54, "a":48, "pim":80, "ppg":20,"sog":290,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mike Liut",         "tm":["STL","HAR","WSH"],       "f":1979,"t":1987,"pos":"G", "nat":"CAN","pts":0,  "g":0,  "a":0,  "pim":0,  "ppg":0, "sog":0,  "w":33,"sv":.899,"gaa":2.84,"so":4},
    {"n":"Ray Bourque",       "tm":["BOS","COL"],             "f":1979,"t":2001,"pos":"D", "nat":"CAN","pts":96, "g":21, "a":75, "pim":74, "ppg":12,"sog":266,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Brian Trottier",    "tm":["NYI","PIT"],             "f":1975,"t":1987,"pos":"C", "nat":"CAN","pts":134,"g":50, "a":89, "pim":72, "ppg":20,"sog":320,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mike Foligno",      "tm":["DET","BUF","TOR","FLA"], "f":1979,"t":1987,"pos":"RW","nat":"CAN","pts":82, "g":41, "a":41, "pim":175,"ppg":11,"sog":240,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Peter Stastny",     "tm":["QUE","NJ","STL"],        "f":1980,"t":1987,"pos":"C", "nat":"SVK","pts":139,"g":46, "a":93, "pim":78, "ppg":19,"sog":270,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Michel Goulet",     "tm":["QUE","CHI"],             "f":1979,"t":1987,"pos":"LW","nat":"CAN","pts":121,"g":57, "a":64, "pim":76, "ppg":22,"sog":310,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Dino Ciccarelli",   "tm":["MIN","WSH","DET","TB","FLA"],"f":1981,"t":1999,"pos":"RW","nat":"CAN","pts":106,"g":55,"a":51,"pim":122,"ppg":22,"sog":310,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Rick Middleton",    "tm":["NYR","BOS"],             "f":1974,"t":1987,"pos":"RW","nat":"CAN","pts":105,"g":51, "a":54, "pim":12, "ppg":15,"sog":280,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Gil Perreault",     "tm":["BUF"],                   "f":1970,"t":1987,"pos":"C", "nat":"CAN","pts":113,"g":51, "a":69, "pim":36, "ppg":18,"sog":248,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Mike Rogers",       "tm":["VAN","HAR","NYR","EDM"], "f":1974,"t":1986,"pos":"C", "nat":"CAN","pts":105,"g":44, "a":61, "pim":24, "ppg":14,"sog":220,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Blaine Stoughton",  "tm":["PIT","KC","HAR","NYR"],  "f":1973,"t":1984,"pos":"RW","nat":"CAN","pts":100,"g":56, "a":44, "pim":58, "ppg":20,"sog":290,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Rick Martin",       "tm":["BUF","LA"],              "f":1971,"t":1982,"pos":"LW","nat":"CAN","pts":83, "g":52, "a":31, "pim":56, "ppg":20,"sog":280,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Rene Robert",       "tm":["PIT","BUF","COL"],       "f":1970,"t":1982,"pos":"RW","nat":"CAN","pts":74, "g":40, "a":44, "pim":64, "ppg":14,"sog":220,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Darryl Sittler",    "tm":["TOR","PHI","DET"],       "f":1970,"t":1985,"pos":"C", "nat":"CAN","pts":117,"g":45, "a":72, "pim":111,"ppg":14,"sog":280,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Larry Robinson",    "tm":["MTL","LA"],              "f":1972,"t":1987,"pos":"D", "nat":"CAN","pts":85, "g":19, "a":66, "pim":68, "ppg":8, "sog":230,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Borje Salming",     "tm":["TOR","DET"],             "f":1973,"t":1987,"pos":"D", "nat":"SWE","pts":90, "g":17, "a":73, "pim":148,"ppg":8, "sog":240,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Brad Park",         "tm":["NYR","BOS","DET"],       "f":1968,"t":1985,"pos":"D", "nat":"CAN","pts":82, "g":25, "a":57, "pim":106,"ppg":12,"sog":240,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Serge Savard",      "tm":["MTL","WPG"],             "f":1966,"t":1983,"pos":"D", "nat":"CAN","pts":57, "g":16, "a":41, "pim":82, "ppg":7, "sog":180,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Brian Propp",       "tm":["PHI","BOS","MIN","HAR","STL"],"f":1979,"t":1987,"pos":"LW","nat":"CAN","pts":97,"g":40,"a":57,"pim":59,"ppg":14,"sog":278,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Tim Kerr",          "tm":["PHI","NYR","HAR"],       "f":1980,"t":1987,"pos":"C", "nat":"CAN","pts":81, "g":54, "a":43, "pim":66, "ppg":26,"sog":240,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Joe Mullen",        "tm":["STL","CGY","PIT","BOS"], "f":1980,"t":1987,"pos":"RW","nat":"USA","pts":110,"g":51, "a":59, "pim":14, "ppg":18,"sog":270,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Hakan Loob",        "tm":["CGY"],                   "f":1983,"t":1989,"pos":"RW","nat":"SWE","pts":106,"g":50, "a":56, "pim":28, "ppg":18,"sog":240,"w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Doug Gilmour",      "tm":["STL","CGY","TOR","NJ","CHI","BUF","MTL"],"f":1983,"t":2003,"pos":"C","nat":"CAN","pts":105,"g":35,"a":70,"pim":58,"ppg":9,"sog":200,"w":0,"sv":0,"gaa":0,"so":0},
    # Pre-expansion era
    {"n":"Gordie Howe",       "tm":["DET","HFD"],             "f":1946,"t":1980,"pos":"RW","nat":"CAN","pts":103,"g":49, "a":67, "pim":109,"ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Bobby Hull",        "tm":["CHI","WPG","HAR"],       "f":1957,"t":1980,"pos":"LW","nat":"CAN","pts":107,"g":58, "a":49, "pim":52, "ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Stan Mikita",       "tm":["CHI"],                   "f":1958,"t":1980,"pos":"C", "nat":"SVK","pts":97, "g":35, "a":62, "pim":146,"ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Frank Mahovlich",   "tm":["TOR","DET","MTL"],       "f":1956,"t":1975,"pos":"LW","nat":"CAN","pts":89, "g":49, "a":40, "pim":131,"ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Jean Beliveau",     "tm":["MTL"],                   "f":1950,"t":1971,"pos":"C", "nat":"CAN","pts":91, "g":47, "a":58, "pim":143,"ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Maurice Richard",   "tm":["MTL"],                   "f":1942,"t":1960,"pos":"RW","nat":"CAN","pts":80, "g":50, "a":33, "pim":112,"ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Norm Ullman",       "tm":["DET","TOR"],             "f":1955,"t":1977,"pos":"C", "nat":"CAN","pts":85, "g":42, "a":56, "pim":76, "ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Alex Delvecchio",   "tm":["DET"],                   "f":1950,"t":1974,"pos":"C", "nat":"CAN","pts":83, "g":31, "a":67, "pim":37, "ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Yvan Cournoyer",    "tm":["MTL"],                   "f":1963,"t":1979,"pos":"RW","nat":"CAN","pts":89, "g":47, "a":40, "pim":21, "ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Ken Hodge",         "tm":["CHI","BOS","NYR"],       "f":1964,"t":1978,"pos":"RW","nat":"CAN","pts":105,"g":50, "a":55, "pim":113,"ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    {"n":"Johnny Bucyk",      "tm":["DET","BOS"],             "f":1955,"t":1978,"pos":"LW","nat":"CAN","pts":83, "g":51, "a":65, "pim":28, "ppg":0, "sog":0,  "w":0,"sv":0,"gaa":0,"so":0},
    # Pre-1987 goalies
    {"n":"Ken Dryden",        "tm":["MTL"],                   "f":1970,"t":1979,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":42,"sv":.916,"gaa":2.24,"so":10},
    {"n":"Tony Esposito",     "tm":["MTL","CHI"],             "f":1968,"t":1984,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":38,"sv":.906,"gaa":2.92,"so":15},
    {"n":"Billy Smith",       "tm":["NYI"],                   "f":1972,"t":1989,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":32,"sv":.893,"gaa":2.73,"so":5},
    {"n":"Bernie Parent",     "tm":["BOS","PHI","TOR"],       "f":1965,"t":1979,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":38,"sv":.905,"gaa":1.89,"so":12},
    {"n":"Gerry Cheevers",    "tm":["BOS","CLE"],             "f":1961,"t":1980,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":32,"sv":.900,"gaa":2.89,"so":8},
    {"n":"Rogie Vachon",      "tm":["MTL","LA","DET","BOS"],  "f":1966,"t":1982,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":32,"sv":.893,"gaa":2.99,"so":7},
    {"n":"Glenn Hall",        "tm":["DET","CHI","STL"],       "f":1952,"t":1971,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":36,"sv":.900,"gaa":2.49,"so":11},
    {"n":"Terry Sawchuk",     "tm":["DET","BOS","TOR","LA","NYR"],"f":1949,"t":1970,"pos":"G","nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":33,"sv":.904,"gaa":1.98,"so":14},
    {"n":"Jacques Plante",    "tm":["MTL","NYR","STL","TOR","BOS"],"f":1952,"t":1973,"pos":"G","nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":34,"sv":.906,"gaa":2.15,"so":9},
    {"n":"Grant Fuhr",        "tm":["EDM","TOR","BUF","LA","STL"],"f":1981,"t":2000,"pos":"G","nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":40,"sv":.880,"gaa":3.87,"so":1},
    {"n":"Pete Peeters",      "tm":["PHI","BOS","WSH"],       "f":1978,"t":1991,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":31,"sv":.895,"gaa":3.08,"so":5},
    {"n":"Rejean Lemelin",    "tm":["ATL","CGY","BOS"],       "f":1978,"t":1987,"pos":"G", "nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":29,"sv":.887,"gaa":3.44,"so":2},
    {"n":"Mike Vernon",       "tm":["CGY","DET","SJ","SJS","FLA","DAL"],"f":1983,"t":2002,"pos":"G","nat":"CAN","pts":0,"g":0,"a":0,"pim":0,"ppg":0,"sog":0,"w":36,"sv":.895,"gaa":2.98,"so":3},
]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("NHL Player Database Builder")
    print("=" * 60)

    # 1. Fetch from NHL API (1987-present)
    skaters = fetch_nhl_api(is_goalie=False)
    goalies = fetch_nhl_api(is_goalie=True)
    api_players = skaters + goalies

    print(f"\nNHL API total: {len(api_players)} players")

    # 2. Merge/add pre-1987 historical players
    # The NHL API only goes back to ~1987-88 so pre-1987 legends need to be
    # added from our curated dataset. Some may also appear in the API with
    # incomplete data — in that case we patch what's missing.
    api_by_name = {p["n"].lower(): p for p in api_players}

    added = 0
    updated = 0
    for p in PRE_1987:
        name_key = p["n"].lower()
        if name_key in api_by_name:
            ep = api_by_name[name_key]
            # Patch any missing or wrong data the API has for this player
            ep["f"]   = min(ep["f"], p["f"])
            ep["t"]   = max(ep["t"], p["t"])
            if p["nat"]:
                ep["nat"] = p["nat"]  # our curated nat is more reliable
            for t in p["tm"]:
                if t and t not in ep["tm"]:
                    ep["tm"].append(t)
            for stat in ["pts","g","a","pim","ppg","sog","w","so"]:
                ep[stat] = max(ep[stat], p[stat])
            if p["sv"] > 0:
                ep["sv"] = max(ep["sv"], p["sv"])
            if p["gaa"] > 0:
                ep["gaa"] = p["gaa"] if ep["gaa"] == 0 else min(ep["gaa"], p["gaa"])
            updated += 1
        else:
            # Not in API at all — add from our dataset
            new_p = dict(p)
            new_p["id"] = None  # no NHL API id for pre-API players
            api_players.append(new_p)
            api_by_name[name_key] = api_players[-1]
            added += 1
            print(f"  Added missing player: {p['n']}")

    print(f"Pre-1987 dataset: added {added} missing players, patched {updated} existing")
    print(f"Total: {len(api_players)} players")

    # 3. Clean up
    players = []
    blank_nat = 0
    blank_name = 0
    bad_years = 0
    for p in api_players:
        # Skip players with no name
        if not p.get("n", "").strip():
            blank_name += 1
            continue
        # Fix players who only appeared in bios (f=9999, t=0)
        if p.get("f", 9999) == 9999 or p.get("t", 0) == 0:
            bad_years += 1
            continue  # skip — no season data, not useful
        if not p.get("nat"):
            blank_nat += 1
        players.append(p)

    print(f"Removed {blank_name} players with blank names")
    print(f"Removed {bad_years} players with no season data")
    print(f"Players with blank nationality: {blank_nat}")

    # 4. Sort by name for easy debugging
    players.sort(key=lambda p: p["n"])

    # 5. Write to JSON
    out = json.dumps(players, separators=(",", ":"))
    with open("players.json", "w") as f:
        f.write(out)

    size_kb = len(out) / 1024
    print(f"\n✓ Written players.json — {len(players)} players, {size_kb:.0f}KB")
    print("\nNext steps:")
    print("  1. Commit players.json to your GitHub repo root")
    print("  2. Update index.html to fetch /players.json instead of hitting the NHL API")
    print("  3. Re-run this script each offseason to refresh stats")

if __name__ == "__main__":
    main()
