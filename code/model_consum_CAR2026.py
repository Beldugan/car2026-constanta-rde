# -*- coding: utf-8 -*-
"""
model_consum_CAR2026.py
================================================================================
Lanțul complet de calcul al consumului din lucrarea CAR2026, într-o singură
implementare: relația turație-viteză, calibrarea Willans, predicțiile pe
traseele neparcurse, validarea out-of-sample, efectul termic, modelul energetic
al vehiculului electric echivalent și abaterile din figura 6.

Toate tabelele și figurile care conțin consum sau CO2 se calculează de aici.
Nicio valoare nu este scrisă manual în alt script.

    python model_consum_CAR2026.py            # raportul complet
    python model_consum_CAR2026.py --json     # aceleași cifre, ca JSON

Cale de bază: variabila de mediu CAR2026_BASE sau constanta BASE de mai jos.
Dependințe: numpy, pandas. scipy este opțional (implementarea Lawson-Hanson de
mai jos dă aceleași rezultate).

CONVENȚIILE MODELULUI, declarate explicit
--------------------------------------------------------------------------------
(1) Puterea la roată, ecuația (1) din lucrare, cu ε = 0,05 pentru vehiculele cu
    ardere internă. Modelul vehiculului electric folosește ε = 0 — vezi
    energie_EV().

(2) Debitul de combustibil, ecuația (2):
        ṁ = A1·min(P, P*)⁺ + A2·max(P − P*, 0) + B·Vd·n/120 + C
    Termenul de sarcină mică se evaluează pe partea NENEGATIVĂ a puterii:
    min(P, P*) se limitează inferior la zero înainte de înmulțirea cu A1. La
    decelerare, debitul este guvernat de regula de tăiere a injecției, nu de
    relația fitată.

(3) Calibrarea: NNLS (coeficienți ≥ 0) pe debitul masic, secundă cu secundă, pe
    secundele în care relația guvernează efectiv debitul — adică fără secundele
    de staționare, unde se aplică ralantiul fix, și fără cele cu tăiere de
    injecție, unde se aplică factorul rezidual. Numărul de secunde folosite se
    raportează.

(4) Turația: pe traseele parcurse efectiv de vehicul se folosește turația
    înregistrată prin OBD-II. Pentru traseele pe care vehiculul NU a circulat nu
    există turație măsurată, așa că se reconstruiește din relația n(v) a
    vehiculului: mediana turației înregistrate pe intervale de 5 km/h, prelungită
    peste domeniul acoperit cu panta ultimelor două intervale. Diferența
    introdusă de această substituție se cuantifică în raport.
================================================================================
"""

import io
import json
import os
import sys

import numpy as np
import pandas as pd

try:
    from scipy.optimize import nnls
except ImportError:
    def nnls(A, b, tol=1e-10, maxiter=None):
        """Lawson-Hanson în numpy pur; interfață identică cu scipy."""
        A = np.asarray(A, float)
        b = np.asarray(b, float)
        n = A.shape[1]
        if maxiter is None:
            maxiter = 3 * n
        P = np.zeros(n, bool)
        x = np.zeros(n)
        w = A.T @ (b - A @ x)
        it = 0
        while (not P.all()) and (w[~P] > tol).any() and it < maxiter:
            it += 1
            j = np.where(~P)[0][np.argmax(w[~P])]
            P[j] = True
            s = np.zeros(n)
            s[P] = np.linalg.lstsq(A[:, P], b, rcond=None)[0]
            while s[P].min() <= 0:
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
    for c in candidati:
        if os.path.isdir(c):
            return c
    return candidati[-1]


DIR_RUTE = _primul_dir(os.path.join(BASE, "Loguri rute"),
                       os.path.join(BASE, "data"))

