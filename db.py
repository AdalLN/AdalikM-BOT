# DB.PY
import os
import aiosqlite
import hashlib
from datetime import datetime, timezone
from typing import Optional, List
from config import DB_PATH, STORAGE_DIR

# Asegura que exista la carpeta física de almacenamiento
os.makedirs(STORAGE_DIR, exist_ok=True)
# =========================================================


# UTILIDADES GENERALES
def sha256(data: bytes) -> str:
    """Calcula el hash SHA-256 de un bloque de bytes."""
    return hashlib.sha256(data).hexdigest()


def path_for(filename: str) -> str:
    """Construye la ruta absoluta de un archivo dentro del storage."""
    return os.path.join(STORAGE_DIR, filename)


# =========================================================

# ESQUEMAS DE TABLAS
CREATE_FILES = """
CREATE TABLE IF NOT EXISTS files(
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  key_hash     TEXT UNIQUE,
  filename     TEXT,
  content      BLOB,
  uploader_id  INTEGER,
  used         INTEGER DEFAULT 0,
  created_at   TEXT,
  file_sha     TEXT,
  expires_at   TEXT,
  used_by      INTEGER,
  used_at      TEXT
);
"""

CREATE_CCS = """
CREATE TABLE IF NOT EXISTS ccs(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  bin       TEXT UNIQUE,
  name       TEXT,
  type       TEXT,
  quantity   INTEGER DEFAULT 800,
  active     INTEGER DEFAULT 1,
  created_at TEXT,
  updated_at TEXT
);
"""
# =========================================================


# INICIALIZACIÓN DE BASE DE DATOS
async def init_db():
    """
    Inicializa las tablas principales del sistema:
    - files
    - ccs
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_FILES)
        await db.execute(CREATE_CCS)
        await db.commit()


# =========================================================


# OPERACIONES SOBRE ARCHIVOS
async def file_exists_by_hash(file_sha: str) -> bool:
    """Verifica si ya existe un archivo con el mismo hash."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM files WHERE file_sha = ? LIMIT 1",
            (file_sha,),
        )
        return (await cur.fetchone()) is not None


async def insert_file(
    key_hash: str,
    stored_name: str,
    data: bytes,
    uploader_id: int,
    created_at_iso: str,
    file_sha: str,
    expires_at_iso: Optional[str],
):
    """Inserta un nuevo archivo en la tabla files."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO files(
                key_hash,
                filename,
                content,
                uploader_id,
                used,
                created_at,
                file_sha,
                expires_at
            )
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                key_hash,
                stored_name,
                data,
                uploader_id,
                created_at_iso,
                file_sha,
                expires_at_iso,
            ),
        )
        await db.commit()


async def get_file_by_keyhash(key_hash: str) -> Optional[aiosqlite.Row]:
    """Obtiene un archivo por el hash de su clave."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, filename, content, used, expires_at, uploader_id
            FROM files
            WHERE key_hash = ?
            """,
            (key_hash,),
        )
        return await cur.fetchone()


async def mark_used(fid: int, used_by: int):
    """Marca un archivo como usado e informa quién lo consumió."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE files
            SET used = 1,
                used_by = ?,
                used_at = ?
            WHERE id = ? AND used = 0
            """,
            (used_by, datetime.now(timezone.utc).isoformat(), fid),
        )
        await db.commit()


async def purge_expired_and_used():
    """
    Limpia registros y archivos físicos que ya no sirven:
    - usados
    - expirados
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    to_delete: List[int] = []

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, filename FROM files
            WHERE used = 1
               OR (expires_at IS NOT NULL AND expires_at < ?)
            """,
            (now_iso,),
        )
        rows = await cur.fetchall()

        for fid, fname in rows:
            try:
                fpath = path_for(os.path.basename(fname))
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

            to_delete.append(fid)

        if to_delete:
            q = f"DELETE FROM files WHERE id IN ({','.join('?' * len(to_delete))})"
            await db.execute(q, to_delete)
            await db.commit()


# =========================================================


# OPERACIONES SOBRE cc (INVENTARIO GENÉRICO)
async def insert_cc(
    bin: str,
    name: str,
    type_: str,
    quantity: int = 800,
    active: int = 1,
):
    """
    Inserta un cc nuevo en el inventario.
    Si no se especifica quantity, usa 800 por default.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO ccs(bin, name, type, quantity, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (bin, name, type_, quantity, active, now_iso, now_iso),
        )
        await db.commit()


async def upsert_cc(
    bin: str,
    name: str,
    type_: str,
    quantity: int = 800,
    active: int = 1,
):
    """
    Inserta un cc si no existe.
    Si ya existe, actualiza nombre, tipo, cantidad, estado y updated_at.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO ccs(bin, name, type, quantity, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bin) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                quantity = excluded.quantity,
                active = excluded.active,
                updated_at = excluded.updated_at
            """,
            (bin, name, type_, quantity, active, now_iso, now_iso),
        )
        await db.commit()


async def get_cc_by_bin(bin: str) -> Optional[aiosqlite.Row]:
    """Busca un cc por su bin."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT bin, name, type, quantity, active FROM ccs WHERE bin = ?",
            (bin,),
        )
        return await cur.fetchall()


async def get_cc_by_name(name: str):
    """Busca coincidencias por nombre aunque la BD tenga nombres largos o sucios."""

    search = name.strip().split()[0]  # toma la primera palabra del usuario

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT bin, name, type, quantity, active
            FROM ccs
            WHERE UPPER(name) LIKE UPPER(?)
            ORDER BY active DESC, name ASC
            """,
            (f"%{search}%",),
        )
        return await cur.fetchall()


async def list_ccs() -> List[aiosqlite.Row]:
    """Devuelve todos los ccs ordenados por bin."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, bin, name, type, quantity, active, created_at, updated_at
            FROM ccs
            ORDER BY 
                active DESC,
                CASE 
                    WHEN type = 'CREDITO' THEN 1
                    WHEN type = 'DEBITO' THEN 2
                    WHEN type = 'CREDITO_VIP' THEN 3
                    WHEN type = 'DEBITO_VIP' THEN 4
                    ELSE 5
                END;"""
        )
        return await cur.fetchall()


async def update_cc_quantity(bin: str, quantity: int) -> int:
    """
    Actualiza la cantidad de un cc por su bin.
    Retorna el número de filas afectadas.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE ccs
            SET quantity = ?, updated_at = ?
            WHERE bin = ?
            """,
            (quantity, now_iso, bin),
        )
        await db.commit()
        return cur.rowcount


async def update_cc_active(bin: str, active: int) -> int:
    """
    Actualiza el estado activo/inactivo de un cc.
    Retorna el número de filas afectadas.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE ccs
            SET active = ?, updated_at = ?
            WHERE bin = ?
            """,
            (active, now_iso, bin),
        )
        await db.commit()
        return cur.rowcount


async def delete_cc_by_bin(bin: str) -> int:
    """
    Elimina un cc por su bin.
    Retorna el número de filas eliminadas.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM ccs WHERE bin = ?",
            (bin,),
        )
        await db.commit()
        return cur.rowcount
