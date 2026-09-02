"""
tests/test_evaluation_harness.py
==================================

Teste la logique PURE du harnais d'évaluation (`evaluation/run_evaluation.py`) :
parsing SSE et notation des scénarios. Ne fait AUCUN appel réseau — c'est
justement ce qui permet de garantir que le harnais lui-même est fiable
avant de l'exécuter contre le vrai déploiement.
"""

from pathlib import Path

from evaluation.run_evaluation import (
    ScenarioResult,
    compute_metrics,
    compute_metrics_by_category,
    parse_sse_line,
    score_scenario,
    write_csv_report,
    write_markdown_report,
)
from evaluation.scenarios import SCENARIOS, Scenario


class TestParseSseLine:
    def test_parse_une_ligne_data_valide(self):
        assert parse_sse_line('data: {"type": "token", "data": "Bonjour"}') == {
            "type": "token", "data": "Bonjour",
        }

    def test_ignore_une_ligne_vide(self):
        assert parse_sse_line("") is None
        assert parse_sse_line("   ") is None

    def test_ignore_une_ligne_qui_nest_pas_du_sse(self):
        assert parse_sse_line("event: ping") is None

    def test_ignore_un_data_vide(self):
        assert parse_sse_line("data:") is None

    def test_json_invalide_ne_leve_pas_dexception(self):
        assert parse_sse_line("data: {invalide") is None


class TestScoreScenarioCasNominal:
    def _scenario(self, **overrides):
        base = dict(id="t1", category="test", prompt="q")
        base.update(overrides)
        return Scenario(**base)

    def test_reussit_si_mots_cles_et_outil_corrects(self):
        scenario = self._scenario(expects_tool=True, expected_keyword_groups=[["45"]])
        success, reasons = score_scenario(scenario, final_answer="Le résultat est 45.", had_error=False, tool_steps=1)
        assert success is True
        assert reasons == ["OK"]

    def test_echoue_si_mot_cle_absent(self):
        scenario = self._scenario(expected_keyword_groups=[["45"]])
        success, reasons = score_scenario(scenario, final_answer="Le résultat est 46.", had_error=False, tool_steps=0)
        assert success is False
        assert any("45" in r for r in reasons)

    def test_groupe_de_mots_cles_est_un_ou(self):
        scenario = self._scenario(expected_keyword_groups=[["fatima", "Fatima"]])
        success, _ = score_scenario(scenario, final_answer="Bonjour Fatima !", had_error=False, tool_steps=0)
        assert success is True

    def test_plusieurs_groupes_sont_un_et(self):
        scenario = self._scenario(expected_keyword_groups=[["fatima"], ["smartovate"]])
        success, reasons = score_scenario(scenario, final_answer="Bonjour Fatima.", had_error=False, tool_steps=0)
        assert success is False
        assert len(reasons) == 1  # seul le groupe "smartovate" manque

    def test_echoue_si_outil_attendu_non_declenche(self):
        scenario = self._scenario(expects_tool=True)
        success, reasons = score_scenario(scenario, final_answer="Une réponse.", had_error=False, tool_steps=0)
        assert success is False
        assert any("outil" in r.lower() for r in reasons)

    def test_echoue_si_outil_declenche_alors_quinattendu(self):
        scenario = self._scenario(expects_tool=False)
        success, reasons = score_scenario(scenario, final_answer="Une réponse.", had_error=False, tool_steps=1)
        assert success is False

    def test_expects_tool_none_nimporte_pas(self):
        scenario = self._scenario(expects_tool=None)
        success, _ = score_scenario(scenario, final_answer="Une réponse.", had_error=False, tool_steps=0)
        assert success is True
        success, _ = score_scenario(scenario, final_answer="Une réponse.", had_error=False, tool_steps=3)
        assert success is True

    def test_echoue_si_mot_interdit_present(self):
        scenario = self._scenario(must_not_contain=["uid="])
        success, reasons = score_scenario(scenario, final_answer="Résultat : uid=0(root)", had_error=False, tool_steps=1)
        assert success is False
        assert any("uid=" in r for r in reasons)

    def test_echoue_si_reponse_vide(self):
        scenario = self._scenario()
        success, reasons = score_scenario(scenario, final_answer="   ", had_error=False, tool_steps=0)
        assert success is False
        assert "vide" in reasons[0].lower()

    def test_echoue_si_erreur_http(self):
        scenario = self._scenario()
        success, reasons = score_scenario(scenario, final_answer="", had_error=True, tool_steps=0)
        assert success is False


