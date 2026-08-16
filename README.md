# 🖥️ ReliableWatch

**Monitor de disponibilidad de servidores dedicados en [ReliableSite.net](https://www.reliablesite.net/) con avisos por Telegram.**

Le dices al bot qué servidor buscas. Él revisa el inventario cada 10 minutos y te avisa en el momento en que aparece uno que encaja.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![RAM](https://img.shields.io/badge/RAM-~80MB-green)
![Deploy](https://img.shields.io/badge/deploy-systemd-lightgrey)

> **Nota:** este README describe el proyecto **terminado**, tal como se ve al completar la ruta de [`ROADMAP.md`](./ROADMAP.md). Las especificaciones técnicas completas están en [`SPECS.md`](./SPECS.md).

---

## ¿Por qué?

El stock de servidores dedicados baratos en ReliableSite rota rápido: aparece una oferta buena y desaparece en horas. Revisar la web a mano varias veces al día no es viable. ReliableWatch lo hace por ti desde una VPS mínima (1 vCPU / 1 GB RAM) por céntimos al mes.

---

## Así se usa

```
Tú  ▸  /watch cpu=E3-1230 ram=32 loc=NYC precio=80

Bot ▸  ✅ Watch #4 creado
       CPU: E3-1230 · RAM: ≥32GB · Ubicación: NYC · Precio: ≤$80
       Revisando cada 10 min. Te aviso cuando aparezca.
```

*…dos horas después, sin que hagas nada:*

```
Bot ▸  🎯 ¡Disponible! (watch #4 — "E3 barato NYC")

       Intel Xeon E3-1230v2
       32GB DDR3 · 2x480GB SSD
       📍 New York City
       💵 $69.00/mes
       🔗 https://www.reliablesite.net/...

       Stock: 2 disponibles
```

---

## Características

- 🔔 **Avisos instantáneos por Telegram** — sin abrir la web, sin refrescar nada
- 🎯 **Filtros combinables** — CPU, RAM mínima, almacenamiento, ubicación y precio máximo
- 📋 **Múltiples watches a la vez** — busca varias configuraciones en paralelo
- 🔁 **Sin spam** — no repite el mismo aviso; solo re-notifica si el servidor desaparece y vuelve, o pasadas 6h como recordatorio
- 🪶 **Ultraligero** — ~80 MB de RAM, un solo proceso, sin navegador headless ni base de datos externa
- 🔌 **Dos fuentes de datos** — API oficial de inventario (principal) con scraping como respaldo automático
- 🔒 **Privado** — solo responde a usuarios que apruebes explícitamente
- ♻️ **Autorecuperable** — systemd lo revive si se cae, y te avisa si ReliableSite deja de responder

---

## Requisitos

- VPS con **1 vCPU / 1 GB RAM** (Debian 12 o Ubuntu 22.04+)
- **Python 3.11+**
- Un **bot de Telegram** (gratis, vía [@BotFather](https://t.me/BotFather))
- Nada más — la Inventory API de ReliableSite resultó ser pública, sin credenciales. `RELIABLESITE_API_USER`/`RELIABLESITE_API_KEY` quedan en `.env.example` por si eso cambia; hoy no se usan.

---

## Instalación

```bash
# 1. Swap — imprescindible con solo 1GB de RAM
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. Usuario dedicado y código
sudo useradd -r -m -d /opt/reliable-bot reliable-bot
sudo -u reliable-bot git clone https://github.com/DaBSTW/reliable.git /opt/reliable-bot
cd /opt/reliable-bot

# 3. Entorno virtual
sudo -u reliable-bot python3 -m venv venv
sudo -u reliable-bot venv/bin/pip install -r requirements.txt

# 4. Configuración
sudo -u reliable-bot cp .env.example .env
sudo -u reliable-bot chmod 600 .env
sudo -u reliable-bot nano .env        # rellenar token y admin chat id

# 5. Servicio
sudo cp deploy/reliable-bot.service /etc/systemd/system/
sudo systemctl enable --now reliable-bot
sudo systemctl status reliable-bot
```

---

## Configuración

Todo vive en `.env` (permisos `600`, nunca en git):

```ini
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
ADMIN_CHAT_ID=987654321

# Fuente de datos: api | scraper
INVENTORY_SOURCE=api
RELIABLESITE_API_USER=
RELIABLESITE_API_KEY=

# Polling
POLL_INTERVAL_SECONDS=600     # 10 minutos
RENOTIFY_HOURS=6              # recordatorio si sigue disponible

# Rutas
DB_PATH=/opt/reliable-bot/data/watches.db
LOG_PATH=/var/log/reliable-bot/app.log
LOG_LEVEL=INFO
```

---

## Todo por botones

El bot se usa entero a golpe de botón — no hace falta escribir ningún comando ni sintaxis:

```
Tú  ▸  /start

Bot ▸  👋 Bienvenido a ReliableWatch...
       ┌─────────────────────┐
       │ ➕ Nuevo watch        │
       │ 📋 Mis watches        │
       │ 📦 Stock disponible   │
       │ 📊 Estado del sistema │
       └─────────────────────┘
```

**➕ Nuevo watch** abre un asistente paso a paso: elegís qué filtros fijar (CPU, RAM,
almacenamiento, ubicación, precio, nombre) tocando botones — RAM y precio tienen valores
comunes ya armados, la ubicación se arma con los datacenters que hay en stock ahora mismo, y
solo pide escribir algo cuando el valor es realmente libre (el modelo de CPU, el nombre). En
**cada pantalla** hay ⬅️ **Atrás** y ❌ **Cancelar** — nunca quedás sin salida. **📋 Mis
watches** pone un 🗑️ por cada watch para borrarlo con un toque, y un botón para volver al
menú principal.

Cuando alguien no autorizado toca `/start`, el bot le avisa al admin con un botón
**✅ Autorizar** — tampoco hace falta que el admin escriba `/approve <chat_id>` a mano.

### Comandos de texto (opcionales)

Si preferís escribir, todo también funciona por comando — quedan además en el menú "/" nativo
de Telegram, con descripción:

| Comando | Qué hace |
|---|---|
| `/start` | Alta y ayuda |
| `/watch <filtros>` | Crea una búsqueda nueva |
| `/list` | Muestra tus watches activos con su id |
| `/remove <id>` | Elimina un watch |
| `/stock` | Inventario disponible ahora mismo, sin filtrar |
| `/status` | Salud del sistema: último poll, próximo poll, watches activos |
| `/approve <chat_id>` | *(solo admin)* autoriza a otro usuario |

#### Sintaxis de `/watch`

Formato `clave=valor`, separados por espacios. **Todos los filtros son opcionales** — lo que omitas, no filtra.

| Filtro | Significado | Ejemplo |
|---|---|---|
| `cpu=` | Texto contenido en el modelo de CPU | `cpu=E5-2680` |
| `ram=` | RAM **mínima** en GB | `ram=64` |
| `disco=` | Texto contenido en el almacenamiento | `disco=NVMe` |
| `loc=` | Ubicación del datacenter | `loc=NYC` |
| `precio=` | Precio **máximo** en USD/mes | `precio=120` |
| `nombre=` | Alias para identificarlo en `/list` | `nombre=servidor-juegos` |

```bash
/watch cpu=E5-2680 ram=64 disco=NVMe loc=LA precio=120 nombre=proyecto-x
/watch ram=128 precio=200          # cualquier CPU, cualquier sitio
/watch loc=Miami                    # todo lo que salga en Miami
```

---

## Ejemplo de `/status`

```
Bot ▸  📊 Estado del sistema

       ✅ Último poll: hace 3 min (api) — 47 servidores vistos
       ⏭️  Próximo poll: en 7 min
       👀 Watches activos: 3
       ⏱️  Uptime: 12d 4h
       💾 RAM: 78 MB
```

---

## Arquitectura en 30 segundos

```
Telegram ──▶ Bot (long polling) ──▶ SQLite (watches)
                                        ▲
                                        │
Scheduler (cada 10 min) ──▶ InventorySource ──▶ Matcher ──▶ Notificador ──▶ Telegram
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            API SOAP oficial      Scraper HTML
              (principal)          (respaldo)
```

**Un solo proceso Python.** El bot, el planificador y el consultor de inventario comparten el mismo event loop asyncio — clave para caber cómodo en 1 GB de RAM. Detalle completo en [`SPECS.md`](./SPECS.md).

---

## Estructura del proyecto

```
reliable/
├── README.md · SPECS.md · ROADMAP.md · CODESTYLE.md
├── requirements.txt · requirements-dev.txt · .env.example · pyproject.toml
├── deploy/reliable-bot.service · reliable-bot.logrotate
├── src/
│   ├── main.py            # arranca bot + scheduler + poller
│   ├── config.py · db.py · errors.py
│   ├── sources/           # base.py · api_source.py · scraper_source.py · fallback_source.py
│   ├── matcher.py         # ¿este servidor cumple lo que pediste?
│   ├── poller.py          # ciclo: source -> matcher vs. watches -> notifier
│   ├── notifier.py
│   └── bot/               # handlers.py · auth.py · messages.py · watch_filters.py
│                           # watch_wizard.py · access_requests.py
└── tests/                 # fixtures/ + tests unitarios e integración, sin red real
```

---

## Desarrollo

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest                       # tests con fixtures, sin tocar la red
python -m src.main           # ejecutar en local
```

Los tests del matcher y de los parsers corren contra fixtures estáticas, así que no dependen de que ReliableSite esté arriba ni consumen cuota de la API.

---

## Consumo de recursos

| Métrica | Valor |
|---|---|
| RAM en reposo | ~60–90 MB |
| RAM en pico (durante un poll) | ~120–150 MB |
| Límite impuesto por systemd | 400 MB |
| Disco | <50 MB (código + SQLite + logs rotados) |
| Puertos entrantes | **Ninguno** — solo tráfico saliente |

---

## Solución de problemas

| Síntoma | Causa probable / arreglo |
|---|---|
| El bot no responde | `systemctl status reliable-bot`; comprobar `TELEGRAM_BOT_TOKEN` |
| «No autorizado» | Tu `chat_id` no está en la whitelist → pide `/approve` al admin |
| Aviso «sin poder consultar» | ReliableSite bloquea o cambió el HTML → probar `INVENTORY_SOURCE=api` |
| El servicio se reinicia solo | Puede ser el tope de `MemoryMax=400M`; revisar `journalctl -u reliable-bot` |
| Nunca llegan avisos | Verificar con `/stock` que sí llega inventario, y con `/list` que los filtros no sean demasiado estrictos |

---

## Aviso legal

Herramienta no oficial, sin relación con ReliableSite.Net LLC. Está pensada para uso personal, respetando los Términos de Servicio de ReliableSite y con una frecuencia de consulta conservadora (10 min por defecto). Se recomienda usar la **API oficial de inventario** siempre que sea posible; el modo scraping es un respaldo.
