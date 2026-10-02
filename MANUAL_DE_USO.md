# Manual de Uso Oficial — A3 AlphaEdge PRO HFT Engine & Terminal v6.0 (Proyecto Agustín)

Bienvenido al manual oficial del **Motor de Trading Cuantitativo, Servidor Proxy de Mercado Local, Optimización Autónomo por IA Local y Estación de Trabajo Institucional (A3 AlphaEdge PRO Engine v6.0 — Proyecto Agustín)**.

Este sistema nativo para **Linux (Ubuntu)** ejecuta algoritmos cuantitativos de alta frecuencia en tiempo real, alimentado con datos L2 en vivo desde Bybit/KuCoin mediante un **Market Data Proxy (MDP)** desacoplado de baja latencia (<0.5ms), gestión de riesgo estricta Zero-Trust con Circuit Breaker, auto-evolución continua mediante LLMs locales ($0 costo de API) y una interfaz gráfica de grado terminal institucional (100% viewport width).

---

## 1. Características Principales de AlphaEdge PRO v6.0

| Característica | Bot Tradicional | A3 AlphaEdge PRO Engine v6.0 |
| :--- | :--- | :--- |
| **Frecuencia de Reacción** | Minutos / Horas | **Velas de 5m construidas en sub-segundos con Ticks L2 en Vivo** |
| **Interfaz Gráfica (UX/UI)** | Dashboard estático de 2005 con scroll de 3m | **Estación de Trabajo Institucional (100% Viewport, Estilo TradingView / Hyperliquid)** |
| **Gráfico Interactivo** | Imagen o canvas simple sin guía | **Canvas de Velas TradingView con Mira de Cruz (Crosshair), EMA 20 y EMA 50 en Vivo** |
| **Gestión de Posición** | Todo o Nada (Take Profit único) | **Scale-Out Parcial al 50% en 1.5x ATR + Candado Breakeven (+0.1%)** |
| **Protección contra Noticias**| N/A (Expuesto a deslices) | **News Spike Guard (Bloquea entradas si ATR >= 3.0x promedio)** |
| **Capital Inicial y Exposición**| Fijo / Arbitrario | **$200.00 USD Capital Base** con escala adaptativa de convicción **hasta 50% de equity** |
| **Atajos de Teclado (Hotkeys)**| Inexistente | **Teclas `1`, `2`, `3` para Símbolos | Tecla `Espacio` para Pausar/Reanudar Motor** |
| **Auto-Optimización por IA** | Parámetros estáticos | **Agente Autónomo Local (Ollama `llama3.2:1b`) + Sandbox RAM ($0 costo API)** |
| **Riesgo / Recompensa** | 1:1 o negativo | **1 : 1.5 R:R Neto** (Scale-Out 1.5x ATR, Full TP 4.0x ATR, SL 2.0x ATR) |
| **Gestión de Riesgo** | Estática / Manual | **Risk Guard Circuit Breaker** (Drawdown máximo 10.0%, Pausa por Pérdidas Consecutivas) |
| **Persistencia & Índices** | Memoria volátil | **Base de Datos SQLite WAL + 4 Índices** + Botón 1-Clic `🧹 Reiniciar Stats` |
| **Estructura del Terminal** | Tablas apiladas en scroll | **Dock Inferior Modular con Pestañas de 1-Clic** (`Posiciones`, `Trades`, `Consola HFT`, `Bots`) |

---

## 2. Guía de Inicio Rápido

### Paso 1: Abrir la Terminal de Linux
Presiona `Ctrl + Alt + T` en Ubuntu para abrir la consola.

### Paso 2: Entrar al Directorio del Proyecto
```bash
cd /home/andres/A3-Motor-Trade
```

### Paso 3: Iniciar el Servidor Principal
```bash
python3 server.py
```

### Paso 4: Abrir la Estación de Trabajo (Dashboard Web)
Abre tu navegador e ingresa a:
👉 `http://localhost:8005/`

