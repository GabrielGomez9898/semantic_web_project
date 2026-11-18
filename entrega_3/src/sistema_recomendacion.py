"""Sistema de recomendación (punto 5): une los puntos 2, 3 y 4 detrás de una sola llamada.

    sistema = SistemaRecomendacion()                       # conecta a Neo4j y prepara grafo + ranking
    r = sistema.recomendar(artistas=['Bukka White'], k=10)  # Top-K con explicación de cada recomendación

Nada está precalculado. Cada llamada ejecuta Personalized PageRank sobre el grafo (punto 3), aplica el ranking con las
preferencias de usuarios (punto 4) y busca en el índice vectorial (punto 2) el fragmento de reseña que mejor respalda
cada recomendación.
"""
import re
from collections import Counter

import numpy as np

from conexion import Neo4jConReintentos
from ranking import Ranking
from recomendador_grafo import GrafoRecomendador

# Cómo se nombra cada relación del grafo en la explicación
REL_TEXTO = {'SIMILAR_TO': 'suena parecido a', 'SUNG_BY': 'artista', 'APPEARS_ON': 'álbum', 'RELEASED_BY': 'artista del álbum',
             'HAS_TAG': 'etiqueta', 'REVIEWED': 'reseña', 'ORIGIN': 'país de origen', 'ASSOCIATED_WITH_GENRE': 'género',
             'INFLUENCED_BY_GENRE': 'influencia', 'PLAYS_INSTRUMENT': 'instrumento', 'PRODUCED_BY': 'productor',
             'COLLABORATED_WITH': 'colaboración'}


def _lista(valor):
    if not valor:
        return []
    if isinstance(valor, str):
        return [x.strip() for x in re.split(r'[,;\n]', valor) if x.strip()]
    return [x for x in valor if x]


def _recortar(texto, n=260):
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto if len(texto) <= n else texto[:n].rsplit(' ', 1)[0] + '…'


