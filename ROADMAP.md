# ROADMAP.md — Ruta de trabajo

Ruta de ejecución derivada de [`SPECS.md`](./SPECS.md). Ordenada por dependencias: cada fase asume terminada la anterior, salvo lo marcado como **paralelizable**.

---

## Arranque inmediato (día 1, en paralelo)

Estas dos tareas dependen de terceros y tienen tiempo de espera. **Lanzarlas antes que cualquier código**, para que no bloqueen después.

- [ ] **Solicitar acceso a la Inventory API** de ReliableSite (soporte/ticket). Es el bloqueante externo más largo del proyecto.
  - [ ] Pedir explícitamente: credenciales, método de autenticación (header SOAP vs. usuario/clave) y confirmación de rate limits permitidos
  - [ ] Preguntar si el polling cada 10 min está dentro de su uso aceptable
- [ ] **Crear el bot de Telegram** con @BotFather → obtener `TELEGRAM_BOT_TOKEN`
  - [ ] Obtener el `ADMIN_CHAT_ID` propio (vía @userinfobot o similar)
- [ ] **Revisar ToS y `robots.txt`** de reliablesite.net para validar la vía de scraping como fallback legítimo

---

## Fase 0 — Preparar terreno

**Objetivo:** VPS lista y repo esqueleto que arranca sin hacer nada útil todavía.

### Infraestructura VPS
- [ ] Crear swap file de 2 GB (**crítico** con 1 GB de RAM — sin esto, un `apt upgrade` puede tumbar la máquina)
- [ ] Crear usuario no privilegiado `reliable-bot`
- [ ] Instalar Python 3.11+ y `python3-venv`
- [ ] `ufw`: `deny incoming` salvo SSH (el bot solo hace tráfico saliente)

### Repo
- [ ] Crear estructura de directorios de §9 de SPECS
- [ ] `requirements.txt`: `python-telegram-bot`, `zeep`, `httpx`, `selectolax`, `APScheduler`, `aiosqlite`, `python-dotenv`
- [ ] `.gitignore` con `.env`, `*.db`, `venv/`, `__pycache__/`
- [ ] `.env.example` (§10 de SPECS) — **sin valores reales**
- [ ] `config.py`: carga de `.env` y validación de que las variables obligatorias existen al arrancar
- [ ] `main.py` mínimo que arranca, loguea "started" y sale limpio

**Hecho cuando:** `python -m src.main` arranca y termina sin error en la VPS.

---

## Fase 1 — Núcleo de datos (sin red, sin bot)

**Objetivo:** poder decidir si un servidor cumple lo que el usuario pidió. Todo testeable en local sin tocar internet.

### Contratos
- [ ] `sources/base.py`: dataclass `ServerListing` (product_id, description, cpu, ram_gb, storage, location, price_usd, in_stock, url)
- [ ] `sources/base.py`: interfaz abstracta `InventorySource.get_available_servers() -> list[ServerListing]`

### Persistencia
- [ ] `db.py`: esquema SQL de §7 (`watches`, `poll_log`, `authorized_users`) + migración inicial idempotente
- [ ] `db.py`: CRUD async de watches (crear, listar por chat, desactivar, actualizar `last_notified_at`/`last_match_hash`)

### Lógica de match
- [ ] `matcher.py`: comparar un `ServerListing` contra un `watch`
  - [ ] `cpu_pattern` → substring case-insensitive sobre description
  - [ ] `ram_min_gb` → comparación `>=`
  - [ ] `location` → match exacto normalizado (NYC/LA/etc.)
  - [ ] `price_max_usd` → comparación `<=`
  - [ ] Campos `null` = "cualquiera" (no filtran)
- [ ] `matcher.py`: lógica de deduplicación — hash de product_ids + ventana `RENOTIFY_HOURS`

### Tests
- [ ] `fixtures/sample_inventory.json` con ~10 servidores representativos
- [ ] `test_matcher.py`: match exacto, match por RAM mínima, sin match, precio fuera de rango, watch con campos vacíos, re-notificación dentro/fuera de ventana

**Hecho cuando:** `pytest` pasa en verde y el matcher está cubierto sin haber hecho una sola request de red.

---

## Fase 2 — Fuente de datos real (scraper primero)

**Objetivo:** traer inventario real de ReliableSite. Se empieza por el scraper porque no depende de que llegue el acceso a la API.

