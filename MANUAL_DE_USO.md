# Manual de Uso Oficial — A3 AlphaEdge HFT Engine v4.2

Bienvenido al manual oficial del **Motor de Trading Cuantitativo, Servidor Proxy de Mercado Local y Gestión de Riesgo Enterprise (A3 AlphaEdge Engine v4.2)**.

Este sistema nativo para **Linux (Ubuntu)** ejecuta algoritmos de trading cuantitativo en tiempo real, soporta ejecución multiactivo simultánea (SOL, BTC, ETH, ADA, XRP, AVAX, DOT, LINK), simulación de datos sub-segundo con alimentación en vivo desde KuCoin L2 mediante un **Market Data Proxy (MDP)** desacoplado de baja latencia y control estricto de riesgo con Circuit Breaker.

---

## 1. Características Principales del Motor AlphaEdge v4.1

| Característica | Bot Tradicional | A3 AlphaEdge HFT Engine v4.2 |
| :--- | :--- | :--- |
| **Frecuencia de Reacción** | Minutos / Horas | **Velas de 5 Minutos construidas con Ticks Sub-segundo** |
| **Alimentación de Mercado** | Consultas directas N x Exchange | **Market Data Proxy (MDP) Local**: 1 consulta por símbolo cada 300ms compartida por todos los bots en RAM |
| **Estrategia Principal** | Indicadores básicos / Simples | **AlphaEdge Trend-Pullback** (Confirmación cuádruple: EMA Stack + ADX + RSI + ATR Volatility Gate) |
| **Estrategia Secundaria** | N/A | **Orderbook L2 Scalper** (Microestructura con Volume Imbalance Ratio y OFI Delta) |
| **Warmup de Arranque** | Espera de 200+ min en frío | **Instantáneo** (Generación sintética de 215 velas de calentamiento para cálculo inmediato de EMA200) |
| **Gestión de Riesgo** | Estática / Manual | **Risk Guard Circuit Breaker** (Límite por Drawdown diario, Peak Equity Drawdown y Cooldown por pérdidas consecutivas) |
| **Estructura de Comisiones**| Sin comisiones simuladas | **Realista Exchange (KuCoin L2)**: Maker/Taker Fee (0.10% c/u = 0.20% round-trip) + Slippage dinámico |
| **Persistencia & Índices** | Memoria volátil / Logs | **Base de Datos SQLite en modo WAL + 4 Índices** (`id DESC`, `symbol+strategy`, `pnl`, `profile_id`) con caché de 64MB |
| **Streaming & UI** | Consola plana / Refresh fijo | **Dashboard HUD Web en Puerto 8005** con SSE (Server-Sent Events) a 200ms y gráfico interactivo |
| **Modos de Operación** | Estático | **Presets preconfigurados** ($1k, $2.5k, Multi-Asset) + Wizard para crear bots personalizados |

---

## 2. Guía de Inicio Rápido

### Paso 1: Abrir la Terminal de Linux
Presiona `Ctrl + Alt + T` en Ubuntu para abrir la consola.

### Paso 2: Entrar al Directorio del Proyecto
```bash
cd /home/andres/A3-HFT-Engine
```

### Paso 3: Iniciar el Servidor Principal (con Market Data Proxy activo)
```bash
python3 server.py
```

### Paso 4: Abrir la Interfaz de Control (Dashboard Web)
Abre Chrome, Firefox o Brave e ingresa a:
👉 `http://localhost:8005/`

> **Nota:** El motor arranca por defecto en **Modo LIVE** con datos reales de mercado procesados a través del proxy local. Puedes pausar/iniciar en cualquier momento mediante los botones del dashboard.

---

## 3. Arquitectura de Datos: Market Data Proxy (MDP v1.0)

Para evitar saturar la API pública de KuCoin y prevenir bloqueos por *rate limits* al ejecutar múltiples bots o monedas en paralelo, el motor acopla su propia **API Proxy de Datos de Mercado Local**.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       A3-HFT-Engine Process                             │
│                                                                         │
│  KuCoin REST API       ┌─────────────────────┐      ┌────────────────┐ │
│  (1 req/símbolo/300ms) │  Market Data Proxy  │──┐   │  Bot SOL-USDT  │ │
│ ─────────────────────▶ │  (background thread)│  ├──▶│  Bot BTC-USDT  │ │
│                        └──────────┬──────────┘  └──▶│  Bot ETH-USDT  │ │
│                                   │                 └────────────────┘ │
│                                   │ expone nuestra                     │
│                                   ▼ propia API                         │
│                        GET /proxy/orderbook?symbol=X                    │
│                        GET /proxy/ticker?symbol=X                       │
│                        GET /proxy/all_tickers                           │
│                        GET /proxy/status                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Criptomonedas & Pares Soportados por el Proxy
El proxy mantiene cotizaciones y libros de órdenes actualizados en memoria para los siguientes pares:
- `SOL-USDT` (Solana)
- `BTC-USDT` (Bitcoin)
- `ETH-USDT` (Ethereum)
- `ADA-USDT` (Cardano)
- `XRP-USDT` (Ripple)
- `AVAX-USDT` (Avalanche)
- `DOT-USDT` (Polkadot)
- `LINK-USDT` (Chainlink)

