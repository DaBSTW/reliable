# ROADMAP.md — Ruta de trabajo

Ruta de ejecución derivada de [`SPECS.md`](./SPECS.md). Ordenada por dependencias: cada fase asume terminada la anterior, salvo lo marcado como **paralelizable**.

> **Estado:** Fases 0 a 6 completas en código (`ruff format`, `ruff check`, `mypy --strict` y
> `pytest` en verde — 75 tests, sin tocar red real salvo la verificación manual puntual descrita
> abajo). Lo que queda sin marcar son pasos que requieren infraestructura o cuentas del usuario
> que este entorno de trabajo no tiene: una VPS real, un `TELEGRAM_BOT_TOKEN` de @BotFather, y
> una revisión manual de ToS/`robots.txt` (bloqueados por un reto de Cloudflare para cualquier
> cliente automatizado). El hallazgo más importante: la Inventory API de ReliableSite no
> necesita credenciales — se usa en vivo, sin esperar a nadie.

---

## Arranque inmediato (día 1, en paralelo)

Estas dos tareas dependen de terceros y tienen tiempo de espera. **Lanzarlas antes que cualquier código**, para que no bloqueen después.

- [x] ~~Solicitar acceso a la Inventory API~~ — **no hizo falta pedir nada**: se inspeccionó el
  WSDL real (`api.reliablesite.net/inventory.svc?wsdl`) y la operación `ServersList` es
  pública, sin autenticación, sin API key. `api_source.py` la consume directamente. Los
  campos `RELIABLESITE_API_USER`/`RELIABLESITE_API_KEY` se dejan en `.env.example` por si
  ReliableSite empieza a exigir credenciales más adelante, pero hoy no se usan.
  - [ ] Rate limits: no confirmados con soporte (no fue necesario contactarlos). El poll cada
    10 min es conservador; si ReliableSite bloquea la IP, revisar este punto con ellos.
- [ ] **Crear el bot de Telegram** con @BotFather → obtener `TELEGRAM_BOT_TOKEN` — pendiente,
  requiere una cuenta de Telegram real; no lo puede hacer un agente.
  - [ ] Obtener el `ADMIN_CHAT_ID` propio (vía @userinfobot o similar) — igual, pendiente.
- [ ] **Revisar ToS y `robots.txt`** de reliablesite.net — intentado; el sitio devuelve un
  reto de Cloudflare (JS) incluso para `/robots.txt`, así que no se pudo leer mecánicamente.
  Requiere revisión manual desde un navegador antes de activar el scraper en producción.

---

## Fase 0 — Preparar terreno

**Objetivo:** VPS lista y repo esqueleto que arranca sin hacer nada útil todavía.

### Infraestructura VPS
- [ ] Crear swap file de 2 GB (**crítico** con 1 GB de RAM — sin esto, un `apt upgrade` puede tumbar la máquina) — pendiente, requiere la VPS real.
- [ ] Crear usuario no privilegiado `reliable-bot` — pendiente, requiere la VPS real.
- [ ] Instalar Python 3.11+ y `python3-venv` — pendiente, requiere la VPS real.
- [ ] `ufw`: `deny incoming` salvo SSH (el bot solo hace tráfico saliente) — pendiente, requiere la VPS real.

### Repo
- [x] Crear estructura de directorios de §9 de SPECS
- [x] `requirements.txt`: `python-telegram-bot`, `zeep`, `httpx`, `selectolax`, `APScheduler`, `aiosqlite`, `python-dotenv`
- [x] `.gitignore` con `.env`, `*.db`, `venv/`, `__pycache__/`
- [x] `.env.example` (§10 de SPECS) — **sin valores reales**
- [x] `config.py`: carga de `.env` y validación de que las variables obligatorias existen al arrancar
- [x] `main.py` mínimo que arranca, loguea "started" y sale limpio

**Hecho cuando:** `python -m src.main` arranca y termina sin error en la VPS. — código listo y
probado localmente (`ruff` + `mypy --strict` + `pytest` en verde); falta ejecutarlo en la VPS
real, que no existe todavía en este entorno.

---

## Fase 1 — Núcleo de datos (sin red, sin bot)

**Objetivo:** poder decidir si un servidor cumple lo que el usuario pidió. Todo testeable en local sin tocar internet.

### Contratos
- [x] `sources/base.py`: dataclass `ServerListing` (product_id, description, cpu, ram_gb, storage, location, price_usd, in_stock, url)
- [x] `sources/base.py`: interfaz abstracta `InventorySource.get_available_servers() -> list[ServerListing]`

### Persistencia
- [x] `db.py`: esquema SQL de §7 (`watches`, `poll_log`, `authorized_users`) + migración inicial idempotente
- [x] `db.py`: CRUD async de watches (crear, listar por chat, desactivar, actualizar `last_notified_at`/`last_match_hash`)