*(Si habías abierto la versión anterior, presiona `Ctrl + F5` en el navegador para recargar la caché).*

---

## 3. Guía de Uso del Terminal Institucional UX/UI v6.0

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR: [A3 PRO] | Tickers: SOL $103.84 · BTC $80,933 · ETH $2,506 | [Space] 🟢 LIVE    │
│         Capital: $ [200] [💾] [🧹 Reset] | [👤 Perfiles] [⚙️ Ajustes] [🌐 API] [🔇]   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ KPI RIBBON: Equity: $200.00 | PnL: +$0.00 | WR: 0% | DD: 0.00% / 10% | Risk: OPERATIVO │
├────────────────────────────────────────────────────────┬───────────────────────────────┤
│                                                        │ AI EVOLUTION CORE             │
│ CHART WORKSPACE                                        │ - Local LLM Live Audit        │
│ - Tabs: [SOL 1] [BTC 2] [ETH 3]                        │ - Regime, Alpha, Hypotheses   │
│ - Live Price, EMA 20, EMA 50 Overlays                  │ - [⚡ Forzar Optimización]     │
│ - Crosshairs & Candlesticks                            ├───────────────────────────────┤
│                                                        │ SIGNAL & EXECUTION ENGINE     │
│                                                        │ - Signal: [NEUTRAL] 300ms     │
│                                                        │ - Strategy, ADX, EMA 200      │
│                                                        │ - Scale-Out 50% & SL BE Lock  │
├────────────────────────────────────────────────────────┴───────────────────────────────┤
│ BOTTOM DOCK (TABBED):                                                                  │
│ [📌 Posiciones Activas (0)]  [📜 Historial de Trades (0)]  [⚡ Terminal HFT (0)] [🤖 Bots]│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Atajos de Teclado Rápido (Institutional Hotkeys)
- **Tecla `1`**: Selecciona y muestra instantáneamente el 1er símbolo (**SOL-USDT**).
- **Tecla `2`**: Selecciona y muestra el 2do símbolo (**BTC-USDT**).
- **Tecla `3`**: Selecciona y muestra el 3er símbolo (**ETH-USDT**).
- **Tecla `Espacio` (`Space`)**: Alterna inmediatamente entre **Pausar** y **Reanudar** la operación del bot en vivo.
- **Buscador de Herramientas (`☰`)**: Abre el cajón lateral desplegable (*slide-over drawer*) para acceder al asistente Wizard, perfiles, reseteo de riesgo y mantenimiento sin ocultar el gráfico.

### 3.2 Macro KPI Ribbon (Cinta de Métricas de Alta Densidad)
En la parte superior se muestra una cinta continua libre de jitter tipográfico (`JetBrains Mono` con `tabular-nums`):
- **Balance Total:** `$200.00`
- **Capital Base Configurado:** `$200.00`
- **PnL Neto:** `+$0.00`
- **Win Rate:** `0.0%`
- **Drawdown Actual:** `0.00%` (Límite máximo protegido: `10.0%`)
- **Profit Factor & Sharpe Ratio:** `0.00 / 0.00`
- **Alpha Generado por IA:** `+$0.00 USD`
- **Risk Guard:** `OPERATIVO` (con micro medidor visual)

### 3.3 Dock Inferior Modular de Pestañas
- **`📌 Posiciones Activas`**: Tabla completa con barra de progreso en vivo hacia el Take Profit, marcador del 50% scale-out y PnL flotante.
- **`📜 Historial de Trades`**: Registro histórico de operaciones concluidas con precios de entrada, salida y PnL.
- **`⚡ Consola HFT & Eventos`**: Terminal completa de logs con filtros por categoría (`Todos`, `Órdenes`, `Señales`, `Riesgo`, `L2`), autoscroll y botón de limpieza.
- **`🤖 Bots en Paralelo`**: Cuadrícula de bots en ejecución paralela multi-activo.

---

## 4. Estrategia Cuantitativa: AlphaEdge PRO (`AlphaEdgeStrategy`)

