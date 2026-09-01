# Rapport d'évaluation — Agent IA Autonome

Généré le 2026-08-27 02:24 UTC — 23 scénarios exécutés.

## Résumé global

- **Taux de succès** : 100.0% (23/23)
- **Latence moyenne** : 7.64 s
- **Latence médiane** : 6.79 s
- **Latence P95** : 9.58 s
- **Latence max** : 18.84 s

### Métriques SSE

- **TTFT moyen** : 3.6 s
- **TTFT médian** : 2.98 s
- **TTFT P95** : 4.97 s
- **Chunks SSE moyens** : 60.3
- **Débit moyen** : 7.41 chunks/s
## Détail par catégorie

| Catégorie | Succès | Total | Taux | Latence moy. |
|---|---|---|---|---|
| calculator | 4 | 4 | 100.0% | 5.92 s |
| culture_generale | 2 | 2 | 100.0% | 4.57 s |
| memoire | 2 | 2 | 100.0% | 5.31 s |
| multi_outils | 2 | 2 | 100.0% | 13.03 s |
| prompt_systeme | 4 | 4 | 100.0% | 6.61 s |
| rag_interne | 3 | 3 | 100.0% | 9.2 s |
| robustesse | 2 | 2 | 100.0% | 5.44 s |
| weather | 2 | 2 | 100.0% | 6.97 s |
| web_search | 2 | 2 | 100.0% | 13.68 s |

## Détail par scénario

| ID | Catégorie | Succès | Latence (s) | TTFT (s) | Chunks | Chunks/s | Outils | Raisons |
|---|---|---|---:|---:|---:|---:|---:|---|
| gk-01 | culture_generale | ✅ | 5.12 | 3.71 | 23 | 4.49 | 0 | OK |
| gk-02 | culture_generale | ✅ | 4.03 | 2.50 | 24 | 5.96 | 0 | OK |
| calc-01 | calculator | ✅ | 6.31 | 4.82 | 6 | 0.95 | 1 | OK |
| calc-02 | calculator | ✅ | 5.32 | 2.64 | 23 | 4.32 | 1 | OK |
| calc-03 | calculator | ✅ | 6.05 | 2.77 | 38 | 6.28 | 1 | OK |
| calc-04-edge | calculator | ✅ | 5.98 | 3.85 | 35 | 5.85 | 1 | OK |
| weather-01 | weather | ✅ | 7.03 | 2.92 | 29 | 4.13 | 1 | OK |
| weather-02-edge | weather | ✅ | 6.92 | 4.88 | 34 | 4.92 | 1 | OK |
| web-01 | web_search | ✅ | 8.52 | 4.36 | 92 | 10.80 | 1 | OK |
| web-02 | web_search | ✅ | 18.84 | 3.04 | 240 | 12.74 | 1 | OK |
| rag-01 | rag_interne | ✅ | 8.62 | 2.57 | 90 | 10.44 | 1 | OK |
| rag-02 | rag_interne | ✅ | 9.58 | 2.86 | 81 | 8.45 | 1 | OK |
| rag-03 | rag_interne | ✅ | 9.40 | 2.81 | 111 | 11.80 | 1 | OK |
| multi-01 | multi_outils | ✅ | 7.65 | 2.76 | 30 | 3.92 | 1 | OK |
| multi-02 | multi_outils | ✅ | 18.41 | 7.26 | 79 | 4.29 | 2 | OK |
| mem-01a | memoire | ✅ | 6.79 | 4.97 | 52 | 7.66 | 0 | OK |
| mem-01b | memoire | ✅ | 3.84 | 2.88 | 12 | 3.13 | 0 | OK |
| hors-sujet-01 | prompt_systeme | ✅ | 6.21 | 2.64 | 68 | 10.95 | 0 | OK |
| hors-sujet-02-religion | prompt_systeme | ✅ | 7.73 | 2.62 | 118 | 15.27 | 0 | OK |
| humour-creatif | prompt_systeme | ✅ | 5.98 | 5.55 | 40 | 6.68 | 0 | OK |
| clarification-01 | prompt_systeme | ✅ | 6.52 | 3.64 | 50 | 7.66 | 0 | OK |
| robustesse-01-message-vide | robustesse | ✅ | 1.76 | - | 0 | - | 0 | Message is required; Rejet propre obtenu, comme attendu. |
| robustesse-02-injection-calcul | robustesse | ✅ | 9.11 | 3.27 | 112 | 12.30 | 0 | OK |

## Réponses complètes (scénarios en échec uniquement)

Aucun échec 



