
import csv
import os
import time
import requests
import pandas as pd

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# -----------------------------------
# Configuración
# -----------------------------------

INPUT_PATH = "artists_catalog.csv"
OUTPUT_PATH = "artist_texts.csv"

LIMIT = 50
DELAY = 2
MAX_RETRIES = 5

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": (
        "SemanticWebMusicProject/1.0 "
        "(academic research; contact: TU_CORREO@uniandes.edu.co)"
    )
}

FIELDS = [
    "artist_mbid",
    "artist_name",
    "page_title",
    "source_url",
    "text",
    "status",
]

session = requests.Session()
session.headers.update(HEADERS)


class RateLimitExceeded(Exception):
    pass


def wait_before_retry(response, attempt):

    retry_after = response.headers.get("Retry-After")

    if retry_after:
        try:
            seconds = float(retry_after)
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(retry_after)
                seconds = (
                    retry_date - datetime.now(timezone.utc)
                ).total_seconds()
            except (ValueError, TypeError):
                seconds = 30 * (2 ** attempt)
    else:
        seconds = 30 * (2 ** attempt)

    seconds = max(1, min(seconds, 300))

    print(f"    Esperando {seconds:.0f} segundos...")
    time.sleep(seconds)


def request_json(params):

    params = {
        **params,
        "format": "json",
        "maxlag": 5,
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=30,
            )

            if response.status_code in (429, 503):
                if attempt == MAX_RETRIES - 1:
                    raise RateLimitExceeded(
                        f"Wikipedia sigue limitando solicitudes "
                        f"(HTTP {response.status_code})."
                    )

                wait_before_retry(response, attempt)
                continue

            response.raise_for_status()
            data = response.json()

            # Wikipedia puede comunicar maxlag dentro del JSON.
            if "error" in data:
                error = data["error"]

                if error.get("code") == "maxlag":
                    if attempt == MAX_RETRIES - 1:
                        raise RateLimitExceeded(
                            "Wikipedia sigue reportando maxlag."
                        )

                    time.sleep(30 * (2 ** attempt))
                    continue

                raise RuntimeError(
                    f"Error de Wikipedia: {error}"
                )

            time.sleep(DELAY)
            return data

        except requests.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise

            time.sleep(10 * (2 ** attempt))

    raise RuntimeError("No se pudo completar la solicitud.")


def search_wikipedia(artist_name):
    """Busca una página candidata para el artista."""

    data = request_json({
        "action": "query",
        "list": "search",
        "srsearch": artist_name,
        "srlimit": 5,
    })

    results = data.get("query", {}).get("search", [])

    if not results:
        return None

    # Es un candidato, no una identificación confirmada.
    return results[0]["title"]


def get_page_extract(page_title):

    data = request_json({
        "action": "query",
        "prop": "extracts|info",
        "explaintext": 1,
        "exintro": 1,
        "inprop": "url",
        "titles": page_title,
        "redirects": 1,
    })

    pages = data.get("query", {}).get("pages", {})

    for page in pages.values():
        if "missing" in page:
            continue

        return (
            page.get("fullurl", ""),
            page.get("extract", ""),
        )

    return None, None


def load_completed():

    if not os.path.exists(OUTPUT_PATH):
        return {}, set()

    with open(OUTPUT_PATH, newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    completed = {}
    for row in rows:
        if row.get("status") in (
            "ok",
            "not_found",
            "empty_extract",
        ):
            completed[row["artist_mbid"]] = row

    # Reescribe el archivo solo con resultados terminados,
    # descartando errores temporales que se volverán a intentar.
    with open(
        OUTPUT_PATH, "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(completed.values())

    return completed, set(completed)


def main():
    artists = pd.read_csv(INPUT_PATH).head(LIMIT)

    completed_rows, completed_ids = load_completed()

    print("Artistas ya procesados:", len(completed_ids))

    with open(
        OUTPUT_PATH, "a", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)

        for position, (_, artist) in enumerate(
            artists.iterrows(), start=1
        ):
            artist_id = str(artist["artist_mbid"])

            if artist_id in completed_ids:
                continue

            artist_name = str(artist["artist_name"]).strip()

            row = {
                "artist_mbid": artist_id,
                "artist_name": artist_name,
                "page_title": "",
                "source_url": "",
                "text": "",
                "status": "",
            }

            try:
                title = search_wikipedia(artist_name)

                if not title:
                    row["status"] = "not_found"
                else:
                    url, text = get_page_extract(title)

                    row.update({
                        "page_title": title,
                        "source_url": url or "",
                        "text": text or "",
                        "status": (
                            "ok" if text and text.strip()
                            else "empty_extract"
                        ),
                    })

            except RateLimitExceeded as error:
                print(f"\nProceso detenido: {error}")
                print("El progreso anterior está guardado.")
                break

            except (
                requests.RequestException,
                RuntimeError,
            ) as error:
                row["status"] = f"request_error: {error}"

            writer.writerow(row)
            file.flush()

            print(
                f"[{position}/{len(artists)}] "
                f"{artist_name} -> {row['status']}"
            )

    print(f"\nResultados guardados en {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
