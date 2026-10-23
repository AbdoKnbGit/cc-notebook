<!-- claude-notebook: {"version": 1, "title": "Visual lab · decay experiment"} -->

<!-- claude-cell: {"id": "c331cd7bdc19", "type": "markdown", "trailing_newline": false} -->
````markdown
# A visual lab inside Claude Code

One experiment connects an explanation, a diagram, an equation and a Python plot.

```mermaid
graph LR
  Q[Question] --> P[Python]
  P --> E[Explanation]
```

Our model uses a time constant $\tau = 2$ and initial signal $A = 1$.

$$
y(t) = A e^{-t / \tau}
$$

Select cell 2 for an inline image. Run cell 3 for live Python output.
````

<!-- claude-cell: {"id": "307531db9c82", "type": "markdown", "trailing_newline": false} -->
```markdown
## An image embedded in Markdown

<!-- /lab demo inserts the generated plot here -->

The blue curve is the proposed model. Orange points show where we sample it.
On terminals without native images, this appears as a coloured block preview.
Use **Open original image** for full detail.
```

<!-- claude-cell: {"id": "a173068f4dc3", "type": "python", "trailing_newline": false} -->
```python
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, Markdown, Latex

A, tau = 1.0, 2.0
t = np.linspace(0, 6, 80)
y = A * np.exp(-t / tau)

display(Markdown("### Computed result\nThe explanation, equation and figure below are outputs of this cell."))
display(Latex(r"y(t) = A e^{-t / \tau}"))
fig, ax = plt.subplots(figsize=(7, 3.5), layout="constrained")
ax.plot(t, y, color="#2563eb", linewidth=3)
ax.set(xlabel="Time (s)", ylabel="Signal", title="Live kernel: exponential decay")
ax.grid(alpha=0.2)
plt.show()
print(f"After {tau:g} seconds, signal = {A * np.exp(-1):.4f}")
```

<!-- claude-cell: {"id": "d5e63d2bc597", "type": "markdown", "trailing_newline": false} -->
```markdown
## Interpret and iterate

After running cell 3, compare its final printed value with the curve.
Edit `tau` and run it again: a larger time constant should produce slower decay.

Python variables remain alive between cells. Editing a cell does not execute it.
The AI cell below generates editable cells only when you choose **Generate cells**.
```

<!-- claude-cell: {"id": "f81f7a583d27", "type": "ai", "trailing_newline": false} -->
```text
Explain the measured result above. Add a Markdown cell with a short interpretation and a Mermaid diagram of the experiment. Then add a Python cell comparing tau=1, tau=2 and tau=4 on one plot. Do not claim the proposed comparison has already run.
```
