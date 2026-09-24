import os
import kagglehub
import pandas as pd
import requests
import streamlit as st
from kagglehub import KaggleDatasetAdapter
import plotly.express as px
st.set_page_config(page_title="EK 2024 en welvaart", layout="wide")
# spelers via de Kaggle-API
@st.cache_data
def haal_spelers():
    if "KAGGLE_USERNAME" in st.secrets:
        os.environ["KAGGLE_USERNAME"] = st.secrets["KAGGLE_USERNAME"]
        os.environ["KAGGLE_KEY"] = st.secrets["KAGGLE_KEY"]

    return kagglehub.dataset_load(
        KaggleDatasetAdapter.PANDAS,
        "damirdizdarevic/uefa-euro-2024-players",
        "euro2024_players.csv",
    )

# bbp per inwoner via de World Bank-API
@st.cache_data
def haal_gdp(indicator="NY.GDP.PCAP.PP.CD", jaar="2024"):
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
    antwoord = requests.get(url, params={"format": "json", "date": jaar, "per_page": 400})
    df = pd.json_normalize(antwoord.json()[1])       # [0] is uitleg, [1] is de data
    df = df[["country.value", "value"]]
    df.columns = ["land", "GDP_per_persoon"]
    return df.dropna(subset=["GDP_per_persoon"])

spelers = haal_spelers()
gdp = haal_gdp()
#  Data opschoning
# 1 kolomnamen vertaald
spelers = spelers.rename(columns={
    "Name": "Naam",
    "Position": "Positie",
    "Age": "Leeftijd",
    "Club": "Club",
    "Height": "Lengte",
    "Foot": "Voet",
    "Caps": "Interlands",
    "Goals": "Goals",
    "MarketValue": "Marktwaarde",
    "Country": "Land",
})

# 2 linies samenvoegen
linies = {
    "Goalkeeper": "Keeper",
    "Centre-Back": "Verdediger",
    "Left-Back": "Verdediger",
    "Right-Back": "Verdediger",
    "Defensive Midfield": "Middenvelder",
    "Central Midfield": "Middenvelder",
    "Attacking Midfield": "Middenvelder",
    "Left Midfield": "Middenvelder",
    "Right Midfield": "Middenvelder",
    "Left Winger": "Aanvaller",
    "Right Winger": "Aanvaller",
    "Second Striker": "Aanvaller",
    "Centre-Forward": "Aanvaller",
}
spelers["Positie"] = spelers["Positie"].map(linies)

# 3 voetvoorkeur: '-' en lege waarden zijn allebei onbekend
spelers["Voet"] = spelers["Voet"].replace("-", pd.NA).fillna("onbekend")

# samenvoegen Data

# 1 landnamen die bij de World Bank anders heten
naam_wb = {"England": "United Kingdom", "Scotland": "United Kingdom",
           "Czech Republic": "Czechia", "Slovakia": "Slovak Republic",
           "Turkey": "Turkiye"}
spelers["WB_naam"] = spelers["Land"].replace(naam_wb)

data = pd.merge(spelers, gdp, left_on="WB_naam", right_on="land", how="left")
data = data.drop(columns=["WB_naam", "land"])
data = data.rename(columns={"GDP_per_persoon": "BBP"})

st.title("EK 2024-spelers met het bbp per inwoner van hun land")
st.caption("Bronnen: spelers via de Kaggle-API (UEFA Euro 2024 Players, Transfermarkt) · "
           "bbp per inwoner via de World Bank-API (NY.GDP.PCAP.PP.CD, 2024).")


# filters
landen = sorted(data["Land"].unique())
keuze = st.sidebar.multiselect("Kies landen", landen, default=landen)
posities = st.sidebar.multiselect(
    "Welke posities wil je meenemen?",
    sorted(data["Positie"].unique()),
    default=sorted(data["Positie"].unique()),
)

selectie = data[data["Land"].isin(keuze) & data["Positie"].isin(posities)].copy()

selectie["Leeftijdsgroep"] = pd.cut(selectie["Leeftijd"],
                                    bins=[15, 20, 23, 26, 29, 32, 45],
                                    labels=["<21", "21-23", "24-26", "27-29", "30-32", "33+"])


# staafdiagram: marktwaarde per land, gekleurd op bbp
if selectie.empty:
    st.warning("Geen spelers in je selectie. Kies minstens één land en één positie.")
    st.stop()
k1, k2, k3 = st.columns(3)
k1.metric("Spelers", len(selectie))
k2.metric("Landen", selectie["Land"].nunique())
k3.metric("Totale waarde", f"€ {selectie['Marktwaarde'].sum() / 1e9:.2f} mld")
st.subheader("Marktwaarde per land, gekleurd naar welvaart")

kol1, kol2 = st.columns(2)
maatstaf = kol1.radio("Maatstaf", ["gemiddelde", "mediaan", "totaal"], horizontal=True)
aantal_landen = selectie["Land"].nunique()

if aantal_landen > 3:
    top_n = kol2.slider("Aantal landen", 3, aantal_landen, min(10, aantal_landen))
else:
    top_n = aantal_landen
    kol2.caption(f"{aantal_landen} land(en) geselecteerd, geen top-N nodig")

func = {"gemiddelde": "mean", "mediaan": "median", "totaal": "sum"}[maatstaf]

per_land = selectie.groupby("Land", as_index=False).agg(
    waarde=("Marktwaarde", func),
    BBP=("BBP", "first"),
    spelers=("Naam", "count"),
)
per_land["waarde_mln"] = (per_land["waarde"] / 1_000_000).round(1)
per_land = per_land.sort_values("waarde", ascending=False).head(top_n)