# ------------------------------------------------------------------ PARAMETRI
M_MAS, CDA_MAS, VD_MAS = 1235.0, 0.666, 1.598      # kg, m2, L — Opel Astra Z16XEP
M_MAC, CDA_MAC, VD_MAC = 1670.0, 0.790, 1.968      # kg, m2, L — VW Touran BKD
CRR, RHO_AER, EPS = 0.011, 1.2, 0.05
RHO_BENZINA, RHO_MOTORINA = 745.0, 835.0            # g/L
CO2_BENZINA, CO2_MOTORINA = 3.17, 3.16              # g CO2 / g combustibil
AFR = 14.7
P_STAR = 12.0                                       # kW
RALANTI_MAS, RALANTI_MAC = 0.75, 0.55               # L/h
FACTOR_TAIERE = 0.15
T_CALD = 694.0                                      # s
PRET_BENZINA, PRET_MOTORINA = 9.90, 10.38           # RON/L
PAS_NV = 5.0                                        # km/h, intervalul relației n(v)

# vehiculul electric echivalent — tabelul 4
EV = dict(masa=1400.0, f=0.010, cd=0.35, arie=2.13, eps=0.0,
          eta_motor=0.90, eta_transmisie=0.95, eta_regen=0.60,
          p_aux=0.7, baterie=30.0, utilizabil=0.90)

LOG = {"R_A": "log_RUTA_A_Bratianu-Ferdinand-Mamaia_11-13.csv",
       "R_B": "log_RUTA_B_Mamaia-Navodari_15-17.csv",
       "R_DN3": "log_DIESEL_Constanta-DN3-Murfatlar_09-10.csv"}

MAS = dict(nume="SI", masa=M_MAS, cda=CDA_MAS, vd=VD_MAS, rho=RHO_BENZINA,
           co2=CO2_BENZINA, ralanti=RALANTI_MAS, pret=PRET_BENZINA)
MAC = dict(nume="CI", masa=M_MAC, cda=CDA_MAC, vd=VD_MAC, rho=RHO_MOTORINA,
           co2=CO2_MOTORINA, ralanti=RALANTI_MAC, pret=PRET_MOTORINA)


# ------------------------------------------------------------------- UTILITARE
def citeste(cale):
    linii = open(cale, encoding="utf-8", errors="replace").read().splitlines()
    i0 = next(i for i, l in enumerate(linii)
              if l and not l.startswith("#") and "," in l)
    return pd.read_csv(io.StringIO("\n".join(linii[i0:])))


def incarca(nume):
    return citeste(os.path.join(DIR_RUTE, LOG[nume]))


def putere_roata(v_kmh, a_ms2, masa, cda, eps=EPS, crr=CRR):
    """Ecuația (1), în kW."""
    v = np.asarray(v_kmh, float) / 3.6
    a = np.asarray(a_ms2, float)
    F = crr * masa * 9.81 + 0.5 * RHO_AER * cda * v ** 2 + masa * a * (1 + eps)
    return F * v / 1000.0


def relatie_nv(dfs, pas=PAS_NV):
    """Mediana turației pe intervale de `pas` km/h, din datele vehiculului."""
    v = np.concatenate([d["v_kmh"].values for d in dfs])
    n = np.concatenate([d["rpm"].values for d in dfs])
    ok = np.isfinite(v) & np.isfinite(n)
    v, n = v[ok], n[ok]
    b = np.floor(v / pas).astype(int)
    chei = sorted(np.unique(b))
    return {int(k): float(np.median(n[b == k])) for k in chei}, pas


def turatie_din_viteza(v_kmh, tabel, pas=PAS_NV):
    """Aplică relația n(v); peste domeniul acoperit prelungește cu panta
    ultimelor două intervale (raportul ultimei trepte de viteză)."""
    v = np.asarray(v_kmh, float)
    chei = sorted(tabel)
    centre = np.array([(k + 0.5) * pas for k in chei])
    valori = np.array([tabel[k] for k in chei])
    panta = (valori[-1] - valori[-2]) / (centre[-1] - centre[-2])
    b = np.floor(v / pas).astype(int)
    out = np.array([tabel.get(int(x), np.nan) for x in b], float)
    peste = np.isnan(out) & (b > chei[-1])
    out[peste] = valori[-1] + panta * (v[peste] - centre[-1])
    out[np.isnan(out)] = valori[0]
    return out


