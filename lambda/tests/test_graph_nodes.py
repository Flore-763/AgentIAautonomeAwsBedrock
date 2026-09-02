"""
tests/test_graph_nodes.py
===========================

Coeur de la logique agent (F1 du CDC) : routage de la boucle ReAct et les
deux garde-fous (nombre max d'itérations, détection de boucle sur 3
répétitions identiques). Ce sont des fonctions (quasi) pures qui prennent
un `AgentState` (dict) en entrée : pas besoin de mocker le LLM pour les
tester, seul `call_tools` (exécution réelle des outils) en a besoin.
"""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from graph.nodes import (
    LOOP_THRESHOLD,
    call_tools,
    finalize,
    handle_loop_detected,
    handle_max_iterations,
    route_after_model,
    route_after_tools,
)
import graph.nodes as nodes_module


def _ai_message(tool_calls=None, content="Voici la réponse finale."):
    return AIMessage(content=content, tool_calls=tool_calls or [])


def _tool_call(name, args, call_id="call_1"):
    return {"name": name, "args": args, "id": call_id}


def _base_state(**overrides):
    state = {
        "user_sub": "user-1",
        "session_id": "user-1#sess-1",
        "raw_session_id": "sess-1",
        "messages": [],
        "context": None,
        "iterations": 0,
        "max_iterations": 10,
        "tool_call_history": [],
        "final_answer": None,
        "error": None,
        "has_recent_upload": False,
        "recent_upload_filenames": [],
    }
    state.update(overrides)
    return state


class TestRouteAfterModel:
    def test_reponse_directe_sans_outil_va_a_finalize(self):
        state = _base_state(messages=[_ai_message(tool_calls=[])], iterations=1)
        assert route_after_model(state) == "finalize"

    def test_appel_doutil_va_a_call_tools(self):
        state = _base_state(
            messages=[_ai_message(tool_calls=[_tool_call("get_weather", {"city": "Paris"})])],
            iterations=1,
        )
        assert route_after_model(state) == "call_tools"

    def test_max_iterations_atteint_est_prioritaire(self):
        # Même si le LLM redemande un outil, on s'arrête si le plafond est atteint.
        state = _base_state(
            messages=[_ai_message(tool_calls=[_tool_call("get_weather", {"city": "Paris"})])],
            iterations=10,
            max_iterations=10,
        )
        assert route_after_model(state) == "max_iterations"

    def test_juste_en_dessous_du_plafond_continue_normalement(self):
        state = _base_state(messages=[_ai_message(tool_calls=[])], iterations=9, max_iterations=10)
        assert route_after_model(state) == "finalize"


class TestRouteAfterTools:
    def test_moins_de_trois_appels_ne_declenche_pas_la_detection(self):
        history = [
            {"tool": "calculator", "args": {"expression": "1+1"}},
            {"tool": "calculator", "args": {"expression": "1+1"}},
        ]
        state = _base_state(tool_call_history=history)
        assert route_after_tools(state) == "call_model"

    def test_trois_appels_identiques_declenche_la_boucle(self):
        call = {"tool": "calculator", "args": {"expression": "1+1"}}
        state = _base_state(tool_call_history=[call, dict(call), dict(call)])
        assert route_after_tools(state) == "loop_detected"

    def test_trois_appels_avec_arguments_differents_ne_declenche_pas(self):
        history = [
            {"tool": "calculator", "args": {"expression": "1+1"}},
            {"tool": "calculator", "args": {"expression": "2+2"}},
            {"tool": "calculator", "args": {"expression": "3+3"}},
        ]
        state = _base_state(tool_call_history=history)
        assert route_after_tools(state) == "call_model"

    def test_trois_appels_a_des_outils_differents_ne_declenche_pas(self):
        history = [
            {"tool": "calculator", "args": {"expression": "1+1"}},
            {"tool": "get_weather", "args": {"city": "Paris"}},
            {"tool": "calculator", "args": {"expression": "1+1"}},
        ]
        state = _base_state(tool_call_history=history)
        assert route_after_tools(state) == "call_model"

    def test_seuls_les_n_derniers_appels_comptent(self):
        # 3 appels identiques, mais suivis d'un appel différent : la
        # fenêtre glissante des LOOP_THRESHOLD DERNIERS appels ne doit
        # plus contenir la répétition -> pas de détection.
        call = {"tool": "calculator", "args": {"expression": "1+1"}}
        history = [dict(call), dict(call), dict(call), {"tool": "get_weather", "args": {"city": "Paris"}}]
        state = _base_state(tool_call_history=history)
        assert route_after_tools(state) == "call_model"

    def test_ordre_des_cles_dans_args_nimporte_pas(self):
        # json.dumps(sort_keys=True) doit rendre la comparaison insensible
        # à l'ordre des clés du dict d'arguments.
        history = [
            {"tool": "get_weather", "args": {"city": "Paris", "unit": "celsius"}},
            {"tool": "get_weather", "args": {"unit": "celsius", "city": "Paris"}},
            {"tool": "get_weather", "args": {"city": "Paris", "unit": "celsius"}},
        ]
        state = _base_state(tool_call_history=history)
        assert route_after_tools(state) == "loop_detected"

    def test_le_seuil_loop_threshold_est_bien_trois(self):
        # Documente/verrouille la valeur attendue par le CDC ("répétée
        # plusieurs fois" -> l'implémentation choisit 3).
        assert LOOP_THRESHOLD == 3


