# -*- coding: utf-8 -*-
"""
ruleaza_seeds.py  (versiunea 2)
================================================================================
Rulează fiecare scenariu S0–S5 cu mai multe seed-uri și raportează media ±
abaterea standard, atât la nivel de scenariu (Tabelul 10 din lucrare), cât și
pe clasă de vehicul (Tabelul 9). Ambele tabele provin astfel din același set de
rulări, ceea ce elimină ultima inconsecvență din lucrare.

Se pune în același folder cu `constanta.net.xml`, `vtypes.add.xml` și
`routes_S0..S5.rou.xml` (adică SUMO_Constanta_Complete) și se rulează:

    python ruleaza_seeds.py

Scrie:
  - `seeds_rezultate.csv`   — o linie pe scenariu și seed, cu factorii pe km;
  - `seeds_sinteza.csv`     — media ± SD pe scenariu și variațiile față de S0;
  - `seeds_pe_clase.csv`    — factorii pe clasă de vehicul din scenariul de
                              referință, media ± SD (Tabelul 9 din lucrare);
  - `seeds_contorizare.csv` — contorizarea completă a vehiculelor: încărcate,
                              inserate, parcursuri încheiate, rămase în rețea la
                              final, neinserate și teleportări, pe cauze;
  - `ti_<scenariu>_seed<N>.xml` — ieșirile brute, păstrate pentru verificare.

Verificare încorporată: factorul de CO2 al scenariului S0 trebuie să iasă în
jur de 250 g/km. Dacă iese de o mie de ori mai mare sau mai mic, unitatea
atributelor din tripinfo diferă în versiunea instalată — se ajustează
constanta MG_PE_UNITATE de mai jos.
================================================================================
"""

import glob
import os
import shutil
import subprocess
import sys
import sysconfig
from statistics import mean, stdev
from xml.etree import ElementTree as ET

SCENARII = ["S0", "S1", "S2", "S3", "S4", "S5"]
SEEDS = [1, 2, 3, 4, 5]          # cinci replicări; se pot adăuga altele
SFARSIT = 7200                   # s, ca toate vehiculele să ajungă
MG_PE_UNITATE = 1.0              # atributele *_abs din tripinfo sunt în mg
REFERINTA = "S0"                 # scenariul din care se ia tabelul pe clase

# denumirile lungi ale claselor, pentru tabelul din lucrare
CLASE = {
    "g3": "g3 petrol Euro 3", "g4": "g4 petrol Euro 4",
    "g5": "g5 petrol Euro 5", "g6": "g6 petrol Euro 6ab",
    "d3": "d3 diesel Euro 3", "d4": "d4 diesel Euro 4",
    "d5": "d5 diesel Euro 5", "d6": "d6 diesel Euro 6ab",
    "ev": "ev battery electric",
}
ORDINE = ["g3", "g4", "g5", "g6", "d3", "d4", "d5", "d6", "ev"]


def gaseste_sumo():
    """Aceeași căutare ca în run_scenarios.py: PATH, pachetul pip, SUMO_HOME."""
    cand = []
    w = shutil.which("sumo")
    if w:
        cand.append(w)
    try:
        import sumo as _s
        d = os.path.dirname(_s.__file__)
        cand += glob.glob(os.path.join(d, "bin", "sumo.exe"))
        cand += glob.glob(os.path.join(d, "bin", "sumo"))
    except Exception:
        pass
    try:
        sc = sysconfig.get_path("scripts")
        cand += glob.glob(os.path.join(sc, "sumo.exe"))
        cand += glob.glob(os.path.join(sc, "sumo"))
    except Exception:
        pass
    h = os.environ.get("SUMO_HOME")
    if h:
        cand += glob.glob(os.path.join(h, "bin", "sumo.exe"))
        cand += glob.glob(os.path.join(h, "bin", "sumo"))
    for p in cand:
        if p and os.path.isfile(p):
            return p
    return None