### Lógica de match
- [x] `matcher.py`: comparar un `ServerListing` contra un `watch`
  - [x] `cpu_pattern` → substring case-insensitive sobre description
  - [x] `ram_min_gb` → comparación `>=`
  - [x] `location` → match exacto normalizado (NYC/LA/etc.)
  - [x] `price_max_usd` → comparación `<=`
  - [x] Campos `null` = "cualquiera" (no filtran)
- [x] `matcher.py`: lógica de deduplicación — hash de product_ids + ventana `RENOTIFY_HOURS`

### Tests
- [x] `fixtures/sample_inventory.json` con ~10 servidores representativos
- [x] `test_matcher.py`: match exacto, match por RAM mínima, sin match, precio fuera de rango, watch con campos vacíos, re-notificación dentro/fuera de ventana

**Hecho cuando:** `pytest` pasa en verde y el matcher está cubierto sin haber hecho una sola request de red. ✅

---

## Fase 2 — Fuente de datos real (scraper primero)

**Objetivo:** traer inventario real de ReliableSite. Se empieza por el scraper porque no depende de que llegue el acceso a la API.

- [x] `scraper_source.py`: cliente `httpx` async con headers de navegador realistas
- [x] Parsear `/dedicated-servers/specials.aspx` con `selectolax` → `list[ServerListing]`
- [x] Normalizar: extraer RAM en GB, precio numérico y ubicación desde el texto crudo
- [x] Manejo de errores: 403 / 429 / 503 → backoff exponencial (base 30s, tope 15 min)
- [x] Guardar un HTML como fixture para poder testear el parser sin red
- [x] Test del parser contra ese fixture

> ⚠️ Confirmado durante este trabajo: el sitio devuelve un **reto de Cloudflare (JS)** a
> cualquier request automatizado, no un 403 simple — ajustar headers no alcanza, haría falta
> un navegador real (Playwright/Selenium), que está fuera de presupuesto de RAM (§2 de SPECS).
> Por eso la API oficial pasó a ser la fuente **principal** (Fase 5) y el scraper quedó como
> **respaldo real pero no verificable en producción**: sus selectores (`.server-card`, etc.)
> son un supuesto razonable documentado en el código, no confirmados contra HTML real.
>
> **Hecho cuando:** ~~un script one-off imprime por consola la lista de servidores disponibles reales~~ — no se pudo cumplir tal cual por el bloqueo de Cloudflare; en su lugar, `api_source.py` (Fase 5) sí imprime inventario real.

---

## Fase 3 — Bot de Telegram

**Objetivo:** el usuario puede pedir lo que busca.

- [x] `bot/auth.py`: whitelist por `chat_id`, bootstrap del admin desde `ADMIN_CHAT_ID`, `/approve <chat_id>`
- [x] `bot/handlers.py`:
  - [x] `/start` — registro + ayuda
  - [x] `/watch cpu=... ram=... loc=... precio=...` — parser de clave=valor con errores claros si el formato está mal
  - [x] `/list` — watches activos con su id
  - [x] `/remove <id>` — con validación de que el watch pertenece a ese chat
  - [x] `/status` — último poll OK, próximo poll, nº de watches
  - [x] `/stock` — inventario actual sin filtrar
- [x] Long polling arrancando desde `main.py`

**Hecho cuando:** se puede crear, listar y borrar un watch desde el móvil, y un `chat_id` no
autorizado recibe rechazo. — lógica cubierta por `tests/test_handlers.py` (52 casos, incluido
rechazo a no-autorizados); la prueba manual desde el móvil real queda pendiente porque no hay
`TELEGRAM_BOT_TOKEN` real todavía (ver "Arranque inmediato").

---

## Fase 4 — Integración end-to-end

**Objetivo:** que el sistema avise solo. Este es el hito en el que el producto ya sirve.

- [x] `APScheduler` (AsyncIOScheduler) en el mismo event loop del bot, cada `POLL_INTERVAL_SECONDS`
- [x] Ciclo completo: poll → source → matcher vs. watches activos → notifier (`poller.py`)
- [x] `notifier.py`: mensaje formateado con specs, precio y link directo al servidor
- [x] Escribir cada intento en `poll_log` (éxito/error, nº listings)
- [x] Alerta al admin si hay **>3 fallos consecutivos** o **>30 min sin poll exitoso**
- [x] Test de integración con `InventorySource` mockeado (ciclo completo, sin red)
- [x] Verificar dedup: dos polls seguidos con el mismo stock → **una sola** notificación

