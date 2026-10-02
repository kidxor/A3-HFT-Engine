# 🏦 Smart Money Concepts (SMC) & Institutional Order Flow Mastery
**Metodología:** Smart Money Concepts (SMC), Liquidity Pools, Fair Value Gaps (FVG) y Order Blocks (OB)  
**Categoría:** Liquidez Institucional y Cacería de Stops  

---

## 1. La Lógica de la Liquidez Institucional

Los grandes participantes institucionales (*Bancos, Creadores de Mercado y Fondos Algorítmicos*) manejan órdenes de tal magnitud que no pueden entrar directamente a mercado sin mover el precio en su contra. Por lo tanto, necesitan **Liquidez Oculta (Stop Losses de los traders minoristas)** para llenar sus órdenes.

### Zonas de Liquidez (*Liquidity Pools*)
- **BSL (Buy-Side Liquidity / Liquidez de Compra):** Se acumula por encima de los máximos iguales (*Equal Highs / EQH*) donde residen los Stop Loss de las posiciones en corto y órdenes Buy Stop de breakout.
- **SSL (Sell-Side Liquidity / Liquidez de Venta):** Se acumula por debajo de los mínimos iguales (*Equal Lows / EQL*) donde residen los Stop Loss de los compradores.

---

## 2. Los Bloques de Construcción del SMC

### 1. Liquidity Sweep (Barrido de Liquidez / Stop Hunt)
- El algoritmo institucional impulsa el precio deliberadamente por encima de un máximo previo (o por debajo de un mínimo) para ejecutar los Stops.
- Inmediatamente después de absorber esa liquidez, el precio realiza un giro violento en la dirección opuesta (*Reversal*).

### 2. Market Structure Shift (MSS / Cambio de Estructura de Mercado)
- Ocurre cuando el precio, tras un barrido de liquidez, rompe con fuerza y cuerpo de vela el último mínimo más alto (*Higher Low*) en caso bajista, o el último máximo más bajo (*Lower High*) en caso alcista.
- Confirma que el flujo institucional ha cambiado de dirección.

### 3. Fair Value Gap (FVG / Desbalance de Precios)
- Un FVG es un desbalance de 3 velas consecutivas donde existe un vacío de liquidez entre la mecha de la Vela 1 y la mecha de la Vela 3.
- El mercado tiene una tendencia natural a regresar y rellenar (*mitigar*) este vacío antes de continuar la tendencia.
- **Regla de Entrada:** Colocar orden límite en el 50% del FVG (*Consequent Encroachment / CE*).

### 4. Order Block (OB / Bloque de Órdenes Institucional)
- **Bullish Order Block:** La última vela bajista antes de un movimiento alcista impulsivo que rompe estructura (BOS/MSS).
- **Bearish Order Block:** La última vela alcista antes de un desplome impulsivo.
- **Regla de Entrada:** Entrada al re-testeo del Order Block con Stop Loss inmediatamente al otro lado del bloque.

---

## 3. Matriz de Confluencias de Alta Convicción SMC (Calificación A+)
Una operación alcanza la **Máxima Convicción (8% de Riesgo)** cuando reúne estas 4 confluencias simultáneas:
1. **Barrido de Liquidez (Sweep):** Toma de BSL o SSL previo.
2. **Cambio de Estructura (MSS):** Ruptura del swing fractal con vela de desplazamiento.
3. **Mitigación de FVG / Order Block:** Entrada precisa en retroceso del 50%-61.8% de Fibonacci.
4. **Confirmación en Orderbook L2:** Desbalance de volumen (VIR > 1.4 para compras o < 0.7 para ventas).