---

## 4. Endpoints de Nuestra API Local Proxy (`/proxy/*`)

Nuestra propia API permite consumir cotizaciones y libros de órdenes en tiempo real con latencia de RAM local (0ms de retraso de red externa):

### 4.1 Orderbook L2 Cacheado
- **Endpoint**: `GET /proxy/orderbook?symbol=SOL-USDT`
- **Formato**: Formato nativo KuCoin L2 20 niveles.
- **Ejemplo de Respuesta**:
```json
{
  "code": "200000",
  "data": {
    "bids": [["72.83", "112.8"], ["72.82", "161.2"]],
    "asks": [["72.84", "85.4"], ["72.85", "140.1"]],
    "time": 1785580000000
  }
}
```

### 4.2 Ticker de un Símbolo Específico
- **Endpoint**: `GET /proxy/ticker?symbol=BTC-USDT`
- **Ejemplo de Respuesta**:
```json
{
  "symbol": "BTC-USDT",
  "best_bid": 63041.9,
  "best_ask": 63042.0,
  "mid_price": 63041.95,
  "spread": 0.1,
  "timestamp_ms": 1785580000000,
  "is_fresh": true
}
```

### 4.3 Tickers de Todas las Monedas
- **Endpoint**: `GET /proxy/all_tickers`
- **Descripción**: Devuelve los precios de mid, bid, ask y spread de todas las monedas monitoreadas en una sola llamada.

### 4.4 Estado y Salud del Proxy
- **Endpoint**: `GET /proxy/status`
- **Descripción**: Muestra si el proxy está activo, intervalo de refresco, número de símbolos y salud de cada mercado.

---

## 5. Estrategias Cuantitativas Integradas

### 5.1 AlphaEdge — Trend-Pullback Strategy (`AlphaEdgeStrategy`)
- **Filosofía**: Captura retrocesos dentro de tendencias fuertes confirmadas. Entrar en el corredor de pullback mejora el precio de entrada, lo que permite Stop Loss más ajustados y un ratio Riesgo:Recompensa muy superior.
- **Confirmaciones**:
  1. **Alineación de Tendencia (EMA Stack)**:
     - LONG: `EMA(20) > EMA(50)` y `Close > EMA(200)`.
     - SHORT: `EMA(20) < EMA(50)` y `Close < EMA(200)`.
  2. **Corredor de Pullback Acotado + Filtro de Soporte (EMA 50)**:
     - LONG: El precio debe ubicarse en la banda del corredor alrededor de `EMA(20)` y mantenerse sobre el soporte de `EMA(50)` (`Close >= EMA(50)`).
     - SHORT: El precio debe mantenerse debajo de la resistencia de `EMA(50)` (`Close <= EMA(50)`).
  3. **Filtro de Fuerza de Tendencia (ADX)**: `ADX > 25.0` (Requiere tendencias fuertes consolidadas).
  4. **Filtro de Momentum Neutral (RSI)**: `35 <= RSI <= 60` para compras.
  5. **Puerta de Volatilidad (ATR Gate)**: Exige que el `ATR` sea superior a un umbral mínimo (`0.4%` del precio actual) para garantizar que el movimiento del mercado puede cubrir holgadamente las comisiones (`0.20%` round-trip).
  6. **Cooldown de Velas**: Pausa de 3 velas (15 minutos) tras abrir un trade para evitar reentradas continuas en el mismo nivel.
- **Riesgo / Recompensa Dinámico por Volatilidad**: **1 : 2.33** (Take Profit = 3.5x ATR 5m | Stop Loss = 1.5x ATR 5m). R:R neto efectivo descontando comisiones: ~1.7:1.

### 5.2 Orderbook L2 Scalper (`OrderbookScalperStrategy`)
- **Filosofía**: Estrategia de microestructura que evalúa la presión de la punta de compra vs venta en el libro de órdenes Nivel 2.
- **Métricas**:
  - **VIR (Volume Imbalance Ratio)**: Relación de volumen acumulado en los 10 niveles top del libro. Compras si `VIR >= 2.0` y ventas si `VIR <= 0.5`.
  - **OFI Delta (Order Flow Imbalance)**: Flujo neto de liquidez agregada/retirada entre ticks.

