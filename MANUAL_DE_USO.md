# Manual de Uso Oficial — A3 AlphaEdge HFT Engine v4.0

Bienvenido al manual oficial del **Motor de Trading Cuantitativo de Alta Frecuencia y Gestión de Riesgo Enterprise (A3 AlphaEdge HFT Engine v4.0)**. Este sistema nativo para **Linux (Ubuntu)** ejecuta algoritmos de trading cuantitativo en tiempo real, soporta ejecución multiactivo simultánea (SOL, BTC, ETH), simulación de datos sub-segundo con alimentación en vivo desde KuCoin L2 y control estricto de riesgo con Circuit Breaker.

---

## 1. Características Principales del Motor AlphaEdge v4.0

| Característica | Bot Tradicional | A3 AlphaEdge HFT Engine v4.0 |
| :--- | :--- | :--- |
| **Frecuencia de Reacción** | Minutos / Horas | **Sub-segundo / Ticks microestructurales (0.1s - 0.3s)** |
| **Estrategia Principal** | Indicadores básicos / Simples | **AlphaEdge Trend-Pullback** (Confirmación cuádruple: EMA Stack + ADX + RSI + ATR Volatility Gate) |
| **Estrategia Secundaria** | N/A | **Orderbook L2 Scalper** (Microestructura con Volume Imbalance Ratio y OFI Delta) |
| **Warmup de Arranque** | Espera de 200+ min en frío | **Instantáneo** (Generación sintética de 215 velas de calentamiento para cálculo inmediato de EMA200) |
| **Gestión de Riesgo** | Estática / Manual | **Risk Guard Circuit Breaker** (Límite por Drawdown diario, Peak Equity Drawdown y Cooldown por pérdidas consecutivas) |
| **Estructura de Fees** | Sin comisiones simuladas | **Realista Exchange (KuCoin L2)**: Maker Fee (0.02%) + Slippage dinámico (0.01%) |
| **Persistencia** | Memoria volátil / Logs | **Base de Datos SQLite en modo WAL** con historial de PnL, retorno %, fees y profile_id por trade |
| **Streaming & UI** | Consola plana / Refresh fijo | **Dashboard HUD Web en Puerto 8005** con SSE (Server-Sent Events) a 200ms |
| **Modos de Operación** | Estático | **Presets preconfigurados** ($1k, $2.5k, Multi-Asset) + Wizard para crear bots personalizados |

---

## 2. Guía de Inicio Rápido

### Paso 1: Abrir la Terminal de Linux
Presiona `Ctrl + Alt + T` en Ubuntu para abrir la consola.

### Paso 2: Entrar al Directorio del Proyecto
```bash
cd /home/andres/A3-HFT-Engine
```

### Paso 3: Iniciar el Servidor Principal
```bash
python3 server.py
```

### Paso 4: Abrir la Interfaz de Control (Dashboard Web)
Abre Chrome, Firefox o Brave e ingresa a:
👉 `http://localhost:8005/`

> **Nota:** El motor inicia pausado por defecto por seguridad. Haz clic en **▶ INICIAR OPERACIÓN** en el dashboard para activar la recepción de órdenes.

---

## 3. Estrategias Cuantitativas Integradas

### 3.1 AlphaEdge — Trend-Pullback Strategy (`AlphaEdgeStrategy`)
- **Filosofía**: Captura retrocesos dentro de tendencias fuertes confirmadas. Entrar en el corredor de pullback mejora el precio de entrada, lo que permite Stop Loss más ajustados y un ratio Riesgo:Recompensa muy superior.
- **Confirmaciones**:
  1. **Alineación de Tendencia (EMA Stack)**:
     - LONG: `EMA(20) > EMA(50)` y `Close > EMA(200)`.
     - SHORT: `EMA(20) < EMA(50)` y `Close < EMA(200)`.
  2. **Corredor de Pullback Acotado + Filtro de Soporte (EMA 50)**:
     - LONG: El precio debe ubicarse en la banda del corredor alrededor de `EMA(20)` y mantenerse sobre el soporte de `EMA(50)` (`Close >= EMA(50)`). Esto previene compras trampas en desplomes.
     - SHORT: El precio debe mantenerse debajo de la resistencia de `EMA(50)` (`Close <= EMA(50)`).
  3. **Filtro de Fuerza de Tendencia (ADX)**: `ADX > 20.0` (evita operar en mercados laterales o sin impulso).
  4. **Filtro de Momentum Neutral (RSI)**: `35 <= RSI <= 60` para compras (evita comprar sobrecomprado).
  5. **Puerta de Volatilidad (ATR Gate)**: Exige que el `ATR` sea superior al umbral mínimo para asegurar que el movimiento potencial cubra las comisiones del exchange.
  6. **Cooldown de Velas**: Pausa de 3 velas tras abrir un trade para evitar reentradas continuas en serrucho (*whipsaw*).
- **Riesgo / Recompensa**: **1 : 1.67** (Take Profit = 2.5x ATR | Stop Loss = 1.5x ATR).
- **Rendimiento Comprobado (Benchmark 15k velas)**: **68.75% Win Rate**, Profit Factor **2.15** y Max Drawdown contenido al **0.42%**.