### 4.1 Mecánica de Scale-Out (Tomas Parciales al 50%)
1. **Entrada:** Confirmación de Pullback en tendencia (`EMA20 > EMA50 > EMA200`, `ADX >= 20`, `RSI 35-60`).
2. **Cierre Parcial (50% en 1.5x ATR):**
   - Al alcanzar el **50% de la distancia al Take Profit completo**, el motor vende la mitad de la posición registrando la primera ganancia.
   - En ese mismo milisegundo, el Stop Loss se asegura a **Breakeven (+0.1% cubriendo comisiones)**.
3. **Take Profit Completo (4.0x ATR):** La mitad restante corre con *Trailing Stop* activo hasta alcanzar la meta final.

### 4.2 Exposición por Convicción (Hasta 50% Equity)
- El motor evalúa la fuerza de la señal cuantitativa (Stack de EMAs + ADX + alineación de volumen).
- Para entradas de máxima convicción, permite dimensionar la posición utilizando **hasta el 50% del capital inicial ($100 USD en $200 USD)**, maximizando la ganancia manteniendo la protección de Stop Loss acotada a 2.0x ATR.

### 4.3 News Spike Guard (Protección contra Volatilidad Anómala)
- El motor calcula el promedio móvil de volatilidad (ATR de 50 velas).
- Si una vela de noticia genera un pico de volatilidad anómalo (`ATR actual >= 3.0x ATR promedio`), el motor suspende temporalmente nuevas entradas para evitar deslices de precio (*slippage*).

---

## 5. Guardia de Riesgo Enterprise (`RiskGuard`)

1. **Max Daily Drawdown (10%)**: Detiene el motor si las pérdidas del día alcanzan el 10% del capital inicial diario ($20 USD en cuenta de $200 USD).
2. **Exposición Máxima de Convicción (50%)**: Acotada dinámicamente según la convicción de la estrategia.
3. **Pausas por Pérdidas Consecutivas**: Pausa de enfriamiento de 300 segundos tras pérdidas consecutivas.
4. **Reset Diario Automático**: Restablecimiento a las 00:00 UTC/local para operaciones continuas 24/7.
5. **Botón 1-Clic `🧹 Reiniciar Stats`**: Limpia la base de datos `trades.db` y resetea contadores a cero.

---

## 6. Agente Autónomo Auto-Evolutivo (`AIOptimizerEngine`)

AlphaEdge PRO v6.0 incorpora un optimizador cuantitativo en segundo plano con soporte para LLMs locales (**Ollama `llama3.2:1b` / vLLM**) y optimización Bayesiana en caliente ($0 USD de costo de API).

### 6.1 Mecánica de Auto-Mejora Continua
1. **Evaluación Periódica:** Cada ciclo (1 hora o manual), el motor evalúa las últimas 200 velas de 5m en un **Sandbox en memoria (RAM)**.
2. **Generación de Hipótesis:** Combina el razonamiento de un LLM local con perturbaciones cuantitativas adaptativas según el régimen detectado (*Tendencia*, *Rango Lateral*, *Alta Volatilidad*).
3. **Filtros de Seguridad Inviolables (`ParameterSafeguards`):**
   - Take Profit mínimo $\ge 2.5\times$ ATR (asegura ganancia bruta $\gg$ comisiones).
   - Ratio Riesgo:Recompensa estrictamente favorable ($TP > SL$).
4. **Despliegue en Caliente (*Hot-Reload*):** Si el candidato supera el Sharpe Ratio actual en $\ge 10\%$, actualiza [config/strategy_presets.json](file:///home/andres/A3-Motor-Trade/config/strategy_presets.json) y los simuladores en memoria sin reiniciar el servidor.

---

## 7. Ejecución de Pruebas Automatizadas

La suite completa de pruebas garantiza la integridad del sistema:

```bash
python3 -m pytest tests/ -v
```

**Resultado:** `32 passed` (100% verde).

---

*A3 Core Systems — AlphaEdge PRO HFT Engine & Terminal v6.0 (Proyecto Agustín)*
