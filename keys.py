# KEYS.PY
# IMPORTS ESTÁNDAR DE PYTHON
import os
import hashlib
import secrets
import re
from datetime import datetime, timezone
from typing import Optional

# =========================================================


# LÓGICA DE CLAVES
# Estas funciones generan, procesan y normalizan las claves
# del sistema.
def gen_single_use_key() -> str:
    """
    Genera una clave única de un solo uso.

    Estructura:
    - Prefijo de 6 dígitos
    - Variante numérica pequeña (1..3)
    - Sufijo hexadecimal largo (64 caracteres)

    Ejemplo:
        547146-1_d1ba88be95ad625f...

    Esta estructura hace que la clave:
    - sea difícil de adivinar
    - se vea identificable para el usuario
    - tenga suficiente entropía para seguridad
    """
    prefix = f"{secrets.randbelow(900000)+100000}"  # número de 6 dígitos
    variant = str(secrets.randbelow(3) + 1)  # variante 1, 2 o 3
    suffix = secrets.token_hex(32)  # 64 caracteres hexadecimales
    return f"{prefix}-{variant}_{suffix}"


def key_to_hash(key: str) -> str:
    """
    Convierte una clave en un hash SHA-256.

    Esto se usa para NO guardar la clave real en base de datos,
    sino una versión hasheada, mejorando seguridad.

    Entrada:
        "123456-1_abcd..."
    Salida:
        "f4e9d3c2..."
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def normalize_key(text: str) -> Optional[str]:
    """
    Limpia y trata de extraer una clave válida desde un texto.

    Esto permite soportar entradas como:
    - /get 123456-1_abcd...
    - texto con saltos de línea
    - texto con espacios extra
    - claves pegadas junto con otras palabras

    Retorna:
    - la clave encontrada si el patrón coincide
    - None si no puede reconocer ninguna clave válida
    """
    text = (text or "").replace("\n", " ").strip()

    # Patrón principal esperado:
    # 6 dígitos - variante _ string alfanumérico largo
    m = re.search(r"(\d{6}-[0-9]+_[A-Za-z0-9]{20,})", text)
    if m:
        return m.group(1)

    # Fallback más genérico por si el texto viene alterado
    m = re.search(r"([A-Za-z0-9_-]{20,})", text)
    return m.group(1) if m else None


# =========================================================


# MENSAJES / RESPUESTAS DEL SISTEMA DE CLAVES
# Estas funciones solo construyen texto.
# bot.py decide cuándo enviarlas.
def msg_key_created(key: str, expiry_hours: int) -> str:
    """
    Mensaje que se envía cuando se genera correctamente una nueva clave.
    """
    return (
        f"Clave de descarga:\n"
        f"Usa /get {key}\n"
        f"Clave de un solo uso, expira en {expiry_hours}h."
    )


def msg_key_invalid() -> str:
    """
    Mensaje para clave inválida o ya inutilizable.
    """
    return "Clave inválida o ya utilizada."


def msg_key_not_found() -> str:
    """
    Mensaje para cuando la clave no existe en base de datos.
    """
    return "No existe esa clave."


def msg_key_unrecognized() -> str:
    """
    Mensaje para cuando el texto recibido no contiene
    una clave con formato reconocible.
    """
    return "No pude reconocer la clave."


def msg_key_expired(expiry_hours: int) -> str:
    """
    Mensaje para clave vencida.
    """
    return f"Clave expirada ({expiry_hours}h). Pide una nueva."


def msg_key_used() -> str:
    """
    Mensaje para indicar que la clave ya fue consumida.
    """
    return "Esa clave ya fue utilizada."


def msg_key_still_valid_no_exp() -> str:
    """
    Mensaje de status cuando la clave sigue válida
    y no tiene expiración configurada.
    """
    return "Sigue vigente (sin expiración configurada)."


def msg_status_usage() -> str:
    """
    Texto de ayuda para usar correctamente /status.
    """
    return "Uso: /status <clave>"


def msg_get_usage() -> str:
    """
    Texto de ayuda para usar correctamente /get.
    """
    return "Uso: /get <clave>"


def msg_status_result(filename: str, expires_at: str) -> str:
    """
    Construye el mensaje de estado para una clave vigente.

    Parámetros:
    - filename: nombre del archivo asociado a la clave
    - expires_at: fecha/hora ISO de expiración

    Calcula:
    - horas restantes
    - minutos restantes

    Devuelve un texto amigable para el comando /status.
    """
    exp_dt = datetime.fromisoformat(expires_at)
    remaining = exp_dt - datetime.now(timezone.utc)

    hrs = int(remaining.total_seconds() // 3600)
    mins = int((remaining.total_seconds() % 3600) // 60)

    return (
        f"Vigencia del archivo *{os.path.basename(filename)}*. "
        f"Tiempo restante: {hrs}h {mins}m."
    )


def msg_file_missing_content() -> str:
    """
    Mensaje para cuando no se encuentra el contenido del archivo,
    ni en disco ni en el BLOB de la base de datos.
    """
    return "No se encontró el contenido del archivo."


def msg_send_failed() -> str:
    """
    Mensaje genérico para errores al enviar el archivo al usuario.
    """
    return "No se pudo enviar el archivo. Intenta de nuevo."
