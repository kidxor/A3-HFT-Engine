# 📐 Compendio de Algoritmos Estadísticos y Cuantitativos — A3 AlphaEdge PRO

Este documento detalla formalmente los **algoritmos matemáticos, estadísticos y de microestructura de mercado** que componen el motor algorítmico **A3 AlphaEdge PRO**, organizados por capa operativa.

---

## 1. Microestructura de Mercado y Flujo de Órdenes (L1 / L2)

### A. Micro-Price Ponderado por Volumen (Volume-Weighted Mid-Price)
* **Objetivo:** Calcular el precio de equilibrio real de mercado en el microsegundo, anticipando hacia dónde se moverá el precio antes de que se ejecute la última transacción en el libro.
* **Fórmula Matemática:**
  $$\text{MicroPrice} = \frac{P_{\text{bid}} \cdot V_{\text{ask}} + P_{\text{ask}} \cdot V_{\text{bid}}}{V_{\text{bid}} + V_{\text{ask}}}$$
  Donde:
  - $P_{\text{bid}}, P_{\text{ask}}$: Mejores precios de compra y venta del libro (*Top of the Book*).
  - $V_{\text{bid}}, V_{\text{ask}}$: Volúmenes disponibles en el mejor bid y mejor ask.
* **Uso en el Motor:** Si el $\text{MicroPrice}$ se desvía por encima del $\text{MidPrice}$, indica que la oferta institucional está siendo absorbida en compras.

### B. Volume Imbalance Ratio (VIR — Desbalance de Liquidez L2)
* **Objetivo:** Medir la presión direccional neta de liquidez en la profundidad del mercado.
* **Fórmula Matemática:**
  $$\text{VIR} = \frac{\sum_{i=1}^{10} \text{Volumen Bid}_i}{\sum_{i=1}^{10} \text{Volumen Ask}_i}$$
* **Criterio de Decisión:**
  - $\text{VIR} \ge 1.20$: Presión compradora institucional dominante (favorable para setups LONG).
  - $\text{VIR} \le 0.80$: Presión vendedora institucional dominante (favorable para setups SHORT).
  - $0.80 < \text{VIR} < 1.20$: Equilibrio relativo o absorción neutra.

---

## 2. Geometría Fractal y Estructura de Mercado

### A. Fractales de Williams (Rolling Fractal Window)
* **Objetivo:** Detección algorítmica de pivotes de inflexión (*Swing Highs* y *Swing Lows*) eliminando el ruido intradía.
* **Algoritmo:**
  Dada una serie de precios $\{P_t\}$ y una ventana fractal $k=3$:
  - **Swing High:** Se detecta en $t$ si $H_t = \max(H_{t-k}, \dots, H_{t+k})$.
  - **Swing Low:** Se detecta en $t$ si $L_t = \min(L_{t-k}, \dots, L_{t+k})$.
* **Uso en el Motor:** Los pivotes detectados se utilizan para proyectar zonas de soporte, resistencia y colocación de Stop Loss.

### B. Clustering Aglomerativo 1D para Soportes y Resistencias
* **Objetivo:** Agrupar niveles de precio donde múltiples pivotes fractales coinciden dentro de un umbral de tolerancia.
* **Algoritmo:**
  1. Se toman todos los máximos y mínimos locales de las últimas 60 velas.
  2. Se ejecuta un clustering unidimensional con distancia relativa:
     $$D(P_a, P_b) = \frac{|P_a - P_b|}{P_a} \le 0.8\%$$
  3. Los clusters se ordenan de mayor a menor según el número de testeos (*touches*).
* **Uso en el Motor:** Un nivel con $\ge 3$ testeos es considerado **Zona Clave Institucional**.

### C. Retrocesos y Proyecciones de Fibonacci
* **Objetivo:** Identificar niveles de equilibrio áureo tras un impulso direccional dominante.
* **Niveles Calculados:**
  $$\text{Rango} = \text{SwingHigh} - \text{SwingLow}$$
  $$\text{Fib}_{0.382} = \text{SwingHigh} - 0.382 \cdot \text{Rango}$$
  $$\text{Fib}_{0.500} = \text{SwingHigh} - 0.500 \cdot \text{Rango}$$
  $$\mathbf{\text{Fib}_{0.618}} = \text{SwingHigh} - \mathbf{0.618} \cdot \text{Rango} \quad (\text{Zona Dorada})$$
* **Uso en el Motor:** Las compras se gatillan preferentemente cuando el precio testea la Zona Dorada ($50\% - 61.8\%$).

### D. Smart Money Concepts (BOS y CHoCH)
* **BOS (Break of Structure):** Cierre de vela con cuerpo por encima del Swing High previo en tendencia alcista (o bajo el Swing Low en bajista).
* **CHoCH (Change of Character):** Ruptura del último mínimo estructural que invalida la secuencia de *Higher Lows*, indicando agotamiento y posible giro.

---

## 3. Volatilidad, Tendencia y Momento

### A. Average True Range (ATR de Wilder, $N=14$)
* **Objetivo:** Cuantificar la volatilidad intrínseca del activo en dólares reales para fijar distancias dinámicas de riesgo y objetivo.
* **Fórmula Matemática:**
  $$\text{TR}_t = \max\big(H_t - L_t, \; |H_t - C_{t-1}|, \; |L_t - C_{t-1}|\big)$$
  $$\text{ATR}_t = \frac{\text{ATR}_{t-1} \cdot 13 + \text{TR}_t}{14}$$
