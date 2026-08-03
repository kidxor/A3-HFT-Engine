# Manual y Documentación de la API — A3 HFT Engine v4.2

Documentación oficial de la **API REST, Streaming SSE y Market Data Proxy (MDP)** del motor A3 HFT Engine.

---

## 1. Arquitectura de Datos: ¿Cómo recibe la información nuestra API?

**Sí, nuestra API recibe la información directamente desde KuCoin en tiempo real.**

### Flujo de Datos
```
  ┌──────────────────┐
  │  KuCoin REST L2  │ (1 petición por símbolo cada 300ms)
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 A3 Market Data Proxy (MDP)                  │
  │  - Thread de fondo en segundo plano                         │
  │  - Almacena libros de órdenes L2 y tickers en RAM          │
  │  - Valida la frescura de los datos (timestamp age_ms)       │
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
                                 Clientes / Apps Externas
```

1. **Hilo Poller de Fondo**: Un hilo secundario dedicado dentro del proceso de Python realiza peticiones HTTP a KuCoin cada 300ms por cada uno de los 8 símbolos monitoreados (`SOL-USDT`, `BTC-USDT`, `ETH-USDT`, `ADA-USDT`, `XRP-USDT`, `AVAX-USDT`, `DOT-USDT`, `LINK-USDT`).
2. **Caché en Memoria (RAM)**: Los libros de órdenes y mejores precios (*bid/ask/mid/spread*) se parsean y guardan en estructuras en RAM.
3. **Servicio Desacoplado**: Tanto los bots de trading como la interfaz web y los clientes externos consumen los datos desde **nuestra API**, asegurando 0 retraso de red interna y evitando que KuCoin bloquee peticiones por exceso de tráfico (*Rate Limiting*).

---

## 2. Base URL y Formato de Respuestas

- **Base URL**: `http://localhost:8005` (o el puerto configurado en la variable `PORT`)
- **Headers Estándar**:
  - `Content-Type: application/json`
  - `Access-Control-Allow-Origin: *` (Soporte CORS habilitado)

---

## 3. Endpoints de Datos de Mercado (`/proxy/*`)

### 3.1 Obtener Cotizaciones de Todas las Monedas
Devuelve el precio actual (*mid_price*), la mejor punta de compra (*best_bid*), la mejor punta de venta (*best_ask*), el *spread* y la frescura de los datos para todas las criptomonedas monitoreadas.

- **Método**: `GET`
- **Ruta**: `/proxy/all_tickers`
- **Ejemplo de Consulta**:
```bash
curl -s http://localhost:8005/proxy/all_tickers
```
- **Respuesta de Ejemplo (200 OK)**:
```json
{
  "SOL-USDT": {
    "symbol": "SOL-USDT",
    "best_bid": 72.81,
    "best_ask": 72.82,
    "mid_price": 72.815,
    "spread": 0.01,
    "timestamp_ms": 1785580466445,
    "is_fresh": true
  },
  "BTC-USDT": {
    "symbol": "BTC-USDT",
    "best_bid": 63043.4,
    "best_ask": 63043.5,
    "mid_price": 63043.45,
    "spread": 0.1,
    "timestamp_ms": 1785580466913,
    "is_fresh": true
  },
  "ETH-USDT": {
    "symbol": "ETH-USDT",
    "best_bid": 1865.24,
    "best_ask": 1865.25,
    "mid_price": 1865.245,
    "spread": 0.01,
    "timestamp_ms": 1785580467241,
    "is_fresh": true
  }
}
```

---

### 3.2 Obtener Cotización de un Símbolo Específico
Devuelve la cotización y spread de una sola moneda.

- **Método**: `GET`
- **Ruta**: `/proxy/ticker?symbol={SYMBOL}`
- **Parámetros Query**:
  - `symbol` (opcional, default `SOL-USDT`): El par de trading deseado (ej. `BTC-USDT`, `ETH-USDT`).
- **Ejemplo de Consulta**:
```bash
curl -s "http://localhost:8005/proxy/ticker?symbol=BTC-USDT"
```
- **Respuesta de Ejemplo (200 OK)**:
```json
{
  "symbol": "BTC-USDT",
  "best_bid": 63043.4,
  "best_ask": 63043.5,
  "mid_price": 63043.45,
  "spread": 0.1,
  "timestamp_ms": 1785580466913,
  "is_fresh": true
}
```
- **Errores Posibles**:
  - `503 Service Unavailable`: Si los datos del símbolo aún no se han descargado.
    ```json
    { "error": "Ticker not ready for symbol" }
    ```

---

### 3.3 Obtener Libro de Órdenes (Orderbook L2)
Retorna las 20 mejores puntas de compra (*bids*) y venta (*asks*) en el mismo formato estructurado que el API nativo de KuCoin L2.

- **Método**: `GET`
- **Ruta**: `/proxy/orderbook?symbol={SYMBOL}`
- **Parámetros Query**:
  - `symbol` (opcional, default `SOL-USDT`): El par de trading.
- **Ejemplo de Consulta**:
```bash
curl -s "http://localhost:8005/proxy/orderbook?symbol=SOL-USDT"
```
- **Respuesta de Ejemplo (200 OK)**:
```json
{
  "code": "200000",
  "data": {
    "bids": [
      ["72.83", "112.805"],
      ["72.82", "161.244"],
      ["72.81", "95.120"]
    ],
    "asks": [
      ["72.84", "85.410"],
      ["72.85", "140.100"],
      ["72.86", "210.050"]
    ],
    "time": 1785580466445
  }
}
```

