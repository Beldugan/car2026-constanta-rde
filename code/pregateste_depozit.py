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
            "matrice_pe_clase_RDE.csv", "calibrare_rezultate.csv",
            "tabel_parametri_RDE_ferestre.csv", "tabel_parametri_RDE_diesel.csv"]
SUMO_FIS = ["vtypes.add.xml"] + ["routes_S%d.rou.xml" % i for i in range(6)] + \
           ["seeds_rezultate.csv", "seeds_sinteza.csv", "seeds_pe_clase.csv",
            "seeds_contorizare.csv"]
SCRIPTURI = ["prelucrare_loguri_CAR2026.py", "model_consum_CAR2026.py",
             "genereaza_figuri.py"]
SCRIPTURI_SUMO = ["ruleaza_seeds.py"]


def citeste(cale):
    linii = open(cale, encoding="utf-8", errors="replace").read().splitlines()
    i0 = next(i for i, l in enumerate(linii)
              if l and not l.startswith("#") and "," in l)
    antet = "\n".join(l for l in linii[:i0] if l.startswith("#"))
    return antet, pd.read_csv(io.StringIO("\n".join(linii[i0:])))


LIPSA = []                   # fișiere obligatorii negăsite; verificat în main()
PERMITE_INCOMPLET = os.environ.get("CAR2026_PERMITE_INCOMPLET") == "1"
ACCEPTA_RESPINSE = os.environ.get("CAR2026_ACCEPTA_RANDURI_RESPINSE") == "1"
RESPINSE = []                # (fișier, rândul respins) pentru exporturile brute


def lipseste(cale):
    """Înregistrează un fișier obligatoriu negăsit. Pachetul nu se închide fără
    ca acest lucru să fie semnalat: vezi verificarea de la finalul lui main()."""
    if cale in LIPSA:
        return
    LIPSA.append(cale)
    print("   LIPSEȘTE:", cale)


def copiaza(sursa, dest_dir, nume=None):
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.exists(sursa):
        lipseste(sursa)
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
            lipseste(sursa)
            continue
        if COORDONATE == "integral":
            shutil.copy2(sursa, os.path.join(d, f))
            continue
        prima = open(sursa, encoding="utf-8", errors="replace").readline()
        are_antet = prima.startswith("GPS Time")

        # Rândurile pe care parserul nu le poate citi nu se pierd în tăcere: se
        # colectează, se raportează și, implicit, opresc construcția.
        respinse_fis = []

        def colecteaza(rand, _f=f):
            respinse_fis.append(rand)
            RESPINSE.append((_f, rand))
            return None

        if are_antet:
            g = pd.read_csv(sursa, engine="python", on_bad_lines=colecteaza)
        else:
            g = pd.read_csv(sursa, engine="python", on_bad_lines=colecteaza,
                            header=None, names=antet_ref)
        g.columns = [c.strip() for c in g.columns]
        scoase = [c for c in GEO_BRUT if c in g.columns]
        g = g.drop(columns=scoase)
        g.to_csv(os.path.join(d, f), index=False, encoding="utf-8")

        # Control independent: câte linii de date are fișierul sursă.
        brute = [l for l in open(sursa, encoding="utf-8",
                                 errors="replace").read().splitlines() if l.strip()]
        asteptate = len(brute) - (1 if are_antet else 0)
        print("   %s: %d rânduri din %d linii de date, respinse: %d, "
              "coloane de poziție eliminate: %s"
              % (f, len(g), asteptate, len(respinse_fis),
                 ", ".join(scoase) or "niciuna"))
        if len(g) != asteptate and not respinse_fis:
            RESPINSE.append((f, ["(diferență de %d rânduri neexplicată de parser)"
                                 % (asteptate - len(g))]))


def scrie_loguri():
    """Aplică politica privind coordonatele și scrie logurile publicate."""
    d_data = os.path.join(IESIRE, "data")
    d_geo = os.path.join(IESIRE, "data", "geometry")
    os.makedirs(d_data, exist_ok=True)
    for k, f in LOGURI.items():
        cale = os.path.join(DIR_RUTE, f)
        if not os.path.exists(cale):
            lipseste(cale)
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

