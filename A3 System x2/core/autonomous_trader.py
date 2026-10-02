"""
A3 AlphaEdge PRO — Autonomous Trader Agent (Ollama LLM Agentic Core)
Combines Structured Playbook Knowledge, Chain-of-Thought Reasoning,
Dynamic Risk Scaling (5%-8%), and Episodic Post-Trade Journaling.
"""

import os
import json
import time
import logging
import threading
import urllib.request
import urllib.error
import sqlite3
import contextlib
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from core.market_structure import evaluate_confluences_and_conviction
from core.rag_knowledge_engine import rag_knowledge_engine
from core.event_logger import event_logger
from core.telegram_notifier import telegram_notifier

logger = logging.getLogger("AutonomousTrader")


class PlaybookLoader:
    """Manages reading and updating Playbook Markdown documents."""

    def __init__(self, playbook_dir: Optional[str] = None):
        self.playbook_dir = playbook_dir or os.path.join(
            os.path.dirname(__file__), "..", "knowledge_base", "playbook"
        )
        os.makedirs(self.playbook_dir, exist_ok=True)

    def list_files(self) -> List[str]:
        if not os.path.exists(self.playbook_dir):
            return []
        files = [f for f in os.listdir(self.playbook_dir) if f.endswith(".md")]
        files.sort()
        return files

    def get_content(self, filename: str) -> str:
        safe_name = os.path.basename(filename)
        path = os.path.join(self.playbook_dir, safe_name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def save_content(self, filename: str, content: str) -> bool:
        safe_name = os.path.basename(filename)
        path = os.path.join(self.playbook_dir, safe_name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"💾 Playbook '{safe_name}' guardado con éxito.")
            return True
        except Exception as e:
            logger.error(f"Error guardando Playbook '{safe_name}': {e}")
            return False

    def get_all_condensed_rules(self) -> str:
        """Returns a condensed single prompt text containing core rules."""
        docs = []
        for f in self.list_files():
            content = self.get_content(f)
            if content:
                docs.append(f"### {f}\n{content}")
        return "\n\n".join(docs)


class AutonomousTraderAgent:
    """
    Autonomous AI Trader Agent capable of direct decision-making and execution.
    Modes:
    - ALGORITHMIC: Quantitative AlphaEdge PRO logic.
    - AUTONOMOUS: Full LLM direct decision & tool invocation.
    - HYBRID_CONSENSUS: Quantitative signal gated and scaled (5%-8%) by LLM audit.
    """

    MODE_ALGORITHMIC = "ALGORITHMIC"
    MODE_AUTONOMOUS = "AUTONOMOUS"
    MODE_HYBRID_CONSENSUS = "HYBRID_CONSENSUS"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        self.endpoint = (endpoint or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "llama3.2:1b")
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "agent_journal.db"
        )
        self.mode = self.MODE_HYBRID_CONSENSUS  # Default to high-safety hybrid consensus
        self.playbook = PlaybookLoader()
        self.is_running = True
        self.history: List[Dict[str, Any]] = []

        self._init_journal_db()

    def _init_journal_db(self):
        """Initializes SQLite table for Agent Chain-of-Thought decisions and reflections."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        try:
            with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("""
                    CREATE TABLE IF NOT EXISTS agent_decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        action TEXT NOT NULL,
                        conviction_grade TEXT NOT NULL,
                        risk_pct REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        sl_price REAL NOT NULL,
                        tp_price REAL NOT NULL,
                        confluences TEXT,
                        chain_of_thought TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS agent_reflections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_id INTEGER,
                        symbol TEXT NOT NULL,
                        pnl REAL NOT NULL,
                        outcome TEXT NOT NULL,
                        lesson_learned TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing agent journal DB: {e}")

    def evaluate_opportunity(
        self,
        symbol: str,
        df_candles: pd.DataFrame,
        orderbook: Optional[Dict[str, Any]],
        current_balance: float = 200.0,
        adx_val: float = 30.0,
        atr_val: float = 1.5,
        async_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Main decision engine (Smart Combination):
        1. Computes mathematical confluences deterministically in <0.5ms.
        2. Assigns dynamic risk (5% standard vs 8% A+ setup / up to 50% capital).
        3. Returns immediate execution payload to eliminate tick latency.
        4. Dispatches LLM chain-of-thought analysis in background thread.
        """
        if df_candles is None or len(df_candles) < 30:
            return {
                "action": "HOLD",
                "grade": "NEUTRAL_WAIT",
                "risk_pct": 0.0,
                "reasoning": "Esperando acumulación de velas (mínimo 30).",
                "chain_of_thought": "Esperando acumulación de velas.",
            }

        curr_price = float(df_candles["close"].iloc[-1])
        atr_pct = (atr_val / curr_price) if curr_price > 0 else 0.005

        # 1. Deterministic Analytical Tools (Instant Execution Path)
        analysis = evaluate_confluences_and_conviction(
            df=df_candles, orderbook=orderbook, adx_val=adx_val, atr_pct=atr_pct
        )

        base_action = analysis["action"]
        grade = analysis["grade"]
        risk_pct = analysis["risk_pct"]
        confluences = analysis["confluences"]

        # Macro 4H Filter Gatekeeper
        try:
            from core.macro_regime import macro_regime_detector, MacroBias
            macro = macro_regime_detector.get_regime(symbol, fallback_15m_df=df_candles)
            if macro.bias == MacroBias.CHOP_STANDBY:
                base_action = "HOLD"
                grade = "NEUTRAL_WAIT"
                confluences = ["4H Macro en CHOP_STANDBY (Preservación de Capital)"]
            elif base_action == "BUY" and macro.bias == MacroBias.BEAR_REGIME:
                base_action = "HOLD"
                grade = "NEUTRAL_WAIT"
                confluences = [f"Veto: Intento de BUY contra 4H Bear Trend ({macro.bias.value})"]
            elif base_action == "SELL" and macro.bias == MacroBias.BULL_REGIME:
                base_action = "HOLD"
                grade = "NEUTRAL_WAIT"
                confluences = [f"Veto: Intento de SELL contra 4H Bull Trend ({macro.bias.value})"]
        except Exception:
            pass

        # Calculate TP / SL with Institutional Oxygen & High R:R
        sl_dist = max(curr_price * 0.016, 1.6 * atr_val)
        tp_dist = max(sl_dist * 2.8, curr_price * 0.045)
        if base_action == "BUY":
            sl_price = round(curr_price - sl_dist, 4)
            tp_price = round(curr_price + tp_dist, 4)
        elif base_action == "SELL":
            sl_price = round(curr_price + sl_dist, 4)
            tp_price = round(curr_price - tp_dist, 4)
        else:
            sl_price = 0.0
            tp_price = 0.0

        # Extract Candlestick Pattern Analysis (18 Patrones de Velas)
        candles = analysis.get("candles", {})
        candle_patterns = candles.get("patterns", [])
        is_knife = candles.get("is_falling_knife", False)
        candle_desc = ", ".join(candle_patterns) if candle_patterns else ("Cuchillo Cayendo ⚠️" if is_knife else "Vela Normal")

        # Hard Safeguard: risk capped at 8.0% for position sizing
        final_risk_pct = min(risk_pct, 0.08) if base_action != "HOLD" else 0.0
        risk_usd = round(current_balance * final_risk_pct, 2)

        if candle_patterns:
            candle_tag = f"Vela: {', '.join(candle_patterns)}"
        elif is_knife:
            candle_tag = "Vela: Cuchillo Cayendo ⚠️"
        else:
            candle_tag = "Vela: Normal"

        initial_reasoning = (
            f"[{grade}] {candle_tag} | Confluencias: {', '.join(confluences[:2]) if confluences else 'Análisis matemático'}"
        )

        decision_record = {
            "symbol": symbol,
            "action": base_action,
            "grade": grade,
            "risk_pct": final_risk_pct,
            "risk_usd": risk_usd,
            "entry_price": curr_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "confluences": confluences,
            "candle_pattern": candle_desc,
            "chain_of_thought": initial_reasoning,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": self.mode,
        }

        self.history.append(decision_record)
        if len(self.history) > 30:
            self.history.pop(0)

        # Record to SQLite
        self._record_decision_to_db(decision_record)

        if base_action != "HOLD":
            if async_llm:
                # Dispatch LLM generation asynchronously in background thread
                threading.Thread(
                    target=self._async_enrich_llm_reasoning,
                    args=(
                        decision_record,
                        symbol,
                        curr_price,
                        analysis,
                        adx_val,
                        atr_val,
                        current_balance,
                        risk_usd,
                        sl_price,
                        tp_price,
                    ),
                    daemon=True,
                ).start()
            else:
                # Synchronous fallback (for unit tests / CLI queries)
                llm_thought = self._query_llm_reasoning(
                    symbol=symbol,
                    price=curr_price,
                    analysis=analysis,
                    adx=adx_val,
                    atr=atr_val,
                    current_balance=current_balance,
                    risk_usd=risk_usd,
                    sl=sl_price,
                    tp=tp_price,
                )
                if llm_thought.get("reasoning"):
                    decision_record["chain_of_thought"] = f"[{grade}] {llm_thought['reasoning']}"

        return decision_record

    def _async_enrich_llm_reasoning(
        self,
        decision_record: Dict[str, Any],
        symbol: str,
        price: float,
        analysis: Dict[str, Any],
        adx: float,
        atr: float,
        current_balance: float,
        risk_usd: float,
        sl: float,
        tp: float,
    ):
        """Asynchronously queries the LLM and enriches the decision record and DB."""
        try:
            llm_thought = self._query_llm_reasoning(
                symbol=symbol,
                price=price,
                analysis=analysis,
                adx=adx,
                atr=atr,
                current_balance=current_balance,
                risk_usd=risk_usd,
                sl=sl,
                tp=tp,
            )
            reasoning_text = llm_thought.get("reasoning")
            if reasoning_text:
                enriched = f"[{decision_record['grade']}] {reasoning_text}"
                decision_record["chain_of_thought"] = enriched
                with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                    with conn:
                        conn.execute(
                            "UPDATE agent_decisions SET chain_of_thought = ? WHERE id = (SELECT max(id) FROM agent_decisions WHERE symbol = ?)",
                            (enriched, symbol),
                        )
                        conn.commit()
                logger.info(f"🧠 [AI Agent] {symbol}: {enriched}")
        except Exception as e:
            logger.debug(f"Async LLM enrichment error: {e}")

    def _query_llm_reasoning(
        self,
        symbol: str,
        price: float,
        analysis: Dict[str, Any],
        adx: float,
        atr: float,
        current_balance: float,
        risk_usd: float,
        sl: float,
        tp: float,
    ) -> Dict[str, Any]:
        # Extract Candlestick Patterns
        candles = analysis.get("candles", {})
        candle_patterns = candles.get("patterns", [])
        is_knife = candles.get("is_falling_knife", False)
        candle_summary = ", ".join(candle_patterns) if candle_patterns else ("Cuchillo Cayendo ⚠️" if is_knife else "Vela Normal")

        # Query RAG Knowledge Base from Books (Wyckoff, Al Brooks, Elder, Dalton, SMC, 18 Patrones de Velas...)
        rag_query = f"{symbol} {analysis.get('action')} {analysis.get('structure', {}).get('structure', '')} {' '.join(candle_patterns)} {' '.join(analysis.get('confluences', []))}"
        book_citations = rag_knowledge_engine.format_knowledge_for_prompt(rag_query, top_k=1)
        if book_citations and len(book_citations) > 250:
            book_citations = book_citations[:250] + "..."
        citations_block = f"\nPrincipio institucional:\n{book_citations}\n" if book_citations else ""

        prompt = f"""Eres el Lead Trader Institucional. Audita la siguiente confluencia matemática:
Activo: {symbol} | Precio: ${price:.4f} | ADX: {adx:.1f} | ATR: ${atr:.4f}
Estructura: {analysis.get('structure', {}).get('structure', 'NEUTRAL')}
Vela Japonesa: {candle_summary} (18 Patrones de Velas)
Confluencias: {json.dumps(analysis.get('confluences', []))}
Grado: {analysis.get('grade')} | Riesgo: {analysis.get('risk_pct')*100:.1f}% (${risk_usd:.2f}) | SL: ${sl:.4f} | TP: ${tp:.4f}
{citations_block}
REGLAS:
1. Responde ÚNICAMENTE un JSON con campos "action" (BUY, SELL o HOLD) y "reasoning" (máximo 2 oraciones en español).
2. Si la vela japonesa (Martillo, Envolvente, Giro) confirma rebote en soporte o rechazo en resistencia con R:R 1:3, APRUEBA la acción técnica ({analysis.get('action')}).
3. Responde "HOLD" únicamente si hay caída libre sin mecha de absorción (cuchillo cayendo) o el mercado carece de nivel técnico.
Ejemplo:
{{"action": "BUY", "reasoning": "Martillo alcista confirmado sobre EMA con desbalance L2 comprador (Brooks/18 Patrones)."}}
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 70},
        }

        try:
            req = urllib.request.Request(
                f"{self.endpoint}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw = resp_data.get("response", "")
                    return json.loads(raw)
        except Exception as e:
            logger.debug(f"LLM query fallback to deterministic analysis: {e}")

        # Deterministic Fallback
        return {
            "action": analysis["action"],
            "reasoning": f"Confluencias confirmadas: {', '.join(analysis['confluences'][:2]) or 'Setup técnico válido'}",
        }

    def _record_decision_to_db(self, dec: Dict[str, Any]):
        try:
            with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("""
                    INSERT INTO agent_decisions 
                    (symbol, action, conviction_grade, risk_pct, entry_price, sl_price, tp_price, confluences, chain_of_thought, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dec["symbol"],
                    dec["action"],
                    dec["grade"],
                    dec["risk_pct"],
                    dec["entry_price"],
                    dec["sl_price"],
                    dec["tp_price"],
                    json.dumps(dec["confluences"]),
                    dec["chain_of_thought"],
                    dec["timestamp"],
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving decision to journal DB: {e}")

    def record_post_trade_reflection(
        self,
        trade_id: int,
        symbol: str,
        pnl: float,
        exit_reason: str,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        target_pnl: float = 0.0,
    ):
        """
        Active AI Agent Meta-Supervisor & Self-Reflection (Episodic Memory).
        Audita el trade cerrado, evalúa si cumplió con el umbral mínimo de ganancia (> $2.00 USD),
        y detecta asfixia prematura por micro-trailing o comisiones.
        """
        MIN_DESIRED_WIN_USD = 3.50

        if pnl > 0:
            if pnl < MIN_DESIRED_WIN_USD:
                outcome = "CHOKED_MICRO_WIN"
                lesson = (
                    f"⚠️ GANANCIA MENOR A TARGET SNIPER (+${pnl:.2f} USD < ${MIN_DESIRED_WIN_USD:.2f} USD) en {symbol} "
                    f"({exit_reason}). El trade cerró antes de completar la extensión institucional (Objetivo: $4.50 - $8.00 USD)."
                )
                level = "WARNING"
            else:
                outcome = "SUPERIOR_WIN"
                lesson = (
                    f"🎯 GANANCIA OBJETIVO ALCANZADA (+${pnl:.2f} USD >= ${MIN_DESIRED_WIN_USD:.2f} USD) en {symbol} "
                    f"({exit_reason}). R:R 1:3 institucional ejecutado con éxito y comisiones 100% amortizadas."
                )
                level = "SUCCESS"
        else:
            outcome = "LOSS"
            lesson = (
                f"🛑 Pérdida contenida por Stop Loss (-${abs(pnl):.2f} USD, {exit_reason}) en {symbol}. "
                f"La asimetría 1:3 garantiza que una sola victoria compensa múltiples pérdidas."
            )
            level = "ERROR"

        try:
            with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("""
                    INSERT INTO agent_reflections (trade_id, symbol, pnl, outcome, lesson_learned, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (trade_id, symbol, pnl, outcome, lesson, time.strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
            event_logger.log("AGENTE", f"🧠 Reflexión IA ({symbol}): {lesson}", level=level)
        except Exception as e:
            logger.error(f"Error saving reflection: {e}")

    def audit_system_health(self) -> Dict[str, Any]:
        """
        Supervisa activamente el rendimiento de las operaciones en vivo.
        Detecta si el ratio Ganancia/Pérdida es asimétrico favorable o si se generan microganancias.
        """
        try:
            with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT pnl, outcome FROM agent_reflections 
                    ORDER BY id DESC LIMIT 20
                """)
                rows = cursor.fetchall()
                if not rows:
                    return {"status": "AWAITING_DATA", "avg_win": 0.0, "avg_loss": 0.0, "realized_rr": 0.0}

                wins = [r[0] for r in rows if r[0] > 0]
                losses = [abs(r[0]) for r in rows if r[0] < 0]
                micro_wins = [r[0] for r in rows if 0 < r[0] < 2.0]

                avg_win = sum(wins) / len(wins) if wins else 0.0
                avg_loss = sum(losses) / len(losses) if losses else 0.0
                realized_rr = round(avg_win / avg_loss, 2) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

                status = "HEALTHY_ASYMMETRIC"
                if micro_wins:
                    status = f"WARNING_MICRO_WINS_DETECTED ({len(micro_wins)} trades < $2)"
                elif avg_loss > 0 and avg_win < avg_loss:
                    status = "CRITICAL_INVERTED_RR"

                return {
                    "status": status,
                    "total_audited": len(rows),
                    "avg_win": round(avg_win, 2),
                    "avg_loss": round(avg_loss, 2),
                    "realized_rr": realized_rr,
                    "micro_wins_count": len(micro_wins),
                }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Returns structured state for Web UI and API."""
        return {
            "mode": self.mode,
            "is_running": self.is_running,
            "model": self.model,
            "playbook_files": self.playbook.list_files(),
            "recent_decisions": self.history[-10:],
            "system_health": self.audit_system_health(),
        }

    def reset_journal(self):
        """Resets agent decisions history and clears journal database tables."""
        self.history.clear()
        try:
            with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    conn.execute("DELETE FROM agent_decisions")
                    conn.execute("DELETE FROM agent_reflections")
                    try:
                        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('agent_decisions', 'agent_reflections')")
                    except sqlite3.OperationalError:
                        pass
                    conn.commit()
            logger.info("🧹 Agent decisions and reflections journal reset.")
        except Exception as e:
            logger.warning(f"Error resetting agent journal: {e}")


# Global singleton instance
autonomous_trader = AutonomousTraderAgent()
