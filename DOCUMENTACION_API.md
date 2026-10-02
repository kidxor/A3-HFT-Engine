# Manual y Documentación de la API — A3 HFT Engine & Pro Terminal v6.0

Documentación oficial de la **API REST, Streaming SSE, AI Evolution Core y Market Data Proxy (MDP)** del motor A3 HFT Engine v6.0 (Proyecto Agustín).

---

## 1. Arquitectura de Datos: ¿Cómo recibe la información nuestra API?

**Nuestra API recibe la información directamente desde Bybit / KuCoin en tiempo real.**

```
  ┌──────────────────┐
  │  Bybit / KuCoin  │ (Petición L2 cada 300ms por símbolo)
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 A3 Market Data Proxy (MDP)                  │
  │  - Thread de fondo en segundo plano                         │
  │  - Almacena libros de órdenes L2 y tickers en RAM          │
  │  - Valida la frescura de los datos (timestamp age_ms <50ms)  │
  └────────┬────────────────────────────────────────────────────┘
           │
           ├───────────────────────────────┐
           ▼                               ▼
  ┌──────────────────┐            ┌──────────────────┐
  │  Bots Internos   │            │  Nuestra API     │
  │  (0ms latencia)  │            │  GET /proxy/*    │
  └──────────────────┘            └──────────────────┘
                                           │
                                           ▼
                                 Clientes / Apps / Web UI
```

---

## 2. Base URL y Formato de Respuestas

- **Base URL**: `http://localhost:8005` (o el puerto configurado en la variable de entorno `PORT`)
- **Headers Estándar**:
  - `Content-Type: application/json`
  - `Access-Control-Allow-Origin: *` (CORS Habilitado)

---

## 3. Endpoints de Datos de Mercado (`/proxy/*`)

### 3.1 Obtener Cotizaciones de Todos los Pares
Retorna precio medio (*mid_price*), punta de compra (*best_bid*), punta de venta (*best_ask*), *spread* y estado de frescura de todos los símbolos monitoreados.

- **Método**: `GET`
- **Ruta**: `/proxy/all_tickers`
- **Ejemplo**:
```bash
curl -s http://localhost:8005/proxy/all_tickers
```
- **Respuesta (200 OK)**:
```json
{
  "SOL-USDT": {
    "symbol": "SOL-USDT",
    "best_bid": 103.84,
    "best_ask": 103.85,
    "mid_price": 103.845,
    "spread": 0.01,
    "timestamp_ms": 1785580466445,
    "is_fresh": true
  },
  "BTC-USDT": {
    "symbol": "BTC-USDT",
    "best_bid": 80933.7,
    "best_ask": 80933.8,
    "mid_price": 80933.75,
    "spread": 0.1,
    "timestamp_ms": 1785580466913,
    "is_fresh": true
  },
  "ETH-USDT": {
    "symbol": "ETH-USDT",
    "best_bid": 2506.38,
    "best_ask": 2506.39,
    "mid_price": 2506.385,
    "spread": 0.01,
    "timestamp_ms": 1785580467241,
    "is_fresh": true
  }
}
```

---

### 3.2 Obtener Libro de Órdenes (Orderbook L2)
Retorna las 20 mejores puntas de compra (*bids*) y venta (*asks*) en formato L2.

- **Método**: `GET`
- **Ruta**: `/proxy/orderbook?symbol={SYMBOL}`
- **Ejemplo**:
```bash
curl -s "http://localhost:8005/proxy/orderbook?symbol=SOL-USDT"
```

---

### 3.3 Estado y Salud del Proxy
- **Método**: `GET`
- **Ruta**: `/proxy/status`
- **Ejemplo**:
```bash
curl -s http://localhost:8005/proxy/status
```

---

## 4. Endpoints del Agente Autónomo IA (`/api/ai/*`)

### 4.1 Estado del Optimizador IA Local
Retorna el estado de auditoría en vivo del modelo local (`llama3.2:1b`), régimen de mercado detectado, Sharpe Ratio sandbox y Alpha generado.