`model_consum_CAR2026.py` holds the whole consumption chain in one place: the
speed-to-engine-speed relation, the Willans calibration, the predictions for the
route-vehicle combinations that were never driven, the out-of-sample check, the
thermal comparison and the electric-vehicle energy balance. Its header states the
conventions that fix the result — how the low-load branch treats negative wheel
power, which seconds enter the regression, and where the engine speed comes from.
The scripts in `code/` recompute every derived table of the paper — tables 5 to
11 — and figures 2 to 8 from the files published here. Tables 1, 3 and 4 state
vehicle specifications and adopted scenario parameters and are not computed from
data. Two exceptions to reproducibility are worth stating plainly:

* **Figure 1** maps the route coverage and needs latitude and longitude, which
  are not published (see *Privacy note*). `genereaza_figuri.py` redraws it from
  the thinned, trimmed traces in `data/geometry/`, so the map is recognisable but
  not identical to the published figure. The map-matched street names and the
  `dist_map_match_m` column of the R_A record are likewise carried through from
  the original processing and cannot be recomputed here.
* **Tables 9 and 10** come from the SUMO runs, which need `constanta.net.xml`.
  That network is derived from OpenStreetMap and is not redistributed; it is
  regenerated as described under *The street network is not included*. The
  scenario definitions, the vehicle types and the five-seed results are published
  in `sumo/`, so the numbers can be checked without rerunning the simulation.

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
data/raw/        the Torque Pro exports, position columns removed
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

**The files in `data/raw/` are not byte-identical to the Torque Pro exports.**
They carry the same channels and the same rows, but the four position columns
`Longitude`, `Latitude`, `GPS Latitude(°)` and `GPS Longitude(°)` have been
dropped and each file has been rewritten by pandas, so quoting, line endings and
the formatting of numeric fields follow pandas rather than the logging
application. One export was written without a header row and has been given the
header of the others. No value in the remaining channels has been altered.

**Accelerations must be computed after resampling.** Counting raw April samples
as seconds underestimates duration and distance and inflates accelerations by
about 77%.

## Reproducing the paper

```
python code/prelucrare_loguri_CAR2026.py audit     # segmentation audit
python code/prelucrare_loguri_CAR2026.py rerun     # rebuild the records from the raw exports
python code/model_consum_CAR2026.py                # calibration, tables 7, 8 and 11
python code/model_consum_CAR2026.py --scrie        # write the files the figures read
python code/genereaza_figuri.py                    # figures 1-8 at 600 dpi
python code/ruleaza_seeds.py                       # tables 9 and 10, 6 scenarios x 5 seeds
```

Run them in this order: `genereaza_figuri.py` reads `calibrare_rezultate.csv` and
the two result matrices, which `model_consum_CAR2026.py --scrie` writes. No
number in the figure script is typed by hand.

`ruleaza_seeds.py` needs the SUMO configuration files, which live in `sumo/`; it
finds that folder itself whether it is started from the archive root or from
`sumo/`, and `CAR2026_SUMO` overrides the search. It also needs
`constanta.net.xml`, which is not redistributed — see below.

`prelucrare_loguri_CAR2026.py rerun` rebuilds the three published records from
the raw exports, applying the analysed windows of table 2. It reproduces R_A
exactly, 2378 s in two segments, and R_B and R_DN3 to within one second, a
difference in how the last second of a segment is counted when its span is not
an integer number of seconds. The script prints the comparison for each route.

`ruleaza_seeds.py` writes four files into `sumo/`: `seeds_rezultate.csv`, one
line per scenario and seed; `seeds_sinteza.csv`, the means and standard
deviations reported in table 10; `seeds_pe_clase.csv`, the per-class factors of
table 9; and `seeds_contorizare.csv`, the vehicle accounting quoted in section
3.5 — vehicles loaded, inserted, arrived, still in the network at the end of the
simulated period, never inserted, and teleported, averaged over the five seeds.

The scripts take the project root from the environment variable `CAR2026_BASE`
and otherwise use the path written at the top of each file.

## The street network is not included

