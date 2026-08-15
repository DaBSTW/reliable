# CODESTYLE.md — Estándar de código

Reglas obligatorias para todo el código de este repositorio. No son sugerencias: lo que no las cumpla no entra a `main`.

> **Idioma de este documento:** la prosa va en español, igual que [`SPECS.md`](./SPECS.md), [`ROADMAP.md`](./ROADMAP.md) y [`README.md`](./README.md). **Todo lo que es código va en inglés** — identificadores, comentarios, docstrings, logs, mensajes de commit y nombres de fichero. Sin excepciones.

---

## 1. Inglés en todo el código

Identificadores, comentarios, docstrings, logs, nombres de archivo, ramas y mensajes de commit: **inglés**.

```python
# ✅ Correcto
async def get_available_servers(self) -> list[ServerListing]:
    """Fetch current inventory, excluding out-of-stock entries."""
    logger.info("inventory fetch started", extra={"source": self.name})

# ❌ Incorrecto
async def obtener_servidores(self) -> list[Servidor]:
    """Trae el inventario actual."""
    logger.info("empezando consulta de inventario")
```

### La única excepción: texto que ve el usuario

El bot habla al usuario en español. Ese texto es **producto**, no código, y por tanto:

- Vive **exclusivamente** en `src/bot/messages.py`. Ningún string en español fuera de ese módulo.
- Las claves que lo referencian van en inglés.

```python
# src/bot/messages.py
WATCH_CREATED = "✅ Watch #{watch_id} creado\n{summary}"
NOT_AUTHORIZED = "⛔ No estás autorizado. Pide acceso al administrador."

# src/bot/handlers.py
await update.message.reply_text(messages.WATCH_CREATED.format(...))   # ✅
await update.message.reply_text("✅ Watch creado")                     # ❌ string suelto
```

Esto mantiene la codebase 100% en inglés y deja la traducción/ajuste de tono en un único fichero.

---

## 2. Comentarios: pocos, técnicos y solo si aportan

El código bien nombrado se explica solo. Un comentario existe **únicamente** cuando el código no puede expresar la información por sí mismo.

### Reglas

- **Explica el _por qué_, nunca el _qué_.** Si el comentario parafrasea la línea siguiente, sobra.
- **Solo información técnica**: una restricción de una librería, un workaround, una decisión no obvia, una unidad de medida ambigua.
- **Una línea siempre que sea posible.** Un párrafo es señal de que el código necesita refactor, no explicación.
- **Prohibido**: código comentado, banners decorativos, `TODO` sin ticket/issue, notas personales, changelogs en comentarios (para eso está git).

```python
# ✅ Aporta: información que el código no puede expresar
# zeep is sync; running it inline would block the bot's event loop.
listings = await asyncio.to_thread(self._client.service.GetServers)

# ✅ Aporta: restricción externa no evidente
# ReliableSite returns 403 without a browser-like Accept-Language header.
headers = {"Accept-Language": "en-US,en;q=0.9", ...}

# ❌ Parafrasea el código
# Increment the retry counter
retry_count += 1

# ❌ Banner decorativo
# ============================
# ===  MATCHER FUNCTIONS   ===
# ============================

# ❌ Código muerto: bórralo, git lo recuerda
# old_price = parse_price(raw)
# if old_price > 100:
#     return None

# ❌ TODO huérfano
# TODO: arreglar esto algún día
```

### Docstrings

Solo en lo público y no evidente: módulos, clases e interfaces. Una línea imperativa. Si la firma tipada ya lo dice todo, no escribas docstring.

```python
# ✅
def matches(listing: ServerListing, watch: Watch) -> bool:
    """Return True when the listing satisfies every non-null filter in the watch."""

# ❌ Redundante con la firma
def get_watch_id(watch: Watch) -> int:
    """Get the watch id."""
    return watch.id
```

---

## 3. Depurabilidad

Cuando algo falle a las 3 de la mañana en la VPS, los logs tienen que bastar para entenderlo sin reproducirlo.

### Logging

- `logging` de stdlib con un logger por módulo: `logger = logging.getLogger(__name__)`.
- **Nunca `print()`** en `src/`.
- Mensajes con **contexto estructurado**, no interpolado a mano.
- Cada ciclo de poll lleva un `cycle_id` para poder seguir toda su traza.

```python
# ✅ Trazable y filtrable
logger.warning(
    "inventory fetch failed",
    extra={"cycle_id": cycle_id, "source": "scraper", "status": 403, "attempt": 3},
)

# ❌ Inútil dentro de seis meses
logger.warning("error")
print(f"fallo: {e}")
```

