import csv
import json
import zipfile
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR.parent / "dataset" / "grupo_3_enriched.csv"
LASTFM_ZIP = BASE_DIR / "lastfm" / "lastfm_subset.zip"

LASTFM_TRACKS_FILE = BASE_DIR.parent / "dataset" / "lastfm_tracks.csv"
LASTFM_SIMILARS_FILE = BASE_DIR.parent / "dataset" / "lastfm_similars.csv"
OUTPUT_FILE = BASE_DIR.parent / "dataset" / "grupo_3_final.csv"


# ---------------------------------------------------------------------------
# 1. Leer dataset original
# ---------------------------------------------------------------------------

print("Leyendo dataset...")

df = pd.read_csv(INPUT_FILE)

print(f"Registros del dataset: {len(df)}")

track_ids = set(
    df["track_id"]
    .dropna()
    .astype(str)
)

print(f"Tracks únicos: {len(track_ids)}")


# ---------------------------------------------------------------------------
# 2. Leer Last.fm directamente desde el ZIP
# ---------------------------------------------------------------------------

tracks = []
similars = []

encontrados = 0

print("\nProcesando Last.fm...")


with zipfile.ZipFile(LASTFM_ZIP, "r") as z:

    archivos = [
        name
        for name in z.namelist()
        if name.endswith(".json")
    ]

    print(f"JSON encontrados en Last.fm: {len(archivos)}")

    for i, filename in enumerate(archivos, start=1):

        # El nombre del archivo es el track_id
        track_id = Path(filename).stem

        # Solo procesamos tracks que están en nuestro dataset
        if track_id not in track_ids:
            continue

        try:

            with z.open(filename) as f:
                data = json.load(f)

            encontrados += 1

            # ---------------------------------------------------------------
            # Datos de la canción
            # ---------------------------------------------------------------

            tags = data.get("tags", [])

            # Ordenamos por score descendente
            tags = sorted(
                tags,
                key=lambda x: float(x[1]),
                reverse=True
            )

            tag_names = [
                str(tag[0])
                for tag in tags
            ]

            top_tag = tag_names[0] if tag_names else None

            top_tag_score = (
                float(tags[0][1])
                if tags
                else None
            )

            tracks.append({
                "track_id": track_id,
                "lastfm_artist": data.get("artist"),
                "lastfm_title": data.get("title"),
                "lastfm_top_tag": top_tag,
                "lastfm_top_tag_score": top_tag_score,
                "lastfm_tags": "|".join(tag_names)
            })

            # ---------------------------------------------------------------
            # Canciones similares
            # ---------------------------------------------------------------

            for similar in data.get("similars", []):

                if len(similar) < 2:
                    continue

                similar_track_id = similar[0]
                similarity_score = similar[1]

                similars.append({
                    "track_id": track_id,
                    "similar_track_id": similar_track_id,
                    "similarity_score": float(similarity_score)
                })

        except Exception as e:

            print(
                f"Error leyendo {filename}: {e}"
            )


# ---------------------------------------------------------------------------
# 3. Crear lastfm_tracks.csv
# ---------------------------------------------------------------------------

tracks_df = pd.DataFrame(tracks)

tracks_df.to_csv(
    LASTFM_TRACKS_FILE,
    index=False,
    encoding="utf-8"
)

print("\n--- Last.fm tracks ---")
print(f"Tracks encontrados: {encontrados}")
print(f"Archivo: {LASTFM_TRACKS_FILE}")


# ---------------------------------------------------------------------------
# 4. Crear lastfm_similars.csv
# ---------------------------------------------------------------------------

similars_df = pd.DataFrame(similars)

similars_df.to_csv(
    LASTFM_SIMILARS_FILE,
    index=False,
    encoding="utf-8"
)

print("\n--- Last.fm similars ---")
print(f"Relaciones encontradas: {len(similars_df)}")
print(f"Archivo: {LASTFM_SIMILARS_FILE}")


# ---------------------------------------------------------------------------
# 5. Merge con grupo_3_enriched.csv
# ---------------------------------------------------------------------------

print("\nHaciendo merge...")

df_final = df.merge(
    tracks_df,
    on="track_id",
    how="left"
)

df_final.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8"
)

print("\n--- Resultado final ---")
print(f"Registros: {len(df_final)}")
print(f"Columnas: {len(df_final.columns)}")
print(f"Archivo: {OUTPUT_FILE}")

print("\nColumnas finales:")

for column in df_final.columns:
    print(f"  - {column}")