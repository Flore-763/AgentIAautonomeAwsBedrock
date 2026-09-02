"""
tests/test_search.py
======================

`recherche_documentaire` dépend de deux services externes, tous deux
mockés ici :
  1. `invoke_titan_embedding` (Bedrock) — jamais de vrai appel Bedrock.
  2. `vector_store.semantic_search` (OpenSearch) — jamais de vrai appel
     OpenSearch.
"""

from unittest.mock import patch

from tools.search import KNOWLEDGE_BASE_SESSION_ID, recherche_documentaire


def _run(query: str) -> str:
    return recherche_documentaire.invoke({"query": query})


FAKE_EMBEDDING = [0.1, 0.2, 0.3]


class TestRechercheAvecResultats:
    @patch("tools.search.vector_store.semantic_search")
    @patch("tools.search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_formate_les_resultats_avec_score(self, mock_embed, mock_search):
        mock_search.return_value = [
            {"_source": {"content": "Smartovate Ltd est une entreprise de conseil cloud."}, "_score": 0.87},
            {"_source": {"content": "Le support est disponible du lundi au vendredi."}, "_score": 0.65},
        ]

        result = _run("Que fait Smartovate ?")

        assert "Smartovate Ltd est une entreprise de conseil cloud." in result
        assert "0.87" in result
        assert "Le support est disponible du lundi au vendredi." in result
        assert "[1]" in result and "[2]" in result

    @patch("tools.search.vector_store.semantic_search")
    @patch("tools.search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_utilise_la_session_technique_knowledge_base(self, mock_embed, mock_search):
        mock_search.return_value = []
        _run("question")

        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["session_id"] == KNOWLEDGE_BASE_SESSION_ID == "knowledge_base"
        assert call_kwargs["k"] == 5
        assert call_kwargs["embedding"] == FAKE_EMBEDDING

    @patch("tools.search.vector_store.semantic_search")
    @patch("tools.search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_tronque_les_contenus_trop_longs(self, mock_embed, mock_search):
        long_content = "a" * 500
        mock_search.return_value = [{"_source": {"content": long_content}, "_score": 0.5}]

        result = _run("question")

        assert result.count("a") <= 303  # 300 caractères + "..."
        assert result.endswith("...")


class TestRechercheSansResultats:
    @patch("tools.search.vector_store.semantic_search", return_value=[])
    @patch("tools.search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_aucun_resultat_pertinent(self, mock_embed, mock_search):
        result = _run("question hors sujet")
        assert "Aucun document pertinent" in result


class TestGestionErreurs:
    @patch("tools.search.invoke_titan_embedding", side_effect=RuntimeError("Bedrock indisponible"))
    def test_erreur_calcul_embedding(self, mock_embed):
        result = _run("question")
        assert "Erreur lors de la recherche documentaire" in result
        assert "Bedrock indisponible" in result

    @patch("tools.search.vector_store.semantic_search", side_effect=ConnectionError("OpenSearch down"))
    @patch("tools.search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_erreur_opensearch(self, mock_embed, mock_search):
        result = _run("question")
        assert "Erreur lors de la recherche documentaire" in result
        assert "OpenSearch down" in result


class TestOutilLangChain:
    def test_nom_de_loutil(self):
        assert recherche_documentaire.name == "recherche_documentaire"

    def test_description_non_vide(self):
        assert recherche_documentaire.description