**Niveles**, sin ambigüedad:

| Nivel | Cuándo |
|---|---|
| `DEBUG` | Detalle de parseo, payloads recortados. Apagado en producción |
| `INFO` | Hitos del ciclo: poll iniciado/terminado, watch creado, aviso enviado |
| `WARNING` | Fallo recuperable: un reintento, un campo que no parseó |
| `ERROR` | Fallo que rompe el ciclo o pierde datos |
| `CRITICAL` | El proceso no puede continuar |

### Errores

- **Prohibido `except:` y `except Exception:` sin re-lanzar o registrar.** Nada de fallos silenciosos.
- Captura la excepción **más específica** que puedas.
- Al re-lanzar, conserva la causa: `raise ParseError(...) from exc`.
- Excepciones propias en `src/errors.py` (`InventoryUnavailableError`, `ParseError`, …), no `Exception` genérica.

```python
# ✅
try:
    price = Decimal(raw_price.strip("$"))
except (InvalidOperation, AttributeError) as exc:
    logger.warning("price parse failed", extra={"raw": raw_price, "product_id": pid})
    raise ParseError(f"unparseable price for {pid}") from exc

# ❌ Se traga el fallo y devuelve datos corruptos
try:
    price = Decimal(raw_price)
except:
    price = 0
```

### Reglas de depurabilidad

- **Nunca dato inventado por defecto.** Ante un fallo de parseo, `None` explícito o excepción — jamás `0`, `""` o `[]` haciéndose pasar por dato real.
- **Timeout explícito en toda llamada de red.** Sin excepción.
- **Nunca loguear secretos.** Tokens, API keys y `chat_id` completos fuera de los logs; usa `token[:6] + "..."`.
- **Registrar cada poll en `poll_log`** (éxito, nº de listings, error). `/status` se alimenta de ahí.
- **Fallos ruidosos**: >3 fallos consecutivos avisan al admin por Telegram. Un sistema que calla y no monitoriza nada es peor que uno caído.

---

## 4. Formato: automático, nunca manual

El formato **no se discute ni se revisa a mano** — lo impone la herramienta.

- **[Ruff](https://docs.astral.sh/ruff/)** para formateo y linting (reemplaza black + isort + flake8, y es notablemente más rápido, lo que importa en una VPS de 1 vCPU).
- **Longitud de línea: 100.**
- **Comillas dobles.** Trailing commas en multilínea.
- Imports ordenados por Ruff: stdlib → terceros → local. Un import por línea. **Nunca `from x import *`.**
- **`pre-commit` obligatorio**: el formateo entra en cada commit, no en la revisión.

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "ARG", "PTH", "RUF"]
ignore = ["E501"]  # handled by the formatter

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
strict = true
warn_unreachable = true
```

```bash
ruff format . && ruff check --fix . && mypy src/    # antes de cada commit
```

---

## 5. Tipado

- **Type hints obligatorios** en toda firma de función y atributo de clase. `mypy --strict` debe pasar limpio.
- Sintaxis moderna: `list[str]`, `str | None` — no `List`, no `Optional`.
- **`Any` prohibido** salvo en el borde SOAP (`zeep` devuelve objetos dinámicos), y aun ahí se convierte a un `ServerListing` tipado **de inmediato**.
- Contratos entre módulos con `@dataclass(frozen=True)`, no diccionarios sueltos.

```python
# ✅ Contrato explícito e inmutable
@dataclass(frozen=True)
class ServerListing:
    product_id: str
    cpu: str
    ram_gb: int
    price_usd: Decimal
    location: str
    in_stock: bool
    url: str | None = None

# ❌ Diccionario que nadie sabe qué contiene
def parse(raw) -> dict:
    return {"cpu": ..., "ram": ...}
```

---

## 6. Estructura de la codebase

### Dirección de dependencias

Estricta y en un solo sentido. **Las flechas nunca se invierten.**

```
bot/ ──▶ db/ ◀── matcher/ ◀── sources/
  │                 ▲
  └────────▶ notifier/
