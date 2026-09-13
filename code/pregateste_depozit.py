# -*- coding: utf-8 -*-
"""
pregateste_depozit.py
================================================================================
Construiește depozitul de date care însoțește lucrarea CAR2026: copiază fișierele
care trebuie publicate, aplică politica privind coordonatele, scrie README-ul,
licențele și un manifest cu sume de control.

    python pregateste_depozit.py

Politica privind coordonatele se alege din constanta COORDONATE de mai jos:

  "fara"      (implicit) — coloanele lat/lon se scot din logurile publicate și se
                publică separat doar geometria traseelor, scurtată la capete.
                Niciun rezultat numeric din lucrare nu depinde de coordonate:
                distanța cumulată este integrala vitezei, verificată. Se pierde
                doar refacerea exactă a figurii 1 și potrivirea pe hartă.
  "trunchiat" — se păstrează coordonatele, dar primii și ultimii METRI_TAIATI
                metri ai fiecărui traseu se elimină din TOT logul. Atenție:
                schimbă distanțele și mediile față de cele raportate în lucrare.
  "integral"  — se publică totul, inclusiv punctele de plecare și de sosire.

Nu se redistribuie rețeaua de străzi: `constanta.osm` și `constanta.net.xml` sunt
derivate din OpenStreetMap și intră sub ODbL, care este share-alike. README-ul dă
în schimb caseta de coordonate și comanda de regenerare.
================================================================================
"""

import hashlib
import io
import os
import shutil

import pandas as pd

BASE = os.environ.get("CAR2026_BASE", r"D:\Lucrare CAR2026")
IESIRE = os.path.join(BASE, "zenodo_depozit")
COORDONATE = "fara"          # "fara" | "trunchiat" | "integral"
METRI_TAIATI = 400           # folosit numai la "trunchiat"
METRI_GEOMETRIE = 400        # cât se taie la capete din fișierul de geometrie

DIR_RUTE = os.path.join(BASE, "Loguri rute")
DIR_SUMO = os.path.join(BASE, "files", "SUMO_Constanta_v2", "SUMO_Constanta_Complete")
DIR_BRUT = os.path.join(BASE, "Date brute CSV")

LOGURI = {
    "R_A": "log_RUTA_A_Bratianu-Ferdinand-Mamaia_11-13.csv",
    "R_B": "log_RUTA_B_Mamaia-Navodari_15-17.csv",
    "R_DN3": "log_DIESEL_Constanta-DN3-Murfatlar_09-10.csv",
}
BRUTE = ["trackLog-2026-apr.-02_11-01-45.csv", "trackLog-2026-apr.-02_11-32-38.csv",
         "trackLog-2026-apr.-02_11-38-27.csv", "trackLog-2026-apr.-02_15-28-27.csv",
         "trackLog_diesel_2.0TDI_BKD_2026sept.11_091422.csv"]
DERIVATE = ["extrapolat_R_A_diesel.csv", "extrapolat_R_B_diesel.csv",
            "extrapolat_R_DN3_benzina.csv", "matrice_comparativa_benzina_diesel.csv",
            "matrice_pe_clase_RDE.csv", "tabel_parametri_RDE_ferestre.csv",
            "tabel_parametri_RDE_diesel.csv"]
SUMO_FIS = ["vtypes.add.xml"] + ["routes_S%d.rou.xml" % i for i in range(6)] + \
           ["seeds_rezultate.csv", "seeds_sinteza.csv", "seeds_pe_clase.csv"]
SCRIPTURI = ["prelucrare_loguri_CAR2026.py", "calibrare_validare_CAR2026.py",
             "genereaza_figuri.py"]
SCRIPTURI_SUMO = ["ruleaza_seeds.py"]


def citeste(cale):
    linii = open(cale, encoding="utf-8", errors="replace").read().splitlines()
    i0 = next(i for i, l in enumerate(linii)
              if l and not l.startswith("#") and "," in l)
    antet = "\n".join(l for l in linii[:i0] if l.startswith("#"))
    return antet, pd.read_csv(io.StringIO("\n".join(linii[i0:])))


def copiaza(sursa, dest_dir, nume=None):
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.exists(sursa):
        print("   LIPSEȘTE:", sursa)
        return None
    dst = os.path.join(dest_dir, nume or os.path.basename(sursa))
    shutil.copy2(sursa, dst)
    return dst


