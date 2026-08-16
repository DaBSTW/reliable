"""User-facing strings (Spanish). The only module allowed to contain Spanish text."""

from src.db import Watch
from src.sources.base import ServerListing

WELCOME = (
    "👋 Bienvenido a ReliableWatch.\n\n"
    "Te aviso por Telegram en cuanto aparezca un servidor dedicado que cumpla lo que buscas "
    "en ReliableSite. Usá los botones de abajo — no hace falta escribir nada.\n\n"
    "Comandos de texto, si los preferís:\n"
    "/watch <filtros> — crea una búsqueda (ej. cpu=E3-1230 ram=32 loc=NYC precio=80)\n"
    "/list — tus watches activos\n"
    "/remove <id> — elimina un watch\n"
    "/stock — inventario disponible ahora, sin filtrar\n"
    "/status — salud del sistema"
)

NOT_AUTHORIZED = "⛔ No estás autorizado. Pide acceso al administrador."
ACCESS_REQUESTED = "⛔ No estás autorizado. Le avisé al administrador; te aviso cuando te apruebe."

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
APPROVE_REQUEST_FOR_ADMIN = "🔔 Nuevo usuario pidiendo acceso: {chat_id}{username}"
APPROVE_DONE_FOR_ADMIN = "✅ Autorizado {chat_id}."
APPROVE_NOTIFY_USER = "✅ ¡Ya te aprobaron! Tocá /start para empezar."

BUTTON_LIST = "📋 Mis watches"
BUTTON_STOCK = "📦 Stock disponible"
BUTTON_STATUS = "📊 Estado del sistema"
BUTTON_REMOVE = "🗑️ Eliminar #{watch_id}"
BUTTON_NEW_WATCH = "➕ Nuevo watch"  # noqa: RUF001 -- emoji, not the plus operator
BUTTON_MAIN_MENU = "🏠 Menú principal"
BUTTON_BACK = "⬅️ Atrás"
BUTTON_CANCEL = "❌ Cancelar"
BUTTON_CREATE_WATCH = "✅ Crear watch"
BUTTON_ANY_VALUE = "· Cualquiera ·"
BUTTON_CUSTOM_VALUE = "✏️ Escribir un valor"
BUTTON_REMOVE_FILTER = "🗑️ Quitar {label}"
BUTTON_APPROVE = "✅ Autorizar"

# (command, description) shown in Telegram's "/" command menu.
COMMAND_DESCRIPTIONS = [
    ("start", "Alta y ayuda"),
    ("watch", "Crea una búsqueda nueva"),
    ("list", "Tus watches activos"),
    ("remove", "Elimina un watch"),
    ("stock", "Inventario disponible ahora"),
    ("status", "Salud del sistema"),
]

WIZARD_INTRO = "🛠️ Armemos tu watch. Elegí qué filtros fijar (los que dejes afuera no filtran):"
WIZARD_SUMMARY = "📝 Watch en progreso:\n{summary}\n\nElegí qué más ajustar, o creá el watch."
WIZARD_FILTER_CPU = "🖥️ CPU"
WIZARD_FILTER_RAM = "💾 RAM mínima"
WIZARD_FILTER_STORAGE = "💽 Almacenamiento"
WIZARD_FILTER_LOCATION = "📍 Ubicación"
WIZARD_FILTER_PRICE = "💵 Precio máximo"
WIZARD_FILTER_LABEL = "🏷️ Nombre"
WIZARD_ASK_RAM = "💾 Elegí la RAM mínima:"
WIZARD_ASK_STORAGE = "💽 Elegí el tipo de almacenamiento:"
WIZARD_ASK_PRICE = "💵 Elegí el precio máximo:"
WIZARD_ASK_LOCATION = "📍 Elegí la ubicación:"
WIZARD_ASK_LOCATION_UNAVAILABLE = "📍 No pude traer las ubicaciones disponibles. Escribila a mano:"
WIZARD_ASK_CPU_TEXT = "🖥️ Escribí el modelo de CPU (o parte del nombre), ej. E3-1230:"
WIZARD_ASK_LABEL_TEXT = "🏷️ Escribí un nombre para identificar este watch:"
WIZARD_CANCELLED = "❌ Watch cancelado."
WIZARD_INVALID_VALUE = "⚠️ {error}\n\nProbá de nuevo:"
WIZARD_EXPIRED = "⌛ Esa sesión de watch ya no está activa. Empezá de nuevo."

TEXT_HINT = "Usá los botones 👇"

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


def format_wizard_filters(filters: dict[str, str]) -> str:
    """Render the /watch key=value filters accumulated so far in the wizard."""
    parts = []
    if filters.get("cpu"):
        parts.append(f"CPU: {filters['cpu']}")
    if filters.get("ram"):
        parts.append(f"RAM: ≥{filters['ram']}GB")
    if filters.get("disco"):
        parts.append(f"Almacenamiento: {filters['disco']}")
    if filters.get("loc"):
        parts.append(f"Ubicación: {filters['loc']}")
    if filters.get("precio"):
        parts.append(f"Precio: ≤${filters['precio']}")
    summary = " · ".join(parts) if parts else "sin filtros (cualquier servidor)"
    return f'"{filters["nombre"]}" — {summary}' if filters.get("nombre") else summary


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
