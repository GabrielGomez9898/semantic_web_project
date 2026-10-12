
import pandas as pd

# -----------------------------------
# Carga del dataset original
# -----------------------------------

CSV_PATH = "../../dataset/grupo_3_final_total.csv"
OUTPUT_PATH = "artists_catalog.csv"

df = pd.read_csv(CSV_PATH)

# -----------------------------------
# Catálogo único de artistas
# -----------------------------------

artists = (
    df.dropna(subset=["artist_mbid", "artist_name"])
    .groupby("artist_mbid", as_index=False)
    .agg(
        artist_name=("artist_name", "first"),
        country=("country", "first"),
        area=("area", "first"),
        artist_type=("artist_type", "first"),
        gender=("gender", "first"),
        total_tracks=("track_id", "nunique"),
    )
)

# Ordenar para facilitar la revisión
artists = artists.sort_values("artist_name")

# -----------------------------------
# Guardar resultados
# -----------------------------------

artists.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

print("Catálogo de artistas generado.")
print("Artistas únicos:", len(artists))
print("Archivo:", OUTPUT_PATH)
print()
print(artists.head(10).to_string(index=False))
