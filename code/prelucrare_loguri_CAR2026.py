# -*- coding: utf-8 -*-
"""
prelucrare_loguri_CAR2026.py
================================================================================
Prelucrarea logurilor Torque Pro pentru lucrarea CAR2026 (RDE Constanta)
si auditul segmentarii — raspunsul verificabil la intrebarea:
  ce intervale au fost eliminate, dupa ce criteriu, si cat timp s-a exclus
  din fiecare incercare.

Moduri de rulare:
  python prelucrare_loguri_CAR2026.py audit
      reconstituie, din datele brute + logurile livrate, lista exacta a
      intervalelor eliminate, inventarul opririlor pastrate si contraproba.
  python prelucrare_loguri_CAR2026.py rerun
      reface prelucrarea de la zero cu regula de mai jos si scrie loguri noi
      la 1 Hz in `Loguri rute\\reprocesat`.

Cale de baza: variabila de mediu CAR2026_BASE sau constanta BASE.
Dependinte: pandas, numpy.

================================================================================
CRITERIUL DE ELIMINARE — formularea corecta, verificata pe date (12.09.2026)
--------------------------------------------------------------------------------
Formularea "segmentare la pauze > 30 s" din antetul logurilor livrate este
inexacta si induce in eroare. Verificarea secunda cu secunda arata urmatoarele:

  A) NICIO oprire in trafic nu a fost eliminata. In logurile livrate raman
     opriri de 105 s, 97 s, 85 s, 67 s, 63 s etc. — semafoare, intersectii,
     cozi. Un prag de 30 s aplicat literal ar fi taiat 8 opriri din RUTA_A si
     ar fi coborat stationarea de la 32,1% la 12,7% (vezi sectiunea [4] a
     auditului), adica ar fi distrus exact fenomenul masurat.

  B) Singurele intervale absente din loguri sunt intervalele in care
     INREGISTRAREA NU A PRODUS DATE — Torque a fost oprit / pus in pauza —
     plus doua fisiere scurte inregistrate integral in punctul de plecare, cu
     vehiculul imobil. Nu a existat o decizie de filtrare a opririlor: tot ce
     a fost inregistrat in miscare se afla in logurile livrate.
     Verificare aritmetica: durata bruta pe ceas minus golurile de inregistrare
     este egala, la o secunda, cu durata logurilor livrate.

  C) Pragul de 30 s este pragul de SEGMENTARE: doua esantioane consecutive
     raman in acelasi segment doar daca sunt la mai putin de 30 s unul de
     altul; peste acest prag se deschide un segment nou (coloana `segment`),
     tocmai pentru ca accelerarile nu se calculeaza peste o discontinuitate.
     Este un prag de continuitate temporala, nu un filtru de opriri.

  D) Rezerva care trebuie declarata explicit in lucrare: golul de 557 s de la
     inceputul inregistrarii RUTA_A nu este ralanti, ci lipsa de date — intre
     11:38:56 si 11:48:05 vehiculul s-a deplasat efectiv ~1,86 km (pozitia GPS
     de dinainte si cea de dupa difera). Prin urmare RUTA_A nu este o incercare
     continua, ci doua tronsoane, iar cei 13,39 km nu includ acel kilometraj.
================================================================================
"""

import io
import os
import re
import sys

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ PARAMETRI
BASE = os.environ.get("CAR2026_BASE", r"D:\Lucrare CAR2026")
def _primul_dir(*candidati):
    """Merge și în structura de lucru, și în cea a depozitului public."""
    for c in candidati:
        if os.path.isdir(c):
            return c
    return candidati[-1]


DIR_BRUT = _primul_dir(os.path.join(BASE, "Date brute CSV"),
                       os.path.join(BASE, "data", "raw"))
DIR_RUTE = _primul_dir(os.path.join(BASE, "Loguri rute"),
                       os.path.join(BASE, "data"))