---

### 3.4 Estado y Salud del Proxy
Muestra métricas del hilo poller, contadores de peticiones a KuCoin, tiempo de refresco y estado de frescura por cada símbolo.

- **Método**: `GET`
- **Ruta**: `/proxy/status`
- **Ejemplo de Consulta**:
```bash
curl -s http://localhost:8005/proxy/status
```
- **Respuesta de Ejemplo (200 OK)**:
```json
{
  "running": true,
  "interval_ms": 300,
  "symbol_count": 8,
  "symbols": [
    "SOL-USDT", "BTC-USDT", "ETH-USDT", "ADA-USDT",
    "XRP-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT"
  ],
  "symbol_status": {
    "SOL-USDT": {
      "fresh": true,
      "age_ms": 12.0,
      "fetch_count": 1420,
      "error_count": 0,
      "last_error": null,
      "best_bid": 72.83,
      "best_ask": 72.84
    }
  }
}
```

---

## 4. Endpoints de Control y Estado del Motor (`/api/*`)

### 4.1 Streaming SSE en Tiempo Real
Permite suscribirse a un flujo continuo de datos en tiempo real mediante *Server-Sent Events (SSE)*. Emite payloads cada 200ms.

- **Método**: `GET`
- **Ruta**: `/api/stream`
- **Headers**:
  - `Accept: text/event-stream`
- **Ejemplo de Consumo en JavaScript**:
```javascript
const evtSource = new EventSource("http://localhost:8005/api/stream");
evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Capital Total:", data.portfolio.total_capital);
  console.log("Precios:", data.price_histories);
};
```

---

### 4.2 Control de Ejecución (Iniciar, Pausar, Reiniciar)

- **Iniciar Motor**: `GET /api/start`
- **Pausar Motor**: `GET /api/stop`
- **Reiniciar Motor**: `GET /api/restart`

**Ejemplo de Consulta**:
```bash
curl -s http://localhost:8005/api/start
```
**Respuesta**:
```json
{ "status": "started", "running": true }
```

---

### 4.2.1 Limpiar Base de Datos (Hard Reset)

Limpia la base de datos histórica y todos los contadores de sesión (PNL, número de operaciones).

- **Método**: `GET`
- **Ruta**: `/api/cleardb`
- **Ejemplo de Consulta**:
```bash
curl -s http://localhost:8005/api/cleardb
```
- **Respuesta**:
```json
{ "status": "cleared", "db_wiped": true }
```

---

### 4.3 Cambiar Preset de Estrategia

- **Método**: `GET`
- **Ruta**: `/api/strategy?name={PRESET_KEY}&symbol={SYMBOL}&capital={CAPITAL}`
- **Parámetros**:
  - `name` o `key`: Identificador del preset (`alpha_edge_1000`, `alpha_edge_2500`, `alpha_edge_multi`).
  - `symbol` (opcional): Símbolo o `MULTI-ASSET`.
  - `capital` (opcional): Capital asignado.

**Ejemplo de Consulta**:
```bash
curl -s "http://localhost:8005/api/strategy?name=alpha_edge_1000&symbol=SOL-USDT&capital=1000"
```

---

### 4.4 Cambiar Modo (LIVE / DEMO)

- **Método**: `GET`
- **Ruta**: `/api/mode?live=true` o `/api/mode?live=false`

**Ejemplo de Consulta**:
```bash
curl -s "http://localhost:8005/api/mode?live=true"
```

---

### 4.5 Reset de Guardia de Riesgo (Circuit Breaker)
Restablece manualmente el Circuit Breaker de `RiskGuard` tras un evento de seguridad.

- **Método**: `GET`
- **Ruta**: `/api/reset_risk`

---

### 4.6 Obtener y Modificar Configuración Global

- **Obtener Configuración**: `GET /api/config`
- **Actualizar Configuración**: `POST /api/config`
- **Configurar Bots Múltiples**: `POST /api/configure_bots`

**Ejemplo `POST /api/configure_bots`**:
```bash
curl -X POST http://localhost:8005/api/configure_bots \
  -H "Content-Type: application/json" \
  -d '{
    "bots": [
      {"symbol": "SOL-USDT", "strategy": "alpha_edge", "capital": 500},
      {"symbol": "BTC-USDT", "strategy": "alpha_edge", "capital": 500}
    ]
  }'
```

---

## 5. Código de Ejemplo de Consumo en Python

```python
import requests

BASE_URL = "http://localhost:8005"

# 1. Obtener todas las cotizaciones
response = requests.get(f"{BASE_URL}/proxy/all_tickers")
tickers = response.json()
print("Cotización SOL-USDT:", tickers.get("SOL-USDT", {}).get("mid_price"))

# 2. Obtener libro de órdenes L2 de Bitcoin
ob_resp = requests.get(f"{BASE_URL}/proxy/orderbook?symbol=BTC-USDT")
orderbook = ob_resp.json()
best_bid = orderbook["data"]["bids"][0]
best_ask = orderbook["data"]["asks"][0]
print(f"BTC-USDT -> Bid: {best_bid[0]} | Ask: {best_ask[0]}")

# 3. Verificar estado del proxy
status_resp = requests.get(f"{BASE_URL}/proxy/status")
print("Símbolos monitoreados:", status_resp.json().get("symbols"))
```

---

*A3 Core Systems — Documentación Oficial de la API v4.2*