def coloane_model(P, rpm, vd):
    """Coloanele ecuației (2). Termenul de sarcină mică se evaluează pe partea
    nenegativă a puterii — vezi convenția (2) din antet."""
    return np.c_[np.clip(np.minimum(P, P_STAR), 0.0, None),
                 np.maximum(P - P_STAR, 0.0),
                 vd * np.asarray(rpm, float) / 120.0,
                 np.ones(len(P))]


def masti(v_kmh, stationare, P, rpm):
    idle = np.asarray(stationare) == 1
    taiere = (P < -1) & (np.asarray(v_kmh) > 15) & (np.asarray(rpm) > 1300) & ~idle
    return idle, taiere


def debit(X, coef, idle, taiere, ralanti_lh, rho):
    """Relația, apoi regulile fixe, în ordinea declarată în lucrare."""
    m = np.maximum(X @ np.asarray(coef, float), 0.0)
    m = np.where(taiere, m * FACTOR_TAIERE, m)
    m = np.where(idle, ralanti_lh * rho / 3600.0, m)
    return m


def l100(mdot_g_s, km, rho):
    return 100.0 * (np.nansum(mdot_g_s) / rho) / km


def km_din(d):
    return float(d["dist_cum_m"].max()) / 1000.0


# --------------------------------------------------------------- REFERINȚELE
def referinta_MAS(d):
    """Consum de referință din debitul de aer măsurat, în g/s."""
    return (d["maf_g_s"] / AFR).values


def referinta_MAC(d):
    """Media celor două estimări indirecte, în g/s."""
    ml_s = (d["debit_comb_fizic_ml_s"].values +
            d["debit_comb_model_ml_s"].values) / 2.0
    return ml_s * RHO_MOTORINA / 1000.0


# ------------------------------------------------------------------ CALIBRARE
def calibreaza(dfs, veh, tinta):
    """NNLS pe secundele guvernate de relație. Returnează (coef, n_secunde)."""
    Xs, ys = [], []
    for d in dfs:
        P = putere_roata(d["v_kmh"], d["a_ms2"], veh["masa"], veh["cda"])
        idle, taiere = masti(d["v_kmh"].values, d["stationare"].values,
                             P, d["rpm"].values)
        X = coloane_model(P, d["rpm"].values, veh["vd"])
        y = tinta(d)
        m = ~(idle | taiere) & np.isfinite(y) & np.isfinite(X).all(1)
        Xs.append(X[m])
        ys.append(y[m])
    X = np.vstack(Xs)
    y = np.concatenate(ys)
    coef, _ = nnls(X, y)
    return coef, int(len(y))


def ruleaza(d, veh, coef, tabel_nv=None):
    """Consum modelat pe un traseu. Cu tabel_nv, turația se reconstruiește din
    viteză (traseu neparcurs de acest vehicul); altfel se folosește cea măsurată."""
    v = d["v_kmh"].values
    P = putere_roata(v, d["a_ms2"], veh["masa"], veh["cda"])
    rpm = (turatie_din_viteza(v, tabel_nv) if tabel_nv is not None
           else d["rpm"].values)
    idle, taiere = masti(v, d["stationare"].values, P, rpm)
    X = coloane_model(P, rpm, veh["vd"])
    return debit(X, coef, idle, taiere, veh["ralanti"], veh["rho"]), P


def energie_roata(d, veh):
    """Energia pozitivă la roată, kWh/100 km — coloana din tabelul 7."""
    P = putere_roata(d["v_kmh"], d["a_ms2"], veh["masa"], veh["cda"])
    return 100.0 * (np.clip(P, 0, None).sum() / 3600.0) / km_din(d)


# ------------------------------------------------------ CLASELE DE VITEZĂ RDE
def clase(v_kmh):
    v = np.asarray(v_kmh)
    return {"Urban": v <= 60, "Rural": (v > 60) & (v <= 90), "Motorway": v > 90}


