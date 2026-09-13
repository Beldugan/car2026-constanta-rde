# -*- coding: utf-8 -*-
"""
genereaza_figuri.py
================================================================================
Regenerează cele opt figuri ale lucrării CAR2026 direct din seriile de date, la
600 dpi, cu font Times/Liberation Serif și dimensiuni potrivite lățimii de
coloană IOP (16,5 cm).

    python genereaza_figuri.py

Citește din `Loguri rute`: cele trei loguri la 1 Hz, cele trei serii extrapolate
și cele două matrice. Scrie `Figuri lucrare\\EN_fig1..EN_fig8.png`.

Reguli de reprezentare respectate: nicio axă dublă (mărimile de scări diferite
stau în panouri suprapuse care împart axa timpului), paletă categorială fixă
verificată pentru daltonism (albastru #2a78d6 pentru MAS, portocaliu #eb6834
pentru MAC, verde-albastru #1baf7a pentru al treilea traseu), rampă sequvențială
cu o singură nuanță pentru sarcina motorului, marcaje subțiri, grilă discretă,
legendă la două sau mai multe serii și etichete directe pentru procente.
================================================================================
"""

import io
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

BASE = os.environ.get("CAR2026_BASE", r"D:\Lucrare CAR2026")
DIR_RUTE = None          # se rezolvă mai jos
DIR_FIG = None
DPI = 600
CM = 1 / 2.54
LAT = 16.5 * CM          # lățimea de plasare în lucrare

