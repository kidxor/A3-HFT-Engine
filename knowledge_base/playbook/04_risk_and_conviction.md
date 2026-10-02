# 🛡️ Playbook 04: Gestión de Riesgo Dinámico y Escala de Convicción

## 1. Escala Dinámica de Riesgo por Convicción
El capital arriesgado se calcula sobre el **Balance Vivo Total** (con reinversión de beneficios/compounding natural):

* **Riesgo Estándar (5.0% del Capital):**
  - Asignado a setups sólidos con tendencia clara (EMA Stack + ADX >= 25) y rebote en soporte confirmado.
* **Riesgo Máxima Convicción A+ Setup (8.0% del Capital):**
  - Asignado ÚNICAMENTE cuando confluyen TODOS los factores:
    1. Alineación de 3-EMA Stack + ADX >= 30.
    2. Rebote en Zona Dorada de Fibonacci (50%-61.8%) o soporte clave probado.
    3. Desbalance comprador en libro L2 (VIR > 1.5).
    4. Vela de confirmación con mecha de rechazo y volumen alto.

## 2. Parámetros de Stop Loss y Take Profit (Asimetría Matemática Pura)
* **Stop Loss (SL):** Situado a **1.5x ATR** o quirúrgicamente en el extremo de la mecha de la vela de giro (Swing Low / Swing High).
* **Take Profit (TP):** Situado a **4.5x ATR** o mínimo **3 veces la distancia del riesgo (1:3 R:R estricto)**.
* **Regla Inviolable de Espacio de Respiración (Cero Breakeven Prematuro):**
  - **PROHIBIDO** mover el Stop Loss a Breakeven en los primeros avances (30%-50% del TP). Los retrocesos naturales de las velas sacan la posición antes de tiempo y las comisiones devoran el saldo.
  - El trade debe tener libertad total para oscilar hasta tocar el Take Profit completo (1:3) o el Stop Loss.
  - **Trailing Stop Tardío:** Únicamente se permite asegurar ganancias si el precio ya alcanzó al menos el **70% del recorrido hacia el Take Profit (> 2:1 R:R)**, garantizando que cualquier salida anticipada deje una ganancia sustancial limpia tras comisiones.

## 3. Circuit Breaker Inviolable (Regla de Máxima Protección)
* **Límite de Drawdown Diario:** **5.0%** estricto.
* Si se acumula un 5.0% de pérdida en el día, **el sistema se bloquea automáticamente por el resto de la jornada** para preservar el 95% del capital y evitar sobreoperativa o revancha contra el mercado.
