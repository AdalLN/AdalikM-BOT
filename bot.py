# BOT.PY
# Archivo principal del bot.
# Aquí viven:
# - handlers y comandos de Telegram
# - reglas generales del bot
# - control de rate limit
# - recepción de documentos
# - arranque e inicialización
#
# La lógica especializada se delega a módulos:
# - keys.py  -> claves y mensajes relacionados con claves
# - db.py    -> persistencia y archivos
# - ccs.py   -> módulo de inventario genérico

# IMPORTS ESTÁNDAR DE PYTHON
import os
import asyncio
import time
from io import BytesIO
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# =========================================================

# CONFIGURACIÓN CENTRAL
from config import (
    DB_PATH,
    BOT_TOKEN,
    STORAGE_DIR,
    EXPIRY_HOURS,
    MAX_BYTES,
    MIN_INTERVAL,
    AUTO_PURGE_INTERVAL,
    AUTH_FORWARDERS,
    ALLOWED_UPLOADERS,
)

# =========================================================

# MÓDULO DE CLAVES
from keys import (
    gen_single_use_key,
    key_to_hash,
    normalize_key,
    msg_key_created,
    msg_key_invalid,
    msg_key_not_found,
    msg_key_unrecognized,
    msg_key_expired,
    msg_key_used,
    msg_key_still_valid_no_exp,
    msg_status_usage,
    msg_get_usage,
    msg_status_result,
    msg_file_missing_content,
    msg_send_failed,
)

# =========================================================

# MÓDULO DE BASE DE DATOS / ARCHIVOS
from db import (
    init_db,
    file_exists_by_hash,
    insert_file,
    get_file_by_keyhash,
    mark_used,
    purge_expired_and_used,
    sha256,
    path_for,
)

# =========================================================

# MÓDULO DE INVENTARIO
from ccs import (
    is_inventory_admin,
    addcc_cmd,
    modifycc_cmd,
    deletecc_cmd,
    cancelcc_cmd,
    infocc_cmd,
    infoccbyname_cmd,
    listccs_cmd,
    ccs_text_handler,
)

# =========================================================

# ESTADO EN MEMORIA DEL BOT
# Se usa para controlar el rate limit por usuario.
LAST_HIT = defaultdict(float)
# =========================================================


# UTILIDADES GENERALES DEL BOT
def rate_limit_ok(user_id: int) -> bool:
    """
    Controla cuántas veces puede interactuar un usuario en poco tiempo.
    """
    now = time.time()

    if now - LAST_HIT[user_id] < MIN_INTERVAL:
        return False

    LAST_HIT[user_id] = now
    return True


def is_txt(filename: str, mime: Optional[str]) -> bool:
    """
    Verifica si el archivo recibido parece ser un TXT válido.
    """
    return filename.lower().endswith(".txt") or (mime or "").startswith("text/")


def extract_forwarder_id(update: Update) -> Optional[int]:
    """
    Extrae el ID del usuario que interactúa actualmente.
    Se usa como referencia para validaciones simples.
    """
    try:
        uid = update.effective_user.id
        return uid if uid is not None else None
    except Exception:
        return None


# =========================================================