def suma(cale):
    h = hashlib.sha256()
    with open(cale, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


GEO_BRUT = ["Longitude", "Latitude", "GPS Latitude(°)", "GPS Longitude(°)"]


def scrie_brute():
    """Copiază exporturile Torque. Sub politica \"fara\" li se scot coloanele de
    poziție, ca publicarea lor să nu anuleze protecția aplicată logurilor
    prelucrate; restul canalelor rămân neatinse."""
    d = os.path.join(IESIRE, "data", "raw")
    os.makedirs(d, exist_ok=True)
    antet_ref = None
    cale_ref = os.path.join(DIR_BRUT, BRUTE[2])
    if os.path.exists(cale_ref):
        antet_ref = [c.strip() for c in
                     open(cale_ref, encoding="utf-8", errors="replace").readline().split(",")]
    for f in BRUTE:
        sursa = os.path.join(DIR_BRUT, f)
        if not os.path.exists(sursa):
            print("   LIPSEȘTE:", sursa)
            continue
        if COORDONATE == "integral":
            shutil.copy2(sursa, os.path.join(d, f))
            continue
        prima = open(sursa, encoding="utf-8", errors="replace").readline()
        are_antet = prima.startswith("GPS Time")
        if are_antet:
            g = pd.read_csv(sursa, engine="python", on_bad_lines="skip")
        else:
            g = pd.read_csv(sursa, engine="python", on_bad_lines="skip",
                            header=None, names=antet_ref)
        g.columns = [c.strip() for c in g.columns]
        scoase = [c for c in GEO_BRUT if c in g.columns]
        g = g.drop(columns=scoase)
        g.to_csv(os.path.join(d, f), index=False, encoding="utf-8")
        print("   %s: %d rânduri, coloane de poziție eliminate: %s"
              % (f, len(g), ", ".join(scoase) or "niciuna"))


def scrie_loguri():
    """Aplică politica privind coordonatele și scrie logurile publicate."""
    d_data = os.path.join(IESIRE, "data")
    d_geo = os.path.join(IESIRE, "data", "geometry")
    os.makedirs(d_data, exist_ok=True)
    for k, f in LOGURI.items():
        cale = os.path.join(DIR_RUTE, f)
        if not os.path.exists(cale):
            print("   LIPSEȘTE:", cale)
            continue
        antet, g = citeste(cale)
        if COORDONATE == "integral":
            pass
        elif COORDONATE == "trunchiat":
            dmax = g["dist_cum_m"].max()
            g = g[(g["dist_cum_m"] > METRI_TAIATI) &
                  (g["dist_cum_m"] < dmax - METRI_TAIATI)].reset_index(drop=True)
        else:                                   # "fara"
            os.makedirs(d_geo, exist_ok=True)
            dmax = g["dist_cum_m"].max()
            geo = g[(g["dist_cum_m"] > METRI_GEOMETRIE) &
                    (g["dist_cum_m"] < dmax - METRI_GEOMETRIE)]
            geo = geo[["t_rel_s", "lat_deg", "lon_deg", "dist_cum_m"]].iloc[::5]
            geo.to_csv(os.path.join(d_geo, "geometry_%s.csv" % k), index=False)
            g = g.drop(columns=[c for c in ("lat_deg", "lon_deg") if c in g.columns])
        g.to_csv(os.path.join(d_data, f), index=False, encoding="utf-8")
        print("   %s: %d rânduri, %d coloane" % (f, len(g), g.shape[1]))


README = """# Real-driving data and models for Constanța (CAR2026)

Data and code accompanying the paper

> A M Beldugan, T Dordea, L-V Melnic, C Tudor, S L Ionascu and L Stania,
> *Driving cycles recorded in Constanța and model estimates of fuel consumption
> and emissions for SI and CI vehicles*, 36th SIAR International Congress of
> Automotive and Transport Engineering (CAR2026), Pitești, 5–7 November 2026.

Everything reported in the paper — every table, every figure — is reproduced by
the scripts in `code/` from the files in `data/`.

## What was measured

Each route–vehicle combination was traversed **once**. There are no repeated
runs; between-run dispersion cannot be derived from this dataset.

| Route | Vehicle | Date | Time window | Duration | Distance |
|---|---|---|---|---|---|
| R_A — central urban | SI, Opel Astra H 1.6i (Z16XEP), Euro 4 | 2 April 2026 | 11:47–13:10 | 2378 s | 13.39 km |
| R_B — coastal radial | SI, same vehicle | 2 April 2026 | 15:28–16:06 | 1897 s | 17.37 km |
| R_DN3 — mixed | CI, VW Touran 2.0 TDI (BKD), Euro 4, no DPF | 11 September 2026 | 09:14–10:00 | 2788 s | 44.29 km |

Logging: ELM327 v2.1 Bluetooth OBD-II adapter with Torque Pro and the phone GPS.
Raw sampling was ~1.77 s in April and 1.00 s in September; the April records were
linearly resampled to 1 Hz before any calculation.

## Layout

```
data/            processed 1 Hz records, derived series and result matrices
data/geometry/   route geometry, thinned and trimmed at both ends
data/raw/        the original Torque Pro exports, unmodified
sumo/            scenario configuration and the seed-run results
code/            the scripts that reproduce the paper
```

## Column reference for the 1 Hz records

| Column | Unit | Meaning |
|---|---|---|
| `timestamp_local` | — | device time, Europe/Bucharest |
| `t_rel_s` | s | seconds from the start of the segment |
| `v_kmh` | km/h | vehicle speed, OBD-II |
| `a_ms2` | m/s² | acceleration, first difference of speed at 1 Hz |
| `dist_cum_m` | m | cumulative distance, the integral of speed |
| `rpm` | rev/min | engine speed |
| `maf_g_s` | g/s | mass air flow |
| `sarcina_motor_pct` | % | calculated engine load, OBD-II PID 04 |
| `stationare` | 0/1 | 1 when speed is below 1 km/h |
| `clasa_RDE` | — | urban ≤ 60 km/h, rural 60–90, motorway > 90 |
| `segment` | — | segment index; a new segment starts at every recording gap |
| `CO2_g_s_benzina`, `CO2_g_s_diesel` | g/s | carbon-balance CO2 |

The CI record additionally carries `t_lichid_racire_C`, `t_aer_admisie_C`,
`t_ambiant_C`, `altitudine_m`, `p_galerie_psi`, `HDOP` and the three fuel-rate
estimates `debit_comb_fizic_ml_s`, `debit_comb_model_ml_s` and
`CO2_g_s_stoich_MAF`, the last of which is the rejected stoichiometric estimate,
kept only so that the rejection can be checked.

## Two things to know before reusing the records

**Recording gaps, not idling.** The raw files contain intervals in which the
logging application produced no data. These are excluded and marked by the
`segment` column, which changes at every gap longer than 30 s. No traffic stop
was removed: stops at traffic lights, junctions and in congestion are present in
full, the longest being 105 s on R_A, 67 s on R_B and 50 s on R_DN3. One gap of
541 s at the start of R_A contains approximately 1.86 km of driving that is
therefore absent from the analysed distance; R_A consists of two segments.

**Accelerations must be computed after resampling.** Counting raw April samples
as seconds underestimates duration and distance and inflates accelerations by
about 77%.

## Reproducing the paper

```
python code/prelucrare_loguri_CAR2026.py audit     # segmentation audit
python code/calibrare_validare_CAR2026.py          # out-of-sample check, thermal effect
python code/genereaza_figuri.py                    # figures 1-8 at 600 dpi
python code/ruleaza_seeds.py                       # tables 9 and 10, 6 scenarios x 5 seeds
```

The scripts take the project root from the environment variable `CAR2026_BASE`
and otherwise use the path written at the top of each file.

## The street network is not included

`constanta.net.xml` and the OpenStreetMap extract it was built from are derived
from OpenStreetMap and therefore fall under the Open Database Licence, which is
share-alike. They are not redistributed here. To regenerate the network, take an
Overpass extract with the bounding box 44.15–44.34 N, 28.38–28.70 E and run

```
netconvert --osm-files constanta.osm -o constanta.net.xml \\
           --geometry.remove --roundabouts.guess --ramps.guess \\
           --junctions.join --tls.guess-signals --tls.join \\
           --output.street-names true
```

The simulated corridor is the longest non-self-intersecting run of the
map-matched R_A route: 105 edges, 4.051 km, between 44.1692 N, 28.5974 E and
44.1821 N, 28.6424 E. Simulations used Eclipse SUMO 1.27.1.

## Fleet composition used in the scenarios

Fuel split, 48% petrol and 52% diesel, renormalised on petrol and diesel from
Eurostat `road_eqs_carpda` for Romania in 2024: 3 988 219 petrol and 4 322 854
diesel passenger cars out of 8 449 781, the remaining 138 708 alternative-fuel
cars excluded. Distribution over emission standards from the air-quality study of
the municipality of Constanța (2024, figure 5-6, national registration records
for the reference year 2018): 10% pre-Euro, 4% Euro 1, 8% Euro 2, 19% Euro 3, 36%
Euro 4, 18% Euro 5 and 5% Euro 6. Vehicles older than Euro 3 are represented by
the Euro 3 class, the oldest in the HBEFA4 set used, so their emissions are
underestimated.

## Licence

Data files: Creative Commons Attribution 4.0 International (CC BY 4.0).
Scripts in `code/`: MIT Licence, see `LICENSE-CODE.txt`.
Cite the dataset by its DOI and the paper above.

## Privacy note

COORD_NOTE

## Contact

A M Beldugan, Ovidius University of Constanța, beldugan.adrian@gmail.com
"""

NOTA_COORD = {
    "fara": "The 1 Hz records are published without latitude and longitude. No "
            "numerical result in the paper depends on them: cumulative distance "
            "is the integral of speed, and consumption, cycle parameters and "
            "calibration are computed from the speed trace alone. Route geometry "
            "is provided separately in `data/geometry/`, thinned to one point in "
            "five seconds and trimmed by 400 m at both ends, which is enough to "
            "place the routes on a map but not to identify the start and end "
            "addresses.",
    "trunchiat": "The first and last 400 m of each route have been removed from "
                 "the published records so that start and end addresses cannot be "
                 "identified. Distances and means computed from these files are "
                 "therefore slightly lower than the values reported in the paper, "
                 "which refer to the complete records.",
    "integral": "The records are published complete, including start and end "
                "points.",
}

MIT = """MIT License

Copyright (c) 2026 A M Beldugan and co-authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

CITATION = """cff-version: 1.2.0
title: Real-driving data and models for Constanța (CAR2026)
message: If you use this dataset, please cite both the dataset and the paper.
type: dataset
authors:
  - family-names: Beldugan
    given-names: A. M.
    affiliation: Ovidius University of Constanța
  - family-names: Dordea
    given-names: T.
  - family-names: Melnic
    given-names: L.-V.
  - family-names: Tudor
    given-names: C.
  - family-names: Ionascu
    given-names: S. L.
  - family-names: Stania
    given-names: L.
license: CC-BY-4.0
keywords:
  - real driving emissions
  - OBD-II
  - driving cycle
  - SUMO
  - HBEFA
  - Constanța
"""

GITIGNORE = """*.pyc
__pycache__/
ti_*.xml
sum_*.xml
em_*.xml
*.net.xml
*.osm
"""


def main():
    if os.path.exists(IESIRE):
        shutil.rmtree(IESIRE)
    os.makedirs(IESIRE)
    print("Construiesc depozitul în", IESIRE)
    print("Politica privind coordonatele:", COORDONATE)

    print(" data/")
    scrie_loguri()
    for f in DERIVATE:
        copiaza(os.path.join(DIR_RUTE, f), os.path.join(IESIRE, "data"))
    print(" data/raw/")
    scrie_brute()
    print(" sumo/")
    for f in SUMO_FIS:
        copiaza(os.path.join(DIR_SUMO, f), os.path.join(IESIRE, "sumo"))
    print(" code/")
    for f in SCRIPTURI:
        copiaza(os.path.join(BASE, f), os.path.join(IESIRE, "code"))
    for f in SCRIPTURI_SUMO:
        copiaza(os.path.join(DIR_SUMO, f), os.path.join(IESIRE, "code"))
    copiaza(os.path.join(BASE, "pregateste_depozit.py"),
            os.path.join(IESIRE, "code"))

    open(os.path.join(IESIRE, "README.md"), "w", encoding="utf-8").write(
        README.replace("COORD_NOTE", NOTA_COORD[COORDONATE]))
    open(os.path.join(IESIRE, "LICENSE-CODE.txt"), "w", encoding="utf-8").write(MIT)
    open(os.path.join(IESIRE, "CITATION.cff"), "w", encoding="utf-8").write(CITATION)
    open(os.path.join(IESIRE, ".gitignore"), "w", encoding="utf-8").write(GITIGNORE)

    # manifest cu sume de control
    linii = ["file,bytes,sha256"]
    total = 0
    for rad, _, fis in os.walk(IESIRE):
        for f in sorted(fis):
            p = os.path.join(rad, f)
            rel = os.path.relpath(p, IESIRE).replace("\\", "/")
            if rel == "MANIFEST.csv":
                continue
            b = os.path.getsize(p)
            total += b
            linii.append("%s,%d,%s" % (rel, b, suma(p)))
    open(os.path.join(IESIRE, "MANIFEST.csv"), "w", encoding="utf-8").write(
        "\n".join(linii) + "\n")
    print("\n%d fișiere, %.1f MB" % (len(linii) - 1, total / 1e6))
    print("Gata:", IESIRE)


if __name__ == "__main__":
    main()
