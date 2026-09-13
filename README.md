# Real-driving data and models for Constanța (CAR2026)

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
netconvert --osm-files constanta.osm -o constanta.net.xml \
           --geometry.remove --roundabouts.guess --ramps.guess \
           --junctions.join --tls.guess-signals --tls.join \
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

The 1 Hz records are published without latitude and longitude. No numerical result in the paper depends on them: cumulative distance is the integral of speed, and consumption, cycle parameters and calibration are computed from the speed trace alone. Route geometry is provided separately in `data/geometry/`, thinned to one point in five seconds and trimmed by 400 m at both ends, which is enough to place the routes on a map but not to identify the start and end addresses.

## Contact

A M Beldugan, Ovidius University of Constanța, beldugan.adrian@gmail.com