fig = px.bar(per_land.sort_values("waarde"),
             x="waarde_mln", y="Land", orientation="h",
             color="BBP", color_continuous_scale="Blues",
             labels={"waarde_mln": f"Marktwaarde ({maatstaf}, miljoen €)",
                     "Land": "", "BBP": "Bbp per inwoner ($)"},
             hover_data={"spelers": True, "BBP": ":,.0f"})
fig.update_layout(coloraxis_colorbar_title_side="right")
st.plotly_chart(fig, use_container_width=True)

st.caption(f"Landen gerangschikt op {maatstaf} marktwaarde. Donkerder blauw = hoger bbp per inwoner.")


# Boxplot per 3 jaar marktwaarde
st.subheader("De mediane waarde halveert elke drie jaar na je 26e")
fig4 = px.box(selectie, x="Leeftijdsgroep", y="Marktwaarde", log_y=True,
              category_orders={"Leeftijdsgroep": ["<21", "21-23", "24-26",
                                                  "27-29", "30-32", "33+"]},
              labels={"Marktwaarde": "Marktwaarde (€, logaritmisch)"})
st.plotly_chart(fig4, use_container_width=True)

top_clubs = selectie["Club"].value_counts().head(15).reset_index()
top_clubs.columns = ["Club", "Spelers"]


# barplot incl aantal ek deelnemers per club
st.subheader("Inter milaan en Mancester city hebben de meeste voetballers geleverd")
fig5 = px.bar(top_clubs.sort_values("Spelers"), x="Spelers", y="Club",
              orientation="h", labels={"Club": ""})
st.plotly_chart(fig5, use_container_width=True)


# marktwaarde per leeftijd, per voet voorkeur
st.subheader("Marktwaarde over de carrière, per voetvoorkeur")
lijn_data = selectie.copy()

if lijn_data.empty:
    st.warning("Kies minstens één positie.")
else:
    per_groep = (lijn_data.groupby(["Leeftijdsgroep", "Voet"], observed=True, as_index=False)
                 .agg(mediaan=("Marktwaarde", "median"),
                      spelers=("Naam", "count")))
    per_groep["mediaan_mln"] = (per_groep["mediaan"] / 1_000_000).round(1)

    fig7 = px.line(per_groep, x="Leeftijdsgroep", y="mediaan_mln", color="Voet",
                   markers=True, hover_data={"spelers": True},
                   labels={"mediaan_mln": "Mediane marktwaarde (miljoen €)",
                           "Leeftijdsgroep": "Leeftijd", "Voet": "Voetvoorkeur"})
    st.plotly_chart(fig7, use_container_width=True)

    klein = per_groep[per_groep["spelers"] < 5]
    if not klein.empty:
        st.caption("Let op: sommige punten zijn op minder dan 5 spelers gebaseerd. "
                   "Die mediaan zegt weinig.")

# Grafiek met top 3 sterren aandeel aan het land
if aantal_landen > 3:
    top_n_ster = st.slider("Aantal landen in deze vergelijking", 3, aantal_landen,
                       min(10, aantal_landen), key="top_ster")
else:
    top_n_ster = aantal_landen
    st.caption(f"{aantal_landen} land(en) geselecteerd, geen top-N nodig")


top3 = (selectie.sort_values("Marktwaarde", ascending=False)
        .groupby("Land").head(3).groupby("Land", as_index=False)["Marktwaarde"].sum()
        .rename(columns={"Marktwaarde": "top3"}))
totaal = selectie.groupby("Land", as_index=False)["Marktwaarde"].sum()

ster = top3.merge(totaal, on="Land")
ster["aandeel"] = (ster["top3"] / ster["Marktwaarde"] * 100).round(0)
ster = ster.sort_values("aandeel", ascending=False).head(top_n_ster)
ster = ster.sort_values("aandeel")

kop = ster.iloc[-1]
st.subheader(f"{kop['Land']} leunt het zwaarst op zijn sterren: "
             f"{kop['aandeel']:.0f}% van de waarde zit in drie spelers")

fig2 = px.bar(ster, x="aandeel", y="Land", orientation="h",
              color=ster["aandeel"] >= 50,
              color_discrete_map={True: "#e45756", False: "#4c78a8"},
              labels={"aandeel": "Aandeel top 3 spelers (%)", "Land": ""})
fig2.update_layout(showlegend=False)
st.plotly_chart(fig2, use_container_width=True)
st.caption("Rood = meer dan de helft van de squadwaarde zit in drie spelers.")

# welvaart tegenover sterafhankelijkheid
st.subheader("Hoe armer het land, hoe meer afhankelijk van indivuele spelers")

ster["BBP"] = ster["Land"].map(selectie.groupby("Land")["BBP"].first())

fig8 = px.scatter(ster, x="BBP", y="aandeel", text="Land", size="Marktwaarde",
                  color=ster["aandeel"] >= 50,
                  color_discrete_map={True: "#e45756", False: "#4c78a8"},
                  labels={"BBP": "Bbp per inwoner ($, koopkracht)",
                          "aandeel": "Aandeel top 3 spelers (%)"})
fig8.update_traces(textposition="top center")
fig8.update_layout(showlegend=False)
st.plotly_chart(fig8, use_container_width=True)
st.caption(f"Correlatie: {ster['BBP'].corr(ster['aandeel']):.2f}. "
           "Grotere bollen zijn duurdere selecties.")