def citeste(cale):
    """Însumează emisiile și distanța din tripinfo, global și pe clasă.
    Elementul <emissions> este copil al fiecărui <tripinfo>, deci se reține
    tipul vehiculului din părinte înainte de a-l consuma."""
    tot = {"veh": 0, "km": 0.0, "CO2": 0.0, "NOx": 0.0, "PMx": 0.0}
    pe_clasa = {}
    vtip = None
    for ev, el in ET.iterparse(cale, events=("start", "end")):
        if ev == "start" and el.tag == "tripinfo":
            # cu --tripinfo-output.write-unfinished apar si vehiculele care nu
            # si-au terminat parcursul; ele nu au atributul `arrival`. Factorii
            # de emisie se calculeaza numai pe parcursurile incheiate, ca sa
            # ramana comparabili intre scenarii.
            incheiat = el.get("arrival") not in (None, "", "-1", "-1.00")
            vtip = el.get("vType") if incheiat else None
            if incheiat:
                km = float(el.get("routeLength", 0.0)) / 1000.0
                tot["veh"] += 1
                tot["km"] += km
                c = pe_clasa.setdefault(vtip, {"veh": 0, "km": 0.0, "CO2": 0.0,
                                               "NOx": 0.0, "PMx": 0.0})
                c["veh"] += 1
                c["km"] += km
        elif ev == "end" and el.tag == "emissions":
            if vtip is None:          # parcurs neincheiat: se ignora
                el.clear()
                continue
            co2 = float(el.get("CO2_abs", 0.0))
            nox = float(el.get("NOx_abs", 0.0))
            pmx = float(el.get("PMx_abs", 0.0))
            tot["CO2"] += co2
            tot["NOx"] += nox
            tot["PMx"] += pmx
            if vtip in pe_clasa:
                pe_clasa[vtip]["CO2"] += co2
                pe_clasa[vtip]["NOx"] += nox
                pe_clasa[vtip]["PMx"] += pmx
        elif ev == "end" and el.tag == "tripinfo":
            el.clear()
    if tot["km"] <= 0:
        return None, None

    def factori(d):
        return {
            "vehicule": d["veh"],
            "veh_km": d["km"],
            "CO2_g_km": d["CO2"] * MG_PE_UNITATE / 1000.0 / d["km"],
            "NOx_mg_km": d["NOx"] * MG_PE_UNITATE / d["km"],
            "PM_mg_km": d["PMx"] * MG_PE_UNITATE / d["km"],
        }

    return factori(tot), {k: factori(v) for k, v in pe_clasa.items() if v["km"] > 0}


def intra_in_dir_sumo():
    """Scriptul foloseste nume de fisiere relative, deci trebuie sa ruleze din
    folderul care contine configuratia SUMO. Il cauta si intra in el, ca sa poata
    fi lansat si din radacina depozitului (`python code/ruleaza_seeds.py`)."""
    aici = os.path.dirname(os.path.abspath(__file__))
    candidati = [os.environ.get("CAR2026_SUMO"), os.getcwd(),
                 os.path.join(os.getcwd(), "sumo"),
                 os.path.join(os.getcwd(), ".."),
                 os.path.join(aici, "..", "sumo"), aici]
    for c in candidati:
        if not c:
            continue
        c = os.path.abspath(c)
        if all(os.path.isfile(os.path.join(c, f))
               for f in ("vtypes.add.xml", "routes_S0.rou.xml")):
            if c != os.path.abspath(os.getcwd()):
                print("Folderul de lucru SUMO:", c)
            os.chdir(c)
            if not os.path.isfile("constanta.net.xml"):
                print("ATENTIE: constanta.net.xml lipseste din acest folder.\n"
                      "Reteaua este derivata din OpenStreetMap si nu se "
                      "redistribuie; vezi README-ul pentru interogarea Overpass\n"
                      "datata si comanda NETCONVERT care o regenereaza.")
            return
    print("Nu am gasit folderul cu configuratia SUMO (vtypes.add.xml si "
          "routes_S0.rou.xml).\nRuleaza din folderul `sumo/` al depozitului sau "
          "seteaza CAR2026_SUMO catre el.")
    sys.exit(1)


def citeste_statistici(cale):
    """Contorizarea vehiculelor din fișierul --statistic-output:
      loaded    — vehicule create din definițiile de flux;
      inserted  — efectiv introduse în rețea;
      running   — încă în rețea la sfârșitul simulării;
      waiting   — rămase în coada de inserție, niciodată introduse;
      teleports — mutări forțate, cu defalcarea pe cauze."""
    if not os.path.isfile(cale):
        return None
    try:
        r = ET.parse(cale).getroot()
    except Exception:
        return None
    v = r.find("vehicles")
    t = r.find("teleports")
    if v is None:
        return None
    d = {k: int(float(v.get(k, 0))) for k in ("loaded", "inserted", "running",
                                              "waiting")}
    for k in ("total", "jam", "yield", "wrongLane"):
        d["tp_" + k] = int(float(t.get(k, 0))) if t is not None else 0
    return d


