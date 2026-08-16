"""User-facing strings (Spanish). The only module allowed to contain Spanish text."""

from src.db import Watch
from src.sources.base import ServerListing

WELCOME = (
    "👋 Bienvenido a ReliableWatch.\n\n"
    "Te aviso por Telegram en cuanto aparezca un servidor dedicado que cumpla lo que buscas "
    "en ReliableSite.\n\n"
    "Comandos:\n"
    "/watch <filtros> — crea una búsqueda (ej. cpu=E3-1230 ram=32 loc=NYC precio=80)\n"
    "/list — tus watches activos\n"
    "/remove <id> — elimina un watch\n"
    "/stock — inventario disponible ahora, sin filtrar\n"
    "/status — salud del sistema"
)

NOT_AUTHORIZED = "⛔ No estás autorizado. Pide acceso al administrador."

WATCH_CREATED = "✅ Watch #{watch_id} creado\n{summary}"
WATCH_PARSE_ERROR = (
    "⚠️ No entendí ese filtro: {error}\n\n"
    "Formato: /watch cpu=E3-1230 ram=32 loc=NYC precio=80 nombre=mi-servidor"
)

WATCH_LIST_EMPTY = "No tienes watches activos. Crea uno con /watch."
WATCH_LIST_HEADER = "📋 Tus watches activos:"
WATCH_LIST_ITEM = "#{watch_id} — {summary}"

REMOVE_USAGE = "Uso: /remove <id>"
WATCH_REMOVED = "🗑️ Watch #{watch_id} eliminado."
WATCH_NOT_FOUND = "No encontré ese watch (¿el id es tuyo?)."

STOCK_EMPTY = "No hay servidores disponibles ahora mismo (o no se pudo consultar el inventario)."
STOCK_HEADER = "📦 Inventario disponible ahora:"
STOCK_ITEM = "{cpu}\n{ram_gb}GB · {storage}\n📍 {location}\n💵 ${price_usd}/mes"

STATUS_TEMPLATE = (
    "📊 Estado del sistema\n\n{poll_line}\n👀 Watches activos: {active_watches}\n⏱️ Uptime: {uptime}"
)
STATUS_POLL_OK = "✅ Último poll: hace {ago} ({source}) — {listings} servidores vistos"
STATUS_POLL_FAILED = "⚠️ Último poll: hace {ago} ({source}) — falló: {error}"
STATUS_NO_POLL_YET = "⏳ Todavía no se hizo ningún poll"
STATUS_NEXT_POLL = "\n⏭️ Próximo poll: en {minutes} min"

APPROVE_USAGE = "Uso: /approve <chat_id>"
APPROVE_ONLY_ADMIN = "⛔ Solo el administrador puede aprobar usuarios."
APPROVE_INVALID_CHAT_ID = "El chat_id debe ser un número entero."
APPROVE_SUCCESS = "✅ Usuario {chat_id} autorizado."

BUTTON_LIST = "📋 Mis watches"
BUTTON_STOCK = "📦 Stock disponible"
BUTTON_STATUS = "📊 Estado del sistema"
BUTTON_REMOVE = "🗑️ Eliminar #{watch_id}"

# (command, description) shown in Telegram's "/" command menu.
COMMAND_DESCRIPTIONS = [
    ("start", "Alta y ayuda"),
    ("watch", "Crea una búsqueda nueva"),
    ("list", "Tus watches activos"),
    ("remove", "Elimina un watch"),
    ("stock", "Inventario disponible ahora"),
    ("status", "Salud del sistema"),
]

MATCH_FOUND_HEADER = "🎯 ¡Disponible! (watch #{watch_id}{label})"
MATCH_FOUND_ITEM = "{cpu}\n{storage}\n📍 {location}\n💵 ${price_usd}/mes\n🔗 {url}"

ADMIN_ALERT_POLL_FAILING = (
    "🚨 {consecutive_failures} fallos seguidos consultando el inventario ({source}).\n"
    "Último error: {error}"
)
ADMIN_ALERT_POLL_STALLED = (
    "🚨 Llevan {minutes} min sin poder consultar el inventario (posible bloqueo o cambio en el "
    "sitio)."
)


def format_watch_summary(watch: Watch) -> str:
    parts = []
    if watch.cpu_pattern:
        parts.append(f"CPU: {watch.cpu_pattern}")
    if watch.ram_min_gb is not None:
        parts.append(f"RAM: ≥{watch.ram_min_gb}GB")
    if watch.storage_pattern:
        parts.append(f"Almacenamiento: {watch.storage_pattern}")
    if watch.location:
        parts.append(f"Ubicación: {watch.location}")
    if watch.price_max_usd is not None:
        parts.append(f"Precio: ≤${watch.price_max_usd}")
    summary = " · ".join(parts) if parts else "sin filtros (cualquier servidor)"
    return f'"{watch.label}" — {summary}' if watch.label else summary


def format_stock_item(listing: ServerListing) -> str:
    return STOCK_ITEM.format(
        cpu=listing.cpu,
        ram_gb=listing.ram_gb,
        storage=listing.storage,
        location=listing.location,
        price_usd=listing.price_usd,
    )


def format_match_notification(watch: Watch, listing: ServerListing) -> str:
    label = f' — "{watch.label}"' if watch.label else ""
    header = MATCH_FOUND_HEADER.format(watch_id=watch.id, label=label)
    item = MATCH_FOUND_ITEM.format(
        cpu=listing.cpu,
        storage=listing.storage,
        location=listing.location,
        price_usd=listing.price_usd,
        url=listing.url or "—",
    )
    return f"{header}\n\n{item}"