---

## 6. Guardia de Riesgo Enterprise (`RiskGuard`)

El módulo `RiskGuard` vigila cada trade en tiempo real antes y después de su ejecución:

1. **Max Daily Drawdown (5%)**: Si las pérdidas del día alcanzan el 5% del capital inicial diario, se gatilla el **Circuit Breaker** deteniendo automáticamente el motor.
2. **Peak Equity Drawdown**: Monitorea el retroceso desde el pico histórico de balance (*High-Water Mark*).
3. **Cooldown por Pérdidas Consecutivas**: Si el bot sufre **3 pérdidas consecutivas**, entra automáticamente en pausa de seguridad durante 300 segundos (5 minutos).
4. **Límite de Exposición por Posición**: Ninguna orden puede comprometer más del 25% del capital total disponible.
5. **Reset Diario a Medianoche**: Restablece los contadores diarios a las 00:00 UTC/local para operaciones continuas 24/7.

---

## 7. Persistencia SQLite Optimizada y Registro de Eventos

- **Base de Datos (`data/trades.db`)**:
  - Modo WAL (`journal_mode=WAL`) con 64MB de caché en RAM y `synchronous=NORMAL`.
  - **4 Índices SQLite**: `idx_trades_id` (consultas ordenadas), `idx_trades_symbol_strategy`, `idx_trades_pnl` y `idx_trades_profile`.
  - Guarda: `symbol`, `strategy`, `side`, `entry_price`, `exit_price`, `quantity`, `pnl`, `return_pct`, `exit_reason`, `timestamp_ms`, `profile_id` y `fee`.
- **Event Logger (`event_logger.py`)**:
  - Buffer circular optimizado con capacidad para 500 eventos.
  - Emite mensajes categorizados (`ORDER`, `SIGNAL`, `RISK`, `TICK`, `SYSTEM`).

---

## 8. Dashboard Web y Endpoints API Completos

### Panel del Dashboard (`http://localhost:8005`)
- **KPI Cards**: Capital Total, PnL Acumulado, Win Rate, Drawdown Actual y Profit Factor.
- **Badge de Estado**: Muestra `🔴 LIVE REAL` cuando el motor está conectado al Proxy de Mercado.
- **Gráfico en Vivo**: Evolución del precio y PnL mediante Chart.js.
- **Terminal de Eventos**: Log de eventos en tiempo real con filtros por categoría.

### Resumen de Endpoints HTTP

| Tipo | Endpoint | Descripción |
| :--- | :--- | :--- |
| **Stream** | `GET /api/stream` | Stream SSE de datos en vivo (200ms) |
| **Control** | `GET /api/start` / `stop` / `restart` | Inicia, detiene o reinicia la ejecución |
| **Reset DB** | `GET /api/cleardb` | Limpieza física de la tabla de trades y contadores a cero |
| **Risk** | `GET /api/reset_risk` | Reinicio manual del Circuit Breaker |
| **Modo** | `GET /api/mode?live=true` | Cambia entre modo LIVE (Proxy) y DEMO |
| **Config** | `POST /api/config` / `/api/configure_bots` | Configuración dinámica de bots y parámetros |
| **Proxy API** | `GET /proxy/orderbook?symbol=X` | Retorna libro de órdenes L2 cacheado |
| **Proxy API** | `GET /proxy/ticker?symbol=X` | Retorna cotización y spread de una moneda |
| **Proxy API** | `GET /proxy/all_tickers` | Retorna precios de **todas las monedas** |
| **Proxy API** | `GET /proxy/status` | Estado de salud y refresco del proxy local |

---

## 9. Variables de Entorno (Configuración Avanzada)

| Variable | Valor por Defecto | Descripción |
| :--- | :--- | :--- |
| `PORT` | `8005` | Puerto HTTP del servidor y dashboard |
| `LIVE_MODE` | `true` | `true` activa el proxy con datos reales; `false` activa modo demo |
| `AUTO_START_ENGINE` | `true` | Inicia la evaluación de estrategias automáticamente al arrancar |

---

## 10. Despliegue 24/7 en la Nube (Render.com + UptimeRobot)

### Repositorio Oficial en GitHub
- **URL**: `https://github.com/kidxor/A3-HFT-Engine.git`
- **Rama principal**: `main`

### Configuración en Render.com
- **Servicio**: Web Service
- **Entorno**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python3 server.py`
- **Archivos de despliegue**: `render.yaml`, `Procfile`, `requirements.txt`.

---

*A3 Core Systems — AlphaEdge HFT Engine v4.2*
