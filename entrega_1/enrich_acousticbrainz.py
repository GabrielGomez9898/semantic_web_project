#!/usr/bin/env python3
"""
Enriquece grupo_3_final.csv con columnas de tonalidad (key_key, key_scale,
tuning_frequency) provenientes del dump de AcousticBrainz, usando como
puente el mapeo MSD -> MusicBrainz (msd-mbid-2016-01-results-ab.csv).

Flujo:
  1. Carga el mapeo track_id -> mbid (sin encabezado).
  2. Carga grupo_3_final.csv y le pega el mbid correspondiente a cada track_id.
  3. Lee el CSV de tonalidad DIRECTO desde el .tar.zst (sin descomprimir a
     disco), en chunks, quedándose solo con los mbid que nos interesan.
  4. Resuelve duplicados (mismo mbid con varios submission_offset):
     nos quedamos con offset == 0; si no existe, con el primero disponible.
  5. Hace el merge final y exporta el CSV enriquecido.

"""

import subprocess
import sys
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIGURACIÓN — ajusta rutas si es necesario
# ---------------------------------------------------------------------------
MAPPING_FILE = "acousticbrainz/msd-mbid-2016-01-results-ab.csv"
GRUPO3_FILE = "../dataset/grupo_3_final.csv"
TONAL_TAR_ZST = "acousticbrainz/acousticbrainz-lowlevel-features-20220623-tonal.tar.zst"
# Ruta interna del csv dentro del tar (la que usaste con `tar -xOf -`)
TONAL_INNER_PATH = (
    "acousticbrainz-lowlevel-features-20220623/"
    "acousticbrainz-lowlevel-features-20220623-tonal.csv"
)
OUTPUT_FILE = "../dataset/grupo_3_final_total.csv"

TONAL_COLUMNS = [
    "mbid",
    "submission_offset",
    "key_key",
    "key_scale",
    "tuning_frequency",
    "tuning_equal_tempered_deviation",
]
COLS_TO_ADD = ["key_key", "key_scale", "tuning_frequency"]

CHUNK_SIZE = 500_000  # filas por chunk al leer el tonal.csv gigante


def main():
    # -----------------------------------------------------------------
    # 1. Mapeo track_id -> mbid
    # -----------------------------------------------------------------
    print("Cargando mapeo MSD -> MusicBrainz...")
    mapping = pd.read_csv(
        MAPPING_FILE,
        header=None,
        names=["track_id", "mbid", "title_map", "artist_map"],
        usecols=["track_id", "mbid"],
        dtype=str,
    )
    mapping = mapping.drop_duplicates(subset="track_id")
    print(f"  -> {len(mapping):,} track_id con mbid mapeado")

    # -----------------------------------------------------------------
    # 2. Dataset principal
    # -----------------------------------------------------------------
    print("Cargando grupo_3_final.csv...")
    grupo3 = pd.read_csv(GRUPO3_FILE, dtype=str)
    print(f"  -> {len(grupo3):,} filas")

    grupo3 = grupo3.merge(mapping, on="track_id", how="left")
    n_con_mbid = grupo3["mbid"].notna().sum()
    print(f"  -> {n_con_mbid:,} de {len(grupo3):,} canciones tienen mbid asociado")

    # Set de mbids que realmente necesitamos buscar en el CSV gigante
    target_mbids = set(grupo3["mbid"].dropna().unique())
    print(f"  -> {len(target_mbids):,} mbid únicos a buscar en el dump tonal")

    # -----------------------------------------------------------------
    # 3. Leer el tonal.csv en streaming desde el .tar.zst, filtrando
    # -----------------------------------------------------------------
    print("Extrayendo y filtrando el dump de tonalidad ...")

    cmd = (
        f'zstd -dc "{TONAL_TAR_ZST}" | tar -xOf - "{TONAL_INNER_PATH}"'
    )
    proc = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, bufsize=1024 * 1024
    )

    matched_chunks = []
    rows_read = 0
    try:
        reader = pd.read_csv(
            proc.stdout,
            names=TONAL_COLUMNS,
            header=0,  # la primera línea real del csv es el encabezado
            usecols=["mbid", "submission_offset", "key_key", "key_scale",
                     "tuning_frequency"],
            dtype={"mbid": str, "submission_offset": "Int64"},
            chunksize=CHUNK_SIZE,
        )
        for chunk in reader:
            rows_read += len(chunk)
            filtered = chunk[chunk["mbid"].isin(target_mbids)]
            if not filtered.empty:
                matched_chunks.append(filtered)
            print(f"\r  Filas procesadas: {rows_read:,} | matches acumulados: "
                  f"{sum(len(c) for c in matched_chunks):,}", end="", flush=True)
    finally:
        proc.stdout.close()
        proc.wait()

    print()  # salto de línea final del progreso

    if proc.returncode != 0:
        print("ERROR: el proceso zstd/tar terminó con código de error "
              f"{proc.returncode}. Revisa la ruta TONAL_TAR_ZST / TONAL_INNER_PATH.",
              file=sys.stderr)
        sys.exit(1)

    if not matched_chunks:
        print("No se encontró ningún match de mbid en el dump tonal. "
              "Revisa que TONAL_INNER_PATH sea correcto.", file=sys.stderr)
        sys.exit(1)

    tonal_matched = pd.concat(matched_chunks, ignore_index=True)
    print(f"Total de filas de tonalidad encontradas: {len(tonal_matched):,}")

    # -----------------------------------------------------------------
    # 4. Resolver duplicados: preferir submission_offset == 0
    # -----------------------------------------------------------------
    tonal_matched = tonal_matched.sort_values(
        by="submission_offset", ascending=True
    )
    tonal_dedup = tonal_matched.drop_duplicates(subset="mbid", keep="first")
    print(f"  -> {len(tonal_dedup):,} mbid únicos tras deduplicar")

    # -----------------------------------------------------------------
    # 5. Merge final y export
    # -----------------------------------------------------------------
    final = grupo3.merge(
        tonal_dedup[["mbid"] + COLS_TO_ADD], on="mbid", how="left"
    )

    n_enriquecidas = final["key_key"].notna().sum()
    print(f"Canciones enriquecidas con tonalidad: {n_enriquecidas:,} de "
          f"{len(final):,}")

    final.to_csv(OUTPUT_FILE, index=False)
    print(f"Listo. Archivo generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()