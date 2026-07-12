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

    # Etykiety % nad punktami
    for name in ref_scenarios.keys():
        for j, pct in enumerate(prov_data_pct[name]):
            if np.isnan(pct):
                continue
            ax.text(
                j,
                prov_data_zl[name][j] + 100,
                f"{pct:.1f}%",
                ha="center",
                va="bottom",
                fontsize=5,
                color="black",
                fontweight="bold",
                rotation=90,
            )

    ax.set_xticks(x[::5])
    ax.set_xticklabels([f"{r:.1f}%" for r in rates[::5]], rotation=45)
    ax.set_ylabel("Prowizja [zł]")
    ax.set_xlabel(f"Oprocentowanie ({start_rate:.0f}% ← {end_rate:.0f}%)")
    ax.set_title(
        f"Prowizja: Ow={Ow_multiplier:.1f}×ref+{Ow_const:.1f}%, stała {base_rate*100:.2f}%"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7, loc="upper right", bbox_to_anchor=(0.98, 0.98))

    # Tabelka parametrów
    table_data = [
        ["Parametry", ""],
        ["Ow", f"{Ow_multiplier:.1f}×ref + {Ow_const:.1f}%"],
        ["Stała", f"{base_rate*100:.2f}%"],
        ["A 0–1%", f"{band_A*100:.2f}%"],
        ["B 1–2%", f"{band_B*100:.2f}%"],
        ["C 2–3%", f"{band_C*100:.2f}%"],
        ["D 3–4%", f"{band_D*100:.2f}%"],
        ["E 4–5%", f"{band_E*100:.2f}%"],
        ["F 5–6%", f"{band_F*100:.2f}%"],
        ["G >6%", f"{extra_G*100:.2f}%"],
    ]
    tbl = table(
        ax,
        cellText=table_data,
        bbox=[0.02, 0.02, 0.28, 0.35],
        colWidths=[0.5, 0.5],
        cellLoc="left",
    )
    tbl.set_fontsize(7)
    for i in range(len(table_data)):
        tbl[(i, 0)].set_facecolor("#e8f4f8")
        tbl[(i, 0)].set_text_props(weight="bold")
        tbl[(i, 1)].set_facecolor("white")

    st.pyplot(fig)

    # ----------------------
    # Przyciski pobierania (bez use_container_width)
    # ----------------------
    fig.savefig("temp.png", dpi=200, bbox_inches="tight", facecolor="white")

    col_png, col_pdf = st.columns(2)

    with col_png:
        png_data = open("temp.png", "rb").read()
        st.download_button(
            label="💾 Pobierz PNG",
            data=png_data,
            file_name=f"wykres_Ow{Ow_multiplier:.1f}_st{base_rate*100:.2f}.png",
            mime="image/png",
            width=200,
        )

    with col_pdf:
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width_pdf, height_pdf = A4

        # Tytuł u góry
        c.setFont("Helvetica-Bold", 14)
        title_text = f"Symulator Prowizji | Ow={Ow_multiplier:.1f}×ref+{Ow_const:.1f}%, stała {base_rate*100:.2f}%"
        c.drawString(40, height_pdf - 40, title_text)

        # Krótki opis pod tytułem
        c.setFont("Helvetica", 10)
        c.drawString(40, height_pdf - 60, f"Kwota referencyjna (wykres): {loan_amount:,.0f} zł".replace(",", " "))
        c.drawString(40, height_pdf - 75, f"Zakres oprocentowania: {start_rate:.1f}% → {end_rate:.1f}%, krok {step_rate:.1f} p.p.")

        # -------------------
        # WYKRES – STAŁA RAMKA
        # -------------------
        left_margin = 40
        right_margin = 40

        # Stała wysokość i pozycja wykresu: tuż pod opisem, ale nad tabelą
        plot_top_y = height_pdf - 90       # górna krawędź ramki na wykres (bliżej tytułu)
        plot_height = 260                  # wysokość ramki na wykres
        plot_bottom_y = plot_top_y - plot_height

        plot_width = width_pdf - left_margin - right_margin

        c.drawImage(
            "temp.png",
            left_margin,
            plot_bottom_y,
            width=plot_width,
            height=plot_height,
            preserveAspectRatio=True,
            anchor='sw'
        )

        # -------------------
        # TABELA Z KALKULATORA POD WYKRESEM
        # -------------------
        # start tabeli = trochę poniżej dolnej krawędzi wykresu
        table_start_y = plot_bottom_y - 130  # 130 pts pod wykresem
        row_height = 14

        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, table_start_y + row_height * 7 + 8, "Kalkulator prowizji (ref 3,75%) – zestawienie 7 sekcji")

        # Nagłówki tabeli
        headers = ["Sekcja", "Kwota [zł]", "Oprocentowanie [%]", "Prowizja [%]", "Prowizja [zł]"]
        col_x = [40, 110, 230, 360, 460]

        header_y = table_start_y + row_height * 6
        for x, header in zip(col_x, headers):
            c.drawString(x, header_y, header)

        c.setFont("Helvetica", 9)

        # Wiersze danych
        for idx, r in enumerate(rows_data[:7]):
            y = table_start_y + row_height * (5 - idx)
            c.drawString(col_x[0], y, f"{r['sekcja']}")
            c.drawRightString(col_x[1] + 60, y, f"{r['kwota']:,.2f}".replace(",", " ").replace(".", ","))
            c.drawRightString(col_x[2] + 80, y, f"{r['oprocent']:.2f}".replace(".", ","))
            c.drawRightString(col_x[3] + 60, y, f"{r['stawka_pct']:.2f}".replace(".", ","))
            c.drawRightString(col_x[4] + 70, y, f"{r['prow_kwota']:,.2f}".replace(",", " ").replace(".", ","))

        # Podsumowanie pod tabelą
        if rows_data:
            suma_kwot = sum(r["kwota"] for r in rows_data)
            suma_prow = sum(r["prow_kwota"] for r in rows_data)
            sr_stawka = (
                sum(r["stawka_pct"] for r in rows_data if r["kwota"] > 0)
                / max(len([r for r in rows_data if r["kwota"] > 0]), 1)
            )

            sum_y = table_start_y - 40
            c.setFont("Helvetica-Bold", 10)
            c.drawString(40, sum_y, "Podsumowanie:")
            c.setFont("Helvetica", 9)
            c.drawString(120, sum_y, f"Suma kwot: {suma_kwot:,.2f} zł".replace(",", " ").replace(".", ","))
            c.drawString(120, sum_y - 12, f"Suma prowizji: {suma_prow:,.2f} zł".replace(",", " ").replace(".", ","))
            c.drawString(120, sum_y - 24, f"Średnia prowizja: {sr_stawka:.2f} %".replace(".", ","))

        c.save()
        pdf_buffer.seek(0)

        st.download_button(
            label="💾 Pobierz PDF",
            data=pdf_buffer.getvalue(),
            file_name=f"prowizje_Ow{Ow_multiplier:.1f}_st{base_rate*100:.2f}_z_kalkulatorem.pdf",
            mime="application/pdf",
            width=200,
        )