def pe_clase(d, mdot, rho):
    ds = np.diff(d["dist_cum_m"].values, prepend=d["dist_cum_m"].values[0])
    out = {}
    for nume, m in clase(d["v_kmh"].values).items():
        km = ds[m].sum() / 1000.0
        if km <= 0:
            continue
        out[nume] = dict(km=km, l100=100.0 * (mdot[m].sum() / rho) / km)
    return out


# ------------------------------------------------------- VEHICULUL ELECTRIC
def energie_EV(d):
    """Modelul energetic al vehiculului electric echivalent, tabelul 11.
    ε = 0: inerția rotativă nu se aplică acestui vehicul, deoarece parametrii
    adoptați descriu o transmisie cu un singur raport, fără mase rotative
    echivalente estimate. Recuperarea se aplică energiei de frânare la roată."""
    P = putere_roata(d["v_kmh"], d["a_ms2"], EV["masa"], EV["cd"] * EV["arie"],
                     eps=EV["eps"], crr=EV["f"])
    tractiune = np.clip(P, 0, None).sum() / 3600.0 / (EV["eta_motor"] * EV["eta_transmisie"])
    recuperat = np.clip(-P, 0, None).sum() / 3600.0 * EV["eta_regen"]
    auxiliare = EV["p_aux"] * len(d) / 3600.0
    km = km_din(d)
    net = 100.0 * (tractiune - recuperat + auxiliare) / km
    return dict(tractiune=tractiune, recuperat=recuperat, auxiliare=auxiliare,
                net=net, recuperare_pct=100.0 * recuperat / tractiune,
                autonomie_30=EV["baterie"] / net * 100.0,
                autonomie_utila=EV["baterie"] * EV["utilizabil"] / net * 100.0)