* **Aplicación Directa en el Riesgo:**
  - **Stop Loss Base:** $1.5 \times \text{ATR}$ (con piso mínimo de $0.5\%$).
  - **Take Profit Base:** $4.5 \times \text{ATR}$ (garantizando ratio $1:3$).

### B. Average Directional Index (ADX con $+DI$ y $-DI$, $N=14$)
* **Objetivo:** Filtrar matemáticamente el régimen de mercado (tendencia vs. consolidación).
* **Fórmulas:**
  $$\text{DX} = 100 \cdot \frac{|+DI - -DI|}{+DI + -DI}$$
  $$\text{ADX}_t = \frac{\text{ADX}_{t-1} \cdot 13 + \text{DX}_t}{14}$$
* **Reglas de Ejecución:**
  - $\text{ADX} \ge 28.0$: Tendencia fuerte confirmada (autorizado para operar tendencias o continuaciones).
  - $\text{ADX} < 28.0$: Mercado en consolidación lateral. El motor activa el filtro de **Cero Comisiones** y solo permite entradas de giro si hay absorción manifiesta en soporte.

### C. Triple Media Móvil Exponencial (3-EMA Stack: 20, 50, 100)
* **Fórmula de Suavizado:**
  $$\text{EMA}_t = C_t \cdot \alpha + \text{EMA}_{t-1} \cdot (1 - \alpha), \quad \alpha = \frac{2}{N+1}$$
* **Alineación Institucional:**
  - **Bullish Stack:** $\text{EMA}_{20} > \text{EMA}_{50} > \text{EMA}_{100}$ y $\text{Precio} > \text{EMA}_{100}$.
  - **Bearish Stack:** $\text{EMA}_{20} < \text{EMA}_{50} < \text{EMA}_{100}$ y $\text{Precio} < \text{EMA}_{100}$.

### D. Relative Strength Index (RSI de Wilder, $N=14$)
* **Fórmula:**
  $$\text{RSI} = 100 - \frac{100}{1 + \text{RS}}, \quad \text{RS} = \frac{\text{Media de Ganancias}}{\text{Media de Pérdidas}}$$
* **Uso:** Detección de extremos de sobreventa ($\text{RSI} \le 30$) o sobrecompra ($\text{RSI} \ge 70$) en confluencia con niveles de soporte o resistencia.

---

## 4. Detección Anatómica de Velas Japonesas (18 Patrones)

El motor clasifica cada vela de 5 minutos mediante relaciones geométricas proporcionales:

| Patrón | Condición Geométrica | Significado Institucional |
| :--- | :--- | :--- |
| **Martillo (Hammer)** | $\text{Mecha Inferior} \ge 2.0 \cdot \text{Cuerpo}$ y $\text{Mecha Sup} \le 0.15 \cdot \text{Rango}$ | Absorción agresiva de ventas en soporte. |
| **Estrella Fugaz (Shooting Star)** | $\text{Mecha Superior} \ge 2.0 \cdot \text{Cuerpo}$ y $\text{Mecha Inf} \le 0.15 \cdot \text{Rango}$ | Rechazo de precios altos en resistencia. |
| **Libélula / Lápida Doji** | $\text{Cuerpo} \le 0.05 \cdot \text{Rango}$ con mecha extrema unipolar | Indecisión con sesgo de absorción terminal. |
| **Envolvente (Engulfing)** | $\text{Cuerpo}_t > \text{Rango}_{t-1}$ con signo opuesto | Giro completo de control institucional. |
| **Filtro Cuchillo Cayendo** | Cierre bajista con $\text{Cuerpo} \ge 0.70 \cdot \text{Rango}$ y $\text{Mecha Inf} \le 0.08 \cdot \text{Rango}$ | Prohíbe compras suicidas durante caídas libres sin piso. |

---

## 5. Gestión Cuantitativa de Riesgo y Portafolio

### A. Asimetría Matemática Pura (1:3 R:R sin Breakeven Prematuro)
* **Principio:** Para batir las comisiones del exchange y la fricción de mercado (*slippage*), cada operación ganadora debe cubrir al menos 3 pérdidas completas:
  $$\text{Ratio R:R} = \frac{|\text{TP} - \text{Entry}|}{|\text{SL} - \text{Entry}|} \ge 3.0$$
* **Regla del Espacio de Respiración:** Queda prohibido mover el Stop Loss a Breakeven antes de que el precio haya alcanzado al menos el **$70\%$ del recorrido hacia el Take Profit ($> 2:1$ R:R)**, evitando que el ruido ordinario de la vela corte operaciones ganadoras con centavos de ganancia que son devorados por las comisiones.

### B. Ratio de Sharpe Móvil (Running Sharpe Ratio)
* **Fórmula:**
  $$\text{Sharpe} = \frac{\mathbb{E}[R_p] - R_f}{\sigma(R_p)}$$
* Calculado en una ventana deslizante continua de las últimas 500 operaciones para monitorear la calidad del retorno ajustado por volatilidad.

### C. Profit Factor Incremental
* **Fórmula:**
  $$\text{Profit Factor} = \frac{\sum_{i} \max(0, \text{PnL}_i)}{\sum_{i} |\min(0, \text{PnL}_i)|}$$
* Mantenido en $O(1)$ acumulativo para auditorías de rendimiento en tiempo real.

### D. Circuit Breaker de Cola Izquierda (Hard Limit 5.0%)
* Si el *Drawdown* desde el máximo pico de capital diario (*Peak Equity*) alcanza el **5.0%**, el motor activa el corte de emergencia automático por el resto de la sesión para proteger el 95% del capital.

---

*Documento actualizado en Septiembre de 2026 para la arquitectura unificada A3 AlphaEdge PRO.*