class TestNoeudsTerminaux:
    def test_finalize_extrait_le_texte_du_dernier_message(self):
        state = _base_state(messages=[_ai_message(content="Réponse au format texte simple.")], iterations=2)
        result = finalize(state)
        assert result["final_answer"] == "Réponse au format texte simple."

    def test_finalize_gere_un_contenu_en_liste_de_blocs(self):
        # Bedrock Converse peut renvoyer le contenu sous forme de blocs
        # structurés plutôt qu'une simple string.
        message = AIMessage(content=[{"type": "text", "text": "Bloc de texte."}], tool_calls=[])
        state = _base_state(messages=[message], iterations=1)
        result = finalize(state)
        assert result["final_answer"] == "Bloc de texte."

    def test_finalize_repli_si_contenu_vide(self):
        message = AIMessage(content="", tool_calls=[])
        state = _base_state(messages=[message], iterations=1)
        result = finalize(state)
        assert "pas pu générer" in result["final_answer"]

    def test_handle_max_iterations_retourne_une_erreur_explicite(self):
        state = _base_state(iterations=10, max_iterations=10)
        result = handle_max_iterations(state)
        assert result["error"] == "max_iterations_reached"
        assert "10" in result["final_answer"]

    def test_handle_loop_detected_retourne_une_erreur_explicite(self):
        call = {"tool": "calculator", "args": {"expression": "1+1"}}
        state = _base_state(tool_call_history=[dict(call), dict(call), dict(call)], iterations=5)
        result = handle_loop_detected(state)
        assert result["error"] == "loop_detected"
        assert "boucle" in result["final_answer"].lower()

    def test_handle_loop_detected_ne_plante_pas_si_historique_vide(self):
        # Garde-fou défensif : ne doit jamais lever d'IndexError même dans
        # un état improbable où l'historique serait vide.
        state = _base_state(tool_call_history=[], iterations=1)
        result = handle_loop_detected(state)
        assert result["error"] == "loop_detected"