V_STOP = 1.0      # km/h - sub aceasta viteza vehiculul e considerat stationar
T_SEG = 30.0      # s    - gol de inregistrare peste care se deschide segment nou
T_PARK = 180.0    # s    - gol in care vehiculul nu s-a deplasat => parcare
D_PARK = 50.0     # m    - deplasare GPS maxima admisa intr-un gol de tip parcare
FS = 1.0          # Hz   - frecventa de reesantionare

LOGURI_BRUTE = {
    "A_pre": "trackLog-2026-apr.-02_11-01-45.csv",
    "A_pre2": "trackLog-2026-apr.-02_11-32-38.csv",
    "A": "trackLog-2026-apr.-02_11-38-27.csv",
    "B": "trackLog-2026-apr.-02_15-28-27.csv",
    "D": "trackLog_diesel_2.0TDI_BKD_2026sept.11_091422.csv",
}
LOGURI_LIVRATE = {
    "RUTA_A": "log_RUTA_A_Bratianu-Ferdinand-Mamaia_11-13.csv",
    "RUTA_B": "log_RUTA_B_Mamaia-Navodari_15-17.csv",
    "DIESEL": "log_DIESEL_Constanta-DN3-Murfatlar_09-10.csv",
}
SURSE = {"RUTA_A": ["A_pre", "A_pre2", "A"], "RUTA_B": ["B"], "DIESEL": ["D"]}

LUNI = {"ian": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "iun": 6, "iul": 7,
        "aug": 8, "sept": 9, "sep": 9, "oct": 10, "noi": 11, "nov": 11, "dec": 12}


# ------------------------------------------------------------------- UTILITARE
def parse_device_time(s):
    """Torque scrie Device Time localizat romaneste: '02-apr.-2026 11:38:40.875'.
    Se foloseste Device Time, NU GPS Time: in fisierul de la 15:28 campul
    GPS Time este eronat (repeta orele fisierului de la 11:38)."""
    m = re.match(r"\s*(\d+)-([a-zA-Z]+)\.?-(\d{4})\s+(\d+):(\d+):(\d+)(?:\.(\d+))?",
                 str(s))
    if not m:
        return pd.NaT
    d, mo, y, H, M, S, ms = m.groups()
    luna = LUNI.get(mo.lower().strip("."))
    if luna is None:
        return pd.NaT
    return pd.Timestamp(int(y), luna, int(d), int(H), int(M), int(S),
                        int((ms or "0").ljust(3, "0")) * 1000)


def antet_referinta():
    cale = os.path.join(DIR_BRUT, LOGURI_BRUTE["A"])
    with open(cale, encoding="utf-8", errors="replace") as f:
        return [c.strip() for c in f.readline().split(",")]


def citeste_brut(cale, antet_ref=None):
    """Citeste un log Torque. Fisierul 11-01-45 nu are rand de antet -
    i se aplica antetul de referinta."""
    with open(cale, encoding="utf-8", errors="replace") as f:
        prima = f.readline()
    if prima.startswith("GPS Time"):
        df = pd.read_csv(cale, engine="python", on_bad_lines="skip")
    else:
        if antet_ref is None:
            raise ValueError("Fisier fara antet si fara antet de referinta: " + cale)
        df = pd.read_csv(cale, engine="python", on_bad_lines="skip",
                         header=None, names=antet_ref)
    df.columns = [c.strip() for c in df.columns]
    return df


def citeste_livrat(cale):
    """Logurile livrate au un bloc de comentarii '#' inaintea antetului."""
    linii = open(cale, encoding="utf-8", errors="replace").read().splitlines()
    i0 = next(i for i, l in enumerate(linii)
              if l and not l.startswith("#") and "," in l)
    return pd.read_csv(io.StringIO("\n".join(linii[i0:])))


