"""
tests/test_document_search.py
===============================

`search_user_documents` est la fonction interne qui contient toute la
logique (retries KNN, fallback term-only, filtrage par fichier
récemment uploadé). L'outil LangChain `document_search` lui-même n'est
qu'un garde-fou qui refuse de s'exécuter sans contexte injecté par le
backend (`call_tools`) — testé séparément, en dernier.

Mocks : `opensearch.search`, `invoke_titan_embedding`, et `time.sleep`
(pour ne pas ralentir les tests avec les délais de retry réels).
"""

from unittest.mock import patch
import importlib

# NOTE : voir test_tavily_web_search.py pour l'explication du piège
# `tools/__init__.py` qui écrase l'attribut du sous-module par l'outil
# lui-même (même nom `document_search`). On passe par `importlib` pour
# récupérer le vrai module.
doc_search_module = importlib.import_module("tools.document_search")
document_search = doc_search_module.document_search
search_user_documents = doc_search_module.search_user_documents

FAKE_EMBEDDING = [0.1, 0.2, 0.3]


def _hit(filename="rapport.pdf", chunk_id="0", content="Contenu du chunk.", score=0.9):
    return {"_source": {"filename": filename, "chunk_id": chunk_id, "content": content}, "_score": score}


def _search_response(hits):
    return {"hits": {"hits": hits}}


@patch("tools.document_search.time.sleep")  # jamais de vraie attente dans les tests
class TestRechercheBaseNominale:
    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_trouve_du_premier_coup(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([_hit(filename="rapport.pdf")])

        result = search_user_documents(
            query="Quel est le budget ?", user_sub="user-1", session_id="sess-1"
        )

        assert "rapport.pdf" in result
        assert "Contenu du chunk." in result
        assert mock_search.call_count == 1  # pas de retry nécessaire
        mock_sleep.assert_not_called()

    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_filtre_par_session_et_type_document(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([_hit()])

        search_user_documents(query="q", user_sub="user-42", session_id="sess-99")

        body = mock_search.call_args.kwargs["body"]
        must_clauses = body["query"]["knn"]["embedding"]["filter"]["bool"]["must"]
        assert {"term": {"session_id": "document:user-42:sess-99"}} in must_clauses
        assert {"term": {"record_type": "user_document"}} in must_clauses

    def test_requete_vide(self, mock_sleep):
        result = search_user_documents(query="   ", user_sub="u", session_id="s")
        assert "vide" in result

    @patch("tools.document_search.invoke_titan_embedding", return_value=None)
    def test_embedding_impossible(self, mock_embed, mock_sleep):
        result = search_user_documents(query="q", user_sub="u", session_id="s")
        assert "Impossible de calculer" in result


@patch("tools.document_search.time.sleep")
class TestRetriesEtLatenceKnn:
    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_retente_tant_que_pas_de_hit_puis_reussit(self, mock_embed, mock_search, mock_sleep):
        # 2 tentatives vides, puis un hit -> l'indexation KNN a fini par rattraper.
        mock_search.side_effect = [
            _search_response([]),
            _search_response([]),
            _search_response([_hit()]),
        ]

        result = search_user_documents(query="q", user_sub="u", session_id="s")

        assert "Contenu du chunk." in result
        assert mock_search.call_count == 3
        assert mock_sleep.call_count == 2  # une pause entre chaque tentative infructueuse

    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_budget_de_retry_plus_genereux_si_fichier_tout_juste_joint(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([])  # jamais rien, même après tous les retries
        with patch("tools.document_search._term_only_fallback", return_value=[]):
            search_user_documents(
                query="q",
                user_sub="u",
                session_id="s",
                has_recent_upload=True,
                recent_upload_filenames=["nouveau.pdf"],
            )
        # budget "patient" = 11 tentatives (cf. constantes du module)
        assert mock_search.call_count == doc_search_module._KNN_RETRY_ATTEMPTS_PATIENT

    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_budget_normal_si_pas_de_fichier_tout_juste_joint(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([])
        with patch("tools.document_search._term_only_fallback", return_value=[]):
            search_user_documents(query="q", user_sub="u", session_id="s", has_recent_upload=False)
        assert mock_search.call_count == doc_search_module._KNN_RETRY_ATTEMPTS_NORMAL


@patch("tools.document_search.time.sleep")
class TestFiltrageParFichierRecent:
    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_ignore_les_hits_dun_autre_fichier_si_upload_recent_attendu(self, mock_embed, mock_search, mock_sleep):
        # Un hit existe bien, mais il vient d'un AUTRE fichier que celui
        # tout juste uploadé -> ne doit pas être accepté tel quel, le
        # fallback restreint doit prendre le relais.
        mock_search.return_value = _search_response([_hit(filename="ancien.pdf")])
        with patch(
            "tools.document_search._term_only_fallback",
            return_value=[_hit(filename="nouveau.pdf", content="Contenu du nouveau fichier.")],
        ) as mock_fallback:
            result = search_user_documents(
                query="q",
                user_sub="u",
                session_id="s",
                has_recent_upload=True,
                recent_upload_filenames=["nouveau.pdf"],
            )

        assert "Contenu du nouveau fichier." in result
        # Le fallback doit être restreint au(x) fichier(s) attendu(s).
        assert mock_fallback.call_args.kwargs["only_filenames"] == {"nouveau.pdf"}

    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_accepte_immediatement_le_hit_du_bon_fichier(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([_hit(filename="nouveau.pdf")])

        search_user_documents(
            query="q", user_sub="u", session_id="s",
            has_recent_upload=True, recent_upload_filenames=["nouveau.pdf"],
        )

        assert mock_search.call_count == 1  # trouvé du premier coup, pas de retry


@patch("tools.document_search.time.sleep")
class TestAucunResultat:
    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_aucun_resultat_du_tout_sans_upload_recent(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([])
        with patch("tools.document_search._term_only_fallback", return_value=[]):
            result = search_user_documents(query="q", user_sub="u", session_id="s")
        assert "Aucun résultat trouvé" in result

    @patch("tools.document_search.opensearch.search")
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_mentionne_le_nom_du_fichier_attendu(self, mock_embed, mock_search, mock_sleep):
        mock_search.return_value = _search_response([])
        with patch("tools.document_search._term_only_fallback", return_value=[]):
            result = search_user_documents(
                query="q", user_sub="u", session_id="s",
                has_recent_upload=True, recent_upload_filenames=["contrat.pdf"],
            )
        assert "contrat.pdf" in result

    @patch("tools.document_search.opensearch.search", side_effect=ConnectionError("AOSS indisponible"))
    @patch("tools.document_search.invoke_titan_embedding", return_value=FAKE_EMBEDDING)
    def test_exception_opensearch_est_capturee(self, mock_embed, mock_search, mock_sleep):
        result = search_user_documents(query="q", user_sub="u", session_id="s")
        assert "Erreur pendant la recherche" in result
        assert "AOSS indisponible" in result


class TestOutilExposeAuLlm:
    def test_refuse_lexecution_directe_sans_contexte(self):
        # document_search (l'outil @tool) ne doit JAMAIS être exécuté
        # directement par le LLM : le contexte (user_sub/session_id) est
        # injecté uniquement par call_tools() côté backend.
        result = document_search.invoke({"query": "peu importe"})
        assert "contexte utilisateur" in result

    def test_nom_et_description(self):
        assert document_search.name == "document_search"
        assert document_search.description
