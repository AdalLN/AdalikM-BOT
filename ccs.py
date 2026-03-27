# CCS.PY


import os
from io import BytesIO
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from telegram.helpers import escape_markdown
from telegram import Update
from telegram.ext import ContextTypes

from db import (
    insert_cc,
    get_cc_by_bin,
    get_cc_by_name,
    list_ccs,
    update_cc_quantity,
    update_cc_active,
    delete_cc_by_bin,
)

# =========================================================
SUPERADMINS = {
    int(x) for x in os.environ.get("SUPERADMINS", "").split(",") if x.strip().isdigit()
}

# Estado temporal por usuario para saber qué operación está esperando.
# Ejemplo:
# WAITING_INPUTS[123] = "add"
WAITING_INPUTS: Dict[int, str] = {}
# =========================================================


# UTILIDADES GENERALES
def is_inventory_admin(user_id: int) -> bool:
    """Valida si el usuario actual está autorizado para administrar ccs."""
    return user_id in SUPERADMINS


def has_pending_inventory_action(user_id: int) -> bool:
    """Indica si el usuario tiene una operación pendiente."""
    return user_id in WAITING_INPUTS


def clear_pending_inventory_action(user_id: int) -> None:
    """Limpia el estado temporal del usuario."""
    WAITING_INPUTS.pop(user_id, None)


# =========================================================
# MENSAJES DEL MÓDULO
# =========================================================
def msg_inventory_admin_only() -> str:
    return "No tienes permisos para utilizar este módulo."


def msg_addcc_prompt() -> str:
    return (
        "Envía los registros en el siguiente formato, uno por línea:\n\n"
        "bin,name,type,quantity\n\n"
        "Cada línea debe contener:\n"
        "- bin → identificador (6 dígitos)\n"
        "- name → nombre del banco o producto\n"
        "- type → tipo de tarjeta (credito, debito, credito_vip, debito_vip)\n"
        "- quantity → cantidad disponible (opcional)\n\n"
        "Reglas importantes:\n"
        "- Si no especificas quantity, se asignará automáticamente 800\n"
        "- Los espacios antes o después de las comas son ignorados\n"
        "- Los datos se guardan en MAYÚSCULAS automáticamente\n"
        "- Cada línea inválida será ignorada\n\n"
        "Ejemplos válidos:\n"
        "547146,santander gold,credito,100\n"
        "547046,santander premium,credito\n"
        "455511,bbva clasica,debito\n"
        "455512, bbva oro, credito, 300\n\n"
        "Puedes enviar múltiples registros en un solo mensaje respetando el formato."
    )


def msg_modifycc_prompt() -> str:
    return (
        "Envía los cambios en el siguiente formato, uno por línea:\n\n"
        "bin,field,value\n\n"
        "Cada línea debe contener exactamente 3 valores separados por comas:\n"
        "- bin → identificador (6 dígitos)\n"
        "- field → campo a modificar\n"
        "- value → nuevo valor\n\n"
        "Campos permitidos:\n"
        "- quantity → cantidad (número entero)\n"
        "- active → estado (1 = activo, 0 = inactivo)\n\n"
        "Reglas importantes:\n"
        "- El campo 'field' no distingue mayúsculas/minúsculas (quantity, Quantity, QUANTITY son válidos)\n"
        "- Los espacios antes o después de las comas son ignorados\n"
        "- El BIN debe existir en el sistema para que el cambio se aplique\n"
        "- Cada línea inválida será ignorada automáticamente\n\n"
        "Ejemplos válidos:\n"
        "547146,quantity,500\n"
        "547046,active,0\n"
        "455511,ACTIVE,1\n"
        "455512, quantity, 300\n\n"
        "Puedes enviar múltiples cambios en un solo mensaje respetando el formato."
    )


def msg_deletecc_prompt() -> str:
    return (
        "Envía los bins a eliminar, uno por línea.\n\n"
        "Ejemplo:\n"
        "547146\n"
        "547046\n"
        "547047"
    )


def msg_cancel_ok() -> str:
    return "Operación cancelada."


def msg_nothing_to_cancel() -> str:
    return "No hay ninguna operación pendiente."


def msg_addcc_result(inserted: int, skipped: int) -> str:
    return (
        f"Proceso finalizado.\n"
        f"ccs agregados: {inserted}\n"
        f"ccs omitidos: {skipped}"
    )


def msg_modifycc_result(updated: int, skipped: int) -> str:
    return (
        f"Proceso finalizado.\n"
        f"ccs modificados: {updated}\n"
        f"ccs omitidos: {skipped}"
    )


def msg_deletecc_result(deleted: int, skipped: int) -> str:
    return (
        f"Proceso finalizado.\n"
        f"ccs eliminados: {deleted}\n"
        f"ccs omitidos: {skipped}"
    )


def msg_listccs_empty() -> str:
    return "No hay ccs registrados en el inventario."


def msg_text_expected() -> str:
    return "Debes enviar texto con el formato solicitado."


# =========================================================


