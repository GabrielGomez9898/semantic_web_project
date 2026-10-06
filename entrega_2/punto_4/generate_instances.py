import csv
from rdflib import Graph, Namespace, Literal, RDF, RDFS, XSD


# ----------------------------------- Namespaces ----------------------------------- #

VOC = Namespace("http://uniandes.edu.co/wsproject2026/vocab/ontology#")
RES = Namespace("http://uniandes.edu.co/wsproject2026/vocab/lit#")

g = Graph()

g.bind("rbo", VOC)
g.bind("res", RES)


# ----------------------------------- Carga del CSV ----------------------------------- #

with open(
    "../../dataset/grupo_3_final_total.csv",
    encoding="utf-8"
) as archivo:

    for fila in csv.DictReader(archivo):

        # ----------------------------------- Track ----------------------------------- #

        track = RES[f"Track_{fila['track_id']}"]

        g.add((
            track,
            RDF.type,
            RES.Track
        ))

        if fila["title"]:
            g.add((
                track,
                VOC.title,
                Literal(fila["title"])
            ))

        if fila["release"]:
            g.add((
                track,
                VOC.released,
                Literal(fila["release"])
            ))

        if fila["year"]:
            g.add((
                track,
                VOC.year,
                Literal(
                    fila["year"],
                    datatype=XSD.gYear
                )
            ))

        if fila["duration"]:
            g.add((
                track,
                VOC.duration,
                Literal(
                    fila["duration"],
                    datatype=XSD.double
                )
            ))

        if fila["lastfm_top_tag"]:
            g.add((
                track,
                VOC.lastfm_top_tag,
                Literal(fila["lastfm_top_tag"])
            ))

        if fila["lastfm_top_tag_score"]:
            g.add((
                track,
                VOC.lastfm_top_tag_score,
                Literal(
                    fila["lastfm_top_tag_score"],
                    datatype=XSD.double
                )
            ))

        if fila["key_key"]:
            g.add((
                track,
                VOC.key,
                Literal(fila["key_key"])
            ))

        if fila["key_scale"]:
            g.add((
                track,
                VOC.keyScale,
                Literal(fila["key_scale"])
            ))

        if fila["tuning_frequency"]:
            g.add((
                track,
                VOC.tuningFrequency,
                Literal(
                    fila["tuning_frequency"],
                    datatype=XSD.double
                )
            ))


        # ----------------------------------- Artist ----------------------------------- #

        if fila["artist_mbid"]:

            artist = RES[f"Artist_{fila['artist_mbid']}"]

            g.add((
                artist,
                RDF.type,
                RES.Artist
            ))

            if fila["artist_name"]:
                g.add((
                    artist,
                    RDFS.label,
                    Literal(
                        fila["artist_name"],
                        lang="en"
                    )
                ))

            if fila["gender"]:
                g.add((
                    artist,
                    VOC.gender,
                    Literal(fila["gender"])
                ))

            if fila["artist_type"]:
                g.add((
                    artist,
                    VOC.artist_type,
                    Literal(fila["artist_type"])
                ))

            # Relación Track -> Artist
            g.add((
                track,
                VOC.sungBy,
                artist
            ))


            # ----------------------------------- Country ----------------------------------- #

            if fila["country"]:

                country = RES[f"Country_{fila['country']}"]

                g.add((
                    country,
                    RDF.type,
                    RES.Country
                ))

                if fila["area"]:
                    g.add((
                        country,
                        VOC.area,
                        Literal(fila["area"])
                    ))

                # Relación Artist -> Country
                g.add((
                    artist,
                    VOC.origin,
                    country
                ))


# ----------------------------------- Verificación ----------------------------------- #

tracks = list(
    g.subjects(
        RDF.type,
        RES.Track
    )
)

artists = list(
    g.subjects(
        RDF.type,
        RES.Artist
    )
)

countries = list(
    g.subjects(
        RDF.type,
        RES.Country
    )
)

print("Número total de tripletas:", len(g))
print("Tracks:", len(tracks))
print("Artists:", len(artists))
print("Countries:", len(countries))


# ----------------------------------- Serialización ----------------------------------- #

g.serialize(
    destination="../../dataset/modelo_conceptual/instances.ttl",
    format="turtle"
)

print("Archivo instances.ttl generado correctamente.")