`constanta.net.xml` and the OpenStreetMap extract it was built from are derived
from OpenStreetMap and therefore fall under the Open Database Licence, which is
share-alike. They are not redistributed here.

A bounding box and a NETCONVERT command do not by themselves reproduce the same
network, because OpenStreetMap changes continuously and a later download returns
a later map. The extract used here was taken on 2 April 2026, 11:29 UTC. To
obtain the map as it stood then, use an Overpass attic query, which returns the
data valid at a given moment and which the main Overpass instance supports:

```
[out:xml][timeout:900][date:"2026-04-02T11:29:00Z"];
(
  node(44.15,28.38,44.34,28.70);
  way(44.15,28.38,44.34,28.70);
  relation(44.15,28.38,44.34,28.70);
);
(._;>;);
out meta;
```

Save the result as `constanta.osm` and run

```
netconvert --osm-files constanta.osm -o constanta.net.xml \\
           --geometry.remove --roundabouts.guess --ramps.guess \\
           --junctions.join --tls.guess-signals --tls.join \\
           --output.street-names true
```

Without the `date:` line the query returns the current map, which gives a
different network; edge identifiers and junction programmes will not match the
route files in `sumo/`.

The simulated corridor is the longest non-self-intersecting run of the
map-matched R_A route: 105 edges, 4.051 km, between 44.1692 N, 28.5974 E and
44.1821 N, 28.6424 E. Simulations used Eclipse SUMO 1.27.1.

## Fleet composition used in the scenarios

Fuel split, 48% petrol and 52% diesel, renormalised on petrol and diesel from
Eurostat `road_eqs_carpda` for Romania in 2024: 3 988 219 petrol and 4 322 854
diesel passenger cars out of 8 449 781, the remaining 138 708 alternative-fuel
cars excluded. Distribution over emission standards from the air-quality study of
the municipality of Constanța (Amzu R *et al.* 2021, version 2.1, figure 5-6;
records of the national vehicle-registration authority for the 125 439 cars
registered in the municipality in the reference year 2018): 10% pre-Euro, 4%
Euro 1, 8% Euro 2, 19% Euro 3, 36% Euro 4, 18% Euro 5 and 5% Euro 6. Vehicles
older than Euro 3 are represented by the Euro 3 class, which is the oldest class
included in this study rather than the oldest available in HBEFA4. For pollutants
whose HBEFA4 factors rise towards the older classes this understates the
emissions of that fleet share, but those factors are not monotonic in the Euro
label — see the discussion of NOx in the paper — and the direction has not been
checked pollutant by pollutant.

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
    "fara": "The 1 Hz records are published without latitude and longitude. "
            "Cumulative distance is the integral of speed, so the cycle "
            "parameters, the speed-class split and the model calculations do not "
            "use position: the Willans calibration and the modelled fuel rates "
            "are computed from the speed trace together with the vehicle "
            "parameters in table 1, and the SI reference consumption from the "
            "recorded mass air flow, all of which are published. What cannot be "
            "reproduced from these files is figure 1, the map-matched street "
            "names and the `dist_map_match_m` column, all of which need position. "
            "Route geometry is provided separately in `data/geometry/`, thinned "
            "to one point in five seconds and trimmed by 400 m at both ends, "
            "which is enough to place the routes on a map but not to identify the "
            "start and end addresses.",
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


def surse_obligatorii():
    """Toate fișierele care trebuie să existe pentru un pachet complet."""
    c = [os.path.join(DIR_RUTE, f) for f in LOGURI.values()]
    c += [os.path.join(DIR_RUTE, f) for f in DERIVATE]
    c += [os.path.join(DIR_BRUT, f) for f in BRUTE]
    c += [os.path.join(DIR_SUMO, f) for f in SUMO_FIS]
    c += [os.path.join(BASE, f) for f in SCRIPTURI]
    c += [os.path.join(DIR_SUMO, f) for f in SCRIPTURI_SUMO]
    c += [os.path.join(BASE, "pregateste_depozit.py")]
    return c


