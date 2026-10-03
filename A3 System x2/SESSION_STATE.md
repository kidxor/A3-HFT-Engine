# 📊 A3 AlphaEdge PRO — Estado de Sesión y Campaña $200 ➔ $1,200 USD

**Fecha de Registro:** 2 de Octubre, 2026 (Actualizado a las 21:23)  
**Fecha de Próxima Revisión (1 Semana):** 9 de Octubre, 2026  
**Objetivo de la Campaña:** Multiplicar $200.00 USD iniciales hasta $1,200.00 USD (+500%) en Cripto Futuros para costear el servicio de VPS y generar excedente neto.

---

## 🌐 1. Infraestructura de Producción (Hostinger VPS)

* **URL Pública Segura (SSL/HTTPS):** [https://trade.origengeek.tech](https://trade.origengeek.tech)
* **IP del VPS:** `179.199.150.46` (Hostinger KVM)
* **Ruta de Despliegue:** `/opt/a3-trading`
* **Entorno Virtual Python:** `/opt/a3-trading/.venv` (Python 3.14.4 + Pandas + NumPy)
* **Servicio Daemon 24/7:** `systemctl status a3-trading.service` (Auto-restart activo)
* **Proxy Inverso & SSL:** Nginx 1.28 + Certbot Let's Encrypt (vence 31-Dic-2026, auto-renovable)
* **Credenciales de Acceso al Dashboard:**
  * **Usuario:** `razky`
  * **Contraseña:** `Kid8021761@`

---

## 🤖 2. Agente Autónomo de Trading & Bot de Telegram

### Agente Autónomo de Operaciones:
* **Archivo Núcleo:** [`core/autonomous_trader.py`](file:///home/andres/A3-Motor-Trade/core/autonomous_trader.py) (`AutonomousTraderAgent`)
* **Modo Operativo:** `HYBRID_CONSENSUS` (Consenso Híbrido: Reglas Cuantitativas + Confluencias Wyckoff/Brooks + Confirmación LLM)
* **Gestión de Riesgo Dinámica:** 5.0% base por trade; hasta 8.0% exclusivamente en setups institucionales de convicción máxima (`A+`).
* **Bitácora Persistente:** Registra cada decisión, confluencia y razonamiento (Chain of Thought) en `data/agent_journal.db`.
* **Exposición:** Conectado a la API web (`/api/agent/status`) y al bot de Telegram.

### Bot de Telegram Interactivo Bidireccional (@Razky_bot):
* **Archivo:** [`core/telegram_notifier.py`](file:///home/andres/A3-Motor-Trade/core/telegram_notifier.py)
* **Seguridad:** Long-polling en hilo secundario independiente con verificación estricta de `chat_id` (`8631169927`).
* **Comandos en Vivo:**
  * `/status` — Estado del motor, latencia L2 y modo de trading.
  * `/balance` — Capital actual, PnL neto acumulado, Win Rate y % hacia la meta de $1,200.
  * `/pos` — Monitoreo de posiciones abiertas con SL, TP y runners al +1.5R.
  * `/agent` — Último análisis, calificación de setups y razonamiento del Agente Autónomo.
  * `/trades` — Historial de últimas operaciones cerradas.
  * `/reglas` — Resumen del Playbook de la campaña.
  * `/pausar` / `/iniciar` — Control remoto para frenar o reanudar el bot.
* **Consultas en Lenguaje Natural:** Responde preguntas abiertas sobre el mercado consultando directamente al Agente Autónomo.

---

## 📱 3. Interfaz Móvil y Dashboard Simplificado

* **Cero Desbordamiento Horizontal:** Viewport fijado al 100% de la pantalla (`scrollWidth === innerWidth = 390px`) en cualquier smartphone.
* **Sub-Barra Móvil Táctil:** Acceso rápido en la parte superior con pills en tiempo real para **SOL**, **BTC** y **ETH** (con precio y variación %). Tocar cualquiera de ellos cambia de inmediato el gráfico activo.
* **Ribbon 2x2 Ejecutivo:** Los KPIs críticos (Balance, PnL Neto, Win Rate y barra de Risk Guard) se agrupan en una cuadrícula compacta y limpia con tipografía financiera legible.
* **Dock Flotante Glassmorphism:** Barra de navegación inferior con 5 botones accesibles con el pulgar:
  1. **Inicio:** Vuelve al resumen de balance y KPIs.
  2. **Gráfico:** Centra la gráfica interactiva y selector de temporalidades.
  3. **Trades:** Desplaza la vista a las posiciones abiertas y el libro de órdenes.
  4. **IA & Logs:** Accede al registro de eventos del sistema y decisiones del Agente.
  5. **Ajustes:** Abre suavemente el panel lateral para cambiar presets y parámetros.

---

## 🧠 4. Algoritmos, Reglas y Estrategia Activa

* **Estrategia Activa:** `CryptoFuturesHunterStrategy` ([`strategies/crypto_futures_hunter.py`](file:///home/andres/A3-Motor-Trade/strategies/crypto_futures_hunter.py))
* **Preset por Defecto:** `crypto_futures_sniper` ([`config/strategy_presets.json`](file:///home/andres/A3-Motor-Trade/config/strategy_presets.json))
* **Pares Operados en Paralelo:** `SOL-USDT`, `BTC-USDT`, `ETH-USDT` (Feeds L2 Bybit a 300ms)

### Reglas Clave del Sistema:
1. **Filtro Macro 4H Innegociable:**
   * En tendencia alcista macro: **Solo compras (LONGS)**. Prohibido vender en corto contra la tendencia.
   * En tendencia bajista macro: **Solo ventas (SHORTS)**. Prohibido comprar en caídas violentas.
   * En consolidación lateral (**CHOP_STANDBY**): 100% en Cash para proteger el capital.
2. **Caza de Liquidaciones Retail (Bear / Bull Traps):**
   * Detecta falsos rompimientos donde la masa queda atrapada por FOMO y entra con las instituciones tras la mecha de barrido.
3. **Gestión Matemática Asimétrica (R:R 1:2.6+):**
   * **Stop Loss:** Invalidez estructural estricta detrás de la mecha de barrido ($1.3 \times \text{ATR}$).
   * **Take Profit Parcial al +1.5R:** Se cierra el 50% de la posición y el Stop Loss se traslada al precio de entrada (+0.28% buffer de comisiones = Riesgo Cero absoluto).
   * **Trailing Runner:** El 50% restante corre con trailing stop para exprimir expansiones parabólicas.
4. **Escalado Dinámico de Capital:**
   * **Fase 1 ($200 ➔ $400):** Riesgo controlado al 5.0% por trade ($10 USD) buscando +$26 USD por win.
   * **Fase 2 ($400 ➔ $800):** Riesgo escalado al 6.5% utilizando únicamente una fracción del beneficio ganado.
   * **Fase 3 ($800 ➔ $1,200):** Aceleración final asegurando el capital inicial.
5. **Control Emocional Anti-Tilt:**
   * Máximo 3 operaciones diarias (disciplina de francotirador).
   * Enfriamiento obligatorio de 3 velas de 15m (45 minutos) tras el cierre de cualquier operación.
   * Circuit Breaker diario del 6%: Parada de emergencia por 24h si hay racha negativa.

---

## 🛡️ 5. Auditoría de Ciberseguridad & Zero-Trust

* **Autenticación HTTP Basic en Nginx:** El servidor rechaza con `401 Unauthorized` cualquier petición no autenticada antes de llegar a la app.
* **Encabezados de Seguridad Institucional:**
  * `X-Frame-Options: DENY` (Anti-Clickjacking)
  * `X-Content-Type-Options: nosniff` (Anti-MIME injection)
  * `X-XSS-Protection: 1; mode=block`
  * `Referrer-Policy: strict-origin-when-cross-origin`
* **Permisos del Sistema:**
  * Archivo `.env` en VPS con permisos `chmod 600` (solo legible por root).
* **Computadora Local:**
  * Todos los servicios locales (`a3-motor-trade.service`, `ultimate-trading-bot.service`) están **detenidos, deshabilitados y bloqueados permanentemente** para no consumir CPU ni memoria al encender la PC.

---

## 📋 6. Checklist para la Revisión en 1 Semana (9 de Octubre, 2026)

* [ ] Ingresar a [https://trade.origengeek.tech](https://trade.origengeek.tech) con credenciales `razky` o consultar vía Telegram `/balance`.
* [ ] Auditar balance actual vs. base inicial de $200.00 USD.
* [ ] Consultar tabla de trades ejecutados (`/trades` o en el panel).
* [ ] Medir Win Rate y Profit Factor de las operaciones en vivo.
* [ ] Verificar si el saldo cruzó el primer hito de **Fase 1 ($400.00 USD)** para activar el compounding.