def canale(df):
    """Extrage canalele folosite, curatate de randurile corupte."""
    t = df["Device Time"].map(parse_device_time)
    v = pd.to_numeric(df.get("Speed (OBD)(km/h)"), errors="coerce")
    v = v.fillna(pd.to_numeric(df.get("Speed (GPS)(km/h)"), errors="coerce"))
    gol = pd.Series([float("nan")] * len(df))
    lat = pd.to_numeric(df["Latitude"], errors="coerce") if "Latitude" in df else gol
    lon = pd.to_numeric(df["Longitude"], errors="coerce") if "Longitude" in df else gol
    ok = t.notna() & v.notna()
    return (t[ok].reset_index(drop=True), v[ok].reset_index(drop=True),
            lat[ok].reset_index(drop=True), lon[ok].reset_index(drop=True))


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(a))


def goluri(t, lat, lon, prag=T_SEG):
    """Golurile de inregistrare: intervale dintre doua esantioane consecutive
    mai lungi decat `prag`. Returneaza (t0, t1, durata_s, deplasare_GPS_m)."""
    rez = []
    dt = t.diff().dt.total_seconds()
    for i in np.where(dt > prag)[0]:
        try:
            d = float(haversine(lat[i - 1], lon[i - 1], lat[i], lon[i]))
        except Exception:
            d = float("nan")
        rez.append((t[i - 1], t[i], float(dt[i]), d))
    return rez


def la_1hz(t, v, lat, lon):
    """Reesantionare liniara la 1 Hz pe baza Device Time.
    OBLIGATORIE: esantionarea bruta a logurilor din aprilie este ~1,77 s, nu 1 s.
    Fara acest pas acceleratiile si RPA sunt supraestimate cu ~77%."""
    ts = (t - t.iloc[0]).dt.total_seconds()
    grid = np.arange(0, ts.iloc[-1] + 1e-9, 1.0 / FS)
    out = pd.DataFrame({
        "t_rel_s": grid,
        "timestamp": [t.iloc[0] + pd.Timedelta(seconds=float(x)) for x in grid],
        "v_kmh": np.interp(grid, ts, v),
        "lat": np.interp(grid, ts, lat.ffill().bfill()),
        "lon": np.interp(grid, ts, lon.ffill().bfill()),
    })
    out["stationare"] = (out["v_kmh"] < V_STOP).astype(int)
    return out


def episoade(masca):
    """Intervalele continue in care masca e adevarata -> [(i0, i1, durata_s)]"""
    m = np.asarray(masca, dtype=bool)
    rez, i, n = [], 0, len(m)
    while i < n:
        if m[i]:
            j = i
            while j + 1 < n and m[j + 1]:
                j += 1
            rez.append((i, j, j - i + 1))
            i = j + 1
        else:
            i += 1
    return rez


def opriri_pe_segmente(L):
    """Duratele opririlor, numarate PE SEGMENT. Numararea pe fisierul intreg
    lipeste doua opriri separate de o taietura si produce durate fictive
    (ex. 54 s in RUTA_A, 102 s in RUTA_B — artefacte, nu opriri reale)."""
    dur = []
    grup = L.groupby("segment") if "segment" in L.columns else [("tot", L)]
    for _, g in grup:
        g = g.reset_index(drop=True)
        dur += [e[2] for e in episoade(g["stationare"].values)]
    return np.array(sorted(dur, reverse=True))


