import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .config import H3_MIN_SALES, H3_RESOLUTION, MAPS_DIR, ROOT


TEMPLATE = Path(__file__).parent / "templates/painel_geoespacial.html"
COUNTY_GEOJSON = ROOT / "data/geospatial/king_county.geojson"
PANEL_PATH = MAPS_DIR / "painel_geoespacial.html"
ATLANTIC = ["#eaf1f4", "#c7dce1", "#91bbc1", "#5e959f", "#356c7b", "#21485f", "#132f48", "#0b2036"]


def _zipcode_dominante(serie: pd.Series) -> str:
    moda = serie.astype("Int64").astype(str).mode()
    return moda.iat[0] if len(moda) else "não informado"


def _base_espacial(df: pd.DataFrame) -> pd.DataFrame:
    colunas = ["date", "price", "bedrooms", "bathrooms", "sqft_living", "lat", "long", "zipcode"]
    ausentes = set(colunas).difference(df.columns)
    if ausentes:
        raise KeyError(f"Colunas ausentes para o painel: {sorted(ausentes)}")
    base = df[colunas].dropna().copy()
    base = base[
        base["price"].gt(0) & base["sqft_living"].gt(0)
        & base["lat"].between(-90, 90) & base["long"].between(-180, 180)
    ]
    base["area_m2"] = base["sqft_living"] * 0.092903
    base["valor_m2"] = base["price"] / base["area_m2"]
    base["data_iso"] = pd.to_datetime(
        base["date"].astype(str), format="mixed", errors="raise"
    ).dt.strftime("%Y-%m-%d")
    return base


def agregar_valor_m2_h3(
    df: pd.DataFrame,
    resolucao: int = H3_RESOLUTION,
    minimo_vendas: int = H3_MIN_SALES,
) -> tuple[pd.DataFrame, dict]:
    """Resume o valor por m² em H3; indicador restrito à análise exploratória."""
    base = _base_espacial(df)
    base["h3"] = [h3.latlng_to_cell(lat, lon, resolucao) for lat, lon in zip(base["lat"], base["long"])]
    regioes = (
        base.groupby("h3", as_index=False)
        .agg(
            vendas=("price", "size"),
            valor_m2_mediano=("valor_m2", "median"),
            valor_m2_q1=("valor_m2", lambda s: s.quantile(0.25)),
            valor_m2_q3=("valor_m2", lambda s: s.quantile(0.75)),
            preco_mediano=("price", "median"),
            area_mediana_m2=("area_m2", "median"),
            zipcode_dominante=("zipcode", _zipcode_dominante),
        )
    )
    celulas_ocupadas = len(regioes)
    regioes = regioes[regioes["vendas"].ge(minimo_vendas)].copy()
    regioes[["latitude_centro", "longitude_centro"]] = pd.DataFrame(
        [h3.cell_to_latlng(celula) for celula in regioes["h3"]], index=regioes.index
    )
    regioes["iqr_valor_m2"] = regioes["valor_m2_q3"] - regioes["valor_m2_q1"]
    limite_topo = float(regioes["valor_m2_mediano"].quantile(0.90))
    regioes["top_decil"] = regioes["valor_m2_mediano"].ge(limite_topo)
    regioes = regioes.sort_values("valor_m2_mediano", ascending=False, ignore_index=True)
    resumo = {
        "metrica": "mediana do preço por m²",
        "resolucao_h3": resolucao,
        "minimo_vendas_por_celula": minimo_vendas,
        "vendas_validas": int(len(base)),
        "vendas_mapeadas": int(regioes["vendas"].sum()),
        "cobertura_percentual": float(100 * regioes["vendas"].sum() / len(base)),
        "celulas_ocupadas": int(celulas_ocupadas),
        "celulas_exibidas": int(len(regioes)),
        "celulas_top_decil": int(regioes["top_decil"].sum()),
        "limite_top_decil_usd_m2": limite_topo,
        "escala_visual_p05": float(regioes["valor_m2_mediano"].quantile(0.05)),
        "escala_visual_p95": float(regioes["valor_m2_mediano"].quantile(0.95)),
    }
    return regioes, resumo


def _geojson_h3(regioes: pd.DataFrame) -> dict:
    features = []
    for celula in regioes["h3"]:
        contorno = [[lon, lat] for lat, lon in h3.cell_to_boundary(celula)]
        contorno.append(contorno[0])
        features.append({
            "type": "Feature", "id": celula, "properties": {"h3": celula},
            "geometry": {"type": "Polygon", "coordinates": [contorno]},
        })
    return {"type": "FeatureCollection", "features": features}