# ==============================================================  RAPORTUL
def raport():
    dA, dB, dD = incarca("R_A"), incarca("R_B"), incarca("R_DN3")
    R = {}

    nv_MAS, _ = relatie_nv([dA, dB])
    nv_MAC, _ = relatie_nv([dD])
    R["relatie_nv"] = {"SI": nv_MAS, "CI": nv_MAC, "pas_kmh": PAS_NV}

    cM, nM = calibreaza([dA, dB], MAS, referinta_MAS)
    cC, nC = calibreaza([dD], MAC, referinta_MAC)
    R["coeficienti"] = {"SI": dict(zip("A1 A2 B C".split(), map(float, cM)),
                                   secunde=nM),
                        "CI": dict(zip("A1 A2 B C".split(), map(float, cC)),
                                   secunde=nC)}

    ref = {"R_A": l100(referinta_MAS(dA), km_din(dA), RHO_BENZINA),
           "R_B": l100(referinta_MAS(dB), km_din(dB), RHO_BENZINA),
           "R_DN3": l100(referinta_MAC(dD), km_din(dD), RHO_MOTORINA)}
    R["referinte"] = ref

    # abaterile in-sample — valorile din figura 6
    ins = {}
    for nume, d, veh, coef in (("R_A", dA, MAS, cM), ("R_B", dB, MAS, cM),
                               ("R_DN3", dD, MAC, cC)):
        m, _ = ruleaza(d, veh, coef)
        val = l100(m, km_din(d), veh["rho"])
        ins[nume] = dict(model=val, referinta=ref[nume],
                         abatere=100.0 * (val - ref[nume]) / ref[nume])
    R["in_sample"] = ins

    # eroarea introdusă de substituția turației
    subst = {}
    for nume, d, veh, coef, tab in (("R_A", dA, MAS, cM, nv_MAS),
                                    ("R_B", dB, MAS, cM, nv_MAS),
                                    ("R_DN3", dD, MAC, cC, nv_MAC)):
        m1, _ = ruleaza(d, veh, coef)
        m2, _ = ruleaza(d, veh, coef, tab)
        a, b = l100(m1, km_din(d), veh["rho"]), l100(m2, km_din(d), veh["rho"])
        subst[nume] = dict(masurata=a, reconstruita=b, diferenta=100.0 * (b - a) / a)
    R["substitutie_turatie"] = subst

    # tabelul 7 + tabelul 8
    t7, t8 = [], []
    combinatii = [("R_A", dA, MAS, cM, None, ref["R_A"]),
                  ("R_A", dA, MAC, cC, nv_MAC, None),
                  ("R_B", dB, MAS, cM, None, ref["R_B"]),
                  ("R_B", dB, MAC, cC, nv_MAC, None),
                  ("R_DN3", dD, MAS, cM, nv_MAS, None),
                  ("R_DN3", dD, MAC, cC, None, ref["R_DN3"])]
    serii = {}
    for ruta, d, veh, coef, tab, referinta in combinatii:
        if referinta is not None:            # celulă de referință, nu predicție
            mdot = (referinta_MAS(d) if veh is MAS else referinta_MAC(d))
            fel = "referință"
        else:
            mdot, _ = ruleaza(d, veh, coef, tab)
            fel = "model"
        km = km_din(d)
        cons = l100(mdot, km, veh["rho"])
        t7.append(dict(ruta=ruta, vehicul=veh["nume"], fel=fel,
                       energie_roata=energie_roata(d, veh), consum=cons,
                       co2=cons * veh["co2"] * veh["rho"] / 100.0,
                       cost=cons * veh["pret"] / 100.0 * 100.0 / 100.0 * 1.0))
        t7[-1]["cost"] = cons * veh["pret"] / 100.0 * 100
        serii[(ruta, veh["nume"])] = pe_clase(d, mdot, veh["rho"])
    R["tabel7"] = t7

    for ruta in ("R_A", "R_B", "R_DN3"):
        si, ci = serii[(ruta, "SI")], serii[(ruta, "CI")]
        for cl in ("Urban", "Rural", "Motorway"):
            if cl not in si:
                continue
            co2_si = si[cl]["l100"] * CO2_BENZINA * RHO_BENZINA / 100.0
            co2_ci = ci[cl]["l100"] * CO2_MOTORINA * RHO_MOTORINA / 100.0
            t8.append(dict(ruta=ruta, clasa=cl, km=si[cl]["km"],
                           si_l100=si[cl]["l100"], ci_l100=ci[cl]["l100"],
                           si_co2=co2_si, ci_co2=co2_ci,
                           delta=100.0 * (co2_ci - co2_si) / co2_si))
    R["tabel8"] = t8

    # validarea out-of-sample: calibrare pe R_A, validare pe R_B
    cA, nA = calibreaza([dA], MAS, referinta_MAS)
    mB, _ = ruleaza(dB, MAS, cA)
    vB = l100(mB, km_din(dB), RHO_BENZINA)
    R["out_of_sample"] = dict(coef=dict(zip("A1 A2 B C".split(), map(float, cA)),
                                        secunde=nA),
                              model=vB, referinta=ref["R_B"],
                              abatere=100.0 * (vB - ref["R_B"]) / ref["R_B"])

    # efectul termic
    cald = dD["t_rel_s"].values >= T_CALD
    ds = np.diff(dD["dist_cum_m"].values, prepend=dD["dist_cum_m"].values[0])
    y = referinta_MAC(dD)
    t80 = float(dD.loc[dD["t_lichid_racire_C"] >= 80, "t_rel_s"].min())
    integral = l100(y, ds.sum() / 1000.0, RHO_MOTORINA)
    numai_cald = l100(y[cald], ds[cald].sum() / 1000.0, RHO_MOTORINA)
    k = numai_cald / integral
    mRA, _ = ruleaza(dA, MAC, cC, nv_MAC)
    ral = RALANTI_MAC * RHO_MOTORINA / 3600.0
    este_ral = np.isclose(mRA, ral, atol=1e-9)
    rescalat = l100(np.where(este_ral, mRA, mRA * k), km_din(dA), RHO_MOTORINA)
    R["termic"] = dict(t80=t80, durata_pct=100.0 * (~cald).mean(),
                       km_rece=ds[~cald].sum() / 1000.0, km_total=ds.sum() / 1000.0,
                       integral=integral, numai_cald=numai_cald, factor=k,
                       CI_pe_RA=l100(mRA, km_din(dA), RHO_MOTORINA),
                       CI_pe_RA_rescalat=rescalat)

    # vehiculul electric
    R["tabel11"] = {nume: energie_EV(d)
                    for nume, d in (("R_A", dA), ("R_B", dB), ("R_DN3", dD))}

    # domeniul de calibrare
    R["domeniu"] = dict(
        v_max_RA=float(dA["v_kmh"].max()), v_max_RB=float(dB["v_kmh"].max()),
        v_max_RDN3=float(dD["v_kmh"].max()))
    v = dD["v_kmh"].values
    R["domeniu"]["RDN3_peste_78_dist"] = 100.0 * ds[v > 78].sum() / ds.sum()
    R["domeniu"]["RDN3_peste_78_timp"] = 100.0 * (v > 78).mean()
    R["domeniu"]["RDN3_peste_90_dist"] = 100.0 * ds[v > 90].sum() / ds.sum()
    rur = (v > 60) & (v <= 90)
    R["domeniu"]["rural_peste_78_km"] = ds[rur & (v > 78)].sum() / 1000.0
    R["domeniu"]["rural_km"] = ds[rur].sum() / 1000.0
    return R


