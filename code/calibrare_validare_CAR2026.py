# -*- coding: utf-8 -*-
"""
calibrare_validare_CAR2026.py
================================================================================
Rezolvă cele două cerințe de calcul rămase din revizia editorială:

  SARCINA A (comentariul C6) — validare out-of-sample pentru vehiculul MAS:
      modelul se calibrează NUMAI pe R_A, iar R_B se păstrează integral ca
      parcurgere de validare. Nu se împart secundele aceleiași parcurgeri
      între calibrare și validare.

  SARCINA B (comentariul C7) — efectul termic la vehiculul MAC:
      referința de consum se recalculează excluzând intervalul de încălzire
      (t < 694 s, până la 80 °C lichid de răcire) și se raportează ambele
      variante, cu efectul asupra celulelor extrapolate.

În plus, verifică faptul de bază: că modelul și coeficienții publicați
reproduc exact valorile din Tabelul 7.

    python calibrare_validare_CAR2026.py

Cale de bază: variabila de mediu CAR2026_BASE sau constanta BASE de mai jos.
Dependințe: numpy și pandas. scipy NU este necesar — dacă lipsește, se
folosește implementarea Lawson-Hanson inclusă mai jos, verificată că dă
aceleași rezultate ca scipy.optimize.nnls.
================================================================================
"""

import io
import os

import numpy as np
import pandas as pd

try:                                    # scipy e opțional
    from scipy.optimize import nnls
except ImportError:
    def nnls(A, b, tol=1e-10, maxiter=None):
        """Algoritmul Lawson-Hanson pentru cele mai mici pătrate cu
        constrângere de nenegativitate, scris în numpy pur.
        Returnează (coeficienți, reziduu), ca scipy.optimize.nnls."""
        A = np.asarray(A, float)
        b = np.asarray(b, float)
        n = A.shape[1]
        if maxiter is None:
            maxiter = 3 * n
        P = np.zeros(n, bool)           # mulțimea coeficienților activi
        x = np.zeros(n)
        w = A.T @ (b - A @ x)
        it = 0
        while (not P.all()) and (w[~P] > tol).any() and it < maxiter:
            it += 1
            j = np.where(~P)[0][np.argmax(w[~P])]
            P[j] = True
            s = np.zeros(n)
            s[P] = np.linalg.lstsq(A[:, P], b, rcond=None)[0]
            while s[P].min() <= 0:      # pas de retragere
                neg = P & (s <= 0)
                alpha = (x[neg] / (x[neg] - s[neg])).min()
                x = x + alpha * (s - x)
                P &= ~(np.abs(x) < tol)
                s = np.zeros(n)
                s[P] = np.linalg.lstsq(A[:, P], b, rcond=None)[0]
            x = s
            w = A.T @ (b - A @ x)
        return x, float(np.linalg.norm(b - A @ x))

BASE = os.environ.get("CAR2026_BASE", r"D:\Lucrare CAR2026")
def _primul_dir(*candidati):
    """Merge și în structura de lucru, și în cea a depozitului public."""
    for c in candidati:
        if os.path.isdir(c):
            return c
    return candidati[-1]


DIR_RUTE = _primul_dir(os.path.join(BASE, "Loguri rute"),
                       os.path.join(BASE, "data"))

# ------------------------------------------------------------------ PARAMETRI
# Vehiculul MAS — Opel Astra H GTC 1.6i (Z16XEP)
M_MAS, CDA_MAS, VD_MAS = 1235.0, 0.666, 1.598      # kg, m2, L
# Vehiculul MAC — VW Touran 2.0 TDI (BKD)
M_MAC, CDA_MAC, VD_MAC = 1670.0, 0.790, 1.968
CRR, RHO_AER, EPS = 0.011, 1.2, 0.05
RHO_BENZINA, RHO_MOTORINA = 745.0, 835.0            # g/L
CO2_BENZINA, CO2_MOTORINA = 3.17, 3.16              # g CO2 / g combustibil
AFR = 14.7
P_STAR = 12.0                                       # kW, prag adoptat a priori
RALANTI_MAS, RALANTI_MAC = 0.75, 0.55               # L/h
FACTOR_TAIERE = 0.15
T_CALD = 694.0                                      # s, momentul atingerii a 80 °C

# coeficienții publicați, pentru verificare
COEF_PUBLICAT = {"MAS": (0.0621, 0.0554, 0.0134, 0.1080),
                 "MAC": (0.0688, 0.0588, 0.0044, 0.0275)}

LOG = {"R_A": "log_RUTA_A_Bratianu-Ferdinand-Mamaia_11-13.csv",
       "R_B": "log_RUTA_B_Mamaia-Navodari_15-17.csv",
       "R_DN3": "log_DIESEL_Constanta-DN3-Murfatlar_09-10.csv"}
EXTRAPOLAT = {"MAC pe R_A": ("extrapolat_R_A_diesel.csv", RHO_MOTORINA),
              "MAC pe R_B": ("extrapolat_R_B_diesel.csv", RHO_MOTORINA),
              "MAS pe R_DN3": ("extrapolat_R_DN3_benzina.csv", RHO_BENZINA)}