class SistemaRecomendacion:
    def __init__(self, run_cypher=None, log=print):
        self.log = log
        if run_cypher is None:
            self.neo = Neo4jConReintentos(log=log)
            run_cypher = self.neo.run_cypher
        self.run_cypher = run_cypher
        log('Proyectando el grafo desde Neo4j y detectando comunidades (punto 3)...')
        self.gr = GrafoRecomendador(run_cypher)
        log('Cargando reseñas, embeddings y valoraciones (puntos 2 y 4)...')
        self.ranking = Ranking(self.gr, run_cypher)
        self.etiqueta_escena = self.gr.etiquetas_comunidades()
        n_res = Counter(f['usuario'] for f in self.ranking.resenas.values())
        self.usuarios = sorted(((f'{self.gr.nombre[u]} · {n} reseña{"s" * (n > 1)}', u) for u, n in n_res.items()),
                               key=lambda x: x[0].casefold())
        n_tag = Counter(f['o'] for f in self.gr.datos['HAS_TAG'])
        self.tags = sorted({self.gr.nombre[t] for t in n_tag} |
                           {self.gr.nombre[n] for n, t in self.gr.tipo.items() if t == 'Genre'}, key=str.casefold)
        log(f'Listo: {self.gr.ctx["G"].number_of_nodes():,} nodos, {len(self.gr.ctx["comms"])} escenas, '
            f'{len(self.ranking.resenas):,} reseñas.')

    # ------------------------------------------------------------------ preferencia
    def interpretar(self, canciones=(), artistas=(), tags=(), usuario=None, texto=None):
        """Convierte la preferencia en semillas del grafo e informa qué se entendió y qué no se encontró."""
        semillas, entendido, no_encontrado, desde_texto = Counter(), [], [], set()
        for valor, tipos, clase in [(c, ['Track'], 'canción') for c in _lista(canciones)] + \
                                   [(a, ['Artist'], 'artista') for a in _lista(artistas)] + \
                                   [(t, ['Tag', 'Genre'], 'etiqueta') for t in _lista(tags)]:
            try:
                n = self.gr.track_uri[valor] if re.fullmatch(r'TR[A-Z0-9]{16}', valor) else self.gr.buscar(valor, tipos)
                semillas[n] += 1.0
                entendido.append((valor, self.gr.etiqueta(n)))
            except (ValueError, KeyError):
                no_encontrado.append(f'{clase} «{valor}»')
        if usuario:
            n = usuario if usuario in self.gr.tipo else None
            if n is None:
                try:
                    n = self.gr.buscar(usuario, ['User'])
                except ValueError:
                    no_encontrado.append(f'usuario «{usuario}»')
            if n:
                semillas[n] += 1.0
                entendido.append(('usuario', self.gr.etiqueta(n)))
        if texto and texto.strip():
            relacionadas = self.gr.semillas_desde_texto(texto.strip())
            for n, w in relacionadas.items():
                semillas[n] += w
                desde_texto.add(n)
            top = sorted(relacionadas, key=lambda n: -relacionadas[n])[:3]
            entendido.append((f'«{_recortar(texto, 60)}»', 'reseñas parecidas sobre ' + ', '.join(self.gr.etiqueta(n) for n in top)))
        return dict(semillas), entendido, no_encontrado, desde_texto

    # ------------------------------------------------------------------ recomendación
    def recomendar(self, canciones=(), artistas=(), tags=(), usuario=None, texto=None, k=10, misma_escena=False):
        semillas, entendido, no_encontrado, desde_texto = self.interpretar(canciones, artistas, tags, usuario, texto)
        if not semillas:
            return {'error': 'No reconocí ninguna preferencia. ' +
                             (f'No encontré: {", ".join(no_encontrado)}.' if no_encontrado else 'Escribe al menos una.'),
                    'entendido': entendido, 'no_encontrado': no_encontrado, 'items': []}
        n_cand = int(self.ranking.cfg['n_candidatos'])
        escena = self.gr.escena(semillas)
        cands = self.gr.candidatos(semillas, n_cand if not misma_escena else 20 * n_cand)
        if misma_escena and escena:                            # Louvain selecciona la escena, el ranking ordena
            tope = max(escena.values())
            permitidas = {c for c, w in escena.items() if w >= 0.25 * tope}
            cands = [(t, s) for t, s in cands if self.gr.ctx['com'].get(self.gr.artista_de[t]) in permitidas][:n_cand]
        if not cands:
            return {'error': 'No encontré canciones conectadas con esa preferencia en el grafo.',
                    'entendido': entendido, 'no_encontrado': no_encontrado, 'items': []}
        usuario_sem = next((n for n in semillas if self.gr.tipo.get(n) == 'User'), None)
        items, extra = self.ranking.top_k(semillas, cands, k, usuario=usuario_sem, texto=texto)
        fragmentos = self._fragmentos(items, extra['perfil'], usuario_sem)
        principal = escena.most_common(1)[0][0] if escena else None
        total = sum(escena.values()) or 1
        for it in items:
            t = it['uri']
            it['cancion'], it['artista'] = self.gr.nombre[t], self.gr.nombre[self.gr.artista_de[t]]
            com = self.gr.ctx['com'].get(self.gr.artista_de[t])
            it['escena'] = self.etiqueta_escena.get(com) if com is not None else None
            it['misma_escena'] = com is not None and com == principal
            pasos = self.gr.camino(semillas, t)
            it['camino'] = self._camino_texto(pasos)
            it['explicacion'] = self._explicacion(it, pasos, desde_texto, extra['perfil'] is not None)
            it['fragmento'] = fragmentos.get(t)
        return {'entendido': entendido, 'no_encontrado': no_encontrado, 'items': items,
                'escena': [(self.etiqueta_escena.get(c, str(c)), w / total) for c, w in escena.most_common(3)],
                'perfil_textual': extra['perfil'] is not None, 'pesos': self.ranking.pesos, 'n_candidatos': len(cands)}

    # ------------------------------------------------------------------ explicación
    def _camino_texto(self, pasos):
        if not pasos:
            return ''
        partes = [self.gr.etiqueta(pasos[0][0])]
        for n, rel in pasos[1:]:
            partes.append(f'→ [{REL_TEXTO.get(rel, rel)}] → {self.gr.etiqueta(n)}')
        return ' '.join(partes)

    def _motivo_principal(self, pasos, desde_texto):
        if not pasos:
            return 'Está relacionada con tu preferencia en el grafo.'
        semilla, rels = pasos[0][0], [r for _, r in pasos[1:]]
        et, tipo = self.gr.etiqueta(semilla), self.gr.tipo.get(semilla)
        sufijo = ', que coincide con lo que describiste' if semilla in desde_texto else ''
        if tipo == 'User' and len(pasos) > 2:
            resenado = pasos[1][0]
            resto = rels[1:]
            if len(resto) >= 3 and resto[:2] == ['REVIEWED', 'REVIEWED']:
                otro, suyo = pasos[2][0], pasos[3][0]
                return (f'A {self.gr.nombre[otro]}, que también reseñó {self.gr.etiqueta(resenado)}, '
                        f'le interesó {self.gr.etiqueta(suyo)}, de donde viene esta canción.')
            if resto == ['SIMILAR_TO']:
                return f'Reseñaste {self.gr.etiqueta(resenado)} y esta canción suena parecido.'
            if resto in (['SUNG_BY', 'SUNG_BY'], ['RELEASED_BY', 'SUNG_BY'], ['SUNG_BY']):
                return f'Reseñaste {self.gr.etiqueta(resenado)} y esta canción es del mismo artista.'
            return f'Reseñaste {self.gr.etiqueta(resenado)}, que se conecta con esta canción en el grafo.'
        if rels == ['SIMILAR_TO']:
            return f'Suena parecido a {et}{sufijo}.'
        if rels == ['SUNG_BY'] and tipo == 'Artist':
            return f'Es una canción de {et}{sufijo}.'
        if rels in (['SUNG_BY', 'SUNG_BY'], ['RELEASED_BY', 'SUNG_BY']):
            return f'Es del mismo artista que {et}{sufijo}.'
        if rels == ['HAS_TAG']:
            return f'Tiene la etiqueta {et}.'
        if rels == ['APPEARS_ON'] and tipo == 'Album':
            return f'Está en el {et}{sufijo}.'
        if rels in (['RELEASED_BY', 'SUNG_BY'],) and tipo == 'Album':
            return f'Es del artista del {et}{sufijo}.'
        if 'SIMILAR_TO' in rels and len(rels) <= 3:
            return f'Está a pocos pasos de {et}{sufijo} por canciones que suenan parecido.'
        return f'Está conectada en el grafo con {et}{sufijo} ({len(rels)} paso{"s" * (len(rels) > 1)}).'

    def _explicacion(self, it, pasos, desde_texto, hay_perfil):
        detalles = []
        if it['escena']:
            detalles.append(f'Escena musical «{it["escena"]}»' +
                            (' — la misma de tu preferencia.' if it['misma_escena'] else ' — amplía un poco tu preferencia.'))
        if it['reseñas']:
            origen = ('con estrellas' if it['explícitas'] == it['reseñas'] else
                      'estimada a partir del texto' if it['explícitas'] == 0 else f'{it["explícitas"]} con estrellas')
            detalles.append(f'Valoración de usuarios de CritiqueBrainz: {it["estrellas"]:.1f}★ '
                            f'({it["reseñas"]} reseña{"s" * (it["reseñas"] > 1)}, {origen}).')
        if hay_perfil and it['afinidad'] is not None and it['senales']['A'] >= 0.6:
            detalles.append('Sus reseñas hablan de lo mismo que tu preferencia (alta afinidad textual).')
        subida = it['puesto_grafo'] - it['rank']
        if subida >= 5:
            detalles.append(f'Subió {subida} puestos frente al orden del grafo gracias a las opiniones de usuarios.')
        return {'motivo': self._motivo_principal(pasos, desde_texto), 'detalles': detalles}

    def _fragmentos(self, items, perfil, usuario):
        """Fragmento de reseña (índice vectorial del punto 2) que mejor respalda cada canción recomendada."""
        propias = self.ranking.resenas_usuario[usuario] if usuario else set()
        por_cancion = {it['uri']: self.ranking.resenas_cancion.get(it['uri'], set()) - propias for it in items}
        uris = sorted(set().union(*por_cancion.values())) if por_cancion else []
        if not uris:
            return {}
        filas = self.run_cypher('''
            MATCH (c:Chunk)-[:PART_OF]->(r:Review)-[:WRITTEN_BY]->(u:User) WHERE r.uri IN $uris
            RETURN r.uri AS review, r.url AS url, u.name AS autor, c.text AS texto, c.context AS contexto,
                   c.order AS orden, c.embedding AS e''', uris=uris)
        salida = {}
        for t, rs in por_cancion.items():
            cand = [f for f in filas if f['review'] in rs]
            if not cand:
                continue
            if perfil is not None:
                mejor = max(cand, key=lambda f: float(np.asarray(f['e'], dtype=np.float32) @ perfil))
            else:
                mejor = min(cand, key=lambda f: f['orden'])
            salida[t] = {'texto': _recortar(mejor['texto']), 'contexto': mejor['contexto'],
                         'autor': mejor['autor'], 'url': mejor['url']}
        return salida