# COMANDOS BÁSICOS DEL BOT
async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /id
    Devuelve el ID y username del usuario actual.
    """
    if not rate_limit_ok(update.effective_user.id):
        return await update.message.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    try:
        user = update.effective_user
        uid = user.id
        username = f"@{user.username}" if user.username else "(sin username)"
        await update.message.reply_text(f"🆔 Tu ID: {uid}\n👤 Usuario: {username}")
    except Exception:
        await update.message.reply_text("Error al obtener tu ID.")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start
    Muestra la bienvenida principal del bot.
    """
    if not rate_limit_ok(update.effective_user.id):
        return await update.message.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    await update.message.reply_text(
        "🔥💳 *BOT OFICIAL ADALIK CORP* 💳🔥\n\n"
        "📋 *MENÚ PRINCIPAL*\n\n"
        "╭━━━〔 *DESCARGA DE MATERIAL* 〕━━━╮\n"
        "┃ 💎 /get \\<clave\\>  → descargar lote/unidad\n"
        "┃ 💎 /status \\<clave\\>  → estado de la clave\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "╭━━━〔 *STOCK Y SERIES* 〕━━━╮\n"
        "┃ 📊 /list  → ver inventario\n"
        "┃ 🔎 /info \\<bin\\>  → buscar BIN\n"
        "┃ 🔎 /bank \\<banco\\>  → buscar por banco\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "╭━━━〔 *UTILIDAD* 〕━━━╮\n"
        "┃ ⚙️ /help\n"
        "╰━━━━━━━━━━━━━━╯\n\n"
        "_Adalik Corp®_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /help
    Muestra ayuda general del sistema.
    """
    if not rate_limit_ok(update.effective_user.id):
        return await update.message.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    msg = (
        "📦 *ADALIK CORP HELPER* 📦\n\n"
        "📋 *MENÚ DE AYUDA*\n\n"
        "╭━━━〔 *DESCARGA DE MATERIAL* 〕━━━╮\n"
        "┃ • _/get <clave>_ → descarga lote o unidad por clave\n"
        "┃ • _/status <clave>_ → muestra vigencia y tiempo restante\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "╭━━━〔 *STOCK Y SERIES* 〕━━━╮\n"
        "┃ • _/list_ → muestra listado general\n"
        "┃ • _/info <bin>_ → busca información por BIN\n"
        "┃ • _/bank <banco>_ → busca información por banco\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "╭━━━〔 *UTILIDAD GENERAL* 〕━━━╮\n"
        "┃ • _/start_ → mensaje de bienvenida\n"
        "┃ • _/help_ → muestra esta ayuda\n"
        "┃ • _/id_ → devuelve tu identificador de usuario\n"
        "┃ • _/ping_ → comprobación de estado del bot\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "🕒 *Las claves expiran automáticamente tras 24 horas y son de un solo uso*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def admin_help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /adminhelp
    Muestra ayuda para administradores.
    """
    user_id = update.effective_user.id

    if not is_inventory_admin(user_id):
        return await update.message.reply_text(
            "⛔ *No tienes permisos\.*", parse_mode="Markdownv2"
        )

    msg = (
        "🛠 *ADALIK CORP ADMIN HELPER* 🛠\n\n"
        "📋 *MENÚ DE ADMINISTRADOR*\n\n"
        "╭━━━〔 *GESTIÓN DE INVENTARIO* 〕━━━╮\n"
        "┃ • _/addcc_ → agregar nuevos registros\n"
        "┃ • _/modifycc_ → modificar registros existentes\n"
        "┃ • _/deletecc_ → eliminar registros\n"
        "┃ • _/cancelcc_ → cancelar operación en curso\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "╭━━━〔 *CONTROL DE STOCK* 〕━━━╮\n"
        "┃ • _/list_ → ver inventario completo\n"
        "┃ • _/info \<bin\>_ → consultar por BIN\n"
        "┃ • _/bank \<banco\>_ → consultar por banco\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "╭━━━〔 *SISTEMA* 〕━━━╮\n"
        "┃ • _/ping_ → estado del bot\n"
        "┃ • _/id_ → ver tu ID\n"
        "╰━━━━━━━━━━━━━━╯\n\n"
        "⚠️ *Uso exclusivo para administradores*"
    )

    await update.message.reply_text(msg, parse_mode="MarkdownV2")


async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ping
    Permite comprobar que el bot está vivo.
    """
    if not rate_limit_ok(update.effective_user.id):
        return await update.message.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    await update.message.reply_text("pong")


# =========================================================


# COMANDOS RELACIONADOS CON CLAVES
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /status <clave>
    Consulta el estado de una clave sin descargar el archivo.
    """
    if not rate_limit_ok(update.effective_user.id):
        return await update.message.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    if not context.args:
        return await update.message.reply_text(msg_status_usage())

    key = normalize_key(" ".join(context.args))
    if not key:
        return await update.message.reply_text(msg_key_unrecognized())

    row = await get_file_by_keyhash(key_to_hash(key))
    if not row:
        return await update.message.reply_text(msg_key_not_found())

    used = row["used"]
    expires_at = row["expires_at"]
    filename = row["filename"]

    if used:
        return await update.message.reply_text(msg_key_used())

    if expires_at:
        exp_dt = datetime.fromisoformat(expires_at)
        remaining = exp_dt - datetime.now(timezone.utc)

        if remaining.total_seconds() <= 0:
            return await update.message.reply_text("Clave expirada.")

        return await update.message.reply_text(
            msg_status_result(filename, expires_at),
            parse_mode="Markdown",
        )

    return await update.message.reply_text(msg_key_still_valid_no_exp())


async def get_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /get <clave>
    Descarga el archivo asociado a una clave válida.
    """
    if not rate_limit_ok(update.effective_user.id):
        return await update.message.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    if not context.args:
        return await update.message.reply_text(msg_get_usage())

    key = normalize_key(" ".join(context.args))
    if not key:
        return await update.message.reply_text(msg_key_unrecognized())

    row = await get_file_by_keyhash(key_to_hash(key))
    if not row:
        return await update.message.reply_text(msg_key_invalid())

    if row["used"]:
        return await update.message.reply_text(msg_key_invalid())

    exp = row["expires_at"]
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp)
        except Exception:
            exp_dt = None

        if exp_dt and datetime.now(timezone.utc) > exp_dt:
            await mark_used(row["id"], update.effective_user.id)
            return await update.message.reply_text(msg_key_expired(EXPIRY_HOURS))

    fname = row["filename"]
    original_name = os.path.basename(fname)

    if "_" in original_name:
        original_name = original_name.split("_", 1)[-1]

    full_path = os.path.join(STORAGE_DIR, fname)

    try:
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                await update.message.reply_document(document=f, filename=original_name)
        else:
            content = row["content"]
            if content is None:
                return await update.message.reply_text(msg_file_missing_content())

            bio = BytesIO(content)
            bio.name = original_name
            bio.seek(0)
            await update.message.reply_document(document=bio)

        await mark_used(row["id"], update.effective_user.id)

    except Exception:
        return await update.message.reply_text(msg_send_failed())


# =========================================================


# RECEPCIÓN DE DOCUMENTOS
# Maneja archivos TXT que se convierten en claves descargables.
async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler general de documentos.
    Valida, descarga, deduplica, guarda y genera una clave.
    """
    msg = update.message

    if not rate_limit_ok(update.effective_user.id):
        return await msg.reply_text(
            "Demasiadas peticiones; intenta de nuevo en un momento."
        )

    doc = msg.document
    if not doc:
        return

    if not is_txt(doc.file_name, doc.mime_type):
        return await msg.reply_text("Solo acepto archivos .txt")

    if ALLOWED_UPLOADERS and update.effective_user.id not in ALLOWED_UPLOADERS:
        return await msg.reply_text("No tienes permiso para subir archivos.")

    if AUTH_FORWARDERS:
        fid = extract_forwarder_id(update)
        if fid not in AUTH_FORWARDERS:
            return await msg.reply_text("❌ Solo reenviados desde autorizados.")

    if doc.file_size and doc.file_size > MAX_BYTES:
        return await msg.reply_text(
            f"Archivo demasiado grande (máx {MAX_BYTES} bytes)."
        )

    f = await context.bot.get_file(doc.file_id)
    data = await f.download_as_bytearray()

    if len(data) > MAX_BYTES:
        return await msg.reply_text(
            f"Archivo demasiado grande (máx {MAX_BYTES} bytes)."
        )

    file_hash = sha256(data)

    if await file_exists_by_hash(file_hash):
        return await msg.reply_text("❗ Este archivo ya fue subido anteriormente.")

    key = gen_single_use_key()
    k_hash = key_to_hash(key)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=EXPIRY_HOURS)
    stored_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{doc.file_name}"

    with open(path_for(stored_name), "wb") as fp:
        fp.write(data)

    await insert_file(
        key_hash=k_hash,
        stored_name=stored_name,
        data=data,
        uploader_id=msg.from_user.id,
        created_at_iso=now.isoformat(),
        file_sha=file_hash,
        expires_at_iso=expires.isoformat(),
    )

    await msg.reply_text(msg_key_created(key, EXPIRY_HOURS))


