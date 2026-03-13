"""
idea_generator.py
=================
Uses the Groq API (llama-3.1-8b-instant) to generate startup and project
ideas from keyword/metadata context collected by MetadataParser.

This is the **only** module in IdeaDB that calls an LLM.
"""

import asyncio
import re
from typing import Any, Dict, List

from groq import Groq


class IdeaGenerator:
    """
    Wraps the Groq chat-completions API to produce project / startup ideas
    based on aggregated keyword context collected from a Discord server.
    """

    MODEL = "llama-3.1-8b-instant"
    MAX_TOKENS = 2048
    TEMPERATURE = 0.82      # slightly creative but still coherent

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set.")
        self.client = Groq(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_ideas(
        self,
        entries: List[Dict[str, Any]],
        count: int = 5,
    ) -> str:
        """
        Asynchronously generate ``count`` project / startup ideas from a list
        of database entries produced by MetadataParser.

        The heavy Groq call is offloaded to a thread-pool executor so the
        Discord event loop is never blocked.
        """
        context = self._build_context(entries)
        prompt = self._build_prompt(context, count)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
            ),
        )
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, context: str, count: int) -> str:
        return (
            f"You are an innovative startup and project idea generator.\n\n"
            f"Based on the following keywords, topics, technologies, and content "
            f"that a team has been discussing and sharing on Discord, generate "
            f"{count} compelling project or startup ideas.\n\n"
            f"--- Context ---\n{context}\n--- End Context ---\n\n"
            f"Generate exactly {count} creative, actionable ideas. "
            f"For each idea use this format:\n\n"
            f"**[Number]. [Catchy Name]**\n"
            f"🎯 Pitch: <one-sentence pitch>\n"
            f"🔍 Problem: <core problem solved>\n"
            f"👥 Target: <target audience>\n"
            f"🛠️ Stack: <key technologies>\n"
            f"---\n\n"
            f"Be creative, specific, and grounded in the context provided."
        )

    # ------------------------------------------------------------------
    # Context preparation (pure Python, no LLM)
    # ------------------------------------------------------------------

    def _build_context(self, entries: List[Dict[str, Any]]) -> str:
        """
        Aggregate entries into a compact text context for the LLM prompt.
        All aggregation logic is algorithmic — no LLM is called here.
        """
        keyword_freq: Dict[str, int] = {}
        content_type_counts: Dict[str, int] = {}
        tech_terms: List[str] = []
        recent_snippets: List[str] = []

        for entry in entries:
            # Aggregate keyword frequencies
            for kw in entry.get("keywords", []):
                keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

            # Count content types
            ct = entry.get("content_type", "message")
            content_type_counts[ct] = content_type_counts.get(ct, 0) + 1

            # Collect tech terms from raw content
            raw = entry.get("raw_content", "")
            if raw:
                tech_terms.extend(self._quick_tech_scan(raw))

            # Keep a handful of recent message snippets for flavour
            if (
                entry.get("content_type") == "message"
                and raw
                and len(recent_snippets) < 10
            ):
                recent_snippets.append(raw[:200].replace("\n", " "))

        # Top 30 keywords sorted by frequency
        top_keywords = sorted(keyword_freq.items(), key=lambda x: -x[1])[:30]

        parts: List[str] = []

        if top_keywords:
            kw_str = ", ".join(f"{kw} ({cnt})" for kw, cnt in top_keywords)
            parts.append(f"Top keywords & topics: {kw_str}")

        if content_type_counts:
            ct_str = ", ".join(
                f"{ct}: {cnt}" for ct, cnt in content_type_counts.items()
            )
            parts.append(f"Content types shared: {ct_str}")

        unique_tech = list(dict.fromkeys(tech_terms))[:20]
        if unique_tech:
            parts.append(f"Technologies mentioned: {', '.join(unique_tech)}")

        if recent_snippets:
            snippets_str = "\n".join(f"- {s}" for s in recent_snippets)
            parts.append(f"Recent discussion snippets:\n{snippets_str}")

        return "\n\n".join(parts) if parts else "No specific context collected yet."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _quick_tech_scan(text: str) -> List[str]:
        """
        Regex scan for technology keywords inside raw message text.
        Keeps the idea-generation context grounded in actual tech mentions.
        """
        pattern = (
            r"\b(AI|ML|API|LLM|blockchain|python|javascript|react|cloud|"
            r"SaaS|startup|mobile|web|app|database|docker|kubernetes|"
            r"machine.learning|open.source|automation|crypto|NFT|web3)\b"
        )
        return [m.lower() for m in re.findall(pattern, text, re.IGNORECASE)]