SI, CI, A3 = "#2a78d6", "#eb6834", "#1baf7a"
GRI, GRI_SLAB = "#4d4d4d", "#d9d9d9"
RAMPA = LinearSegmentedColormap.from_list(
    "albastru", ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"])

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "legend.fontsize": 7.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "axes.edgecolor": GRI,
    "axes.linewidth": 0.6,
    "axes.grid": True,
    "grid.color": GRI_SLAB,
    "grid.linewidth": 0.5,
    "xtick.color": GRI,
    "ytick.color": GRI,
    "text.color": "#1a1a1a",
    "axes.labelcolor": "#1a1a1a",
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

LOG = {"R_A": "log_RUTA_A_Bratianu-Ferdinand-Mamaia_11-13.csv",
       "R_B": "log_RUTA_B_Mamaia-Navodari_15-17.csv",
       "R_DN3": "log_DIESEL_Constanta-DN3-Murfatlar_09-10.csv"}
ETICHETA = {"R_A": "R$_\\mathrm{A}$ — central urban",
            "R_B": "R$_\\mathrm{B}$ — coastal radial",
            "R_DN3": "R$_\\mathrm{DN3}$ — mixed"}
CULOARE = {"R_A": SI, "R_B": CI, "R_DN3": A3}
WLTP_LOW, WLTP_TOT = 18.9, 46.5


def _primul_dir(*candidati):
    """Scripturile merg atât în structura de lucru, cât și în cea a depozitului
    public (`data/`, `data/raw/`). Se alege primul folder care există."""
    for c in candidati:
        if os.path.isdir(c):
            return c
    return candidati[-1]


DIR_RUTE = _primul_dir(os.path.join(BASE, "Loguri rute"), os.path.join(BASE, "data"))
DIR_FIG = _primul_dir(os.path.join(BASE, "Figuri lucrare"), os.path.join(BASE, "figures"))


def citeste(cale):
    linii = open(cale, encoding="utf-8", errors="replace").read().splitlines()
    i0 = next(i for i, l in enumerate(linii)
              if l and not l.startswith("#") and "," in l)
    return pd.read_csv(io.StringIO("\n".join(linii[i0:])))


def incarca():
    return {k: citeste(os.path.join(DIR_RUTE, f)) for k, f in LOG.items()}


def ax_curat(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_axisbelow(True)


def salveaza(fig, nume):
    os.makedirs(DIR_FIG, exist_ok=True)
    cale = os.path.join(DIR_FIG, nume)
    fig.savefig(cale)
    plt.close(fig)
    print("  scris", nume)


# ------------------------------------------------------------------ figura 1
def geometrie(k, d):
    """Coordonatele traseului. În depozitul public ele nu sunt în log, ci într-un
    fișier separat, scurtat la capete — se caută acolo."""
    g = d[k]
    if "lon_deg" in g.columns:
        return g
    alt = os.path.join(DIR_RUTE, "geometry", "geometry_%s.csv" % k)
    if os.path.exists(alt):
        return pd.read_csv(alt)
    raise FileNotFoundError(
        "lipsesc coordonatele pentru %s: nici în log, nici în %s" % (k, alt))


def fig1(d):
    fig, ax = plt.subplots(figsize=(LAT, 9.5 * CM))
    for k in ("R_DN3", "R_B", "R_A"):
        g = geometrie(k, d)
        ax.plot(g.lon_deg, g.lat_deg, color=CULOARE[k], lw=1.0,
                label=ETICHETA[k], solid_capstyle="round")
    for k, nume in [("R_A", "Constanța centre"), ("R_DN3", "Murfatlar")]:
        g = geometrie(k, d).reset_index(drop=True)
        j = g.lon_deg.idxmin() if k == "R_DN3" else 0
        ax.plot(g.lon_deg[j], g.lat_deg[j], "o", ms=4, mfc="white",
                mec=CULOARE[k], mew=1.0)
        dx, ha = (-7, "right") if k == "R_A" else (7, "left")
        ax.annotate(nume, (g.lon_deg[j], g.lat_deg[j]),
                    textcoords="offset points", xytext=(dx, 7), ha=ha,
                    fontsize=7.5)
    ax.set_xlabel("Longitude [°E]")
    ax.set_ylabel("Latitude [°N]")
    ax.set_aspect(1 / np.cos(np.radians(44.18)))
    ax.legend(frameon=False, loc="upper left")
    ax.margins(x=0.08, y=0.05)
    ax_curat(ax)
    salveaza(fig, "EN_fig1_coverage.png")


# ------------------------------------------------------------------ figura 2
def fig2(d):
    fig, axs = plt.subplots(2, 3, figsize=(LAT, 8.5 * CM), sharex="col",
                            gridspec_kw={"height_ratios": [1.25, 1]})
    for j, k in enumerate(("R_A", "R_B", "R_DN3")):
        g = d[k]
        t = g.t_rel_s / 60.0
        axs[0, j].plot(t, g.v_kmh, color=CULOARE[k], lw=0.5)
        axs[0, j].set_title(ETICHETA[k])
        axs[0, j].set_ylim(0, 130)
        axs[1, j].plot(t, g.rpm, color=CULOARE[k], lw=0.5)
        axs[1, j].set_ylim(0, 3600)
        axs[1, j].set_xlabel("Time [min]")
        for a in (axs[0, j], axs[1, j]):
            ax_curat(a)
            if j:
                a.tick_params(labelleft=False)
    axs[0, 0].set_ylabel("Speed [km/h]")
    axs[1, 0].set_ylabel("Engine speed [rpm]")
    fig.align_ylabels(axs[:, 0])
    fig.subplots_adjust(hspace=0.18, wspace=0.10)
    salveaza(fig, "EN_fig2_speed_rpm.png")


# ------------------------------------------------------------------ figura 3
def fig3(d):
    g = d["R_DN3"]
    t = g.t_rel_s / 60.0
    t80 = g.loc[g.t_lichid_racire_C >= 80, "t_rel_s"].min() / 60.0
    fig, axs = plt.subplots(2, 1, figsize=(LAT, 8.5 * CM), sharex=True,
                            gridspec_kw={"height_ratios": [1.2, 1]})
    for a in axs:
        a.axvspan(0, t80, color="#f2f2f0", zorder=0)
        ax_curat(a)
    axs[0].plot(t, g.v_kmh, color=A3, lw=0.5)
    axs[0].set_ylabel("Speed [km/h]")
    axs[0].set_ylim(0, 130)
    axs[1].plot(t, g.t_lichid_racire_C, color=SI, lw=1.0)
    axs[1].axhline(80, color=GRI, lw=0.7, ls=(0, (4, 3)))
    axs[1].annotate("80 °C reached at %.0f s" % (t80 * 60),
                    (t80, 80), textcoords="offset points", xytext=(6, -12),
                    fontsize=7.5, color=GRI)
    axs[1].set_ylabel("Coolant temperature [°C]")
    axs[1].set_xlabel("Time [min]")
    axs[1].set_ylim(20, 100)
    axs[0].annotate("warm-up", (t80 / 2, 118), ha="center", fontsize=7.5,
                    color=GRI)
    fig.align_ylabels(axs)
    fig.subplots_adjust(hspace=0.10)
    salveaza(fig, "EN_fig3_coldstart.png")


# ------------------------------------------------------------------ figura 4
def fig4(d):
    fig, axs = plt.subplots(1, 2, figsize=(LAT, 6.5 * CM))
    bv = np.arange(0, 126, 5)
    ba = np.arange(-2.5, 2.55, 0.2)
    for k in ("R_A", "R_B", "R_DN3"):
        g = d[k]
        axs[0].hist(g.v_kmh, bins=bv, density=True, histtype="step",
                    color=CULOARE[k], lw=1.1, label=ETICHETA[k])
        axs[1].hist(g.a_ms2.clip(-2.5, 2.5), bins=ba, density=True,
                    histtype="step", color=CULOARE[k], lw=1.1)
    for x, et in [(WLTP_LOW, "WLTP Low"), (WLTP_TOT, "WLTP total")]:
        axs[0].axvline(x, color=GRI, lw=0.7, ls=(0, (4, 3)))
        axs[0].annotate(et, (x, axs[0].get_ylim()[1] * 0.96), rotation=90,
                        fontsize=7, color=GRI, ha="right", va="top")
    axs[0].set_xlabel("Speed [km/h]")
    axs[0].set_ylabel("Probability density")
    axs[1].set_xlabel("Acceleration [m/s$^2$]")
    axs[1].set_ylabel("Probability density")
    axs[0].legend(frameon=False, loc="upper right")
    for a in axs:
        ax_curat(a)
    fig.subplots_adjust(wspace=0.24)
    salveaza(fig, "EN_fig4_distributions.png")


# ------------------------------------------------------------------ figura 5
def fig5(d):
    fig, axs = plt.subplots(1, 3, figsize=(LAT, 6.2 * CM), sharey=True)
    for j, k in enumerate(("R_A", "R_B", "R_DN3")):
        g = d[k].copy()
        m = g.v_kmh > 0
        sc = axs[j].scatter(g.v_kmh[m], g.a_ms2[m], c=g.sarcina_motor_pct[m],
                            cmap=RAMPA, s=1.6, lw=0, alpha=0.75,
                            vmin=0, vmax=100, rasterized=True)
        va = (g.v_kmh * g.a_ms2.clip(lower=0)) / 3.6
        p95 = np.percentile(va[va > 0], 95) if (va > 0).any() else np.nan
        v = np.linspace(1, 125, 200)
        axs[j].plot(v, p95 / (v / 3.6), color="#1a1a1a", lw=0.9,
                    label="$(v\\cdot a)_{95}$ = %.2f m$^2$/s$^3$" % p95)
        axs[j].set_xlim(0, 125)
        axs[j].set_ylim(-3, 3)
        axs[j].set_xlabel("Speed [km/h]")
        axs[j].set_title(ETICHETA[k])
        axs[j].legend(frameon=False, loc="upper right", handlelength=1.2)
        ax_curat(axs[j])
    axs[0].set_ylabel("Acceleration [m/s$^2$]")
    cb = fig.colorbar(sc, ax=axs, fraction=0.022, pad=0.012)
    cb.set_label("Engine load [%]")
    cb.outline.set_linewidth(0.4)
    salveaza(fig, "EN_fig5_va_diagram.png")


# ------------------------------------------------------------------ figura 6
REF = {"R_A": 10.83, "R_B": 8.90, "R_DN3": 4.69}
IN_SAMPLE = {"R_A": -2.1, "R_B": -7.1, "R_DN3": +0.7}
OUT_SAMPLE = {"R_B": -11.8}


def fig6():
    et = ["R$_\\mathrm{A}$", "R$_\\mathrm{B}$", "R$_\\mathrm{DN3}$"]
    k = ["R_A", "R_B", "R_DN3"]
    x = np.arange(3)
    fig, axs = plt.subplots(1, 2, figsize=(LAT, 6.5 * CM))
    w = 0.36
    ref = [REF[i] for i in k]
    mod = [REF[i] * (1 + IN_SAMPLE[i] / 100) for i in k]
    axs[0].bar(x - w / 2, ref, w, color=GRI, label="Reference")
    axs[0].bar(x + w / 2, mod, w, color=SI, label="Willans model")
    for i, (r, m) in enumerate(zip(ref, mod)):
        axs[0].annotate("%+.1f%%" % IN_SAMPLE[k[i]], (i, max(r, m)),
                        textcoords="offset points", xytext=(0, 3),
                        ha="center", fontsize=7.5)
    axs[0].set_xticks(x, et)
    axs[0].set_ylabel("Consumption [L/100 km]")
    axs[0].set_ylim(0, 13)
    axs[0].legend(frameon=False, loc="upper right")

    axs[1].axhspan(-10, 10, color="#eef4fd", zorder=0)
    axs[1].annotate("±10% band", (2.45, 10), fontsize=7, color=GRI,
                    ha="right", va="bottom")
    axs[1].bar(x - 0.19, [IN_SAMPLE[i] for i in k], 0.34, color=SI,
               label="In-sample residual")
    axs[1].bar([1 + 0.19], [OUT_SAMPLE["R_B"]], 0.34, color="none",
               edgecolor=CI, lw=1.1, hatch="///",
               label="Out-of-sample (R$_\\mathrm{B}$ held out)")
    for i in range(3):
        v = IN_SAMPLE[k[i]]
        axs[1].annotate("%+.1f%%" % v, (i - 0.19, v), textcoords="offset points",
                        xytext=(0, 4 if v > 0 else -11), ha="center", fontsize=7.5)
    axs[1].annotate("%+.1f%%" % OUT_SAMPLE["R_B"], (1.19, OUT_SAMPLE["R_B"]),
                    textcoords="offset points", xytext=(0, -11), ha="center",
                    fontsize=7.5, color=CI)
    axs[1].axhline(0, color="#1a1a1a", lw=0.7)
    axs[1].set_xticks(x, et)
    axs[1].set_ylabel("Deviation from reference [%]")
    axs[1].set_ylim(-16, 13)
    axs[1].legend(frameon=False, loc="upper left", handlelength=1.4)
    for a in axs:
        ax_curat(a)
    fig.subplots_adjust(wspace=0.26)
    salveaza(fig, "EN_fig6_model_fit.png")


# ------------------------------------------------------------------ figura 7
def fig7():
    m = citeste(os.path.join(DIR_RUTE, "matrice_comparativa_benzina_diesel.csv"))
    ordine = ["R_A", "R_B", "R_DN3"]
    cheie = {"R_A": "R_A", "R_B": "R_B", "R_DN3": "R_DN3"}
    def val(tr, veh, col):
        s = m[m.traseu.str.startswith(tr.replace("_", "_"))]
        s = s[s.vehicul.str.contains(veh)]
        return float(s[col].iloc[0])
    et = ["R$_\\mathrm{A}$\n20.3 km/h", "R$_\\mathrm{B}$\n33.0 km/h",
          "R$_\\mathrm{DN3}$\n57.2 km/h"]
    x = np.arange(3)
    w = 0.36
    fig, axs = plt.subplots(1, 2, figsize=(LAT, 6.5 * CM))
    for ax, col, lab, lim in [(axs[0], "consum_l_100km", "Fuel consumption [L/100 km]", 13),
                              (axs[1], "CO2_g_km", "CO$_2$ [g/km]", 310)]:
        vs = [val(t, "MAS", col) for t in ordine]
        vc = [val(t, "MAC", col) for t in ordine]
        ax.bar(x - w / 2, vs, w, color=SI, label="SI (petrol)")
        ax.bar(x + w / 2, vc, w, color=CI, label="CI (diesel)")
        for i in range(3):
            ax.annotate("%.0f%%" % (100 * (vc[i] - vs[i]) / vs[i]),
                        (i, max(vs[i], vc[i])), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=7.5)
        ax.set_xticks(x, et)
        ax.set_ylabel(lab)
        ax.set_ylim(0, lim)
        ax_curat(ax)
    axs[0].legend(frameon=False, loc="upper right")
    fig.subplots_adjust(wspace=0.26)
    salveaza(fig, "EN_fig7_consumption_co2.png")


# ------------------------------------------------------------------ figura 8
def fig8():
    m = citeste(os.path.join(DIR_RUTE, "matrice_pe_clase_RDE.csv"))
    m["cheie"] = np.where(m.traseu.str.startswith("R_A"), "R_A",
                 np.where(m.traseu.str.startswith("R_B"), "R_B", "R_DN3"))
    clase = {"urban (≤60)": "urban", "rural (60–90)": "rural",
             "autostradă (>90)": "motorway"}
    titlu = {"R_A": "R$_\\mathrm{A}$ — central urban, 20.3 km/h",
             "R_B": "R$_\\mathrm{B}$ — coastal radial, 33.0 km/h",
             "R_DN3": "R$_\\mathrm{DN3}$ — mixed, 57.2 km/h"}
    fig, axs = plt.subplots(1, 3, figsize=(LAT, 6.5 * CM), sharey=True,
                            gridspec_kw={"width_ratios": [2, 2, 3]})
    for j, k in enumerate(("R_A", "R_B", "R_DN3")):
        g = m[m.cheie == k]
        cls = [c for c in clase if c in set(g.clasa)]
        x = np.arange(len(cls))
        w = 0.36
        vs = [float(g[(g.clasa == c) & (g.vehicul.str.contains("MAS"))].CO2_g_km.iloc[0]) for c in cls]
        vc = [float(g[(g.clasa == c) & (g.vehicul.str.contains("MAC"))].CO2_g_km.iloc[0]) for c in cls]
        axs[j].bar(x - w / 2, vs, w, color=SI, label="SI (petrol)")
        axs[j].bar(x + w / 2, vc, w, color=CI, label="CI (diesel)")
        for i in range(len(cls)):
            axs[j].annotate("%.0f%%" % (100 * (vc[i] - vs[i]) / vs[i]),
                            (i, max(vs[i], vc[i])), textcoords="offset points",
                            xytext=(0, 3), ha="center", fontsize=7.5)
        axs[j].set_xticks(x, [clase[c] for c in cls])
        axs[j].set_title(titlu[k])
        axs[j].set_ylim(0, 300)
        ax_curat(axs[j])
    axs[0].set_ylabel("CO$_2$ [g/km]")
    axs[2].legend(frameon=False, loc="upper right")
    fig.subplots_adjust(wspace=0.10)
    salveaza(fig, "EN_fig8_co2_by_class.png")


if __name__ == "__main__":
    print("Regenerez figurile la %d dpi în %s" % (DPI, DIR_FIG))
    d = incarca()
    fig1(d); fig2(d); fig3(d); fig4(d); fig5(d)
    fig6(); fig7(); fig8()
    print("Gata.")