# =========================================================


# INICIALIZACIÓN Y ARRANQUE DEL BOT
def main():
    """
    Punto de entrada del sistema.

    Se encarga de:
    - validar BOT_TOKEN
    - inicializar base de datos
    - construir la aplicación
    - registrar comandos
    - programar limpieza automática
    - iniciar polling
    """
    if not BOT_TOKEN:
        raise SystemExit("Falta BOT_TOKEN (exporta BOT_TOKEN=...)")

    asyncio.run(init_db())

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ---------------------------------------------------------
    # Comandos generales del bot
    # ---------------------------------------------------------
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("adminhelp", admin_help_cmd))
    app.add_handler(CommandHandler("get", get_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("id", id_cmd))

    # ---------------------------------------------------------
    # Comandos del módulo de inventario
    # ---------------------------------------------------------
    app.add_handler(CommandHandler("addcc", addcc_cmd))
    app.add_handler(CommandHandler("modifycc", modifycc_cmd))
    app.add_handler(CommandHandler("deletecc", deletecc_cmd))
    app.add_handler(CommandHandler("cancelcc", cancelcc_cmd))
    app.add_handler(CommandHandler("list", listccs_cmd))
    app.add_handler(CommandHandler("info", infocc_cmd))
    app.add_handler(CommandHandler("bank", infoccbyname_cmd))

    # ---------------------------------------------------------
    # Handler de texto del módulo de inventario
    # Debe ir antes del resto de handlers de texto genérico
    # ---------------------------------------------------------
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ccs_text_handler))

    # ---------------------------------------------------------
    # Handler de documentos
    # ---------------------------------------------------------
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))

    # ---------------------------------------------------------
    # Purga automática de archivos usados o expirados
    # ---------------------------------------------------------
    if app.job_queue:
        app.job_queue.run_repeating(
            lambda ctx: asyncio.create_task(purge_expired_and_used()),
            interval=AUTO_PURGE_INTERVAL,
            first=0,
        )

    print("Bot corriendo…")
    app.run_polling()


if __name__ == "__main__":
    main()