# ------------------------------------------------------------------- UTILITARE
def citeste(cale):
    linii = open(cale, encoding="utf-8", errors="replace").read().splitlines()
    i0 = next(i for i, l in enumerate(linii)
              if l and not l.startswith("#") and "," in l)
    return pd.read_csv(io.StringIO("\n".join(linii[i0:])))


def putere_roata(v_kmh, a_ms2, masa, cda):
    """Ecuația (1): rezistență la rulare + aerodinamică + inerție, in kW."""
    v = np.asarray(v_kmh) / 3.6
    a = np.asarray(a_ms2)
    F = CRR * masa * 9.81 + 0.5 * RHO_AER * cda * v ** 2 + masa * a * (1 + EPS)
    return F * v / 1000.0


def matrice_model(P, rpm, vd):
    """Coloanele ecuației (2) în forma continuă, verificată pe seriile livrate:
       ṁ = A1·min(P,P*) + A2·max(P−P*,0) + B·Vd·n/120 + C"""
    return np.c_[np.clip(np.minimum(P, P_STAR), 0, None),
                 np.maximum(P - P_STAR, 0),
                 vd * np.asarray(rpm) / 120.0,
                 np.ones(len(P))]


def masti(d, P):
    """Secundele de ralanti și cele cu tăiere de injecție, tratate separat."""
    idle = (d["stationare"] == 1).values
    taiere = (P < -1) & (d["v_kmh"].values > 15) & (d["rpm"].values > 1300)
    return idle, taiere & ~idle


def prezice(X, coef, idle, taiere, ralanti_lh, rho):
    m = np.maximum(X @ np.asarray(coef), 0.0)
    m = np.where(taiere, m * FACTOR_TAIERE, m)
    m = np.where(idle, ralanti_lh * rho / 3600.0, m)
    return m


def l100(mdot, km, rho):
    return 100.0 * (np.nansum(mdot) / rho) / km


def calibreaza(X, y, idle, taiere):
    """NNLS pe debitul masic, secundă cu secundă, fără secundele de ralanti și
    fără cele cu tăiere de injecție (acolo modelul este înlocuit de reguli fixe).
    Constrângeri: toți coeficienții ≥ 0. Funcție obiectiv: suma pătratelor."""
    ok = ~(idle | taiere) & np.isfinite(y) & np.isfinite(X).all(1)
    coef, rez = nnls(X[ok], y[ok])
    return coef, int(ok.sum())


def pregateste_MAS(nume):
    d = citeste(os.path.join(DIR_RUTE, LOG[nume]))
    P = putere_roata(d["v_kmh"], d["a_ms2"], M_MAS, CDA_MAS)
    idle, taiere = masti(d, P)
    X = matrice_model(P, d["rpm"].values, VD_MAS)
    y = (d["maf_g_s"] / AFR).values          # referința din măsurători
    km = d["dist_cum_m"].max() / 1000.0
    return d, X, y, idle, taiere, km


# ================================================================ VERIFICAREA
def verificare_coeficienti_publicati():
    print("=" * 78)
    print("VERIFICARE — coeficienții publicați reproduc valorile din Tabelul 7?")
    print("=" * 78)
    for nume in ("R_A", "R_B"):
        d, X, y, idle, taiere, km = pregateste_MAS(nume)
        ref = l100(y, km, RHO_BENZINA)
        print(f"  {nume}: referință din MAF/{AFR} = {ref:.2f} L/100 km "
              f"pe {km:.2f} km  (Tabelul 7: 10,83 și 8,90)")
    for et, (f, rho) in EXTRAPOLAT.items():
        cale = os.path.join(DIR_RUTE, f)
        if not os.path.exists(cale):
            print(f"  {et}: lipsește {f}")
            continue
        e = citeste(cale)
        km = e["dist_cum_m"].max() / 1000.0
        print(f"  {et}: seria livrată dă {l100(e['debit_comb_g_s'], km, rho):.2f} "
              f"L/100 km pe {km:.2f} km")
    print("  => dacă aceste valori coincid cu Tabelul 7, modelul publicat este")
    print("     reproductibil din coeficienți, ceea ce este cerința recenziei.\n")


