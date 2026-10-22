# Illustrative neural network

A fully connected network with layers of 2, 3, 3 and 1 neurons (illustrative, not trained).

```typst
#import "@preview/cetz:0.5.2"
#cetz.canvas(length: calc.min(theme.width / 12, theme.height / 5), {
  import cetz.draw: *
  set-style(stroke: theme.fg)
  let sizes = (2, 3, 3, 1)
  let names = ([Input], [Hidden 1], [Hidden 2], [Output])
  let xs = (0, 4, 8, 12)
  let pos(l, j) = {
    let n = sizes.at(l)
    (xs.at(l), (n - 1) / 2 - j * 1.0)
  }
  for l in range(sizes.len() - 1) {
    for a in range(sizes.at(l)) {
      for b in range(sizes.at(l + 1)) {
        line(pos(l, a), pos(l + 1, b), stroke: theme.muted + 0.5pt)
      }
    }
  }
  for l in range(sizes.len()) {
    for j in range(sizes.at(l)) {
      let c = theme.palette.at(l)
      circle(pos(l, j), radius: 0.3, fill: c.transparentize(80%), stroke: c)
    }
    content((xs.at(l), -2.6), text(fill: theme.muted, names.at(l)))
  }
})
```

Parameters: 2·3 + 3·3 + 3·1 = 18 weights and 3 + 3 + 1 = 7 biases, 25 in total.