def ms(v):
    return (mean(v), stdev(v) if len(v) > 1 else 0.0)


def main():
    intra_in_dir_sumo()
    sumo = gaseste_sumo()
    if not sumo:
        print("Nu am găsit executabilul sumo. Rulează:  pip install eclipse-sumo")
        sys.exit(1)
    print("SUMO:", sumo)
    v = subprocess.run([sumo, "--version"], capture_output=True, text=True)
    linie = (v.stdout or "").strip().splitlines()
    if linie:
        print(linie[0], "\n")

    rez, rez_clase, rez_stat = {}, {}, {}
    linii = ["scenariu,seed,vehicule,veh_km,CO2_g_km,NOx_mg_km,PM_mg_km"]
    for s in SCENARII:
        rou = "routes_%s.rou.xml" % s
        if not os.path.isfile(rou):
            print("%s: lipsește %s — sar peste" % (s, rou))
            continue
        rez[s], rez_clase[s], rez_stat[s] = [], [], []
        for sd in SEEDS:
            ies = "ti_%s_seed%d.xml" % (s, sd)
            stat = "st_%s_seed%d.xml" % (s, sd)
            cmd = [sumo, "-n", "constanta.net.xml", "-r", rou,
                   "-a", "vtypes.add.xml",
                   "--device.emissions.probability", "1",
                   "--seed", str(sd),
                   "--tripinfo-output", ies,
                   "--tripinfo-output.write-unfinished", "true",
                   "--statistic-output", stat,
                   "--duration-log.statistics", "true",
                   "--time-to-teleport", "300",
                   "--ignore-junction-blocker", "20",
                   "--begin", "0", "--end", str(SFARSIT),
                   "--no-step-log", "--no-warnings"]
            print("  %s seed %d ..." % (s, sd), end=" ", flush=True)
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print("EROARE")
                print((r.stderr or "")[:800])
                continue
            t, pc = citeste(ies)
            if not t:
                print("fără vehicule înregistrate")
                continue
            rez[s].append(t)
            rez_clase[s].append(pc)
            st = citeste_statistici(stat)
            if st:
                rez_stat[s].append(st)
            linii.append("%s,%d,%d,%.1f,%.2f,%.2f,%.3f" % (
                s, sd, t["vehicule"], t["veh_km"], t["CO2_g_km"],
                t["NOx_mg_km"], t["PM_mg_km"]))
            print("CO2 %.1f g/km%s" % (
                t["CO2_g_km"],
                "" if not st else "  (inserate %d, incheiate %d, in retea %d, teleportari %d)"
                % (st["inserted"], t["vehicule"], st["running"], st["tp_total"])))

    open("seeds_rezultate.csv", "w", encoding="utf8").write("\n".join(linii) + "\n")

    # ---------------- sinteza pe scenarii (Tabelul 10) -----------------------
    out = ["scenariu,marime,medie,SD,delta_medie_pct,delta_SD_pct"]
    print("\n--- Tabelul 10: scenarii ---")
    print("%-9s %-10s %12s %8s %16s" % ("scenariu", "mărime", "medie", "SD",
                                        "Δ față de S0"))
    for s in SCENARII:
        if not rez.get(s):
            continue
        for cheie, et in [("CO2_g_km", "CO2 g/km"), ("NOx_mg_km", "NOx mg/km"),
                          ("PM_mg_km", "PM mg/km")]:
            v = [x[cheie] for x in rez[s]]
            m, sd = ms(v)
            if s != "S0" and rez.get("S0"):
                n = min(len(v), len(rez["S0"]))
                d = [100 * (v[i] - rez["S0"][i][cheie]) / rez["S0"][i][cheie]
                     for i in range(n)]
                dm, dsd = ms(d)
                print("%-9s %-10s %12.2f %8.2f   %+7.2f ± %.2f %%"
                      % (s, et, m, sd, dm, dsd))
                out.append("%s,%s,%.4f,%.4f,%.3f,%.3f" % (s, et, m, sd, dm, dsd))
            else:
                print("%-9s %-10s %12.2f %8.2f" % (s, et, m, sd))
                out.append("%s,%s,%.4f,%.4f,," % (s, et, m, sd))
    open("seeds_sinteza.csv", "w", encoding="utf8").write("\n".join(out) + "\n")

    # ---------------- factori pe clasa (Tabelul 9) ---------------------------
    surse = [REFERINTA, "S1"]        # clasa electrică apare abia din S1
    pc_all = {}
    for s in surse:
        for rep in rez_clase.get(s, []):
            for cls, f in rep.items():
                pc_all.setdefault(cls, {"CO2_g_km": [], "NOx_mg_km": [],
                                        "PM_mg_km": []})
                for k in ("CO2_g_km", "NOx_mg_km", "PM_mg_km"):
                    pc_all[cls][k].append(f[k])
    out2 = ["clasa,CO2_g_km,CO2_SD,NOx_mg_km,NOx_SD,PM_mg_km,PM_SD,replicari"]
    print("\n--- Tabelul 9: factori pe clasă (medie ± SD) ---")
    print("%-22s %16s %18s %16s" % ("clasă", "CO2 [g/km]", "NOx [mg/km]",
                                    "PM [mg/km]"))
    for cls in ORDINE:
        if cls not in pc_all:
            continue
        a = pc_all[cls]
        c, cs = ms(a["CO2_g_km"])
        n, ns = ms(a["NOx_mg_km"])
        p, ps = ms(a["PM_mg_km"])
        print("%-22s %8.1f ± %-5.1f %9.1f ± %-6.1f %7.2f ± %-5.2f"
              % (CLASE.get(cls, cls), c, cs, n, ns, p, ps))
        out2.append("%s,%.3f,%.3f,%.3f,%.3f,%.4f,%.4f,%d"
                    % (CLASE.get(cls, cls), c, cs, n, ns, p, ps,
                       len(a["CO2_g_km"])))
    open("seeds_pe_clase.csv", "w", encoding="utf8").write("\n".join(out2) + "\n")

    # ---------------- contorizarea completa a vehiculelor -------------------
    out3 = ["scenariu,incarcate,inserate,incheiate,in_retea_la_final,neinserate,"
            "teleportari,teleportari_blocaj,teleportari_cedare,teleportari_banda,replicari"]
    print("\n--- Contorizarea vehiculelor (medii pe seed-uri) ---")
    print("%-9s %9s %9s %10s %11s %11s %12s" % (
        "scenariu", "încărcate", "inserate", "încheiate", "în rețea", "neinserate",
        "teleportări"))
    for s_ in SCENARII:
        if not rez_stat.get(s_):
            continue
        n = len(rez_stat[s_])
        g = lambda k: mean(x[k] for x in rez_stat[s_])
        incheiate = mean(x["vehicule"] for x in rez[s_]) if rez.get(s_) else 0
        print("%-9s %9.1f %9.1f %10.1f %11.1f %11.1f %12.1f" % (
            s_, g("loaded"), g("inserted"), incheiate, g("running"), g("waiting"),
            g("tp_total")))
        out3.append("%s,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%d" % (
            s_, g("loaded"), g("inserted"), incheiate, g("running"), g("waiting"),
            g("tp_total"), g("tp_jam"), g("tp_yield"), g("tp_wrongLane"), n))
    if len(out3) > 1:
        open("seeds_contorizare.csv", "w", encoding="utf8").write("\n".join(out3) + "\n")
        print("   încheiate = parcursuri complete; factorii de emisie se calculează")
        print("   numai pe acestea. inserate − încheiate − în rețea = vehicule pierdute.")
    else:
        print("   (fișierele de statistică lipsesc — verifică opțiunea --statistic-output)")

    print("\nScrise: seeds_rezultate.csv, seeds_sinteza.csv, seeds_pe_clase.csv,"
          " seeds_contorizare.csv")
    if rez.get("S0"):
        c = mean(x["CO2_g_km"] for x in rez["S0"])
        if not (100 < c < 600):
            print("ATENȚIE: CO2 pe S0 iese %.3f g/km, în afara intervalului "
                  "așteptat (~250). Verifică unitatea atributelor *_abs din "
                  "tripinfo în versiunea instalată și ajustează MG_PE_UNITATE." % c)


if __name__ == "__main__":
    main()
