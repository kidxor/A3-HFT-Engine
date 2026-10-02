# 📐 Trading for a Living & The Triple Screen Trading System
**Autor:** Dr. Alexander Elder  
**Metodología:** Análisis Multi-Temporalidad, Osciladores de Impulso y Reglas de Riesgo Estricto  
**Categoría:** Sistemas de Trading y Gestión Cuantitativa de Riesgo  

---

## 1. El Sistema de la Triple Pantalla (*Triple Screen*)

Dr. Alexander Elder desarrolló este sistema para resolver el dilema clásico del análisis técnico: los indicadores de tendencia señalan compra en gráficos diarios pero los osciladores señalan sobrecompra en gráficos intradiarios. La solución es filtrar en 3 pantallas o capas temporales:

```
Pantalla 1 (Marea / Tendencia Mayor): Gráfico de orden superior (ej. 1H / 4H / 1D).
→ Objetivo: Determinar si la marea general es ALCISTA o BAJISTA mediante EMAs (Stack 20/50/200) o MACD Histogram.

Pantalla 2 (Ola / Contra-Tendencia): Gráfico operativo medio (ej. 5M / 15M).
→ Objetivo: Buscar retrocesos en contra de la marea usando osciladores (RSI, Estocástico o Force Index).

Pantalla 3 (Onda / Gatillo de Entrada): Gráfico de ejecución rápida (ej. 1M / Ticks).
→ Objetivo: Entrar con precisión cuando la ola menor gira de regreso en la dirección de la marea mayor.
```

### Reglas Operativas de la Triple Pantalla
- **Condición para Comprar (Long):**
  1. Pantalla 1: Marea alcista (EMA 20 > EMA 50 > EMA 200).
  2. Pantalla 2: Oscilador en retroceso/sobreventa momentánea (RSI < 40 o retroceso a zona de soporte).
  3. Pantalla 3: Gatillo de ruptura por encima del máximo de la vela anterior.
- **Condición para Vender (Short):**
  1. Pantalla 1: Marea bajista (EMA 20 < EMA 50 < EMA 200).
  2. Pantalla 2: Oscilador en rebote/sobrecompra momentánea (RSI > 60 o retroceso a resistencia).
  3. Pantalla 3: Gatillo de ruptura por debajo del mínimo de la vela anterior.

---

## 2. Divergencias Cuantitativas de MACD e Impulso (Elder Divergences)
- **Divergencia Alcista Clase A (Máxima Convicción):**
  El precio marca un mínimo más bajo (*Lower Low*), pero el indicador de momentum (MACD o RSI) marca un mínimo más alto (*Higher Low*). Indica agotamiento total de la presión vendedora.
- **Divergencia Bajista Clase A:**
  El precio marca un nuevo máximo (*Higher High*), pero el indicador marca un máximo descendente (*Lower High*). Señal inequívoca de distribución o debilidad institucional.

---

## 3. Las Reglas de Control de Capital de Elder: 2% y 6%
- **Regla del 2% (Riesgo Máximo por Operación):** Nunca arriesgar más del 2% al 5% del capital de la cuenta en una sola operación individual calculada al Stop Loss.
- **Regla del 6% (Límite Máximo Mensual / Diario de Drawdown):** Si la cuenta sufre pérdidas acumuladas equivalentes al 6%-10% del capital inicial en un período, **se detiene toda operativa inmediatamente (Circuit Breaker)** para evitar la destrucción de la cuenta.
