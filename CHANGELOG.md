# Historial de Cambios y Pruebas (Changelog)

Este documento mantiene un registro cronológico de las versiones, pruebas, simulaciones y rediseños de la plataforma **A3 Motor Trade**.

---

## [2026-09-04] - Versión 6.0 PRO: Terminal Institucional de Alta Frecuencia & Agente Autónomo Auto-Evolutivo (Proyecto Agustín)

### 🎨 Rediseño Arquitectónico UX/UI del Frontend
- **100% Viewport Workstation Layout**: Eliminación de las barras laterales estáticas fijas de 240px e izquierda/derecha. Recuperación de 550px de ancho continuo para el gráfico y centro de datos.
- **Tipografía Libre de Jitter**: Integración de `Plus Jakarta Sans` para interfaz y `JetBrains Mono` con `tabular-nums` para cotizaciones, KPIs y tablas en tiempo real.
- **Gráfico Interactivo TradingView**: Canvas de velas con mira de cruz (*crosshair*) dinámica en ejes X/Y, superposición de **EMA 20** (Cyan `#00f2fe`) y **EMA 50** (Ámbar `#f59e0b`), tooltip de OHLCV y visualizador flotante de precio.
- **Atajos de Teclado (Institutional Hotkeys)**:
  - Teclas `1`, `2`, `3` para alternar instantáneamente entre **SOL-USDT**, **BTC-USDT** y **ETH-USDT**.
  - Tecla `Espacio` (`Space`) para Pausar / Reanudar el motor algorítmico en vivo.
- **Cinta Macro de KPIs**: Barra horizontal unificada con Balance Total, Capital Base, PnL Neto, Win Rate, Drawdown (límite 10%), Profit Factor, Sharpe, Alpha IA y estado de Risk Guard.
- **Dock Inferior Modular con Pestañas de 1-Clic**:
  - `📌 Posiciones Activas`: Con barra de progreso hacia TP, marcador de Scale-Out al 50% y badge flotante de PnL.
  - `📜 Historial de Trades`: Registro contable completo de ejecuciones.
  - `⚡ Consola HFT & Eventos`: Terminal de logs con filtros por categoría (`Todos`, `Órdenes`, `Señales`, `Riesgo`, `L2`), autoscroll y 1-clic reset.
  - `🤖 Bots en Paralelo`: Monitoreo multi-bot.
- **Cajón Desplegable Lateral (`drawer`)**: Accesible con el botón `☰` para herramientas avanzadas (Wizard, Perfiles, Ajustes, Reset de Riesgo).

### ⚙️ Ajustes de Estrategia, Riesgo & Capital ($200 USD / Convicción 50%)
- **Capital Inicial Base**: Configurado en **$200.00 USD**.
- **Escala por Convicción**: Posibilidad de arriesgar hasta el **50% del balance de la cuenta** en operaciones confirmadas de alta seguridad.
- **Gestión de Posición**: Scale-Out parcial al 50% en 1.5x ATR con candado Breakeven (+0.1%), TP completo en 4.0x ATR, SL en 2.0x ATR y filtro News Spike Guard (3.0x ATR).
- **Botón 1-Clic `🧹 Reiniciar Stats`**: Restablecimiento físico de la base de datos `trades.db` y contadores a cero.

### 🧠 Agente Autónomo Auto-Evolutivo (`AIOptimizerEngine`)
- Integración con LLM local Ollama `llama3.2:1b` (`http://localhost:11434`) a **$0 costo de API**.
- Backtesting en RAM Sandbox sobre velas de 5m con comisiones reales y slippage.
- Validador estricto `ParameterSafeguards` (TP $\ge 2.5\times$ ATR, R:R positivo).

### 🧪 Suite de Pruebas Automatizadas
- **Resultado de pytest**: **32/32 tests pasados** exitosamente (`pytest tests/ -v`).

---

## [2026-08-07] - Ajuste Post-Prueba 10H (AlphaEdge)

### Prueba Realizada
- **Tipo de Test:** Simulación en Vivo (Paper Trading) de 10 Horas Ininterrumpidas.
- **Hora de Inicio:** 2026-08-06 18:36
- **Hora de Fin:** 2026-08-07 04:35
- **Métricas Finales:**
  - Ticks Procesados: 357,965
  - Trades Cerrados: 3 (Todas pérdidas)
  - PnL Total: -$1.27
  - Win Rate: 0.0%
- **Diagnóstico:** El Stop Loss inicial (`1.2x ATR`) era demasiado estrecho para la frecuencia de operativa, causando que el "ruido" (whipsaws) cerrara las posiciones antes de que la tendencia se desarrollara. La exigencia de la tendencia (ADX) era un poco baja.

### Cambios Aplicados
Archivos afectados: `strategies/alpha_edge_strategy.py`
Se ajustaron los parámetros del constructor `__init__`:
- `atr_sl_mult`: **1.2 → 2.0**
- `atr_tp_mult`: **3.5 → 4.0**
- `adx_min`: **18.0 → 20.0**
- **Nuevo Risk:Reward (R:R):** 1:1.5.