# --------------------------------------------------------------------------
# ZAKŁADKA 2 — ALTERNATYWNY (wielomian 3. stopnia)
# Krzywa gładka, bez pasm A–G. Współczynniki dopasowane do domyślnych pasm.
# stawka(%) = K_baza + 0.62879*d + 0.29474*d^2 - 0.03988*d^3, gdzie d = oferta - Ow
# Dla d>5.9 kontynuacja liniowa z nachyleniem G (0.03% na 0.1 p.p.).
# Dla d<0 stawka = K_baza (bez „garbu” z wielomianu).
# --------------------------------------------------------------------------
with tab_alt:
    st.info(
        "Wariant alternatywny używa **gładkiej krzywej** (wielomian 3. stopnia) zamiast pasm A–G. "
        "Współczynniki są dopasowane do domyślnych pasm z zakładki *Oryginał*. "
        "Zmiana suwaków pasm A–G tu nie działa – jest tylko jeden parametr *Stała prowizji* i parametry Ow."
    )

    col1a, col2a = st.columns(2)

    with col1a:
        st.subheader("📊 Parametry (alternatywa)")
        Ow_multiplier_a = st.slider("Mnożnik Ow (×ref)", 1.0, 2.0, 1.4, 0.1, key="alt_mult")
        Ow_const_a = st.slider("Stała Ow (+%)", 0.0, 5.0, 3.0, 0.1, key="alt_const")
        base_rate_a = st.slider("Stała prowizja (%)", 0.0, 5.0, 2.0, 0.1, key="alt_base") / 100
        start_rate_a = st.slider("Oprocentowanie start (%)", 10.0, 25.0, 18.0, 0.5, key="alt_start")
        end_rate_a = st.slider("Oprocentowanie koniec (%)", 2.0, 8.0, 4.0, 0.5, key="alt_end")
        step_rate_a = st.slider("Krok oprocentowania", 0.1, 1.0, 0.2, 0.1, key="alt_step")

    with col2a:
        st.subheader("🧮 Wzór alternatywny")
        st.latex(r"\text{stawka}[\%] = K_{baza} + 0{,}62879\,d + 0{,}29474\,d^{2} - 0{,}03988\,d^{3}")
        st.caption("gdzie d = oprocentowanie oferty − Ow (w p.p.), K_baza = Stała prowizji.")
        st.markdown(
            "- **d < 0** → stawka = K_baza (bez odcięcia 0,10%)\n"
            "- **d ≤ 5,9** → wielomian 3. stopnia\n"
            "- **d > 5,9** → kontynuacja liniowa z nachyleniem 0,03% / 0,1 p.p."
        )

    # Współczynniki stałe (dopasowane do domyślnych pasm A–F: 0.08, 0.12, 0.15, 0.12, 0.08, 0.05)
    A_COEF = -0.03988
    B_COEF = 0.29474
    C_COEF = 0.62879
    D_MAX = 5.9
    # Wartość extra w d = 5.9
    EXTRA_AT_MAX = A_COEF * D_MAX ** 3 + B_COEF * D_MAX ** 2 + C_COEF * D_MAX
    # Nachylenie liniowe dla d > 5.9 (jak pasmo G)
    G_SLOPE = 0.03  # % za każde 0.1 p.p. → w skali 1 p.p. daje 0.3

    ref_scenarios_a = {
        "ref 5.75%": 5.75,
        "ref 5.00%": 5.00,
        "ref 4.50%": 4.50,
        "ref 3.75%": 3.75,
        "ref 3.00%": 3.00,
        "ref 2.00%": 2.00,
        "ref 1.50%": 1.50,
    }

    def Ow_from_ref_a(ref: float) -> float:
        ref_r = round(ref, 1)
        Ow_exact = Ow_multiplier_a * ref_r + Ow_const_a
        return round(Ow_exact, 1)

    def commission_rate_alt(offer_rate: float, Ow: float) -> float:
        """
        Stawka prowizji (w ułamku) wg wzoru alternatywnego (wielomian 3. stopnia).
        """
        d = offer_rate - Ow
        if d <= 0:
            # bez „garbu” dla ujemnych d – tylko baza
            return base_rate_a
        if d <= D_MAX:
            extra_pct = A_COEF * d ** 3 + B_COEF * d ** 2 + C_COEF * d
        else:
            extra_pct = EXTRA_AT_MAX + G_SLOPE * (d - D_MAX) / 0.1
        return base_rate_a + extra_pct / 100  # extra_pct w %, zamieniamy na ułamek

    # ---- Kalkulator 7 sekcji (alternatywny) ----
    st.markdown("## 💰 Kalkulator prowizji w zł (alternatywny)")

    ref_base_name_a = st.selectbox(
        "Wybierz scenariusz stopy referencyjnej (dla kalkulatora poniżej):",
        list(ref_scenarios_a.keys()),
        index=list(ref_scenarios_a.keys()).index("ref 3.75%"),
        key="ref_alt",
    )
    ref_base_value_a = ref_scenarios_a[ref_base_name_a]
    Ow_base_a = Ow_from_ref_a(ref_base_value_a)
    max_r_base_a = 2 * (ref_base_value_a + 3.5)

    st.caption(
        f"Obliczenia poniżej używają scenariusza **{ref_base_name_a}** "
        f"(ref = {ref_base_value_a:.2f}%, Ow = {Ow_base_a:.2f}%) i wzoru wielomianowego."
    )

    default_amounts_a = [5000, 7000, 10000, 15000, 20000, 25000, 30000]
    default_rates_a = [14.5, 14.0, 13.5, 13.0, 12.5, 12.0, 11.5]

    rows_data_a = []

    for i in range(7):
        st.markdown(f"#### Sekcja {i+1}")
        col_l, col_r = st.columns([2, 3])

        with col_l:
            kwota = st.number_input(
                f"Kwota pożyczki [{i+1}] (zł)",
                min_value=0.0,
                max_value=1_000_000.0,
                value=float(default_amounts_a[i]),
                step=100.0,
                key=f"kwota_alt_{i}",
                format="%.2f",
            )
            oprocent = st.number_input(
                f"Oprocentowanie oferty [{i+1}] (%)",
                min_value=0.0,
                max_value=30.0,
                value=float(default_rates_a[i]),
                step=0.1,
                key=f"oprocent_alt_{i}",
                format="%.2f",
            )

        with col_r:
            if oprocent > max_r_base_a:
                st.warning(
                    f"Max oprocentowanie dla {ref_base_name_a} to {max_r_base_a:.2f}%. "
                    f"Podane {oprocent:.2f}% jest powyżej limitu."
                )
                stawka_frac = 0.0
                stawka_pct = 0.0
                prow_kwota = 0.0
            else:
                stawka_frac = commission_rate_alt(oprocent, Ow_base_a)
                stawka_pct = stawka_frac * 100
                prow_kwota = kwota * stawka_frac

            st.metric(
                label=f"Prowizja [{i+1}]",
                value=f"{prow_kwota:,.2f} zł".replace(",", " ").replace(".", ","),
                delta=f"{stawka_pct:.2f} %",
            )

            rows_data_a.append(
                {
                    "sekcja": i + 1,
                    "kwota": kwota,
                    "oprocent": oprocent,
                    "stawka_pct": stawka_pct,
                    "prow_kwota": prow_kwota,
                }
            )

    st.markdown("### Podsumowanie – wariant alternatywny")

    if rows_data_a:
        suma_kwot_a = sum(r["kwota"] for r in rows_data_a)
        suma_prow_a = sum(r["prow_kwota"] for r in rows_data_a)
        sr_stawka_a = (
            sum(r["stawka_pct"] for r in rows_data_a if r["kwota"] > 0)
            / max(len([r for r in rows_data_a if r["kwota"] > 0]), 1)
        )

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric(
                "Suma kwot pożyczek",
                f"{suma_kwot_a:,.2f} zł".replace(",", " ").replace(".", ","),
            )
        with col_s2:
            st.metric(
                "Suma prowizji",
                f"{suma_prow_a:,.2f} zł".replace(",", " ").replace(".", ","),
            )
        with col_s3:
            st.metric(
                "Średnia prowizja (%)",
                f"{sr_stawka_a:.2f} %",
            )

    # ---- Wykres alternatywny ----
    Ow_scen_a = {name: Ow_from_ref_a(v) for name, v in ref_scenarios_a.items()}
    max_rate_scen_a = {name: 2 * (ref + 3.5) for name, ref in ref_scenarios_a.items()}
    rates_a = np.round(np.arange(start_rate_a, end_rate_a - 0.0001, -step_rate_a), 2)

    loan_amount_a = 100000
    prov_zl_a = {}
    prov_pct_a = {}

    for name, ref in ref_scenarios_a.items():
        Ow_val = Ow_scen_a[name]
        max_r = max_rate_scen_a[name]
        zl_list, pct_list = [], []
        for r in rates_a:
            if name == "ref 3.75%" and r > 14.5:
                zl_list.append(np.nan)
                pct_list.append(np.nan)
                continue
            if r > max_r:
                zl_list.append(np.nan)
                pct_list.append(np.nan)
                continue
            stawka_pct = commission_rate_alt(r, Ow_val) * 100
            zl_list.append(loan_amount_a * stawka_pct / 100)
            pct_list.append(stawka_pct)
        prov_zl_a[name] = zl_list
        prov_pct_a[name] = pct_list

    colors_a = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
        "#9467bd", "#8c564b", "#e377c2",
    ]
    markers_a = ["o", "s", "^", "D", "v", "p", "X"]

    fig_a, ax_a = plt.subplots(figsize=(14, 8))
    x_a = np.arange(len(rates_a))

    for i, (name, color) in enumerate(zip(ref_scenarios_a.keys(), colors_a)):
        vals = np.array([np.nan if np.isnan(v) else v for v in prov_zl_a[name]])
        ax_a.plot(
            x_a, vals, label=name, color=color,
            marker=markers_a[i], markersize=3, linewidth=2.0,
        )

    for name in ref_scenarios_a.keys():
        for j, pct in enumerate(prov_pct_a[name]):
            if np.isnan(pct):
                continue
            ax_a.text(
                j, prov_zl_a[name][j] + 100, f"{pct:.1f}%",
                ha="center", va="bottom",
                fontsize=5, color="black", fontweight="bold", rotation=90,
            )

    ax_a.set_xticks(x_a[::5])
    ax_a.set_xticklabels([f"{r:.1f}%" for r in rates_a[::5]], rotation=45)
    ax_a.set_ylabel("Prowizja [zł]")
    ax_a.set_xlabel(f"Oprocentowanie ({start_rate_a:.0f}% ← {end_rate_a:.0f}%)")
    ax_a.set_title(
        f"Wariant ALTERNATYWNY (wielomian): Ow={Ow_multiplier_a:.1f}×ref+{Ow_const_a:.1f}%, "
        f"stała {base_rate_a*100:.2f}%"
    )
    ax_a.grid(True, alpha=0.3)
    ax_a.legend(fontsize=7, loc="upper right", bbox_to_anchor=(0.98, 0.98))

    # Tabelka parametrów wzoru
    table_data_a = [
        ["Parametry (alt.)", ""],
        ["Ow", f"{Ow_multiplier_a:.1f}×ref + {Ow_const_a:.1f}%"],
        ["Stała", f"{base_rate_a*100:.2f}%"],
        ["c1 (d)", f"{C_COEF:+.5f}"],
        ["c2 (d²)", f"{B_COEF:+.5f}"],
        ["c3 (d³)", f"{A_COEF:+.5f}"],
        ["d > 5,9", f"lin. {G_SLOPE:.2f}%/0,1 p.p."],
        ["d < 0", "stawka = baza"],
    ]
    tbl_a = table(
        ax_a,
        cellText=table_data_a,
        bbox=[0.02, 0.02, 0.28, 0.30],
        colWidths=[0.5, 0.5],
        cellLoc="left",
    )
    tbl_a.set_fontsize(7)
    for i in range(len(table_data_a)):
        tbl_a[(i, 0)].set_facecolor("#fef2e0")
        tbl_a[(i, 0)].set_text_props(weight="bold")
        tbl_a[(i, 1)].set_facecolor("white")

    st.pyplot(fig_a)

    # Eksport PNG dla alternatywnego
    fig_a.savefig("temp_alt.png", dpi=200, bbox_inches="tight", facecolor="white")
    png_data_a = open("temp_alt.png", "rb").read()
    st.download_button(
        label="💾 Pobierz PNG (alternatywny)",
        data=png_data_a,
        file_name=f"wykres_ALT_Ow{Ow_multiplier_a:.1f}_st{base_rate_a*100:.2f}.png",
        mime="image/png",
        width=250,
    )
