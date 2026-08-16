"""
services/prompt_service.py
=============================

Construction du system prompt et formatage des souvenirs long terme.

Avec le tool calling natif (voir `services/bedrock_service.get_llm_with_tools`),
on n'a plus besoin de décrire manuellement, dans le prompt système, le
format "Thought / Action / Action Input / Observation / Final Answer" :
Claude gère nativement le format d'appel d'outils via l'API Converse. Le
system prompt se limite donc à :

  - des instructions générales de comportement,
  - le contexte "mémoire long terme" (souvenirs pertinents retrouvés par
    recherche sémantique dans OpenSearch), s'il y en a.
"""

from typing import Dict, List, Optional

BASE_INSTRUCTIONS = """Tu es un agent IA autonome avec aws bedrock,langchain et langgraph.
Tu es précis, professionnel et concis dans tes réponses.

Règles importantes :
- N'utilise un outil que lorsque c'est réellement nécessaire ; ne devine jamais le résultat d'un outil.
- Si la question relève de la culture générale ou d'une connaissance que tu possèdes déjà, réponds directement sans outil.
- Si tu ne connais pas la réponse, dis-le honnêtement plutôt que d'inventer.
- Base-toi sur les souvenirs pertinents ci-dessous quand ils sont utiles ; ignore-les s'ils ne le sont pas.
-Souviens toi qu'on est plus en 2025 meme si tes connaissances se limitent en 2025; On est actuellement en 2026 , tu peux toujours te referer au tool tavily web search pour avoir la data réelle."""


def format_memories_block(semantic_memories: List[Dict]) -> str:
    """
    Formate les résultats de recherche sémantique (OpenSearch, mémoire
    long terme) en un bloc de texte injectable dans le prompt système.
    """
    if not semantic_memories:
        return ""

    lines = ["\n\n===== Souvenirs pertinents =====\n"]
    for memory in semantic_memories:
        # Compatible avec un hit OpenSearch brut ({"_source": {...}}) ou un dict simple.
        source = memory.get("_source", memory)
        content = source.get("content")
        if content:
            lines.append(f"- {content[:300]}")

    return "\n".join(lines)


def build_system_prompt(context: Optional[str]) -> str:
    """Assemble les instructions générales de l'agent + le contexte mémoire long terme."""
    if context:
        return f"{BASE_INSTRUCTIONS}\n{context}"
    return BASE_INSTRUCTIONS