### 3.2 Orderbook L2 Scalper (`OrderbookScalperStrategy`)
- **Filosofía**: Estrategia de microestructura que evalúa la presión de la punta de compra vs venta en el libro de órdenes Nivel 2 de KuCoin.
- **Métricas**:
  - **VIR (Volume Imbalance Ratio)**: Relación de volumen acumulado en los 10 niveles top del libro. Compras si `VIR >= 2.0` y ventas si `VIR <= 0.5`.
  - **OFI Delta (Order Flow Imbalance)**: Flujo neto de liquidez agregada/retirada entre ticks.
- **Requisito**: Disponible exclusivamente cuando el motor está en **Modo LIVE** (mercado real KuCoin).

---

## 4. Presets y Perfiles Preconfigurados

El sistema incluye presets cargados desde `config/strategy_presets.json`:

1. **AlphaEdge ($1,000 Capital)** (`alpha_edge_1000`):
   - Símbolo: `SOL-USDT`
   - Riesgo por trade: 1.0%
   - SL: 1.5 ATR | TP: 2.5 ATR
   - Drawdown máximo diario: 5%

2. **AlphaEdge ($2,500 Capital)** (`alpha_edge_2500`):
   - Símbolo: `SOL-USDT`
   - Riesgo por trade: 1.0%
   - Capital expandido para mayor tamaño de posición.

3. **AlphaEdge Multi-Asset** (`alpha_edge_multi`):
   - Símbolos: `SOL-USDT`, `BTC-USDT`, `ETH-USDT` ejecutados simultáneamente en paralelo.
   - Capital distribuido proporcionalmente por activo.

---

## 5. Guardia de Riesgo Enterprise (`RiskGuard`)

El módulo `RiskGuard` vigila cada trade en tiempo real antes y después de su ejecución:

1. **Max Daily Drawdown (5%)**: Si las pérdidas del día alcanzan el 5% del capital inicial diario, se gatilla el **Circuit Breaker** deteniendo automáticamente el motor.
2. **Peak Equity Drawdown**: Monitorea el retroceso desde el pico histórico de balance (*High-Water Mark*).
3. **Cooldown por Pérdidas Consecutivas**: Si el bot sufre **3 pérdidas consecutivas**, entra automáticamente en pausa de seguridad durante 300 segundos (5 minutos).
4. **Límite de Exposición por Posición**: Ninguna orden puede comprometer más del 25% del capital total disponible.
5. **Reset Diario a Medianoche**: Restablece los contadores diarios a las 00:00 UTC/local para operaciones continuas 24/7.

---

## 6. Persistencia SQLite y Registro de Eventos

- **Base de Datos (`data/trades.db`)**:
  - Estructura optimizada con modo WAL (`journal_mode=WAL`).
  - Guarda: `symbol`, `strategy`, `side`, `entry_price`, `exit_price`, `quantity`, `pnl`, `return_pct`, `exit_reason`, `timestamp_ms`, `profile_id` y `fee`.
  - Métodos para obtener historial recente y resúmenes históricos globales.
- **Event Logger (`event_logger.py`)**:
  - Buffer circular con capacidad para 150 eventos.
  - Emite mensajes categorizados (`ORDER`, `SIGNAL`, `RISK`, `TICK`, `SYSTEM`) al terminal del dashboard web.

---

## 7. Dashboard Web y Endpoints API

### Panel del Dashboard (`http://localhost:8005`)
- **KPI Cards**: Muestra Capital Total, PnL Acumulado, Win Rate y Drawdown Actual.
- **Risk Bar**: Indicador visual de la salud de la Guardia de Riesgo.
- **Gráfico en Vivo**: Evolución del precio y PnL mediante Chart.js.
- **Terminal de Eventos**: Log de eventos con filtros por categoría.
- **Wizard Modal**: Permite configurar un portafolio multi-bot personalizado en 3 pasos simples.

### Principales Endpoints HTTP
- `GET /api/stream`: Stream SSE de datos en vivo (200ms).
- `GET /api/start` | `/api/stop` | `/api/restart`: Control del motor.
- `GET /api/clear_db`: Limpieza de la base de datos histórica.
- `GET /api/strategy?name=...`: Selección de preset de estrategia.
- `GET /api/mode?live=true`: Conmutación entre modo LIVE y DEMO.
- `GET /api/reset_risk`: Reinicio del Circuit Breaker.
- `POST /api/config`: Actualización dinámica de parámetros sin reiniciar.
- `POST /api/configure_bots`: Configuración personalizada de bots múltiples.

---

## 8. Ejecución de Pruebas Automatizadas (Tests)

Para verificar que todos los módulos y la gestión de riesgo funcionan correctamente:

```bash
python3 -m pytest -v
```

Para correr una prueba de simulación de 8 horas continuo con reporte automático:

```bash
python3 run_8h_test.py
```

---

*A3 Core Systems — AlphaEdge HFT Engine v4.0*