ZENODO = r"""{
  "upload_type": "dataset",
  "access_right": "open",
  "license": "cc-by-4.0",
  "language": "eng",
  "title": "Real-driving data and models for Constanța: OBD-II records, vehicle consumption models and SUMO–HBEFA4 scenarios",
  "description": "<p>Data and code accompanying the paper <em>Driving cycles recorded in Constanța and model estimates of fuel consumption and emissions for SI and CI vehicles</em>, presented at the 36th SIAR International Congress of Automotive and Transport Engineering (CAR2026), Pitești, 5–7 November 2026.</p><p>The deposit contains the processed 1 Hz driving records of three routes measured in Constanța with two Euro 4 passenger cars, the original Torque Pro exports, the derived consumption series, the SUMO scenario configuration with its five-seed results, and the scripts that recompute the derived tables and figures. Two exceptions are stated in the README: figure 1 needs the position columns, which are not published, and tables 9 and 10 need the street network, which is not redistributed.</p><p>Each route–vehicle combination was traversed once; there are no repeated runs and between-run dispersion cannot be derived from this dataset. Position columns have been removed from the published records for privacy; route geometry is provided separately, thinned and trimmed at both ends. The street network is derived from OpenStreetMap and is not redistributed: the README gives a dated Overpass query and the NETCONVERT command that regenerate the exact network used here.</p><p>Data files are released under CC BY 4.0; the scripts in <code>code/</code> are released under the MIT Licence, as stated in the README and in LICENSE-CODE.txt.</p>",
  "creators": [
    {
      "name": "Beldugan, A. M.",
      "affiliation": "Ovidius University of Constanța, Faculty of Mechanical, Industrial and Maritime Engineering"
    },
    {
      "name": "Dordea, T.",
      "affiliation": "Ovidius University of Constanța, Faculty of Mechanical, Industrial and Maritime Engineering"
    },
    {
      "name": "Melnic, L.-V.",
      "affiliation": "Ovidius University of Constanța, Faculty of Mechanical, Industrial and Maritime Engineering"
    },
    {
      "name": "Tudor, C.",
      "affiliation": "Ovidius University of Constanța, Faculty of Mechanical, Industrial and Maritime Engineering"
    },
    {
      "name": "Ionascu, S. L.",
      "affiliation": "Ovidius University of Constanța, Faculty of Mechanical, Industrial and Maritime Engineering"
    },
    {
      "name": "Stania, L.",
      "affiliation": "Ovidius University of Constanța, Faculty of Mechanical, Industrial and Maritime Engineering"
    }
  ],
  "keywords": [
    "real driving emissions",
    "on-road measurement",
    "OBD-II",
    "driving cycle",
    "fuel consumption",
    "spark ignition",
    "compression ignition",
    "SUMO",
    "HBEFA4",
    "fleet electrification",
    "Constanța",
    "Romania"
  ],
  "notes": "Processed 1 Hz records, raw OBD-II exports, SUMO configuration and analysis scripts. The whole consumption chain — speed-to-engine-speed relation, Willans calibration, cross-route predictions, out-of-sample check, thermal comparison and electric-vehicle energy balance — is in model_consum_CAR2026.py, whose header states the conventions that fix the result. Simulations were run with Eclipse SUMO 1.27.1. Fleet composition follows Eurostat road_eqs_carpda (2024) for the fuel split and the air-quality study of the municipality of Constanța (Amzu R et al. 2021, version 2.1) for the distribution over emission standards."
}
"""


