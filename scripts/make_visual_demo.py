"""Rebuild the visual demo and its local plot (generated plot is Git-ignored)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'notebook'))
from document import cell, serialize

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

folder = ROOT / 'examples'
assets = folder / 'assets'
assets.mkdir(parents=True, exist_ok=True)
x = np.linspace(0, 6, 80)
fig, ax = plt.subplots(figsize=(7, 3.5), layout='constrained')
fig.patch.set_facecolor('#f8fafc')
ax.set_facecolor('#f8fafc')
ax.plot(x, np.exp(-x / 2), color='#2563eb', lw=3, label='Predicted signal')
ax.scatter(x[::8], np.exp(-x[::8] / 2), color='#ea580c', s=40, label='Sample points', zorder=3)
ax.set(xlabel='Time (s)', ylabel='Signal', title='A reproducible decay experiment')
ax.grid(alpha=.2)
ax.legend()
fig.savefig(assets / 'decay.png', dpi=120)
plt.close(fig)

cells = [
    cell('markdown', r'''# A visual lab inside Claude Code

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

Select cell 2 for an inline image. Run cell 3 for live Python output.'''),
    cell('markdown', '''## An image embedded in Markdown

<!-- /lab demo inserts the generated plot here -->

The blue curve is the proposed model. Orange points show where we sample it.
On terminals without native images, this appears as a coloured block preview.
Use **Open original image** for full detail.'''),
    cell('python', '''import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, Markdown, Latex

A, tau = 1.0, 2.0
t = np.linspace(0, 6, 80)
y = A * np.exp(-t / tau)

display(Markdown("### Computed result\\nThe explanation, equation and figure below are outputs of this cell."))
display(Latex(r"y(t) = A e^{-t / \\tau}"))
fig, ax = plt.subplots(figsize=(7, 3.5), layout="constrained")
ax.plot(t, y, color="#2563eb", linewidth=3)
ax.set(xlabel="Time (s)", ylabel="Signal", title="Live kernel: exponential decay")
ax.grid(alpha=0.2)
plt.show()
print(f"After {tau:g} seconds, signal = {A * np.exp(-1):.4f}")'''.replace(r'\\tau', r'\tau')),
    cell('markdown', '''## Interpret and iterate

After running cell 3, compare its final printed value with the curve.
Edit `tau` and run it again: a larger time constant should produce slower decay.

Python variables remain alive between cells. Editing a cell does not execute it.
The AI cell below generates editable cells only when you choose **Generate cells**.'''),
    cell('ai', 'Explain the measured result above. Add a Markdown cell with a short interpretation and a Mermaid diagram of the experiment. Then add a Python cell comparing tau=1, tau=2 and tau=4 on one plot. Do not claim the proposed comparison has already run.'),
]
(folder / 'visual-lab.nb.md').write_text(serialize({'title': 'Visual lab · decay experiment', 'cells': cells}), encoding='utf-8')
print(folder / 'visual-lab.nb.md')