def tipareste(R):
    L = print
    L("=" * 78)
    L("CALIBRARE")
    L("=" * 78)
    for k, c in R["coeficienti"].items():
        L("  %s (%d s): A1 %.4f  A2 %.4f  B %.4f  C %.4f"
          % (k, c["secunde"], c["A1"], c["A2"], c["B"], c["C"]))
    L("\n  relația n(v), mediana turației pe intervale de %g km/h:" % R["relatie_nv"]["pas_kmh"])
    for k in ("SI", "CI"):
        t = R["relatie_nv"][k]
        L("    %s: %s" % (k, ", ".join("%d-%d:%d" % (int(b) * 5, int(b) * 5 + 5, v)
                                       for b, v in sorted(t.items(), key=lambda x: int(x[0])))))
    L("\n" + "=" * 78)
    L("ABATERI IN-SAMPLE (valorile din figura 6)")
    L("=" * 78)
    for k, v in R["in_sample"].items():
        L("  %-6s model %5.2f  referință %5.2f  ->  %+.1f %%"
          % (k, v["model"], v["referinta"], v["abatere"]))
    L("\n  eroarea introdusă de reconstrucția turației, pe traseele măsurate:")
    for k, v in R["substitutie_turatie"].items():
        L("    %-6s %5.2f -> %5.2f L/100 km  (%+.1f %%)"
          % (k, v["masurata"], v["reconstruita"], v["diferenta"]))
    L("\n" + "=" * 78)
    L("TABELUL 7")
    L("=" * 78)
    L("  %-6s %-3s %-10s %8s %8s %8s %6s" % ("ciclu", "veh", "fel",
                                             "kWh/100", "L/100", "gCO2/km", "RON"))
    for r in R["tabel7"]:
        L("  %-6s %-3s %-10s %8.2f %8.2f %8.1f %6.0f"
          % (r["ruta"], r["vehicul"], r["fel"], r["energie_roata"],
             r["consum"], r["co2"], r["cost"]))
    L("\n" + "=" * 78)
    L("TABELUL 8")
    L("=" * 78)
    L("  %-6s %-9s %7s %8s %8s %9s %9s %8s"
      % ("ciclu", "clasa", "km", "SI L", "CI L", "SI g/km", "CI g/km", "ΔCO2"))
    for r in R["tabel8"]:
        L("  %-6s %-9s %7.2f %8.2f %8.2f %9.1f %9.1f %7.1f%%"
          % (r["ruta"], r["clasa"], r["km"], r["si_l100"], r["ci_l100"],
             r["si_co2"], r["ci_co2"], r["delta"]))
    o = R["out_of_sample"]
    L("\n" + "=" * 78)
    L("VALIDARE OUT-OF-SAMPLE — calibrare pe R_A (%d s), validare pe R_B" % o["coef"]["secunde"])
    L("=" * 78)
    L("  A1 %.4f  A2 %.4f  B %.4f  C %.4f" % (o["coef"]["A1"], o["coef"]["A2"],
                                              o["coef"]["B"], o["coef"]["C"]))
    L("  R_B: model %.2f vs referință %.2f L/100 km  ->  %+.1f %%"
      % (o["model"], o["referinta"], o["abatere"]))
    t = R["termic"]
    L("\n" + "=" * 78)
    L("EFECTUL TERMIC")
    L("=" * 78)
    L("  80 °C atinse la t = %.0f s; încălzirea = %.1f %% din durată, %.2f din %.2f km"
      % (t["t80"], t["durata_pct"], t["km_rece"], t["km_total"]))
    L("  referința CI: %.2f -> %.2f L/100 km  (factor %.4f)"
      % (t["integral"], t["numai_cald"], t["factor"]))
    L("  CI pe R_A: %.2f -> %.2f L/100 km prin rescalare"
      % (t["CI_pe_RA"], t["CI_pe_RA_rescalat"]))
    L("\n" + "=" * 78)
    L("TABELUL 11 — vehiculul electric echivalent (ε = 0)")
    L("=" * 78)
    L("  %-6s %9s %9s %9s %10s %8s %9s %9s"
      % ("ciclu", "tracțiune", "recuperat", "auxiliare", "kWh/100km",
         "recup.%", "30 kWh", "90 % util."))
    for k, v in R["tabel11"].items():
        L("  %-6s %9.3f %9.3f %9.3f %10.2f %7.0f%% %9.0f %9.0f"
          % (k, v["tractiune"], v["recuperat"], v["auxiliare"], v["net"],
             v["recuperare_pct"], v["autonomie_30"], v["autonomie_utila"]))
    d = R["domeniu"]
    L("\n" + "=" * 78)
    L("DOMENIUL DE CALIBRARE")
    L("=" * 78)
    L("  viteze maxime: R_A %.1f, R_B %.1f, R_DN3 %.1f km/h"
      % (d["v_max_RA"], d["v_max_RB"], d["v_max_RDN3"]))
    L("  R_DN3 peste 78 km/h: %.1f %% din distanță, %.1f %% din timp; "
      "peste 90 km/h: %.1f %% din distanță"
      % (d["RDN3_peste_78_dist"], d["RDN3_peste_78_timp"], d["RDN3_peste_90_dist"]))
    L("  din clasa rurală (%.2f km), peste 78 km/h: %.2f km (%.1f %%)"
      % (d["rural_km"], d["rural_peste_78_km"],
         100.0 * d["rural_peste_78_km"] / d["rural_km"]))


