# Rapport d'évaluation — Agent IA Autonome

Généré le 2026-08-27 02:20 UTC — 23 scénarios exécutés.

## Résumé global

- **Taux de succès** : 100.0% (23/23)
- **Latence moyenne** : 8.52 s
- **Latence médiane** : 7.56 s
- **Latence P95** : 14.14 s
- **Latence max** : 18.91 s

## Détail par catégorie

| Catégorie | Succès | Total | Taux | Latence moy. |
|---|---|---|---|---|
| calculator | 4 | 4 | 100.0% | 5.81 s |
| culture_generale | 2 | 2 | 100.0% | 9.33 s |
| memoire | 2 | 2 | 100.0% | 4.76 s |
| multi_outils | 2 | 2 | 100.0% | 11.25 s |
| prompt_systeme | 4 | 4 | 100.0% | 8.89 s |
| rag_interne | 3 | 3 | 100.0% | 9.87 s |
| robustesse | 2 | 2 | 100.0% | 5.55 s |
| weather | 2 | 2 | 100.0% | 6.92 s |
| web_search | 2 | 2 | 100.0% | 15.99 s |

## Détail par scénario

| ID | Catégorie | Succès | Latence (s) | Outils appelés | Raisons |
|---|---|---|---|---|---|
| gk-01 | culture_generale | ✅ | 14.14 | 0 | OK |
| gk-02 | culture_generale | ✅ | 4.52 | 0 | OK |
| calc-01 | calculator | ✅ | 5.12 | 1 | OK |
| calc-02 | calculator | ✅ | 6.14 | 1 | OK |
| calc-03 | calculator | ✅ | 6.15 | 1 | OK |
| calc-04-edge | calculator | ✅ | 5.82 | 1 | OK |
| weather-01 | weather | ✅ | 7.56 | 1 | OK |
| weather-02-edge | weather | ✅ | 6.28 | 1 | OK |
| web-01 | web_search | ✅ | 13.08 | 1 | OK |
| web-02 | web_search | ✅ | 18.91 | 1 | OK |
| rag-01 | rag_interne | ✅ | 10.78 | 1 | OK |
| rag-02 | rag_interne | ✅ | 9.72 | 1 | OK |
| rag-03 | rag_interne | ✅ | 9.11 | 1 | OK |
| multi-01 | multi_outils | ✅ | 8.09 | 1 | OK |
| multi-02 | multi_outils | ✅ | 14.41 | 2 | OK |
| mem-01a | memoire | ✅ | 5.70 | 0 | OK |
| mem-01b | memoire | ✅ | 3.82 | 0 | OK |
| hors-sujet-01 | prompt_systeme | ✅ | 11.16 | 0 | OK |
| hors-sujet-02-religion | prompt_systeme | ✅ | 10.01 | 0 | OK |
| humour-creatif | prompt_systeme | ✅ | 7.14 | 0 | OK |
| clarification-01 | prompt_systeme | ✅ | 7.26 | 0 | OK |
| robustesse-01-message-vide | robustesse | ✅ | 1.74 | 0 | Message is required; Rejet propre obtenu, comme attendu. |
| robustesse-02-injection-calcul | robustesse | ✅ | 9.36 | 0 | OK |

## Réponses complètes (scénarios en échec uniquement)

Aucun échec 