import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.table import table
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import io

# Konfiguracja strony
st.set_page_config(page_title="Symulator Prowizji", layout="wide")
st.title("🔥 Symulator Prowizji Bankowych")

# ==========================================================================
# ZAKŁADKI: Oryginał (schodkowy) + Alternatywny (wielomian)
# Oryginał pozostaje 1:1, alternatywa jest osobno, dzieli tylko suwaki.
# ==========================================================================
tab_org, tab_alt = st.tabs(["Oryginał (schodkowy)", "Alternatywny (wielomian)"])

# --------------------------------------------------------------------------
# ZAKŁADKA 1 — ORYGINAŁ (bez zmian względem poprzedniej wersji)
# --------------------------------------------------------------------------
with tab_org:
    # ----------------------
    # Suwaki parametrów (domyślne: Ow 1.4×ref + 3%, stała 2.00%)
    # ----------------------
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Podstawowe parametry")
        Ow_multiplier = st.slider("Mnożnik Ow (×ref)", 1.0, 2.0, 1.4, 0.1)
        Ow_const = st.slider("Stała Ow (+%)", 0.0, 5.0, 3.0, 0.1)
        base_rate = st.slider("Stała prowizja (%)", 0.0, 5.0, 2.0, 0.1) / 100
        start_rate = st.slider("Oprocentowanie start (%)", 10.0, 25.0, 18.0, 0.5)
        end_rate = st.slider("Oprocentowanie koniec (%)", 2.0, 8.0, 4.0, 0.5)
        step_rate = st.slider("Krok oprocentowania", 0.1, 1.0, 0.2, 0.1)

    with col2:
        st.subheader("📈 Pasma A–F (extra za 0.1 p.p.)")
        band_A = st.slider("A (0–1%)", 0.0, 0.5, 0.08, 0.01) / 100
        band_B = st.slider("B (1–2%)", 0.0, 0.5, 0.12, 0.01) / 100
        band_C = st.slider("C (2–3%)", 0.0, 0.5, 0.15, 0.01) / 100
        band_D = st.slider("D (3–4%)", 0.0, 0.5, 0.12, 0.01) / 100
        band_E = st.slider("E (4–5%)", 0.0, 0.5, 0.08, 0.01) / 100
        band_F = st.slider("F (5–6%)", 0.0, 0.5, 0.05, 0.01) / 100
        extra_G = st.slider("G (>6%)", 0.0, 0.1, 0.03, 0.01) / 100

    # Pasma jako lista
    bands = [
        (0.0, 0.9, band_A),   # A: 0,0–0,9 p.p.
        (0.9, 1.9, band_B),   # B: 0,9–1,9
        (1.9, 2.9, band_C),   # C: 1,9–2,9
        (2.9, 3.9, band_D),   # D: 2,9–3,9
        (3.9, 4.9, band_E),   # E: 3,9–4,9
        (4.9, 5.9, band_F),   # F: 4,9–5,9
    ]
    # extra_G (G > 5,9 p.p.) zostaje tak, jak masz w sliderze
    loan_amount = 100000

    ref_scenarios = {
        "ref 5.75%": 5.75,
        "ref 5.00%": 5.00,
        "ref 4.50%": 4.50,
        "ref 3.75%": 3.75,
        "ref 3.00%": 3.00,
        "ref 2.00%": 2.00,
        "ref 1.50%": 1.50,
    }

    # ----------------------
    # Funkcje obliczeniowe
    # ----------------------
    def Ow_from_ref(ref: float) -> float:
        # ref_r – ref zaokrąglone do 0,1
        ref_r = round(ref, 1)
        # Ow liczone z zaokrąglonego ref
        Ow_exact = Ow_multiplier * ref_r + Ow_const
        # Ow zaokrąglone do 0,1
        Ow = round(Ow_exact, 1)
        return Ow

    def commission_rate_cumulative(offer_rate: float, Ow: float) -> float:
        """
        Liczy ostateczną stawkę prowizji (w ułamku, np. 0.0235 = 2,35%)
        dla danego oprocentowania oferty i Ow.
        """
        # 1. Różnica między ofertą a Ow
        diff = offer_rate - Ow

        # 2. Jeśli poniżej Ow → minimalna prowizja 0,10%
        if diff < 0:
            return 0.001  # 0,10%

        # 3. Dodatkowa prowizja z progów A–G
        extra = 0.0

        # Progi A–F
        for low, high, step_rate_band in bands:
            # Jeśli różnica diff jest mniejsza lub równa dolnej granicy pasma,
            # to to pasmo jeszcze w ogóle nie działa → pomijamy
            if diff <= low:
                continue

            # Ile z diff "wpada" do tego konkretnego pasma
            used = min(diff, high) - low
            # Przeliczamy na kroki po 0,1 p.p. i zaokrąglamy do najbliższej liczby kroków
            steps = int(round(used / 0.1))
            if steps > 0:
                extra += steps * step_rate_band

        # Próg G – wszystko powyżej 5,9 p.p. różnicy
        if diff > 5.9:
            used_G = diff - 5.9
            steps_G = int(round(used_G / 0.1))
            if steps_G > 0:
                extra += steps_G * extra_G

        # 4. Końcowa stawka = baza + suma z progów
        return base_rate + extra

    # ----------------------
    # KALKULATOR PROWIZJI W ZŁ – 7 SEKCJI
    st.markdown("## 💰 Kalkulator prowizji w zł")

    # Wybór scenariusza ref dla kalkulatora
    ref_base_name = st.selectbox(
        "Wybierz scenariusz stopy referencyjnej (dla kalkulatora poniżej):",
        list(ref_scenarios.keys()),
        index=list(ref_scenarios.keys()).index("ref 3.75%"),  # domyślnie 3,75%
        key="ref_org",
    )

    ref_base_value = ref_scenarios[ref_base_name]
    Ow_base = Ow_from_ref(ref_base_value)

    # maksymalne oprocentowanie oferty dla wybranego ref
    max_r_base = 2 * (ref_base_value + 3.5)

    st.caption(
        f"Obliczenia poniżej używają scenariusza **{ref_base_name}** "
        f"(ref = {ref_base_value:.2f}%, Ow = {Ow_base:.2f}%) i aktualnych pasm A–G."
    )

    # Domyślne wartości startowe
    default_amounts = [5000, 7000, 10000, 15000, 20000, 25000, 30000]
    default_rates = [14.5, 14.0, 13.5, 13.0, 12.5, 12.0, 11.5]

    rows_data = []  # tu zbierzemy dane do podsumowania

    for i in range(7):
        st.markdown(f"#### Sekcja {i+1}")
        col_l, col_r = st.columns([2, 3])

        with col_l:
            kwota = st.number_input(
                f"Kwota pożyczki [{i+1}] (zł)",
                min_value=0.0,
                max_value=1_000_000.0,
                value=float(default_amounts[i]),
                step=100.0,
                key=f"kwota_{i}",
                format="%.2f",
            )
            oprocent = st.number_input(
                f"Oprocentowanie oferty [{i+1}] (%)",
                min_value=0.0,
                max_value=30.0,
                value=float(default_rates[i]),
                step=0.1,
                key=f"oprocent_{i}",
                format="%.2f",
            )

        with col_r:
            # Jeśli oprocentowanie przekracza max_r dla wybranego ref – nie liczymy
            if oprocent > max_r_base:
                st.warning(
                    f"Max oprocentowanie dla {ref_base_name} to {max_r_base:.2f}%. "
                    f"Podane {oprocent:.2f}% jest powyżej limitu."
                )
                stawka_frac = 0.0
                stawka_pct = 0.0
                prow_kwota = 0.0
            else:
                # Liczymy prowizję dla tej kwoty i stopy, używając Ow_base
                stawka_frac = commission_rate_cumulative(oprocent, Ow_base)
                stawka_pct = stawka_frac * 100
                prow_kwota = kwota * stawka_frac

            st.metric(
                label=f"Prowizja [{i+1}]",
                value=f"{prow_kwota:,.2f} zł".replace(",", " ").replace(".", ","),
                delta=f"{stawka_pct:.2f} %",
            )

            rows_data.append(
                {
                    "sekcja": i + 1,
                    "kwota": kwota,
                    "oprocent": oprocent,
                    "stawka_pct": stawka_pct,
                    "prow_kwota": prow_kwota,
                }
            )

    st.markdown("### Podsumowanie wprowadzonych kwot i prowizji (ref 3,75%)")

    if rows_data:
        suma_kwot = sum(r["kwota"] for r in rows_data)
        suma_prow = sum(r["prow_kwota"] for r in rows_data)
        # Średnia prowizja % (prosta)
        sr_stawka = (
            sum(r["stawka_pct"] for r in rows_data if r["kwota"] > 0)
            / max(len([r for r in rows_data if r["kwota"] > 0]), 1)
        )

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric(
                "Suma kwot pożyczek",
                f"{suma_kwot:,.2f} zł".replace(",", " ").replace(".", ","),
            )
        with col_s2:
            st.metric(
                "Suma prowizji",
                f"{suma_prow:,.2f} zł".replace(",", " ").replace(".", ","),
            )
        with col_s3:
            st.metric(
                "Średnia prowizja (%)",
                f"{sr_stawka:.2f} %",
            )

    # ----------------------
    # Obliczenia dla scenariuszy
    # ----------------------
    Ow_scenarios = {name: Ow_from_ref(v) for name, v in ref_scenarios.items()}
    max_rate_scen = {name: 2 * (ref + 3.5) for name, ref in ref_scenarios.items()}
    rates = np.round(np.arange(start_rate, end_rate - 0.0001, -step_rate), 2)

    prov_data_zl = {}
    prov_data_pct = {}

    for name, ref in ref_scenarios.items():
        Ow_val = Ow_scenarios[name]
        max_r = max_rate_scen[name]
        zl_list, pct_list = [], []
        for r in rates:
            if name == "ref 3.75%" and r > 14.5:
                zl_list.append(np.nan)
                pct_list.append(np.nan)
                continue
            if r > max_r:
                zl_list.append(np.nan)
                pct_list.append(np.nan)
                continue
            stawka_pct = commission_rate_cumulative(r, Ow_val) * 100
            zl = loan_amount * stawka_pct / 100
            zl_list.append(zl)
            pct_list.append(stawka_pct)
        prov_data_zl[name] = zl_list
        prov_data_pct[name] = pct_list

    # ----------------------
    # Wykres
    # ----------------------
    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
    ]
    markers = ["o", "s", "^", "D", "v", "p", "X"]

    fig, ax = plt.subplots(figsize=(14, 8))
    x = np.arange(len(rates))

    for i, (name, color) in enumerate(zip(ref_scenarios.keys(), colors)):
        vals_zl = np.array([np.nan if np.isnan(v) else v for v in prov_data_zl[name]])
        ax.plot(
            x,
            vals_zl,
            label=name,
            color=color,
            marker=markers[i],
            markersize=3,
            linewidth=2.0,
        )

    # Etykiety % nad punktam