```

- `sources/` **no sabe** que existe Telegram, ni la base de datos, ni el matcher.
- `matcher/` es **lógica pura**: sin I/O, sin red, sin base de datos. Entra `ServerListing` + `Watch`, sale `bool`. Por eso es trivial de testear.
- `bot/handlers.py` **no contiene lógica de negocio**: valida entrada, delega y formatea salida.
- **Cero imports circulares.** Si aparece uno, el diseño está mal, no hace falta un truco de import.

### Reglas de módulo

- **Un módulo, una responsabilidad.** Si necesitas "y" para describir qué hace, pártelo.
- **Máximo ~300 líneas por módulo, ~50 por función.** Superarlo es señal de refactor, no un límite burocrático.
- **I/O en los bordes.** El núcleo (matcher, parsers) es puro y determinista; red y disco viven en `sources/`, `db.py` y `notifier.py`.
- **Configuración solo vía `config.py`.** Ningún módulo lee `os.environ` por su cuenta.
- **Nada de estado global mutable.** Las dependencias se pasan explícitamente por constructor.

### Nombres

| Elemento | Convención | Ejemplo |
|---|---|---|
| Módulos / paquetes | `snake_case` | `api_source.py` |
| Funciones / variables | `snake_case`, verbo primero | `fetch_inventory()` |
| Clases | `PascalCase` | `ScraperSource` |
| Constantes | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT_SECONDS` |
| Privado del módulo | `_` inicial | `_normalize_ram()` |
| Booleanos | prefijo `is_` / `has_` | `is_in_stock` |
| Unidades en el nombre | siempre explícitas | `ram_gb`, `price_usd`, `timeout_seconds` |

Sin abreviaturas (`srv`, `inv`, `cfg`) salvo las universales (`id`, `url`, `db`).

---

## 7. Async

Un solo event loop compartido por bot, scheduler y poller. **Bloquearlo congela el bot entero.**

- **Nada bloqueante en el loop.** `zeep` es síncrono → `asyncio.to_thread()` obligatorio. Igual para cualquier lectura de disco pesada.
- `httpx.AsyncClient` reutilizado, no uno nuevo por request.
- `aiosqlite` para toda la base de datos.
- **Prohibido `time.sleep()`** → `asyncio.sleep()`.
- Toda tarea de fondo con manejo de excepciones propio: una excepción sin capturar en una task la mata en silencio.

```python
# ✅ El loop sigue libre
listings = await asyncio.to_thread(self._client.service.GetServers)

# ❌ Congela el bot durante toda la llamada SOAP
listings = self._client.service.GetServers()
```

---

## 8. Tests

- `pytest` + `pytest-asyncio`. **Ninguna prueba toca la red real**: todo contra fixtures en `tests/fixtures/`.
- Nombres descriptivos de comportamiento: `test_watch_with_null_filters_matches_everything()`, no `test_matcher_2()`.
- Patrón **Arrange–Act–Assert**, separado por líneas en blanco.
- Un `assert` conceptual por test.
- Toda corrección de bug entra con el test que lo reproduce.
- `matcher.py` es lógica pura: **cobertura cercana al 100%**, sin excusa.

---

## 9. Git

- Commits en **inglés**, imperativo, en presente: `add scraper retry backoff` — no `added` ni `añadido`.
- Un commit, un cambio lógico. Formateo automático nunca se mezcla con cambios de lógica.
- Ramas: `feat/`, `fix/`, `chore/` + descripción en inglés con guiones.
- **Nunca commitear** `.env`, `*.db`, credenciales ni logs.

---

## 10. Producción

- **Cero secretos en el código.** Solo `.env` con permisos `600`.
- **Todo lo configurable, configurable** — ningún número mágico incrustado; a `config.py` con su valor por defecto.
- **Apagado limpio**: `SIGTERM` cierra el cliente HTTP y la conexión SQLite antes de salir.
- **Idempotencia**: reiniciar el proceso no debe reenviar avisos ya enviados.
- **Presupuesto de memoria**: nada de cargar el inventario completo en memoria más de una vez por ciclo. La VPS tiene 1 GB.
- **Dependencias fijadas** con versión exacta en `requirements.txt`. Añadir una dependencia nueva requiere justificarla: cada una cuesta RAM y superficie de ataque.

---

## Checklist antes de abrir un PR

- [ ] `ruff format .` y `ruff check .` limpios
- [ ] `mypy src/` sin errores
- [ ] `pytest` en verde
- [ ] Cero español fuera de `bot/messages.py`
- [ ] Cero `print()`, cero `except:` desnudo, cero código comentado
- [ ] Cada comentario superviviente aporta algo que el código no dice
- [ ] Toda llamada de red con timeout
- [ ] Ningún secreto en código, logs ni commits
- [ ] Los fallos nuevos son visibles en los logs con contexto suficiente
