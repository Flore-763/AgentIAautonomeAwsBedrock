"""
tools/search.py
=================

Outil de recherche documentaire (RAG) : interroge la base de connaissances
interne de l'entreprise, indexée dans OpenSearch (`vector_store.py`), en
s'appuyant sur la similarité sémantique (embeddings Amazon Titan).

Correspond à l'US 2.2 du cahier des charges : "En tant qu'utilisateur, je
veux que l'agent puisse interroger une base de documents internes, afin
d'obtenir des réponses basées sur les connaissances de l'entreprise."
Les documents sont indexés au préalable via `index_pdf.py` sous la session
technique `knowledge_base`.
"""

from langchain_core.tools import tool

from services.bedrock_service import invoke_titan_embedding
from vector_store import vector_store

# Les documents internes (PDF, etc.) sont indexés sous cet identifiant de
# session technique par `index_pdf.py` — voir `index_pdfs_in_directory`.
KNOWLEDGE_BASE_SESSION_ID = "knowledge_base"


@tool
def recherche_documentaire(query: str) -> str:
    """
    Interroge la base de connaissances interne de l'entreprise Smartovate Ltd.

    À utiliser quand la question de l'utilisateur porte sur : les
    politiques internes, les procédures, les informations produits ou
    services de l'entreprise, ou la documentation technique interne.
    Ne pas utiliser pour de la culture générale (dans ce cas, répondre
    directement sans outil).

    Args:
        query: La question de l'utilisateur, en langage naturel.

    Returns:
        Les extraits de documents les plus pertinents, avec leur score de
        similarité, ou un message indiquant qu'aucun résultat n'a été trouvé.
    """
    try:
        embedding = invoke_titan_embedding(query)
        results = vector_store.semantic_search(
            embedding=embedding,
            session_id=KNOWLEDGE_BASE_SESSION_ID,
            k=5,
        )

        if not results:
            return "Aucun document pertinent trouvé dans la base de connaissances."

        formatted = []
        for i, result in enumerate(results, 1):
            source = result.get("_source", {})
            content = source.get("content", "")
            score = result.get("_score", 0)

            if len(content) > 300:
                content = content[:300] + "..."

            formatted.append(f"[{i}] (pertinence: {score:.2f})\n{content}")

        return "\n---\n".join(formatted)

    except Exception as error:
        return f"Erreur lors de la recherche documentaire : {error}"