# PARSERS DE ENTRADA
def parse_add_lines(text: str) -> List[Tuple[str, str, str, int]]:
    """
    Lee líneas en formato:
    bin,name,type,quantity

    quantity es opcional; si no viene, usa 800.
    Retorna solo líneas válidas.
    """
    results: List[Tuple[str, str, str, int]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]

        # Mínimo: bin,name,type
        if len(parts) < 3:
            continue

        bin = parts[0]
        name = parts[1]
        type_ = parts[2]

        quantity = 800
        if len(parts) >= 4 and parts[3]:
            try:
                quantity = int(parts[3])
            except Exception:
                quantity = 800

        if not bin or not name or not type_:
            continue

        results.append((bin, name, type_, quantity))

    return results


def parse_modify_lines(text: str) -> List[Tuple[str, str, str]]:
    """
    Lee líneas en formato:
    bin,field,value

    field admitido:
    - quantity
    - active
    """
    results: List[Tuple[str, str, str]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue

        bin, field, value = parts[0], parts[1].lower(), parts[2]

        if field not in {"quantity", "active"}:
            continue

        if not bin:
            continue

        results.append((bin, field, value))

    return results


def parse_delete_lines(text: str) -> List[str]:
    """
    Lee líneas donde cada línea contiene solo un bin.
    """
    results: List[str] = []

    for raw in text.splitlines():
        bin = raw.strip()
        if bin:
            results.append(bin)

    return results


def normalize_active_value(value: str) -> Optional[int]:
    """
    Convierte distintos textos a 0/1.
    """
    v = value.strip().lower()

    if v in {"1", "true", "yes", "on", "activo", "active"}:
        return 1

    if v in {"0", "false", "no", "off", "inactivo", "inactive"}:
        return 0

    return None


# =========================================================


# PROCESAMIENTO DE ACCIONES
async def process_add_ccs(text: str) -> Tuple[int, int]:
    """
    Inserta ccs nuevos.
    Si ya existen, se omiten.
    Retorna: (inserted, skipped)
    """
    rows = parse_add_lines(text)
    inserted = 0
    skipped = 0

    for bin_, name, type_, quantity in rows:

        # 🔥 LIMPIEZA + NORMALIZACIÓN
        bin_ = str(bin_).strip()
        name = str(name).strip().upper()
        type_ = str(type_).strip().upper()
        quantity = int(quantity)

        existing = await get_cc_by_bin(bin_)
        if existing:
            skipped += 1
            continue

        try:
            await insert_cc(bin_, name, type_, quantity)
            inserted += 1
        except Exception:
            skipped += 1

    return inserted, skipped


async def process_modify_ccs(text: str) -> Tuple[int, int]:
    """
    Modifica quantity o active según el campo indicado.
    Retorna: (updated, skipped)
    """
    rows = parse_modify_lines(text)
    updated = 0
    skipped = 0

    for bin, field, value in rows:
        existing = await get_cc_by_bin(bin)
        if not existing:
            skipped += 1
            continue

        try:
            if field == "quantity":
                quantity = int(value)
                affected = await update_cc_quantity(bin, quantity)
                updated += 1 if affected else 0
                skipped += 0 if affected else 1

            elif field == "active":
                active = normalize_active_value(value)
                if active is None:
                    skipped += 1
                    continue

                affected = await update_cc_active(bin, active)
                updated += 1 if affected else 0
                skipped += 0 if affected else 1

        except Exception:
            skipped += 1

    return updated, skipped


async def process_delete_ccs(text: str) -> Tuple[int, int]:
    """
    Elimina ccs por bin.
    Retorna: (deleted, skipped)
    """
    bins = parse_delete_lines(text)
    deleted = 0
    skipped = 0

    for bin in bins:
        try:
            affected = await delete_cc_by_bin(bin)
            deleted += 1 if affected else 0
            skipped += 0 if affected else 1
        except Exception:
            skipped += 1

    return deleted, skipped


# =========================================================
# COMANDOS DEL MÓDULO
# =========================================================
async def addcc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo para agregar ccs."""
    user_id = update.effective_user.id

    if not is_inventory_admin(user_id):
        return await update.message.reply_text(msg_inventory_admin_only())

    WAITING_INPUTS[user_id] = "add"
    await update.message.reply_text(msg_addcc_prompt())


async def modifycc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo para modificar ccs."""
    user_id = update.effective_user.id

    if not is_inventory_admin(user_id):
        return await update.message.reply_text(msg_inventory_admin_only())

    WAITING_INPUTS[user_id] = "modify"
    await update.message.reply_text(msg_modifycc_prompt())


async def deletecc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo para eliminar ccs."""
    user_id = update.effective_user.id

    if not is_inventory_admin(user_id):
        return await update.message.reply_text(msg_inventory_admin_only())

    WAITING_INPUTS[user_id] = "delete"
    await update.message.reply_text(msg_deletecc_prompt())


async def cancelcc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela una operación pendiente del módulo."""
    user_id = update.effective_user.id

    if has_pending_inventory_action(user_id):
        clear_pending_inventory_action(user_id)
        return await update.message.reply_text(msg_cancel_ok())

    return await update.message.reply_text(msg_nothing_to_cancel())


async def infocc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca información por BIN"""

    if not context.args:
        return await update.message.reply_text(
            "⚠️ *Usa: /info \<bin\>*", parse_mode="MarkdownV2"
        )

    bin_value = context.args[0]
    result = await get_cc_by_bin(bin_value)

    if not result:
        return await update.message.reply_text(
            "❌ *BIN no encontrado*", parse_mode="MarkdownV2"
        )

    text = "🔎 *RESULTADO BIN*\n\n\n"

    for row in result:
        bin_db, name, type_, quantity, active = row

        bin_db = escape_markdown(str(bin_db), version=2)
        name = escape_markdown(str(name), version=2)
        type_ = escape_markdown(str(type_), version=2)
        quantity = escape_markdown(str(quantity), version=2)
        estado = escape_markdown("🟢 ACTIVO" if active else "🔴 INACTIVO", version=2)

        text += (
            f"💳 *BIN:* `{bin_db}`\n"
            f"🏷 *Nombre:* {name}\n"
            f"📂 *Tipo:* {type_}\n"
            f"📦 *Cantidad:* {quantity}\n\n"
            f"📌 *Estado:* {estado}\n\n"
        )

    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def infoccbyname_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca información por banco"""

    if not context.args:
        return await update.message.reply_text(
            "⚠️ *Usa: /info \<banco\>*", parse_mode="MarkdownV2"
        )

    name_value = context.args[0]
    result = await get_cc_by_name(name_value)

    if not result:
        return await update.message.reply_text(
            "❌ *Banco no encontrado*", parse_mode="MarkdownV2"
        )

    text = "🔎 *RESULTADOS POR BANCO*\n\n\n"

    for row in result:
        bin_db, name, type_, quantity, active = row

        bin_db = escape_markdown(str(bin_db), version=2)
        name = escape_markdown(str(name), version=2)
        type_ = escape_markdown(str(type_), version=2)
        quantity = escape_markdown(str(quantity), version=2)
        estado = escape_markdown("🟢 ACTIVO" if active else "🔴 INACTIVO", version=2)

        text += (
            f"💳 *BIN:* `{bin_db}`\n"
            f"🏷 *Nombre:* {name}\n"
            f"📂 *Tipo:* {type_}\n"
            f"📦 *Cantidad:* {quantity}\n\n"
            f"📌 *Estado:* {estado}\n\n"
        )

    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def listccs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Genera un TXT con todo el inventario actual.
    """
    user_id = update.effective_user.id

    rows = await list_ccs()

    if not rows:
        return await update.message.reply_text(msg_listccs_empty())

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: List[str] = []
    lines.append(f"Fecha de consulta: {now}")
    lines.append("")
    lines.append("bin      | NAME                 | TYPE         | QUANTITY | ACTIVE")
    lines.append("----------+----------------------+--------------+----------+--------")

    for row in rows:
        active_text = "SI" if row["active"] else "NO"
        lines.append(
            f"{str(row['bin'])[:10]:<10} | "
            f"{str(row['name'])[:20]:<20} | "
            f"{str(row['type'])[:12]:<12} | "
            f"{int(row['quantity']):>8} | "
            f"{active_text:<6}"
        )
        total_bins = len(rows)

    txt_content = "\n".join(lines)

    bio = BytesIO(txt_content.encode("utf-8"))
    bio.name = f"ADALIK CORP {datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{total_bins}.txt"
    bio.seek(0)

    await update.message.reply_document(document=bio)


# =========================================================
# HANDLER DE TEXTO DEL MÓDULO
# Este handler procesa el siguiente mensaje del usuario
# cuando el sistema está esperando datos de add/modify/delete.
# =========================================================
async def ccs_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Si no hay acción pendiente para este usuario, no hacemos nada.
    if user_id not in WAITING_INPUTS:
        return

    if not update.message or not update.message.text:
        return await update.message.reply_text(msg_text_expected())

    mode = WAITING_INPUTS[user_id]
    text = update.message.text

    try:
        if mode == "add":
            inserted, skipped = await process_add_ccs(text)
            clear_pending_inventory_action(user_id)
            return await update.message.reply_text(msg_addcc_result(inserted, skipped))

        if mode == "modify":
            updated, skipped = await process_modify_ccs(text)
            clear_pending_inventory_action(user_id)
            return await update.message.reply_text(
                msg_modifycc_result(updated, skipped)
            )

        if mode == "delete":
            deleted, skipped = await process_delete_ccs(text)
            clear_pending_inventory_action(user_id)
            return await update.message.reply_text(
                msg_deletecc_result(deleted, skipped)
            )

    except Exception:
        clear_pending_inventory_action(user_id)
        return await update.message.reply_text(
            "Ocurrió un error al procesar la operación."
        )
