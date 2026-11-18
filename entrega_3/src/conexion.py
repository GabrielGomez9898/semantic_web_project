"""Conexión a Neo4j (AuraDB) con credenciales desde entrega_3/.env y reintentos ante cortes de conexión."""
import logging
import os
import time
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, ServiceUnavailable, SessionExpired

logging.getLogger('neo4j').setLevel(logging.CRITICAL)

RAIZ = Path(__file__).resolve().parents[1]          # entrega_3/


def cargar_env(ruta=None):
    candidatos = [Path(ruta)] if ruta else [RAIZ / '.env', Path('.env'), Path('../.env')]
    archivo = next((p for p in candidatos if p.exists()), None)
    if archivo is None:
        raise FileNotFoundError('No se encontró entrega_3/.env. Cópialo desde .env.example y completa las credenciales.')
    for linea in archivo.read_text(encoding='utf-8').splitlines():
        if '=' in linea and not linea.lstrip().startswith('#'):
            k, v = linea.split('=', 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


class Neo4jConReintentos:
    def __init__(self, intentos=15, espera=5, log=print):
        cargar_env()
        self.uri, self.user, self.password = (os.environ[k] for k in ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD'))
        self.database = os.environ.get('NEO4J_DATABASE') or None
        self.intentos, self.espera, self.log = intentos, espera, log
        self.driver = self._conectar()

    def _conectar(self):
        for i in range(1, self.intentos + 1):
            d = GraphDatabase.driver(self.uri, auth=(self.user, self.password), connection_timeout=15,
                                     max_transaction_retry_time=120, notifications_min_severity='OFF')
            try:
                d.verify_connectivity()
                return d
            except (ServiceUnavailable, SessionExpired) as e:
                d.close()
                if i == self.intentos:
                    raise
                self.log(f'Neo4j no disponible ({type(e).__name__}); reintento {i}/{self.intentos - 1} en {self.espera}s...')
                time.sleep(self.espera)

    def run_cypher(self, query, **parameters):
        for i in range(1, self.intentos + 1):
            try:
                with self.driver.session(database=self.database) as s:
                    return [dict(r) for r in s.run(query, **parameters)]
            except (ServiceUnavailable, SessionExpired, DriverError) as e:
                if i == self.intentos:
                    raise
                self.log(f'Conexión perdida ({type(e).__name__}); reconectando {i}/{self.intentos - 1}...')
                time.sleep(self.espera)
                try:
                    self.driver.close()
                except Exception:
                    pass
                self.driver = self._conectar()

    def close(self):
        self.driver.close()
