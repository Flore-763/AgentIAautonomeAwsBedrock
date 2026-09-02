"""
evaluation/run_evaluation.py
==============================

Harnais d'évaluation de bout en bout — livrable #4 du CDC ("Rapport
d'évaluation ... ≥ 20 scénarios de test avec métriques : précision,
latence, taux de succès").

Ce script appelle le VRAI endpoint déployé (`/agent/chat/stream`), pas
une version mockée : contrairement aux tests unitaires (`lambda/tests/`,
qui mockent tout pour tester la LOGIQUE), ce harnais mesure le
comportement réel du système en production/staging, latence réseau et
temps de réponse LLM inclus.

Prérequis (impossibles à obtenir depuis un environnement sans accès à
votre compte AWS — c'est VOUS qui exécutez ce script, pas moi) :
  - Un token d'identité Cognito valide (non expiré) pour un utilisateur
    de test.
  - La clé API (`x-api-key`) de votre déploiement.

Usage :
    export AGENT_BASE_URL="https://xxxx.lambda-url.us-west-2.on.aws"
    export AGENT_API_KEY="..."
    export AGENT_ID_TOKEN="eyJraW..."   # cf. README.md pour l'obtenir
    python -m evaluation.run_evaluation

Options utiles :
    python -m evaluation.run_evaluation --category calculator
    python -m evaluation.run_evaluation --scenario calc-01 --scenario weather-01
    python -m evaluation.run_evaluation --output-dir ./rapport_evaluation
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

from evaluation.scenarios import SCENARIOS, Scenario

DEFAULT_TIMEOUT_SECONDS = 90


# --------------------------------------------------------------------------
# Fonctions PURES (aucun accès réseau) : testées indépendamment dans
# tests/test_evaluation_harness.py, sans jamais appeler l'API réelle.
# --------------------------------------------------------------------------

def parse_sse_line(line: str) -> Optional[dict]:
    """Parse une ligne SSE brute ('data: {...}') en dict. None si non pertinente."""
    if not line:
        return None
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return None
    payload = stripped[len("data:"):].strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def score_scenario(scenario: Scenario, final_answer: str, had_error: bool, tool_steps: int) -> tuple[bool, List[str]]:
    """
    Applique le critère de succès du scénario à une réponse déjà obtenue.
    Retourne (succès, [raisons]) — les raisons sont TOUJOURS renseignées
    (y compris en cas de succès : "OK"), pour que le rapport final soit
    lisible sans avoir à deviner pourquoi un scénario a réussi ou échoué.
    """
    reasons: List[str] = []

    if scenario.expect_clean_rejection:
        if had_error:
            return True, ["Rejet propre obtenu, comme attendu."]
        return False, ["Un rejet HTTP propre était attendu, mais la requête a été traitée normalement."]

    if had_error:
        return False, ["Erreur HTTP/SSE inattendue (voir error_message)."]

    if not final_answer.strip():
        return False, ["Réponse finale vide."]

    answer_lower = final_answer.lower()

    if scenario.expects_tool is True and tool_steps < 1:
        reasons.append(f"Aucun outil déclenché alors qu'au moins un était attendu (tool_steps={tool_steps}).")
    if scenario.expects_tool is False and tool_steps > 0:
        reasons.append(f"Un outil a été déclenché alors qu'aucun n'était attendu (tool_steps={tool_steps}).")

    for group in scenario.expected_keyword_groups:
        if not any(keyword.lower() in answer_lower for keyword in group):
            reasons.append(f"Aucun mot-clé de {group} trouvé dans la réponse.")

    for forbidden in scenario.must_not_contain:
        if forbidden.lower() in answer_lower:
            reasons.append(f"Mot-clé interdit détecté : '{forbidden}'.")

    if reasons:
        return False, reasons
    return True, ["OK"]


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    prompt: str
    success: bool
    latency_seconds: float
    had_error: bool
    error_message: Optional[str]
    tool_steps: int
    final_answer: str
    reasons: List[str] = field(default_factory=list)
    http_status: Optional[int] = None


# --------------------------------------------------------------------------
# Exécution réseau réelle
# --------------------------------------------------------------------------

def run_scenario_live(
    scenario: Scenario,
    base_url: str,
    headers: Dict[str, str],
    session_ids: Dict[str, str],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ScenarioResult:
    """Exécute UN scénario contre l'API réellement déployée et le note."""
    url = f"{base_url.rstrip('/')}/agent/chat/stream"
    session_id = session_ids.get(scenario.session_group) if scenario.session_group else None
    payload = {"message": scenario.prompt, "session_id": session_id}

    final_answer = ""
    tool_steps = 0
    had_error = False
    error_message: Optional[str] = None
    http_status: Optional[int] = None
    new_session_id = session_id

    start = time.time()
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout)
        http_status = response.status_code
        if response.status_code >= 400:
            had_error = True
            try:
                error_message = response.json().get("error", response.text[:300])
            except (ValueError, json.JSONDecodeError):
                error_message = response.text[:300]
        else:
            for raw_line in response.iter_lines(decode_unicode=True):
                event = parse_sse_line(raw_line)
                if event is None:
                    continue
                event_type = event.get("type")
                data = event.get("data")
                if event_type == "session" and isinstance(data, dict):
                    new_session_id = data.get("session_id", new_session_id)
                elif event_type == "token" and isinstance(data, str):
                    final_answer += data
                elif event_type == "step" and isinstance(data, dict):
                    if data.get("node") == "call_tools":
                        tool_steps += 1
                elif event_type == "error":
                    had_error = True
                    error_message = data.get("message") if isinstance(data, dict) else str(data)
    except requests.exceptions.RequestException as exc:
        had_error = True
        error_message = str(exc)

    latency = time.time() - start

    if scenario.session_group:
        session_ids[scenario.session_group] = new_session_id

    success, reasons = score_scenario(scenario, final_answer, had_error, tool_steps)
    if had_error and error_message:
        reasons = [error_message] + reasons

    return ScenarioResult(
        scenario_id=scenario.id,
        category=scenario.category,
        prompt=scenario.prompt,
        success=success,
        latency_seconds=latency,
        had_error=had_error,
        error_message=error_message,
        tool_steps=tool_steps,
        final_answer=final_answer,
        reasons=reasons,
        http_status=http_status,
    )


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

