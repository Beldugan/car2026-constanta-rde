# Real-driving data and models for Constanța (CAR2026)

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
netconvert --osm-files constanta.osm -o constanta.net.xml \
           --geometry.remove --roundabouts.guess --ramps.guess \
           --junctions.join --tls.guess-signals --tls.join \
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

The 1 Hz records are published without latitude and longitude. Cumulative distance is the integral of speed, so the cycle parameters, the speed-class split and the model calculations do not use position: the Willans calibration and the modelled fuel rates are computed from the speed trace together with the vehicle parameters in table 1, and the SI reference consumption from the recorded mass air flow, all of which are published. What cannot be reproduced from these files is figure 1, the map-matched street names and the `dist_map_match_m` column, all of which need position. Route geometry is provided separately in `data/geometry/`, thinned to one point in five seconds and trimmed by 400 m at both ends, which is enough to place the routes on a map but not to identify the start and end addresses.

## Contact

A M Beldugan, Ovidius University of Constanța, beldugan.adrian@gmail.com
