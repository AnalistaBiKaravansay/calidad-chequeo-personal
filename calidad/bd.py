"""Conexión a la base: PostgreSQL (Neon) si hay dirección configurada, si no SQLite local.

El resto del código escribe SQL con '?' como en SQLite; aquí se traduce para PostgreSQL. Las filas se leen igual
en los dos casos: fila["columna"], fila[0] y dict(fila).
"""
import sqlite3


class Fila(dict):
    """Fila de PostgreSQL que también se puede leer por posición, como sqlite3.Row."""

    def __init__(self, nombres, valores):
        super().__init__(zip(nombres, valores))
        self._valores = valores

    def __getitem__(self, llave):
        return self._valores[llave] if isinstance(llave, int) else super().__getitem__(llave)


def _fabrica_filas(cursor):
    nombres = [c.name for c in cursor.description] if cursor.description else []
    return lambda valores: Fila(nombres, valores)


class Conexion:
    """Envoltura mínima. `with con:` confirma los cambios al salir (o los deshace si hubo error) sin cerrar."""

    def __init__(self, cruda, postgres):
        self.cruda = cruda
        self.postgres = postgres

    def _sql(self, sql):
        # En psycopg el % es especial y los parámetros van con %s.
        return sql.replace("%", "%%").replace("?", "%s") if self.postgres else sql

    def execute(self, sql, args=()):
        if self.postgres:
            cursor = self.cruda.cursor(row_factory=_fabrica_filas)
            cursor.execute(self._sql(sql), tuple(args))
            return cursor
        return self.cruda.execute(sql, tuple(args))

    def executemany(self, sql, filas):
        if self.postgres:
            with self.cruda.cursor() as cursor:
                cursor.executemany(self._sql(sql), filas)
        else:
            self.cruda.executemany(sql, filas)

    def script(self, sql):
        if self.postgres:
            self.cruda.execute(sql)
            self.cruda.commit()
        else:
            self.cruda.executescript(sql)

    def commit(self):
        self.cruda.commit()

    def close(self):
        self.cruda.close()

    def __enter__(self):
        return self

    def __exit__(self, tipo, *_):
        if tipo is None:
            self.cruda.commit()
        else:
            self.cruda.rollback()
        return False


def abrir(url="", archivo_sqlite=None):
    if url:
        import psycopg
        return Conexion(psycopg.connect(url, connect_timeout=20), postgres=True)
    cruda = sqlite3.connect(archivo_sqlite)
    cruda.row_factory = sqlite3.Row
    return Conexion(cruda, postgres=False)
