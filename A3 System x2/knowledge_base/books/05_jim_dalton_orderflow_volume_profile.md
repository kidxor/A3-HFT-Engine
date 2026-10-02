# 📊 Mind Over Markets & Markets in Profile: Order Flow & Volume Profile
**Autor:** Jim Dalton & Peter Steidlmayer  
**Metodología:** Teoría de la Subasta de Mercado (*Market Auction Theory*) y Volume Profile  
**Categoría:** Order Flow, Liquidez y Microestructura  

---

## 1. La Teoría de la Subasta de Mercado (*Market Auction Theory*)

El mercado financiero tiene un único propósito fundamental: **facilitar el comercio mediante una subasta continua bidireccional entre compradores y vendedores**.

### Conceptos Clave del Perfil de Volumen (*Volume Profile*)
- **POC (Point of Control / Punto de Control):** El nivel de precio exacto donde se negoció el mayor volumen de contratos. Actúa como un poderoso imán de precios o pivote institucional.
- **Value Area (Área de Valor):** La zona de precios donde se negoció el **70% del volumen total**.
  - **VAH (Value Area High):** Límite superior del área de valor (resistencia clave).
  - **VAL (Value Area Low):** Límite inferior del área de valor (soporte clave).
- **HVN (High Volume Node):** Nivel de alta aceptación donde el precio se frena y consolida.
- **LVN (Low Volume Node):** Zona de baja liquidez donde el precio se desplaza a gran velocidad (*Slippage zone*).

---

## 2. Tipos de Participantes y Comportamiento del Flujo

### 1. Actividad de Respuesta (*Responsive Activity* - Comprar Barato / Vender Caro)
- Ocurre cuando el precio sale del Área de Valor y los operadores institucionales perciben el precio como una oportunidad de descuento o sobreprecio.
- **Setup de Compra Responsiva:** El precio cae por debajo del VAL, pero el Orderbook muestra absorción compradora (VIR > 1.4). El precio es empujado de regreso hacia el POC.
- **Setup de Venta Responsiva:** El precio sube por encima del VAH, encuentra absorción vendedora (VIR < 0.7) y regresa al POC.

### 2. Actividad de Iniciativa (*Initiative Activity* - Ruptura con Aceptación)
- Ocurre cuando entra nuevo volumen institucional agresivo empujando el precio fuera del área de valor con desbalance y manteniéndose fuera.
- **Regla:** Si el precio rompe el VAH/VAL y permanece fuera durante 2 o más periodos con volumen alto, el valor se está desplazando; opera en la dirección de la ruptura hacia la siguiente zona de liquidez.

---

## 3. Absorción vs. Agotamiento en el Orderbook
- **Absorción:** Grandes órdenes límite pasivas absorben todas las órdenes a mercado agresivas sin permitir que el precio avance más allá del nivel.
- **Agotamiento (*Exhaustion*):** El volumen agresivo desaparece abruptamente en un extremo del mercado, dejando un vacío que provoca un rebote inmediato.