# ----------------------------------------------------------------------- AUDIT
def audit():
    antet = antet_referinta()
    print("=" * 78)
    print("AUDITUL SEGMENTARII — ce s-a eliminat efectiv din fiecare incercare")
    print("=" * 78)

    brut, gol = {}, {}
    print("\n[1] INREGISTRARI BRUTE (Device Time, dupa reesantionare la 1 Hz)\n")
    for k, f in LOGURI_BRUTE.items():
        cale = os.path.join(DIR_BRUT, f)
        if not os.path.exists(cale):
            print("   LIPSA:", cale)
            continue
        t, v, lat, lon = canale(citeste_brut(cale, antet))
        d = la_1hz(t, v, lat, lon)
        brut[k], gol[k] = d, goluri(t, lat, lon)
        ep = episoade(d["stationare"].values)
        print(f"   {f}")
        print(f"      {t.iloc[0]} -> {t.iloc[-1]} | {len(t)} randuri | "
              f"{len(d)} s pe ceas | dt median {t.diff().dt.total_seconds().median():.3f} s")
        print(f"      stationare {int(d['stationare'].sum())} s "
              f"({100 * d['stationare'].mean():.1f}%) in {len(ep)} episoade")
        for t0, t1, dur, dep in gol[k]:
            if dep != dep:      # NaN: exportul public nu contine coordonate
                tip = "deplasare GPS indisponibila (coloane de pozitie absente)"
            elif dep <= D_PARK:
                tip = "vehicul imobil (deplasare GPS nula)"
            else:
                tip = f"VEHICULUL S-A DEPLASAT {dep:.0f} m — date lipsa, nu ralanti"
            print(f"      gol de inregistrare {dur:7.0f} s: {t0.time()} -> "
                  f"{t1.time()} | {tip}")

    print("\n[2] INTERVALE ELIMINATE (brut pe ceas - livrat)\n")
    for nume, surse in SURSE.items():
        cale = os.path.join(DIR_RUTE, LOGURI_LIVRATE[nume])
        if not os.path.exists(cale) or surse[-1] not in brut:
            print("   LIPSA:", cale)
            continue
        L = citeste_livrat(cale)
        tl = pd.to_datetime(L["timestamp_local"])
        t_brut = sum(len(brut[s]) for s in surse if s in brut)
        t_gol = sum(int(g[2]) for s in surse if s in gol for g in gol[s])
        t_fis = sum(len(brut[s]) for s in surse[:-1] if s in brut)
        print(f"   --- {nume}: brut {t_brut} s -> livrat {len(L)} s | "
              f"ELIMINAT {t_brut - len(L)} s "
              f"({100 * (t_brut - len(L)) / t_brut:.1f}%)")
        for s in surse[:-1]:
            if s in brut:
                b = brut[s]
                print(f"       fisier intreg: {LOGURI_BRUTE[s]} — {len(b)} s, "
                      f"{100 * b['stationare'].mean():.0f}% stationare, "
                      f"inregistrat in punctul de plecare, vehicul imobil")
        for t0, t1, dur, dep in gol[surse[-1]]:
            print(f"       gol de inregistrare: {t0} -> {t1} = {dur:.0f} s "
                  f"(deplasare GPS {dep:.0f} m)")
        print(f"       VERIFICARE: {t_brut} - {t_fis} (fisiere imobile) - "
              f"{t_gol} (goluri) = {t_brut - t_fis - t_gol} s vs "
              f"{len(L)} s livrati -> diferenta "
              f"{abs(t_brut - t_fis - t_gol - len(L))} s (rotunjire)")
        print(f"       => niciun interval nu a fost eliminat prin filtrarea "
              f"opririlor; s-a eliminat doar ce nu a fost inregistrat.")

    print("\n[3] OPRIRI PASTRATE IN LOGURILE LIVRATE "
          "(semafor / intersectie / coada)\n")
    for nume, f in LOGURI_LIVRATE.items():
        cale = os.path.join(DIR_RUTE, f)
        if not os.path.exists(cale):
            continue
        L = citeste_livrat(cale)
        dur = opriri_pe_segmente(L)
        km = L["dist_cum_m"].max() / 1000.0
        print(f"   --- {nume}: {len(L)} s, {km:.2f} km, stationare "
              f"{int(L['stationare'].sum())} s "
              f"({100 * L['stationare'].mean():.1f}%), {len(dur)} opriri, "
              f"cea mai lunga {dur.max()} s")
        for lo, hi in [(1, 10), (10, 30), (30, 60), (60, 121)]:
            sel = (dur >= lo) & (dur < hi)
            if sel.sum():
                print(f"        {lo:3d}-{hi-1:3d} s: {sel.sum():3d} opriri, "
                      f"{dur[sel].sum():4d} s cumulat")
        print(f"        opriri PESTE 30 s pastrate: "
              f"{sorted(dur[dur > 30].tolist(), reverse=True)}")
        for prag in (3, 5, 10):
            n = int((dur >= prag).sum())
            print(f"        nr. opriri cu durata >= {prag:2d} s: {n} "
                  f"-> {n / km:.2f} opriri/km")

    print("\n[4] CONTRAPROBA: ce s-ar fi intamplat daca pragul de 30 s")
    print("    ar fi fost aplicat literal TUTUROR opririlor\n")
    for nume, f in LOGURI_LIVRATE.items():
        cale = os.path.join(DIR_RUTE, f)
        if not os.path.exists(cale):
            continue
        L = citeste_livrat(cale)
        km = L["dist_cum_m"].max() / 1000.0
        pastrez = np.ones(len(L), bool)
        grup = L.groupby("segment") if "segment" in L.columns else [("tot", L)]
        for _, g in grup:
            idx = g.index.values
            for a, b, n in episoade(g["stationare"].values):
                if n > 30:
                    pastrez[idx[a]:idx[b] + 1] = False
        T0, T1 = len(L), int(pastrez.sum())
        print(f"   {nume}: {T0} s -> {T1} s | stationare "
              f"{100 * L['stationare'].mean():.1f}% -> "
              f"{100 * L.loc[pastrez, 'stationare'].mean():.1f}% | v_med "
              f"{3.6 * km * 1000 / T0:.1f} -> {3.6 * km * 1000 / T1:.1f} km/h")
    print("\n   => pragul literal de 30 s ar sterge tocmai opririle in trafic")
    print("      care constituie obiectul masuratorii. Nu a fost aplicat asa.")


