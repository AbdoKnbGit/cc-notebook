<!-- claude-notebook: {"version": 1, "title": "One question, one living experiment"} -->

<!-- claude-cell: {"id": "welcome", "type": "markdown", "trailing_newline": false} -->
```markdown
# Which channel converts best?

This is a tiny **synthetic** dataset. Run cell 2 once to keep df alive, then run cell 3 to draw a chart from the same DataFrame.

Edit the data, rerun, and watch downstream results become stale. The AI instruction can generate an explanation and follow-up cells for you to review.
```

<!-- claude-cell: {"id": "data", "type": "python", "trailing_newline": false} -->
```python
import pandas as pd

df = pd.DataFrame({
    "channel": ["Search", "Community", "Newsletter", "Social"],
    "visitors": [2400, 750, 1200, 3200],
    "signups": [156, 90, 132, 96],
})
df["conversion_pct"] = 100 * df.signups / df.visitors
df
```

<!-- claude-cell: {"id": "plot", "type": "python", "trailing_newline": false} -->
```python
import matplotlib.pyplot as plt

ranked = df.sort_values("conversion_pct")
fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
fig.set_facecolor("#101826")
ax.set_facecolor("#101826")
ax.barh(ranked.channel, ranked.conversion_pct, color=["#617894", "#617894", "#61a5fa", "#c2a87e"])
ax.set_xlabel("Visitors who signed up (%)", color="white")
ax.set_title("A smaller channel can convert better", color="white", loc="left", pad=15)
ax.tick_params(colors="white")
for spine in ax.spines.values():
    spine.set_visible(False)
for i, value in enumerate(ranked.conversion_pct):
    ax.text(value + .15, i, f"{value:.1f}%", color="white", va="center")
ax.set_xlim(0, 14)
plt.show()
```

<!-- claude-cell: {"id": "interpret", "type": "ai", "trailing_newline": false} -->
```text
Explain the observed conversion rates in one short Markdown cell. Distinguish the measured differences from causal claims. Then create a Python cell estimating uncertainty in each rate using only the existing df, NumPy, and matplotlib. Label the data as synthetic. Do not execute anything or install packages.
```

<!-- claude-cell: {"id": "next", "type": "markdown", "trailing_newline": false} -->
```markdown
## Try it

1. Select the data cell and choose **Edit**. Change Community signups from 90 to 60, then save.
2. Run it. The old chart and generated explanation are marked **stale**.
3. Run the chart again. Generate fresh explanations only when you want them.
4. Export the notebook to take the experiment, code, and plots into Jupyter.

**Restart & run all** starts a clean kernel and runs Python cells in order. It leaves AI instructions for you to trigger explicitly.
```