def compute_metrics(results: List[ScenarioResult]) -> dict:
    latencies = [r.latency_seconds for r in results]
    successes = [r for r in results if r.success]
    return {
        "total_scenarios": len(results),
        "successes": len(successes),
        "failures": len(results) - len(successes),
        "success_rate_pct": round(100 * len(successes) / len(results), 1) if results else 0.0,
        "latency_avg_s": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "latency_median_s": round(statistics.median(latencies), 2) if latencies else 0.0,
        "latency_p95_s": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 2) if latencies else 0.0,
        "latency_max_s": round(max(latencies), 2) if latencies else 0.0,
    }


def compute_metrics_by_category(results: List[ScenarioResult]) -> dict:
    by_category: Dict[str, List[ScenarioResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)
    return {category: compute_metrics(subset) for category, subset in by_category.items()}


def write_markdown_report(results: List[ScenarioResult], output_path: Path) -> None:
    overall = compute_metrics(results)
    by_category = compute_metrics_by_category(results)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Rapport d'évaluation — Agent IA Autonome",
        "",
        f"Généré le {now} — {overall['total_scenarios']} scénarios exécutés.",
        "",
        "## Résumé global",
        "",
        f"- **Taux de succès** : {overall['success_rate_pct']}% ({overall['successes']}/{overall['total_scenarios']})",
        f"- **Latence moyenne** : {overall['latency_avg_s']} s",
        f"- **Latence médiane** : {overall['latency_median_s']} s",
        f"- **Latence P95** : {overall['latency_p95_s']} s",
        f"- **Latence max** : {overall['latency_max_s']} s",
        "",
        "## Détail par catégorie",
        "",
        "| Catégorie | Succès | Total | Taux | Latence moy. |",
        "|---|---|---|---|---|",
    ]
    for category, metrics in sorted(by_category.items()):
        lines.append(
            f"| {category} | {metrics['successes']} | {metrics['total_scenarios']} | "
            f"{metrics['success_rate_pct']}% | {metrics['latency_avg_s']} s |"
        )

    lines += ["", "## Détail par scénario", ""]
    lines += ["| ID | Catégorie | Succès | Latence (s) | Outils appelés | Raisons |", "|---|---|---|---|---|---|"]
    for r in results:
        status = "✅" if r.success else "❌"
        reasons = "; ".join(r.reasons).replace("|", "/")[:200]
        lines.append(f"| {r.scenario_id} | {r.category} | {status} | {r.latency_seconds:.2f} | {r.tool_steps} | {reasons} |")

    lines += ["", "## Réponses complètes (scénarios en échec uniquement)", ""]
    failed = [r for r in results if not r.success]
    if not failed:
        lines.append("Aucun échec ")
    for r in failed:
        lines += [
            f"### {r.scenario_id}",
            "",
            f"**Prompt :** {r.prompt}",
            "",
            f"**Réponse obtenue :** {r.final_answer or '(vide)'}",
            "",
            f"**Raisons de l'échec :** {'; '.join(r.reasons)}",
            "",
        ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_csv_report(results: List[ScenarioResult], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario_id", "category", "success", "latency_seconds", "tool_steps", "http_status", "reasons", "final_answer"])
        for r in results:
            writer.writerow([
                r.scenario_id, r.category, r.success, f"{r.latency_seconds:.3f}",
                r.tool_steps, r.http_status, "; ".join(r.reasons), r.final_answer,
            ])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.getenv("AGENT_BASE_URL"), help="URL de base de l'API (ou $AGENT_BASE_URL)")
    parser.add_argument("--api-key", default=os.getenv("AGENT_API_KEY"), help="Header x-api-key (ou $AGENT_API_KEY)")
    parser.add_argument("--id-token", default=os.getenv("AGENT_ID_TOKEN"), help="Token Cognito Bearer (ou $AGENT_ID_TOKEN)")
    parser.add_argument("--category", action="append", default=None, help="Ne lancer qu'une (ou plusieurs) catégorie(s)")
    parser.add_argument("--scenario", action="append", default=None, help="Ne lancer qu'un (ou plusieurs) scénario(s) par id")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-dir", default="./evaluation_report")
    args = parser.parse_args(argv)

    if not args.base_url or not args.api_key or not args.id_token:
        print(
            "Erreur : --base-url, --api-key et --id-token sont requis "
            "(ou les variables d'environnement AGENT_BASE_URL / AGENT_API_KEY / AGENT_ID_TOKEN).\n"
            "Voir evaluation/README.md pour savoir comment les obtenir.",
            file=sys.stderr,
        )
        return 1

    scenarios = SCENARIOS
    if args.category:
        scenarios = [s for s in scenarios if s.category in args.category]
    if args.scenario:
        scenarios = [s for s in scenarios if s.id in args.scenario]
    if not scenarios:
        print("Aucun scénario ne correspond aux filtres fournis.", file=sys.stderr)
        return 1

    headers = {
        "Content-Type": "application/json",
        "x-api-key": args.api_key,
        "Authorization": f"Bearer {args.id_token}",
    }

    session_ids: Dict[str, str] = {}
    results: List[ScenarioResult] = []

    print(f"Lancement de {len(scenarios)} scénario(s) contre {args.base_url}...\n")
    for scenario in scenarios:
        print(f"  -> {scenario.id} ({scenario.category})...", end=" ", flush=True)
        result = run_scenario_live(scenario, args.base_url, headers, session_ids, timeout=args.timeout)
        results.append(result)
        status = "OK" if result.success else "ECHEC"
        print(f"{status} ({result.latency_seconds:.1f}s)")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "rapport_evaluation.md"
    csv_path = output_dir / "rapport_evaluation.csv"
    write_markdown_report(results, markdown_path)
    write_csv_report(results, csv_path)

    overall = compute_metrics(results)
    print(f"\nTaux de succès : {overall['success_rate_pct']}% ({overall['successes']}/{overall['total_scenarios']})")
    print(f"Latence moyenne : {overall['latency_avg_s']}s | P95 : {overall['latency_p95_s']}s")
    print(f"Rapport : {markdown_path}")
    print(f"Données brutes : {csv_path}")

    return 0 if overall["success_rate_pct"] == 100.0 else 0  # informatif, pas bloquant pour un pipeline CI


if __name__ == "__main__":
    sys.exit(main())