- **Método**: `GET`
- **Ruta**: `/api/ai/status`
- **Ejemplo**:
```bash
curl -s http://localhost:8005/api/ai/status
```
- **Respuesta (200 OK)**:
```json
{
  "engine": "AIOptimizerEngine",
  "llm_model": "llama3.2:1b",
  "is_active": true,
  "last_update_str": "00:32:15",
  "market_regime": "TENDENCIA PRO",
  "current_sharpe": 2.45,
  "sandbox_sharpe": 2.82,
  "alpha_generated_usd": 0.0,
  "calibration_cycles": 0,
  "ai_hypothesis": "Optimizando hiperparámetros en Sandbox RAM sobre velas de 5m. Cero costo de API externa."
}
```

---

### 4.2 Forzar Optimización IA Instantánea
Dispara un ciclo inmediato de simulación Sandbox en RAM y auditoría LLM.

- **Método**: `POST`
- **Ruta**: `/api/ai/trigger`
- **Ejemplo**:
```bash
curl -X POST http://localhost:8005/api/ai/trigger
```

---

### 4.3 Activar / Pausar Auto-Evolución
- **Método**: `POST`
- **Ruta**: `/api/ai/toggle`
- **Ejemplo**:
```bash
curl -X POST http://localhost:8005/api/ai/toggle
```

---

## 5. Endpoints de Estado y Operación del Engine (`/api/*`)

### 5.1 Streaming SSE en Tiempo Real
Suscribe a un flujo Server-Sent Events (SSE) que transmite el estado consolidado de carteras, tickers, posiciones activas y métricas de IA cada 200ms.

- **Método**: `GET`
- **Ruta**: `/api/stream`

---

### 5.2 Obtener Estado Completo
- **Método**: `GET`
- **Ruta**: `/api/state`
- **Ejemplo**:
```bash
curl -s http://localhost:8005/api/state
```

---

### 5.3 Control de Ejecución
- **Iniciar Motor:** `GET /api/start`
- **Pausar Motor:** `GET /api/stop`
- **Reiniciar Engine:** `GET /api/restart`

---

### 5.4 Actualización de Capital Inicial Configurado
Actualiza dinámicamente el capital asignado al portafolio y sincroniza la interfaz.

- **Método**: `POST`
- **Ruta**: `/api/config`
- **Body JSON**:
```json
{
  "capital": 200.0
}
```
- **Ejemplo**:
```bash
curl -X POST http://localhost:8005/api/config \
  -H "Content-Type: application/json" \
  -d '{"capital": 200.0}'
```

---

### 5.5 Reiniciar Estadísticas y Base de Datos (1-Clic Reset)
Limpia la base de datos de trades (`trades.db`) y restablece las métricas de rendimiento con un monto base especificado.

- **Método**: `GET`
- **Ruta**: `/api/reset_stats?capital={CAPITAL}`
- **Ejemplo**:
```bash
curl -s "http://localhost:8005/api/reset_stats?capital=200"
```
- **Respuesta**:
```json
{
  "status": "reset",
  "capital": 200.0,
  "trades_wiped": true
}
```

---

### 5.6 Reset de Guardia de Riesgo (`RiskGuard`)
- **Método**: `GET`
- **Ruta**: `/api/reset_risk`

---

## 6. Ejemplo Integrado de Consumo en Python

```python
import requests

BASE_URL = "http://localhost:8005"

# 1. Obtener estado consolidado del motor
state = requests.get(f"{BASE_URL}/api/state").json()
print("Balance Total:", state["portfolio"]["total_capital"])
print("Estrategia Activa:", state["portfolio"]["active_strategy"])

# 2. Consultar el estado del optimizador de IA Local
ai_status = requests.get(f"{BASE_URL}/api/ai/status").json()
print("Régimen de Mercado IA:", ai_status.get("market_regime"))
print("Alpha IA Generado:", ai_status.get("alpha_generated_usd"))

# 3. Consultar cotización L2 en vivo
ticker = requests.get(f"{BASE_URL}/proxy/ticker?symbol=SOL-USDT").json()
print(f"SOL-USDT Mid Price: ${ticker['mid_price']} (Fresh: {ticker['is_fresh']})")
```

---

*A3 Core Systems — Documentación Oficial de la API v6.0*
