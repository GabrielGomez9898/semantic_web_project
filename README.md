# Semantic Web Project

### Entrega 1
# Fuentes de enriquecimiento
- MusicBrainz: Fuente para obtener información adicional de los artistas: https://ftp.musicbrainz.org/pub/musicbrainz/data/json-dumps/20260829-001001/
- Lastfm: Fuente para obtener información adicional de las canciones: http://millionsongdataset.com/lastfm/#getting
- AcousticBrainz: https://data.metabrainz.org/pub/musicbrainz/acousticbrainz/dumps/acousticbrainz-lowlevel-features-20220623/

### Ejecución de python Scripts para enriquecimiento de datasets
# 1.Activar virtual environment
-  source .venv/bin/activate

# 2.Instalar dependencias
- pip install -r requirements.txt

# 3. MusicBrainz
- Es necesario descargar el archivo comprimido "artist.tar.xz" de https://ftp.musicbrainz.org/pub/musicbrainz/data/json-dumps/20260902-001001/
- ejecutar el comando: python enrich_musicbrainz.py

# 4. Last.fm
- Es necesario descargar el archivo comprimido "lastfm_subset.zip" de http://millionsongdataset.com/lastfm/#getting
- ejecutar el comando: python enrich_lastfm.py

# 5. AcousticBrainz
- Es necesario descargar el archivo comprimido "acousticbrainz-lowlevel-features-20220623-tonal.tar.zst" de https://data.metabrainz.org/pub/musicbrainz/acousticbrainz/dumps/acousticbrainz-lowlevel-features-20220623/
- ejecutar el comando: python enrich_acousticbrainz.py

🚀 Una vez termine de ejecutar los tres scripts, podrá visualizar el resultado final en el archivo "grupo_3_final_total.csv".

