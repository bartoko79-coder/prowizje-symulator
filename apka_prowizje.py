import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import json
from matplotlib.table import table

# Konfiguracja strony
st.set_page_config(page_title="Symulator Prowizji", layout="wide")
st.title("🔥 Symulator Prowizji Bankowych")

# ----------------------
# Suwaki parametrów
# ----------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Podstawowe parametry")
    Ow_multiplier = st.slider("Mnożnik Ow (×ref)", 1.0, 2.0, 1.3, 0.1)
    Ow_const = st.slider("Stała Ow (+%)", 0.0, 5.0, 2.8, 0.1)
    base_rate = st.slider("Stała prowizja (%)", 0.0, 5.0, 2.5, 0.1) / 100
    start_rate = st.slider("Oprocentowanie start (%)", 10.0, 25.0, 18.0, 0.5)
    end_rate = st.slider("Oprocentowanie koniec (%)", 2.0, 8.0, 4.0, 0.5)
    step_rate = st.slider("Krok oprocentowania", 0.1, 1.0, 0.2, 0.1)

with col2:
    st.subheader("📈 Pasma A-F (extra za 0.1 p.p.)")
    band_A = st.slider("A (0-1%)", 0.0, 0.5, 0.08, 0.01) / 100
    band_B = st.slider("B (1-2%)", 0.0, 0.5, 0.12, 0.01) / 100
    band_C = st.slider("C (2-3%)", 0.0, 0.5, 0.15, 0.01) / 100
    band_D = st.slider("D (3-4%)", 0.0, 0.5, 0.12, 0.01) / 100
    band_E = st.slider("E (4-5%)", 0.0, 0.5, 0.08, 0.01) / 100
    band_F = st.slider("F (5-6%)", 0.0, 0.5, 0.05, 0.01) / 100
    extra_G = st.slider("G (>6%)", 0.0, 0.1, 0.03, 0.01) / 100

# Pasma jako lista
bands = [
    (0, 1, band_A),
    (1, 2, band_B),
    (2, 3, band_C),
    (3, 4, band_D),
    (4, 5, band_E),
    (5, 6, band_F)
]

loan_amount = 100000
ref_scenarios = {
    'ref 5.75%': 5.75, 'ref 5.00%': 5.00, 'ref 4.50%': 4.50,
    'ref 3.75%': 3.75, 'ref 3.00%': 3.00, 'ref 2.00%': 2.00, 'ref 1.50%': 1.50
}

# ----------------------
# Funkcje obliczeniowe
# ----------------------
def Ow_from_ref(ref):
    return Ow_multiplier * ref + Ow_const

def commission_rate_cumulative(offer_rate, Ow):
    diff = offer_rate - Ow
    if diff < 0:
        return 0.001
    extra = 0.0
    for low, high, step_rate in bands:
        if diff <= low: continue
        used = min(diff, high) - low
        steps = int(round(used / 0.1))
        extra += steps * step_rate
    if diff > 6:
        used_G = diff - 6
        steps_G = int(round(used_G / 0.1))
        extra += steps_G * extra_G
    return base_rate + extra

# Obliczenia
Ow_scenarios = {name: Ow_from_ref(v) for name, v in ref_scenarios.items()}
max_rate_scen = {name: 2 * (ref + 3.5) for name, ref in ref_scenarios.items()}
rates = np.round(np.arange(start_rate, end_rate - 0.0001, -step_rate), 2)

prov_data_zl = {}
prov_data_pct = {}
for name, ref in ref_scenarios.items():
    Ow = Ow_scenarios[name]
    max_r = max_rate_scen[name]
    zl_list, pct_list = [], []
    for r in rates:
        if name == 'ref 3.75%' and r > 14.5:
            zl_list.append(np.nan); pct_list.append(np.nan); continue
        if r > max_r:
            zl_list.append(np.nan); pct_list.append(np.nan); continue
        stawka_pct = commission_rate_cumulative(r, Ow) * 100
        zl = loan_amount * stawka_pct / 100
        zl_list.append(zl)
        pct_list.append(stawka_pct)
    prov_data_zl[name] = zl_list
    prov_data_pct[name] = pct_list

# ----------------------
# WYKRYS
# ----------------------
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']
markers = ['o', 's', '^', 'D', 'v', 'p', 'X']

fig, ax = plt.subplots(figsize=(14, 8))
x = np.arange(len(rates))

for i, (name, color) in enumerate(zip(ref_scenarios.keys(), colors)):
    vals_zl = np.array([np.nan if np.isnan(v) else v for v in prov_data_zl[name]])
    ax.plot(x, vals_zl, label=name, color=color, marker=markers[i], 
            markersize=3, linewidth=2.0)

# Etykiety %
for name in ref_scenarios.keys():
    for j, pct in enumerate(prov_data_pct[name]):
        if np.isnan(pct): continue
        ax.text(j, prov_data_zl[name][j] + 100, f"{pct:.1f}%", 
                ha='center', va='bottom', fontsize=5, color='black', 
                fontweight='bold', rotation=90)

ax.set_xticks(x[::5])
ax.set_xticklabels([f"{r:.1f}%" for r in rates[::5]], rotation=45)
ax.set_ylabel('Prowizja [zł]')
ax.set_xlabel(f'Oprocentowanie ({start_rate:.0f}% ← {end_rate:.0f}%)')
ax.set_title(f'Prowizja: Ow={Ow_multiplier:.1f}×ref+{Ow_const:.1f}%, stała {base_rate*100:.1f}%')
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, loc='upper right', bbox_to_anchor=(0.98, 0.98))

# Tabelka parametrów
table_data = [
    ['Parametry', ''],
    ['Ow', f'{Ow_multiplier:.1f}×ref + {Ow_const:.1f}%'],
    ['Stała', f'{base_rate*100:.1f}%'],
    ['A 0-1%', f'{band_A*100:.2f}%'],
    ['B 1-2%', f'{band_B*100:.2f}%'],
    ['C 2-3%', f'{band_C*100:.2f}%']
]
tbl = table(ax, cellText=table_data, bbox=[0.02, 0.02, 0.22, 0.25],
            colWidths=[0.5, 0.5], cellLoc='left')
tbl.set_fontsize(7)
for i in range(len(table_data)):
    tbl[(i,0)].set_facecolor('#e8f4f8')
    tbl[(i,0)].set_text_props(weight='bold')

st.pyplot(fig)

# Przyciski eksportu
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("💾 Pobierz PNG"):
        fig.savefig('wykres.png', dpi=200, bbox_inches='tight')
        st.success("Zapisano wykres.png!")
with col2:
    if st.button("💾 Pobierz PDF"):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        fig.savefig('temp.png', dpi=200, bbox_inches='tight')
        c = canvas.Canvas('wykres.pdf', pagesize=A4)
        c.drawImage('temp.png', 40, 50, width=540, preserveAspectRatio=True)
        c.save()
        st.success("Zapisano wykres.pdf!")