class TestCallTools:
    """
    `call_tools` dispatche vers le bon outil, journalise chaque appel, et
    intercepte toute exception pour ne jamais faire planter le graphe
    (cf. Bug 2 du CDC : "formate mal les paramètres, provoquant une
    erreur d'exécution"). On remplace `_TOOLS_BY_NAME` par des outils
    factices pour ne dépendre d'aucun service externe réel.
    """

    def _state_with_tool_call(self, tool_name, args):
        return _base_state(
            messages=[_ai_message(tool_calls=[_tool_call(tool_name, args)])],
        )

    @patch("graph.nodes.memory_service")
    def test_execute_loutil_et_produit_un_tool_message_lie(self, mock_memory):
        fake_tool = MagicMock()
        fake_tool.invoke.return_value = "42"
        with patch.object(nodes_module, "_TOOLS_BY_NAME", {"calculator": fake_tool}):
            state = self._state_with_tool_call("calculator", {"expression": "40+2"})
            result = call_tools(state)

        tool_message = result["messages"][0]
        assert tool_message.content == "42"
        assert tool_message.tool_call_id == "call_1"
        fake_tool.invoke.assert_called_once_with({"expression": "40+2"})

    @patch("graph.nodes.memory_service")
    def test_alimente_lhistorique_des_appels_pour_la_detection_de_boucle(self, mock_memory):
        fake_tool = MagicMock()
        fake_tool.invoke.return_value = "resultat"
        with patch.object(nodes_module, "_TOOLS_BY_NAME", {"calculator": fake_tool}):
            state = self._state_with_tool_call("calculator", {"expression": "1+1"})
            result = call_tools(state)

        assert len(result["tool_call_history"]) == 1
        assert result["tool_call_history"][0]["tool"] == "calculator"
        assert result["tool_call_history"][0]["args"] == {"expression": "1+1"}

    @patch("graph.nodes.memory_service")
    def test_outil_inconnu_renvoie_un_message_derreur_sans_planter(self, mock_memory):
        with patch.object(nodes_module, "_TOOLS_BY_NAME", {}):
            state = self._state_with_tool_call("outil_qui_nexiste_pas", {})
            result = call_tools(state)

        assert "inconnu" in result["messages"][0].content

    @patch("graph.nodes.memory_service")
    def test_exception_de_loutil_est_capturee_et_renvoyee_au_llm(self, mock_memory):
        fake_tool = MagicMock()
        fake_tool.invoke.side_effect = ValueError("paramètre invalide")
        with patch.object(nodes_module, "_TOOLS_BY_NAME", {"calculator": fake_tool}):
            state = self._state_with_tool_call("calculator", {"expression": "??"})
            result = call_tools(state)  # ne doit lever aucune exception

        assert "Erreur lors de l'exécution" in result["messages"][0].content
        assert "paramètre invalide" in result["messages"][0].content

    @patch("graph.nodes.memory_service")
    @patch("graph.nodes.search_user_documents")
    def test_document_search_recoit_le_contexte_utilisateur_injecte(self, mock_search_docs, mock_memory):
        # document_search est un cas particulier : le contexte
        # (user_sub/session_id) vient du state, JAMAIS des arguments
        # fournis par le LLM (voir tools/document_search.py).
        mock_search_docs.return_value = "contenu trouvé"
        with patch.object(nodes_module, "_TOOLS_BY_NAME", {"document_search": MagicMock()}):
            state = self._state_with_tool_call("document_search", {"query": "budget 2026"})
            state["user_sub"] = "user-42"
            state["raw_session_id"] = "sess-99"
            state["has_recent_upload"] = True
            state["recent_upload_filenames"] = ["budget.pdf"]
            result = call_tools(state)

        mock_search_docs.assert_called_once_with(
            query="budget 2026",
            user_sub="user-42",
            session_id="sess-99",
            has_recent_upload=True,
            recent_upload_filenames=["budget.pdf"],
        )
        assert result["messages"][0].content == "contenu trouvé"

    @patch("graph.nodes.memory_service")
    def test_une_erreur_de_journalisation_ne_fait_pas_planter_lagent(self, mock_memory):
        # "Journalisation best-effort : un souci de logging ne doit jamais
        # faire planter la boucle de l'agent" (cf. commentaire du code).
        mock_memory.log_tool_call.side_effect = RuntimeError("DynamoDB indisponible")
        fake_tool = MagicMock()
        fake_tool.invoke.return_value = "resultat"
        with patch.object(nodes_module, "_TOOLS_BY_NAME", {"calculator": fake_tool}):
            state = self._state_with_tool_call("calculator", {"expression": "1+1"})
            result = call_tools(state)  # ne doit lever aucune exception

        assert result["messages"][0].content == "resultat"