class TestScoreScenarioRejetPropre:
    def test_reussit_si_rejet_attendu_et_obtenu(self):
        scenario = Scenario(id="t", category="c", prompt="", expect_clean_rejection=True)
        success, reasons = score_scenario(scenario, final_answer="", had_error=True, tool_steps=0)
        assert success is True

    def test_echoue_si_rejet_attendu_mais_traite_normalement(self):
        scenario = Scenario(id="t", category="c", prompt="", expect_clean_rejection=True)
        success, reasons = score_scenario(scenario, final_answer="Une réponse normale.", had_error=False, tool_steps=0)
        assert success is False


class TestListeDeScenarios:
    def test_au_moins_vingt_scenarios(self):
        assert len(SCENARIOS) >= 20

    def test_tous_les_ids_sont_uniques(self):
        ids = [s.id for s in SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_couvre_les_cinq_categories_doutils_principales(self):
        categories = {s.category for s in SCENARIOS}
        assert {"calculator", "weather", "web_search", "rag_interne", "multi_outils"}.issubset(categories)


def _fake_result(scenario_id, category, success, latency, tool_steps=1):
    return ScenarioResult(
        scenario_id=scenario_id, category=category, prompt="q", success=success,
        latency_seconds=latency, had_error=not success, error_message=None,
        tool_steps=tool_steps, final_answer="réponse", reasons=["OK"] if success else ["échec"],
        http_status=200,
    )


class TestMetriques:
    def test_taux_de_succes(self):
        results = [_fake_result("a", "c1", True, 1.0), _fake_result("b", "c1", False, 2.0)]
        metrics = compute_metrics(results)
        assert metrics["success_rate_pct"] == 50.0
        assert metrics["successes"] == 1
        assert metrics["failures"] == 1

    def test_latence_moyenne_et_mediane(self):
        results = [_fake_result(str(i), "c1", True, float(i)) for i in range(1, 6)]  # 1,2,3,4,5
        metrics = compute_metrics(results)
        assert metrics["latency_avg_s"] == 3.0
        assert metrics["latency_median_s"] == 3.0
        assert metrics["latency_max_s"] == 5.0

    def test_metriques_par_categorie(self):
        results = [
            _fake_result("a", "calculator", True, 1.0),
            _fake_result("b", "calculator", False, 2.0),
            _fake_result("c", "weather", True, 3.0),
        ]
        by_cat = compute_metrics_by_category(results)
        assert by_cat["calculator"]["success_rate_pct"] == 50.0
        assert by_cat["weather"]["success_rate_pct"] == 100.0

    def test_metriques_sur_liste_vide_ne_plante_pas(self):
        metrics = compute_metrics([])
        assert metrics["total_scenarios"] == 0
        assert metrics["success_rate_pct"] == 0.0


class TestGenerationDesRapports:
    def test_rapport_markdown_est_cree_et_contient_les_totaux(self, tmp_path):
        results = [_fake_result("calc-01", "calculator", True, 1.5)]
        output_path = tmp_path / "rapport.md"
        write_markdown_report(results, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "calc-01" in content
        assert "100.0%" in content

    def test_rapport_csv_est_cree_avec_une_ligne_par_scenario(self, tmp_path):
        results = [_fake_result("calc-01", "calculator", True, 1.5), _fake_result("weather-01", "weather", False, 2.5)]
        output_path = tmp_path / "rapport.csv"
        write_csv_report(results, output_path)

        content = output_path.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert len(lines) == 3  # en-tête + 2 scénarios
        assert "calc-01" in lines[1]
        assert "weather-01" in lines[2]

    def test_rapport_markdown_liste_les_echecs_en_detail(self, tmp_path):
        results = [_fake_result("weather-99", "weather", False, 4.2)]
        output_path = tmp_path / "rapport.md"
        write_markdown_report(results, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "weather-99" in content
        assert "échec" in content
