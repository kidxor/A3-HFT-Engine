# 🌊 Playbook 03: Flujo de Órdenes (Orderflow) y Gatillos de Confirmación (Los 3 Pilares Puros)

## 1. La Regla de la Simplicidad Radical (Navaja de Ockham)
Para evitar la parálisis por análisis, el retraso matemático (*lag*) y el sangrado por comisiones, el sistema opera con **3 Pilares Puros**:

1. **Ubicación Clave (Estructura):** ¿Dónde está el precio?
   - Soporte o Resistencia institucional probado ($\le 0.8\%$ de proximidad).
   - Zona Dorada de Fibonacci (50.0% - 61.8%).
   - EMA 20 o EMA 50 en retroceso tendencial.
2. **Disparador Anatómico (Acción del Precio):** ¿Qué hace la vela en ese nivel?
   - Vela de rechazo con mecha inferior larga (Martillo / Libélula Doji).
   - Absorción total del cuerpo previo (Envolvente Alcista / Bajista).
   - Prohibido comprar en caída libre (*Cuchillo Cayendo*).
3. **Asimetría Matemática (Protección contra Comisiones):** ¿Vale la pena el trade?
   - Stop Loss ceñido bajo la mecha extrema.
   - **Ratio Riesgo/Beneficio mínimo de 1:3** (arriesgar 1 para ganar 3 a 5).
   - Ganancia mínima proyectada $\ge 4\times$ el costo de comisiones de ida y vuelta.

## 2. Métricas de Microestructura L2
* **Volume Imbalance Ratio (VIR):**
  - Relación entre volumen en Bids y Asks en los primeros 10 niveles del libro.
  - `VIR > 1.20`: Presión compradora institucional dominante (favorable para compras).
  - `VIR < 0.80`: Presión vendedora institucional dominante (favorable para ventas).
* **Absorción en Libro de Órdenes:**
  - Cuando el precio intenta perforar un nivel pero los bids absorben todas las ventas sin permitir que el precio baje -> Señal de rebote inminente.

