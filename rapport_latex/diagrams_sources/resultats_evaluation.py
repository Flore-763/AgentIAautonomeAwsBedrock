# Régénérer à partir de rapport_evaluation.csv (harnais d'évaluation) :
# adapter les listes categories/success_rate/totals aux valeurs de la
# dernière exécution avant de relancer ce script.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

categories = ["calculator", "culture_\ngenerale", "memoire", "multi_\noutils", "prompt_\nsysteme", "rag_\ninterne", "robustesse", "weather", "web_\nsearch"]
success_rate = [100.0, 100.0, 100.0, 100.0, 100.0, 66.7, 100.0, 100.0, 100.0]
totals = [4, 2, 2, 2, 4, 3, 2, 2, 2]

fig, ax = plt.subplots(figsize=(9.5, 4), dpi=180)
colors = ["#3C8C3C" if r == 100.0 else "#B8860B" if r >= 50 else "#A94442" for r in success_rate]
bars = ax.bar(categories, success_rate, color=colors, edgecolor="black", linewidth=0.6)
for bar, rate, total in zip(bars, success_rate, totals):
    n_success = round(rate/100*total)
    ax.text(bar.get_x() + bar.get_width()/2, rate + 2, f"{rate:.0f}%\n({n_success}/{total})", ha="center", va="bottom", fontsize=8)
ax.set_ylim(0, 115)
ax.set_ylabel("Taux de succès")
ax.set_title("Rapport d'évaluation — taux de succès par catégorie (23 scénarios)", fontsize=11.5, fontweight="bold")
ax.axhline(100, color="grey", linewidth=0.5, linestyle=":")
ax.grid(axis="y", linestyle="--", alpha=0.35)
for spine in ["top", "right"]:
    ax.spines[spine].set_visible(False)
plt.xticks(fontsize=8.5)
plt.tight_layout()
plt.savefig("resultats_evaluation.png", dpi=180)
