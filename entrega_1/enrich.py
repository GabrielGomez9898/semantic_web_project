import json
import tarfile
from pathlib import Path

import pandas as pd


# ============================================================
# Rutas
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATASET_DIR = PROJECT_DIR / "dataset"

INPUT_FILE = DATASET_DIR / "grupo_3.csv"
DUMP_FILE = BASE_DIR / "musicbrainz" / "artist.tar.xz"

# Archivo SOLO con información de MusicBrainz
MUSICBRAINZ_OUTPUT = DATASET_DIR / "musicbrainz_artists.csv"

# Archivo final con el merge
MERGED_OUTPUT = DATASET_DIR / "grupo_3_enriched.csv"


# ============================================================
# 1. Leer dataset original
# ============================================================

df = pd.read_csv(INPUT_FILE)

print(f"Registros del dataset original: {len(df)}")


# ============================================================
# 2. Obtener los MBID que necesitamos
# ============================================================

mbids = set(
    df["artist_mbid"]
    .dropna()
    .astype(str)
    .str.strip()
)

print(f"Artistas únicos a buscar: {len(mbids)}")


# ============================================================
# 3. Leer dump de MusicBrainz
# ============================================================

resultados = []

print("\nLeyendo dump de MusicBrainz...")

with tarfile.open(DUMP_FILE, mode="r:xz") as tar:

    archivo = tar.extractfile("mbdump/artist")

    if archivo is None:
        raise RuntimeError(
            "No se encontró mbdump/artist dentro del dump."
        )

    for linea in archivo:

        artista = json.loads(linea)

        mbid = artista.get("id")

        # Solo nos interesan los artistas de nuestro dataset
        if mbid not in mbids:
            continue

        area = artista.get("area")

        resultados.append({
            "artist_mbid": mbid,
            "country": artista.get("country"),
            "area": area.get("name") if area else None,
            "gender": artista.get("gender"),
            "artist_type": artista.get("type")
        })

        # Mostrar progreso cada 500 artistas encontrados
        if len(resultados) % 500 == 0:
            print(f"Artistas encontrados: {len(resultados)}")


# ============================================================
# 4. Crear DataFrame de MusicBrainz
# ============================================================

df_musicbrainz = pd.DataFrame(resultados)


# ============================================================
# 5. Guardar SOLO información de MusicBrainz
# ============================================================

df_musicbrainz.to_csv(
    MUSICBRAINZ_OUTPUT,
    index=False,
    encoding="utf-8"
)

print("\nArchivo MusicBrainz generado:")
print(MUSICBRAINZ_OUTPUT)


# ============================================================
# 6. Hacer MERGE con el dataset original
# ============================================================

df_enriched = df.merge(
    df_musicbrainz,
    on="artist_mbid",
    how="left"
)


# ============================================================
# 7. Guardar dataset enriquecido
# ============================================================

df_enriched.to_csv(
    MERGED_OUTPUT,
    index=False,
    encoding="utf-8"
)


# ============================================================
# 8. Resumen
# ============================================================

print("\n==========================================")
print("Proceso terminado")
print("==========================================")

print(f"Registros originales:       {len(df)}")
print(f"MBID únicos:                {len(mbids)}")
print(f"Artistas encontrados:       {len(df_musicbrainz)}")
print(f"Artistas no encontrados:   {len(mbids - set(df_musicbrainz['artist_mbid']))}")

print("\nArchivos generados:")
print(f"1. {MUSICBRAINZ_OUTPUT}")
print(f"2. {MERGED_OUTPUT}")