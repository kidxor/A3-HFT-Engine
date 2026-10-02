#!/usr/bin/env python3
"""
A3 Motor Trade — RAG Knowledge Engine & Trading Literature Ingestor
===================================================================
Ultra-fast in-memory semantic indexing and retrieval engine for trading books
and institutional playbooks (Wyckoff, Al Brooks, Mark Douglas, Elder, Dalton, Williams, SMC).

Provides sub-5ms contextual query responses and extracts precise author citations
for the Autonomous LLM Agent.
"""

import os
import re
import math
import logging
from collections import Counter
from typing import List, Dict, Any, Optional

logger = logging.getLogger("RAG_Knowledge_Engine")

BOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base", "books")


class RAGKnowledgeEngine:
    """
    RAG & Semantic Retrieval Engine for Institutional Trading Literature.
    """

    def __init__(self, books_dir: str = BOOKS_DIR):
        self.books_dir = books_dir
        self.documents: List[Dict[str, Any]] = []
        self.chunks: List[Dict[str, Any]] = []
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.is_indexed: bool = False
        self.load_and_index_library()

    def _tokenize(self, text: str) -> List[str]:
        """Simple, fast multilingual tokenization and normalization."""
        text = text.lower()
        # Remove markdown symbols and punctuation
        tokens = re.findall(r"\b[a-záéíóúüñ0-9_]{3,}\b", text)
        return tokens

    def load_and_index_library(self):
        """Loads all markdown files in books directory and builds BM25/TF-IDF inverted index."""
        if not os.path.exists(self.books_dir):
            os.makedirs(self.books_dir, exist_ok=True)
            logger.warning(f"Books directory created at: {self.books_dir}")

        self.documents.clear()
        self.chunks.clear()

        files = sorted([f for f in os.listdir(self.books_dir) if f.endswith(".md") or f.endswith(".txt")])

        for fname in files:
            fpath = os.path.join(self.books_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()

                # Extract metadata
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else fname
                author_match = re.search(r"\*\*Autor:\*\*\s*(.+)$", content, re.MULTILINE)
                author = author_match.group(1).strip() if author_match else "Institucional"
                cat_match = re.search(r"\*\*Categoría:\*\*\s*(.+)$", content, re.MULTILINE)
                category = cat_match.group(1).strip() if cat_match else "General"

                doc_info = {
                    "filename": fname,
                    "title": title,
                    "author": author,
                    "category": category,
                    "length": len(content),
                    "path": fpath,
                }
                self.documents.append(doc_info)

                # Chunk document by sections (## Headers)
                sections = re.split(r"\n(?=##\s+)", content)
                for s_idx, sec in enumerate(sections):
                    sec_clean = sec.strip()
                    if not sec_clean or len(sec_clean) < 50:
                        continue

                    sec_header_match = re.search(r"^##\s+(.+)$", sec_clean, re.MULTILINE)
                    section_title = sec_header_match.group(1).strip() if sec_header_match else f"Sección {s_idx+1}"

                    tokens = self._tokenize(sec_clean)
                    if tokens:
                        self.chunks.append({
                            "chunk_id": f"{fname}#sec_{s_idx}",
                            "filename": fname,
                            "title": title,
                            "author": author,
                            "category": category,
                            "section": section_title,
                            "text": sec_clean,
                            "tokens": tokens,
                            "token_counts": Counter(tokens),
                        })

            except Exception as e:
                logger.error(f"Error loading book '{fname}': {e}")

        # Compute IDF for all terms
        num_chunks = len(self.chunks)
        if num_chunks > 0:
            doc_freq: Dict[str, int] = Counter()
            for chunk in self.chunks:
                unique_terms = set(chunk["tokens"])
                for term in unique_terms:
                    doc_freq[term] += 1

            self.idf = {
                term: math.log((num_chunks - count + 0.5) / (count + 0.5) + 1.0)
                for term, count in doc_freq.items()
            }

        self.is_indexed = True
        logger.info(f"📚 RAG Library indexed: {len(self.documents)} books, {len(self.chunks)} semantic chunks.")

    def query_relevant_knowledge(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Retrieves top_k most relevant excerpts from trading books matching the query.
        Uses BM25-style scoring for maximum precision.
        """
        if not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Calculate BM25 scores
        k1 = 1.5
        b = 0.75
        avg_doc_len = sum(len(c["tokens"]) for c in self.chunks) / max(1, len(self.chunks))

        scored_chunks = []
        for chunk in self.chunks:
            doc_len = len(chunk["tokens"])
            score = 0.0
            for term in query_tokens:
                if term in chunk["token_counts"]:
                    tf = chunk["token_counts"][term]
                    idf_val = self.idf.get(term, 0.5)
                    numerator = tf * (k1 + 1.0)
                    denominator = tf + k1 * (1.0 - b + b * (doc_len / avg_doc_len))
                    score += idf_val * (numerator / denominator)

            if score > 0.1:
                scored_chunks.append({
                    "score": round(score, 3),
                    "author": chunk["author"],
                    "book": chunk["title"],
                    "section": chunk["section"],
                    "filename": chunk["filename"],
                    "text": chunk["text"],
                })

        # Sort by score descending
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

    def format_knowledge_for_prompt(self, query: str, top_k: int = 2) -> str:
        """
        Formats top book citations directly for the LLM CoT prompt.
        """
        results = self.query_relevant_knowledge(query, top_k=top_k)
        if not results:
            return ""

        formatted_blocks = []
        for r in results:
            # Extract first 400 chars of text for brevity and high density
            text_snippet = r["text"]
            if len(text_snippet) > 400:
                text_snippet = text_snippet[:397] + "..."

            block = (
                f"📖 [{r['author']} — {r['book']} ({r['section']})]:\n"
                f"{text_snippet}"
            )
            formatted_blocks.append(block)

        return "\n\n".join(formatted_blocks)

    def list_books(self) -> List[Dict[str, Any]]:
        """Returns catalog metadata of all ingested books for the UI."""
        catalog = []
        for doc in self.documents:
            # Count chunks for this book
            chunk_count = sum(1 for c in self.chunks if c["filename"] == doc["filename"])
            catalog.append({
                "filename": doc["filename"],
                "title": doc["title"],
                "author": doc["author"],
                "category": doc["category"],
                "length_chars": doc["length"],
                "chunks_count": chunk_count,
            })
        return catalog

    def get_book_content(self, filename: str) -> Optional[str]:
        """Returns the full text of a specific book."""
        fpath = os.path.join(self.books_dir, os.path.basename(filename))
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                return f.read()
        return None


# Global singleton instance
rag_knowledge_engine = RAGKnowledgeEngine()