def main():
    global IESIRE
    final = IESIRE

    # Verificarea se face ÎNAINTE de a atinge pachetul existent: o rulare care
    # eșuează nu trebuie să distrugă versiunea precedentă.
    for cale in surse_obligatorii():
        if not os.path.exists(cale):
            lipseste(cale)
    if LIPSA:
        print("%d fișiere obligatorii nu au fost găsite:" % len(LIPSA))
        for c in LIPSA:
            print("   -", c)
        if not PERMITE_INCOMPLET:
            print("\nNu s-a construit nimic și pachetul existent este neatins.\n"
                  "Completează fișierele și reia, sau rulează cu\n"
                  "CAR2026_PERMITE_INCOMPLET=1 dacă vrei totuși un pachet marcat\n"
                  "explicit ca incomplet.")
            raise SystemExit(1)
        print("   se continuă: pachetul va fi marcat ca incomplet.\n")

    # Construcția merge într-un dosar temporar; înlocuirea se face la final.
    IESIRE = final + ".tmp"
    if os.path.exists(IESIRE):
        shutil.rmtree(IESIRE)
    os.makedirs(IESIRE)
    print("Construiesc depozitul în", final)
    print("Politica privind coordonatele:", COORDONATE)

    print(" data/")
    scrie_loguri()
    for f in DERIVATE:
        copiaza(os.path.join(DIR_RUTE, f), os.path.join(IESIRE, "data"))
    print(" data/raw/")
    scrie_brute()
    if RESPINSE:
        print("\n%d rânduri au fost respinse la citirea exporturilor brute:"
              % len(RESPINSE))
        for f, r in RESPINSE[:10]:
            print("   %s: %s" % (f, str(r)[:160]))
        raport = os.path.join(IESIRE, "data", "raw", "RANDURI_RESPINSE.txt")
        open(raport, "w", encoding="utf-8").write(
            "Rânduri pe care parserul CSV nu le-a putut citi și care lipsesc din "
            "fișierele\npublicate în data/raw/:\n\n"
            + "\n".join("%s: %s" % (f, r) for f, r in RESPINSE) + "\n")
        if not ACCEPTA_RESPINSE:
            print("\nConstrucția s-a oprit: README-ul afirmă că exporturile brute "
                  "păstrează\ntoate rândurile, iar afirmația nu mai este adevărată. "
                  "Corectează fișierele\nsursă, sau rulează cu "
                  "CAR2026_ACCEPTA_RANDURI_RESPINSE=1 pentru a publica\ntotuși "
                  "pachetul, caz în care lista respinsă rămâne în "
                  "data/raw/RANDURI_RESPINSE.txt.\nPachetul precedent este neatins.")
            raise SystemExit(1)
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

    # Marcajul pachetului incomplet (se ajunge aici doar cu PERMITE_INCOMPLET).
    if LIPSA:
        open(os.path.join(IESIRE, "PACHET_INCOMPLET.txt"), "w",
             encoding="utf-8").write(
            "Acest pachet este INCOMPLET. Următoarele fișiere obligatorii nu au "
            "fost găsite\nla construirea lui și lipsesc din arhivă:\n\n"
            + "\n".join(LIPSA) + "\n")

    avertisment = ("> **This package is incomplete.** %d required files were "
                   "missing when it was built; they are listed in "
                   "`PACHET_INCOMPLET.txt`.\n\n" % len(LIPSA)) if LIPSA else ""
    open(os.path.join(IESIRE, "README.md"), "w", encoding="utf-8").write(
        avertisment + README.replace("COORD_NOTE", NOTA_COORD[COORDONATE]))
    open(os.path.join(IESIRE, "LICENSE-CODE.txt"), "w", encoding="utf-8").write(MIT)
    open(os.path.join(IESIRE, "CITATION.cff"), "w", encoding="utf-8").write(CITATION)
    open(os.path.join(IESIRE, ".gitignore"), "w", encoding="utf-8").write(GITIGNORE)
    open(os.path.join(IESIRE, ".zenodo.json"), "w", encoding="utf-8").write(ZENODO)

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
    # Înlocuirea pachetului precedent, abia acum, după o construcție reușită.
    if os.path.exists(final):
        vechi = final + ".vechi"
        if os.path.exists(vechi):
            shutil.rmtree(vechi)
        os.rename(final, vechi)
        os.rename(IESIRE, final)
        shutil.rmtree(vechi)
    else:
        os.rename(IESIRE, final)
    IESIRE = final

    print("\n%d fișiere, %.1f MB" % (len(linii) - 1, total / 1e6))
    if LIPSA:
        print("PACHET INCOMPLET: %d fișiere obligatorii lipsesc "
              "(vezi PACHET_INCOMPLET.txt)." % len(LIPSA))
    print("Gata:", final)


if __name__ == "__main__":
    main()