# ----------------------------------------------------------------------- RERUN
def rerun():
    """Reface prelucrarea de la zero: 1 Hz + segmentare la goluri > T_SEG.
    Nu se elimina nicio oprire; se elimina doar intervalele fara date."""
    antet = antet_referinta()
    ies_dir = os.path.join(DIR_RUTE, "reprocesat")
    os.makedirs(ies_dir, exist_ok=True)
    for k, f in LOGURI_BRUTE.items():
        cale = os.path.join(DIR_BRUT, f)
        if not os.path.exists(cale):
            continue
        t, v, lat, lon = canale(citeste_brut(cale, antet))
        G = goluri(t, lat, lon)
        # reesantionare pe fiecare tronson continuu, separat
        limite = [t.iloc[0]] + [x for g in G for x in (g[0], g[1])] + [t.iloc[-1]]
        parti, seg = [], 0
        for a, b in zip(limite[::2], limite[1::2]):
            m = (t >= a) & (t <= b)
            if m.sum() < 2:
                continue
            p = la_1hz(t[m].reset_index(drop=True), v[m].reset_index(drop=True),
                       lat[m].reset_index(drop=True), lon[m].reset_index(drop=True))
            p["segment"] = seg
            seg += 1
            parti.append(p)
        if not parti:
            print(f"{f}: prea putine date -> exclus")
            continue
        d = pd.concat(parti, ignore_index=True)
        if d["stationare"].mean() == 1.0:
            print(f"{f}: integral stationar (vehicul imobil) -> exclus")
            continue
        d["dist_cum_m"] = (d["v_kmh"] / 3.6).cumsum()
        d["a_ms2"] = d["v_kmh"].diff().fillna(0) / 3.6
        d.loc[d["segment"].diff() != 0, "a_ms2"] = 0.0
        ies = os.path.join(ies_dir, "reproc_" + f)
        d.to_csv(ies, index=False, encoding="utf-8")
        print(f"{f}: {len(d)} s pastrati in {seg} segment(e), "
              f"{d['dist_cum_m'].max()/1000:.2f} km, "
              f"stationare {100*d['stationare'].mean():.1f}% -> {ies}")


if __name__ == "__main__":
    mod = sys.argv[1] if len(sys.argv) > 1 else "audit"
    (rerun if mod == "rerun" else audit)()
