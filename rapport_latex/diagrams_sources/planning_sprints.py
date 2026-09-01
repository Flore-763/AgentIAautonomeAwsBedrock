import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date

fig, ax = plt.subplots(figsize=(9.5, 3.8), dpi=180)
sprints = [
    ("Sprint 1\nInfrastructure & configuration initiale", date(2026, 7, 1), date(2026, 7, 14), "#2E5C8A"),
    ("Sprint 2\nCapacités cognitives (mémoire, RAG)", date(2026, 7, 15), date(2026, 7, 28), "#3C8C3C"),
    ("Sprint 3\nAutonomie & exécution de tâches (ReAct)", date(2026, 7, 29), date(2026, 8, 11), "#B8860B"),
    ("Sprint 4\nInterface, déploiement & durcissement", date(2026, 8, 12), date(2026, 8, 25), "#A94442"),
]
for i, (label, start, end, color) in enumerate(sprints):
    duration = (end - start).days + 1
    ax.barh(i, duration, left=start, height=0.5, color=color, alpha=0.88, edgecolor="black", linewidth=0.6)
    mid = start + (end - start) / 2
    ax.text(mid, i - 0.42, label, va="top", ha="center", fontsize=8.3, color="black")
ax.set_yticks([]); ax.set_ylim(3.75, -0.75)
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=1))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.set_xlim(date(2026, 6, 29), date(2026, 8, 27))
ax.set_title("Planning du stage (2 mois) — 4 sprints", fontsize=12, fontweight="bold")
ax.grid(axis="x", linestyle="--", alpha=0.4)
for spine in ["top", "right", "left"]:
    ax.spines[spine].set_visible(False)
plt.xticks(rotation=30, ha="right", fontsize=8)
plt.tight_layout()
plt.savefig("planning_sprints.png", dpi=180)