NUME_LUNG = {
    "R_A": "R_A — urban central (Brătianu–Ferdinand–Mamaia)",
    "R_B": "R_B — radial litoral (Mamaia–Năvodari)",
    "R_DN3": "R_DN3 — mixt (Constanța–DN3–Murfatlar)",
}
VEH_LUNG = {"SI": "MAS benzină — Opel Astra 1.6i",
            "CI": "MAC diesel — VW Touran 2.0 TDI"}
CLASA_LUNG = {"Urban": "urban (≤60)", "Rural": "rural (60–90)",
              "Motorway": "autostradă (>90)"}


def scrie_rezultate(R, dir_iesire=None):
    """Scrie fișierele din care se construiesc figurile și tabelele, ca nicio
    valoare să nu fie scrisă de mână în scriptul grafic."""
    d = dir_iesire or DIR_RUTE
    os.makedirs(d, exist_ok=True)
    dfs = {k: incarca(k) for k in LOG}
    desc = {}
    for k, x in dfs.items():
        desc[k] = dict(distanta_km=km_din(x), durata_s=len(x),
                       v_medie_kmh=3.6 * x["dist_cum_m"].max() / len(x) / 1000 * 1000,
                       stationare_pct=100.0 * x["stationare"].mean())
    for k, x in dfs.items():
        desc[k]["v_medie_kmh"] = 3.6 * (km_din(x) * 1000) / len(x)

    linii = ["traseu,vehicul,statut,distanta_km,durata_s,v_medie_kmh,"
             "stationare_pct,E_roata_kWh_100km,consum_l_100km,CO2_g_km"]
    for r in R["tabel7"]:
        k = r["ruta"]
        linii.append("%s,%s,%s,%.2f,%d,%.1f,%.1f,%.2f,%.2f,%.1f" % (
            NUME_LUNG[k], VEH_LUNG[r["vehicul"]],
            "măsurat" if r["fel"] == "referință" else "extrapolat",
            desc[k]["distanta_km"], desc[k]["durata_s"], desc[k]["v_medie_kmh"],
            desc[k]["stationare_pct"], r["energie_roata"], r["consum"], r["co2"]))
    open(os.path.join(d, "matrice_comparativa_benzina_diesel.csv"), "w",
         encoding="utf-8").write("\n".join(linii) + "\n")

    fel = {(r["ruta"], r["vehicul"]): r["fel"] for r in R["tabel7"]}
    linii = ["traseu,vehicul,statut,clasa,distanta_km,consum_l_100km,CO2_g_km"]
    for r in R["tabel8"]:
        k, cl = r["ruta"], CLASA_LUNG[r["clasa"]]
        for veh, l, co2 in (("SI", r["si_l100"], r["si_co2"]),
                            ("CI", r["ci_l100"], r["ci_co2"])):
            linii.append("%s,%s,%s,%s,%.2f,%.2f,%.1f" % (
                NUME_LUNG[k], VEH_LUNG[veh].split(" — ")[0],
                "măsurat" if fel[(k, veh)] == "referință" else "extrapolat",
                cl, r["km"], l, co2))
    open(os.path.join(d, "matrice_pe_clase_RDE.csv"), "w",
         encoding="utf-8").write("\n".join(linii) + "\n")

    linii = ["traseu,referinta_l_100km,model_l_100km,abatere_pct,fel"]
    for k, v in R["in_sample"].items():
        linii.append("%s,%.2f,%.2f,%.1f,in-sample" % (k, v["referinta"], v["model"],
                                                     v["abatere"]))
    o = R["out_of_sample"]
    linii.append("R_B,%.2f,%.2f,%.1f,out-of-sample" % (o["referinta"], o["model"],
                                                      o["abatere"]))
    open(os.path.join(d, "calibrare_rezultate.csv"), "w",
         encoding="utf-8").write("\n".join(linii) + "\n")

    for k, veh, coef_k in (("R_A", MAC, "CI"), ("R_B", MAC, "CI"),
                           ("R_DN3", MAS, "SI")):
        x = dfs[k]
        coef = [R["coeficienti"][coef_k][c] for c in ("A1", "A2", "B", "C")]
        tab = {int(b): v for b, v in R["relatie_nv"][coef_k].items()}
        mdot, _ = ruleaza(x, veh, coef, tab)
        nume = "extrapolat_%s_%s.csv" % (k, "diesel" if veh is MAC else "benzina")
        out = pd.DataFrame(dict(
            t_s=np.arange(len(x)), v_kmh=x["v_kmh"].values, a_ms2=x["a_ms2"].values,
            dist_cum_m=x["dist_cum_m"].values, debit_comb_g_s=np.round(mdot, 4),
            consum_cum_l=np.round(np.cumsum(mdot) / veh["rho"], 4),
            CO2_g_s=np.round(mdot * veh["co2"], 4),
            CO2_cum_g=np.round(np.cumsum(mdot * veh["co2"]), 1)))
        out.to_csv(os.path.join(d, nume), index=False, encoding="utf-8")
    print("Scrise: matricele, calibrare_rezultate.csv și cele trei serii "
          "extrapolate, în %s" % d)


if __name__ == "__main__":
    R = raport()
    if "--scrie" in sys.argv:
        scrie_rezultate(R)
    if "--json" in sys.argv:
        print(json.dumps(R, indent=1, ensure_ascii=False, default=float))
    else:
        tipareste(R)