def criar_mapa_interativo(regioes: pd.DataFrame, resumo: dict):
    """Cria uma prévia H3 compacta para a saída do notebook."""
    fig = px.choropleth_map(
        regioes, geojson=_geojson_h3(regioes), locations="h3",
        featureidkey="properties.h3", color="valor_m2_mediano",
        color_continuous_scale=ATLANTIC,
        range_color=(resumo["escala_visual_p05"], resumo["escala_visual_p95"]),
        opacity=0.82, map_style="carto-positron",
        center={"lat": float(regioes["latitude_centro"].median()), "lon": float(regioes["longitude_centro"].median())},
        zoom=8, hover_name="zipcode_dominante",
        hover_data={
            "h3": False, "valor_m2_mediano": ":,.0f", "vendas": ":,",
            "preco_mediano": ":,.0f", "area_mediana_m2": ":.1f",
            "iqr_valor_m2": ":,.0f", "top_decil": True,
            "latitude_centro": False, "longitude_centro": False,
        },
        labels={
            "zipcode_dominante": "ZIP predominante", "valor_m2_mediano": "Mediana (US$/m²)",
            "vendas": "Vendas", "preco_mediano": "Preço mediano (US$)",
            "area_mediana_m2": "Área mediana (m²)", "iqr_valor_m2": "IQR (US$/m²)",
            "top_decil": "Decil superior",
        },
        title="Valor residencial por metro quadrado — King County",
    )
    fig.update_traces(marker_line_width=0.45, marker_line_color="#f8fafc")
    topo = regioes[regioes["top_decil"]]
    fig.add_trace(go.Choroplethmap(
        geojson=_geojson_h3(topo), locations=topo["h3"], z=np.ones(len(topo)),
        featureidkey="properties.h3", colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
        showscale=False, marker={"line": {"color": "#b08d57", "width": 1.8}}, hoverinfo="skip",
    ))
    fig.update_layout(
        height=680, margin={"l": 0, "r": 0, "t": 70, "b": 0},
        font={"family": "Arial", "color": "#172033"},
        coloraxis_colorbar={"title": "US$/m²", "tickformat": "$,.0f"},
        title={"x": 0.02, "font": {"size": 22}},
    )
    return fig


def _regioes_painel(regioes: pd.DataFrame) -> list[dict]:
    registros = []
    for row in regioes.itertuples(index=False):
        contorno = [[lon, lat] for lat, lon in h3.cell_to_boundary(row.h3)]
        contorno.append(contorno[0])
        registros.append({
            "h3": row.h3, "vendas": int(row.vendas),
            "valor_m2_mediano": float(row.valor_m2_mediano),
            "preco_mediano": float(row.preco_mediano),
            "area_mediana_m2": float(row.area_mediana_m2),
            "zipcode_dominante": str(row.zipcode_dominante),
            "iqr_valor_m2": float(row.iqr_valor_m2), "top_decil": bool(row.top_decil),
            "boundary": contorno,
        })
    return registros


def _transacoes_painel(df: pd.DataFrame) -> list[dict]:
    base = _base_espacial(df)
    return [{
        "lat": float(row.lat), "lon": float(row.long), "price": float(row.price),
        "valor_m2": float(row.valor_m2), "zipcode": str(int(row.zipcode)),
        "date": row.data_iso, "bedrooms": int(row.bedrooms),
        "bathrooms": float(row.bathrooms), "sqft_living": int(row.sqft_living),
    } for row in base.itertuples(index=False)]


def salvar_painel_geoespacial(df: pd.DataFrame, regioes: pd.DataFrame) -> Path:
    pagina = TEMPLATE.read_text(encoding="utf-8")
    substituicoes = {
        "__REGIONS_JSON__": _regioes_painel(regioes),
        "__TRANSACTIONS_JSON__": _transacoes_painel(df),
        "__COUNTY_JSON__": json.loads(COUNTY_GEOJSON.read_text(encoding="utf-8")),
    }
    for marcador, dados in substituicoes.items():
        pagina = pagina.replace(marcador, json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
    pendentes = [marcador for marcador in substituicoes if marcador in pagina]
    if pendentes:
        raise RuntimeError(f"Marcadores não substituídos: {pendentes}")
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    PANEL_PATH.write_text(pagina, encoding="utf-8")
    return PANEL_PATH


def gerar_mapa_valor_m2(df: pd.DataFrame):
    regioes, resumo = agregar_valor_m2_h3(df)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    regioes.to_csv(MAPS_DIR / "regioes_h3_valor_m2.csv", index=False)
    (MAPS_DIR / "resumo_mapa_valor_m2.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    painel = salvar_painel_geoespacial(df, regioes)
    return regioes, resumo, criar_mapa_interativo(regioes, resumo), painel