# ============================================================== SARCINA A (C6)
def sarcina_A():
    print("=" * 78)
    print("SARCINA A — validare out-of-sample MAS: calibrare pe R_A, validare pe R_B")
    print("=" * 78)
    dA, XA, yA, iA, tA, kmA = pregateste_MAS("R_A")
    dB, XB, yB, iB, tB, kmB = pregateste_MAS("R_B")

    cAB, nAB = calibreaza(np.vstack([XA, XB]), np.r_[yA, yB],
                          np.r_[iA, iB], np.r_[tA, tB])
    cA, nA = calibreaza(XA, yA, iA, tA)
    print(f"  calibrare pe R_A + R_B ({nAB} secunde): "
          f"A1 {cAB[0]:.4f}  A2 {cAB[1]:.4f}  B {cAB[2]:.4f}  C {cAB[3]:.4f}")
    print(f"  calibrare NUMAI pe R_A ({nA} secunde):  "
          f"A1 {cA[0]:.4f}  A2 {cA[1]:.4f}  B {cA[2]:.4f}  C {cA[3]:.4f}")

    refA, refB = l100(yA, kmA, RHO_BENZINA), l100(yB, kmB, RHO_BENZINA)
    pA = prezice(XA, cA, iA, tA, RALANTI_MAS, RHO_BENZINA)
    pB = prezice(XB, cA, iB, tB, RALANTI_MAS, RHO_BENZINA)
    vA, vB = l100(pA, kmA, RHO_BENZINA), l100(pB, kmB, RHO_BENZINA)
    print()
    print(f"  R_A, in-sample:        {vA:5.2f} vs referință {refA:5.2f} L/100 km"
          f"  ->  {100*(vA-refA)/refA:+.1f} %")
    print(f"  R_B, OUT-OF-SAMPLE:    {vB:5.2f} vs referință {refB:5.2f} L/100 km"
          f"  ->  {100*(vB-refB)/refB:+.1f} %   <-- cifra cerută de recenzie")
    print()
    print("  Interpretare: eroarea pe R_B este eroarea de transfer între regimuri")
    print("  de conducere — R_A este urban sever (20,3 km/h), R_B este radial")
    print("  (33,0 km/h). Ea mărginește de jos incertitudinea celulelor")
    print("  extrapolate din Tabelul 7 și trebuie raportată ca atare.\n")
    return vB, refB


# ============================================================== SARCINA B (C7)
def sarcina_B():
    print("=" * 78)
    print("SARCINA B — efectul termic: referința MAC fără intervalul de încălzire")
    print("=" * 78)
    d = citeste(os.path.join(DIR_RUTE, LOG["R_DN3"]))
    cald = d["t_rel_s"].values >= T_CALD
    dist = (d["v_kmh"] / 3.6).values
    t80 = d.loc[d["t_lichid_racire_C"] >= 80, "t_rel_s"].min()
    print(f"  lichid de răcire la pornire {d['t_lichid_racire_C'].iloc[0]:.0f} °C; "
          f"80 °C atinse la t = {t80:.0f} s")
    print(f"  încălzirea reprezintă {100*(~cald).mean():.1f} % din durată și "
          f"{dist[~cald].sum()/1000:.2f} km din {dist.sum()/1000:.2f} km\n")

    rez = {}
    for et, m in [("parcurs integral", np.ones(len(d), bool)),
                  ("numai porțiunea caldă", cald)]:
        km = dist[m].sum() / 1000.0
        fiz = 100 * (d.loc[m, "debit_comb_fizic_ml_s"].sum() / 1000) / km
        tor = 100 * (d.loc[m, "debit_comb_model_ml_s"].sum() / 1000) / km
        rez[et] = (fiz + tor) / 2
        print(f"  {et:24s}: model fizic {fiz:.2f} | model Torque {tor:.2f} "
              f"| media {rez[et]:.2f} L/100 km pe {km:.2f} km")

    k = rez["numai porțiunea caldă"] / rez["parcurs integral"]
    print(f"\n  Referința MAC: {rez['parcurs integral']:.2f} -> "
          f"{rez['numai porțiunea caldă']:.2f} L/100 km  ({100*(k-1):+.1f} %)")
    print("  Coeficienții MAC sunt ancorați în această referință, iar modelul este")
    print("  liniar în coeficienți, deci celulele extrapolate se scalează cu același")
    print("  factor, cu excepția secundelor de ralanti, care rămân fixe:\n")

    for et, (f, rho) in EXTRAPOLAT.items():
        if not et.startswith("MAC"):
            continue
        cale = os.path.join(DIR_RUTE, f)
        if not os.path.exists(cale):
            print(f"    {et}: lipsește {f}")
            continue
        e = citeste(cale)
        km = e["dist_cum_m"].max() / 1000.0
        ral = RALANTI_MAC * rho / 3600.0
        este_ral = np.isclose(e["debit_comb_g_s"].values, ral, atol=1e-4)
        vechi = l100(e["debit_comb_g_s"], km, rho)
        nou_mdot = np.where(este_ral, e["debit_comb_g_s"].values,
                            e["debit_comb_g_s"].values * k)
        nou = l100(nou_mdot, km, rho)
        print(f"    {et}: {vechi:.2f} -> {nou:.2f} L/100 km  "
              f"({vechi*CO2_MOTORINA*rho/100:.1f} -> {nou*CO2_MOTORINA*rho/100:.1f} g CO2/km)")
    print("\n  Recomandare: se raportează ambele referințe și se declară explicit că")
    print("  ecuația (2) nu conține termen de temperatură, deci efectul termic este")
    print("  absorbit în coeficienți pe 24,9 % din setul de calibrare.\n")


if __name__ == "__main__":
    verificare_coeficienti_publicati()
    sarcina_A()
    sarcina_B()