- [ ] `scraper_source.py`: cliente `httpx` async con headers de navegador realistas
- [ ] Parsear `/dedicated-servers/` y `/dedicated-servers/specials.aspx` con `selectolax` → `list[ServerListing]`
- [ ] Normalizar: extraer RAM en GB, precio numérico y ubicación desde el texto crudo
- [ ] Manejo de errores: 403 / 429 / 503 → backoff exponencial (base 30s, tope 15 min)
- [ ] Guardar un HTML real como fixture para poder testear el parser sin red
- [ ] Test del parser contra ese fixture

> ⚠️ El sitio devolvió **403 a requests automatizados** durante la investigación. Presupuestar tiempo aquí: puede requerir ajustar headers, o directamente forzar que la API oficial sea la vía única.

**Hecho cuando:** un script one-off imprime por consola la lista de servidores disponibles reales.

---

## Fase 3 — Bot de Telegram

**Objetivo:** el usuario puede pedir lo que busca.

- [ ] `bot/auth.py`: whitelist por `chat_id`, bootstrap del admin desde `ADMIN_CHAT_ID`, `/approve <chat_id>`
- [ ] `bot/handlers.py`:
  - [ ] `/start` — registro + ayuda
  - [ ] `/watch cpu=... ram=... loc=... precio=...` — parser de clave=valor con errores claros si el formato está mal
  - [ ] `/list` — watches activos con su id
  - [ ] `/remove <id>` — con validación de que el watch pertenece a ese chat
  - [ ] `/status` — último poll OK, próximo poll, nº de watches
  - [ ] `/stock` — inventario actual sin filtrar
- [ ] Long polling arrancando desde `main.py`

**Hecho cuando:** se puede crear, listar y borrar un watch desde el móvil, y un `chat_id` no autorizado recibe rechazo.

---

## Fase 4 — Integración end-to-end

**Objetivo:** que el sistema avise solo. Este es el hito en el que el producto ya sirve.

- [ ] `APScheduler` (AsyncIOScheduler) en el mismo event loop del bot, cada `POLL_INTERVAL_SECONDS`
- [ ] Ciclo completo: poll → source → matcher vs. watches activos → notifier
- [ ] `notifier.py`: mensaje formateado con specs, precio y link directo al servidor
- [ ] Escribir cada intento en `poll_log` (éxito/error, nº listings)
- [ ] Alerta al admin si hay **>3 fallos consecutivos** o **>30 min sin poll exitoso**
- [ ] Test de integración con `InventorySource` mockeado (ciclo completo, sin red)
- [ ] Verificar dedup: dos polls seguidos con el mismo stock → **una sola** notificación

**Hecho cuando:** un watch con criterios que sí existen en stock dispara una notificación real al Telegram, y el siguiente poll no la duplica.

---

## Fase 5 — Migrar a la API oficial

**Objetivo:** dejar de depender del HTML. Solo arranca cuando lleguen las credenciales de Fase "arranque inmediato".

- [ ] **Inspeccionar el WSDL real** (`api.reliablesite.net/inventory.svc?wsdl`) y confirmar los puntos que quedaron abiertos en SPECS §3.1:
  - [ ] Nombres exactos de operaciones (¿`GetServers`? ¿`ListServers`?)
  - [ ] Dónde van las credenciales (header SOAP / parámetro / WS-Security)
  - [ ] Campos reales del response y su mapeo a `ServerListing`
- [ ] `api_source.py` con `zeep`, implementando la misma interfaz `InventorySource`
- [ ] Fixture de response SOAP + test del mapeo
- [ ] Cambiar default a `INVENTORY_SOURCE=api`
- [ ] Fallback automático al scraper si la API falla N veces seguidas

**Hecho cuando:** el sistema corre sobre la API oficial y el scraper solo entra si la API se cae.

---

## Fase 6 — Deploy y hardening

**Objetivo:** que sobreviva sin supervisión.

- [ ] `deploy/reliable-bot.service` (systemd) con `Restart=on-failure` y `MemoryMax=400M`
- [ ] Desplegar en `/opt/reliable-bot` con venv propio, `.env` en modo `600`
- [ ] `logrotate` para `/var/log/reliable-bot/app.log` (diario, 7 copias, comprimido)
- [ ] `systemctl enable` + prueba de reboot: confirmar que levanta solo
- [ ] Prueba de resiliencia: matar el proceso → systemd lo revive
- [ ] Verificar consumo real de RAM en reposo (`systemctl status`) contra el presupuesto de ~60–90 MB

**Hecho cuando:** la VPS se reinicia, el bot vuelve solo, y el consumo de memoria está dentro de lo esperado.

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