**Hecho cuando:** un watch con criterios que sí existen en stock dispara una notificación real
al Telegram, y el siguiente poll no la duplica. — verificado con `tests/test_poller.py` contra
un `InventorySource` mockeado; el envío real a un chat de Telegram queda pendiente de la misma
falta de `TELEGRAM_BOT_TOKEN` real que Fase 3.

---

## Fase 5 — Migrar a la API oficial

**Objetivo:** dejar de depender del HTML. ~~Solo arranca cuando lleguen las credenciales~~ —
resultó no hacer falta esperar: el WSDL es público.

- [x] **Inspeccionar el WSDL real** (`api.reliablesite.net/inventory.svc?wsdl`) y confirmar los puntos que quedaron abiertos en SPECS §3.1:
  - [x] Nombre exacto de la operación: **`ServersList`** (no `GetServers`/`ListServers`) — sin parámetros de entrada.
  - [x] Credenciales: **ninguna**. `ServersList` no pide usuario/clave ni header SOAP — confirmado invocándola en vivo.
  - [x] Campos reales del response y su mapeo a `ServerListing` — `Server_Details` trae `Product_Id`, `Description`, `Detail` (texto libre con CPU/RAM/storage separados por `<br/>`), `Data_Center`, `Recurring_1_Month` y `Stock`; documentado en el docstring de `api_source.py`.
- [x] `api_source.py` con `zeep`, implementando la misma interfaz `InventorySource`
- [x] Fixture de response SOAP + test del mapeo (`tests/fixtures/api_servers_sample.json`, `tests/test_api_source.py`)
- [x] Cambiar default a `INVENTORY_SOURCE=api`
- [x] Fallback automático al scraper si la API falla N veces seguidas (`FallbackInventorySource`, umbral 3)

**Hecho cuando:** el sistema corre sobre la API oficial y el scraper solo entra si la API se
cae. ✅ Verificado en vivo: `ApiSource` trajo 366 servidores reales, 38 en stock, los 38
mapeados correctamente a `ServerListing`.

---

## Fase 6 — Deploy y hardening

**Objetivo:** que sobreviva sin supervisión.

- [x] `deploy/reliable-bot.service` (systemd) con `Restart=on-failure` y `MemoryMax=400M` (+ hardening: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`)
- [ ] Desplegar en `/opt/reliable-bot` con venv propio, `.env` en modo `600` — pendiente, requiere la VPS real.
- [x] `logrotate` para `/var/log/reliable-bot/app.log` (diario, 7 copias, comprimido) — `deploy/reliable-bot.logrotate`; `main.py` ahora escribe a `LOG_PATH` con un `RotatingFileHandler` como red de seguridad.
- [ ] `systemctl enable` + prueba de reboot: confirmar que levanta solo — pendiente, requiere la VPS real.
- [ ] Prueba de resiliencia: matar el proceso → systemd lo revive — pendiente, requiere la VPS real.
- [ ] Verificar consumo real de RAM en reposo (`systemctl status`) contra el presupuesto de ~60–90 MB — pendiente, requiere la VPS real.

**Hecho cuando:** la VPS se reinicia, el bot vuelve solo, y el consumo de memoria está dentro
de lo esperado. — los artefactos de deploy están listos y en el repo; falta ejecutarlos porque
no existe una VPS en este entorno de trabajo (agente en contenedor efímero, sin acceso a
infraestructura del usuario).

---

## Ruta crítica

```
Solicitar API ──────────────────────────────────(espera externa)──────────► Fase 5
                                                                              │
Fase 0 ──► Fase 1 ──► Fase 2 ──► Fase 3 ──► Fase 4 ──► Fase 6 ◄──────────────┘
                                              ▲
                                    ya es usable aquí
```

- **El producto ya sirve al terminar la Fase 4.** Las fases 5 y 6 son robustez, no funcionalidad.
- Fase 1 no depende de red: se puede desarrollar aunque el scraping o la API estén bloqueados.
- Fase 3 (bot) es independiente de Fase 2 (scraper): si el 403 se complica, se puede avanzar con el bot en paralelo usando datos del fixture.

---

## Riesgos que pueden alterar la ruta

| Si pasa esto… | …la ruta cambia así |
|---|---|
| ReliableSite no da acceso a la API | Fase 5 se cae; el scraper (Fase 2) pasa a ser permanente → subir prioridad de sus tests y del monitoreo de fallos |
| El 403 anti-bot no se puede sortear | Fase 2 se bloquea; el proyecto queda **dependiente** de la API → la solicitud del día 1 se vuelve bloqueante duro |
| La API resulta ser de pago / solo resellers | Decisión de negocio antes de Fase 5: pagar, o quedarse en scraping asumiendo su fragilidad |
| Consumo de RAM por encima de lo previsto | Revisar `selectolax` vs `beautifulsoup4`, y bajar frecuencia de polling |
