#!/usr/bin/env python3
import pytest
import pandas as pd
import numpy as np
from core.rag_knowledge_engine import rag_knowledge_engine, RAGKnowledgeEngine
from core.autonomous_trader import autonomous_trader


def test_rag_engine_load():
    """Verify that all trading books are loaded and indexed."""
    books = rag_knowledge_engine.list_books()
    assert len(books) >= 7
    assert len(rag_knowledge_engine.chunks) >= 15
    assert rag_knowledge_engine.is_indexed is True

    filenames = [b["filename"] for b in books]
    assert "01_richard_wyckoff_market_cycles.md" in filenames
    assert "02_al_brooks_price_action.md" in filenames
    assert "03_mark_douglas_trading_in_the_zone.md" in filenames
    assert "04_alexander_elder_triple_screen.md" in filenames
    assert "05_jim_dalton_orderflow_volume_profile.md" in filenames
    assert "06_larry_williams_volatility_breakout.md" in filenames
    assert "07_smart_money_concepts_institutional_orderflow.md" in filenames


def test_rag_query_wyckoff():
    """Test retrieval of Wyckoff spring and accumulation concepts."""
    results = rag_knowledge_engine.query_relevant_knowledge("spring acumulacion wyckoff fase C", top_k=2)
    assert len(results) > 0
    top_hit = results[0]
    assert "Wyckoff" in top_hit["author"] or "Wyckoff" in top_hit["book"]


def test_rag_query_al_brooks():
    """Test retrieval of Al Brooks price action and wedge reversals."""
    results = rag_knowledge_engine.query_relevant_knowledge("wedge reversal tres impulsos al brooks", top_k=2)
    assert len(results) > 0
    authors = [r["author"] for r in results]
    assert any("Al Brooks" in a for a in authors)


def test_rag_query_mark_douglas():
    """Test retrieval of Mark Douglas probabilistic psychology."""
    results = rag_knowledge_engine.query_relevant_knowledge("verdades fundamentales ventaja probabilistica", top_k=2)
    assert len(results) > 0
    authors = [r["author"] for r in results]
    assert any("Douglas" in a for a in authors)


def test_rag_query_elder_triple_screen():
    """Test retrieval of Alexander Elder Triple Screen rules."""
    results = rag_knowledge_engine.query_relevant_knowledge("triple pantalla marea ola onda elder", top_k=2)
    assert len(results) > 0
    authors = [r["author"] for r in results]
    assert any("Elder" in a for a in authors)


def test_rag_format_for_prompt():
    """Test formatting citations directly for the LLM prompt."""
    citation_text = rag_knowledge_engine.format_knowledge_for_prompt("desbalance orderbook vir absorcion", top_k=2)
    assert "📖 [" in citation_text
    assert len(citation_text) > 50


def test_autonomous_trader_evaluation_with_rag():
    """Test that autonomous_trader runs evaluate_opportunity and embeds RAG knowledge cleanly."""
    np.random.seed(42)
    n = 60
    closes = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    highs = closes + np.random.uniform(0.1, 0.5, n)
    lows = closes - np.random.uniform(0.1, 0.5, n)
    opens = closes + np.random.uniform(-0.2, 0.2, n)
    volumes = np.random.uniform(100, 500, n)

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    orderbook = {
        "vir": 1.65,
        "spread_pct": 0.0004,
        "bid_volume": 450.0,
        "ask_volume": 270.0,
    }

    decision = autonomous_trader.evaluate_opportunity(
        symbol="BTC-USDT",
        df_candles=df,
        orderbook=orderbook,
        current_balance=250.0,
    )

    assert decision is not None
    assert "action" in decision
    assert "grade" in decision
    assert "risk_pct" in decision
    assert "chain_of_thought" in decision
    assert len(decision["chain_of_thought"]) > 10
