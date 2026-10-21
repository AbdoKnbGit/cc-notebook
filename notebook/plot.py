"""Optional line-plot metadata beside the original PNG, never instead of it."""
import json
import math

MIME = 'text/vnd.cc-notebook.plot+json'


def describe(figure):
    # Only describe figures we can reproduce faithfully. Other artists and
    # transforms retain their normal image preview, rather than losing data.
    if len(figure.axes) != 1:
        return None
    ax = figure.axes[0]
    if (ax.name != 'rectilinear' or not ax.axison or ax.get_xscale() != 'linear' or ax.get_yscale() != 'linear'
            or not ax.lines or ax.images or ax.collections or ax.patches or ax.texts or ax.artists
            or ax.child_axes or len(ax.lines) > 8):
        return None
    from matplotlib.colors import to_hex
    import numpy as np
    series = []
    count = 0
    for line in ax.lines:
        if not line.get_visible() or line.get_alpha() == 0:
            continue
        if line.get_transform() != ax.transData or line.get_drawstyle() != 'default':
            return None
        xy = np.ma.filled(line.get_xydata(), np.nan)
        count += len(xy)
        if count > 4096:
            return None
        points = [[float(x), float(y)] if math.isfinite(x) and math.isfinite(y) else None for x, y in xy]
        label = str(line.get_label())
        series.append({'points': points, 'color': to_hex(line.get_color()),
                       'label': '' if label.startswith('_') else label[:120],
                       'connected': line.get_linestyle() not in ('None', '', ' '),
                       'dashed': line.get_linestyle() in ('--', '-.', ':')})
    limits = [float(n) for n in (*ax.get_xlim(), *ax.get_ylim())]
    if not series or not all(math.isfinite(n) for n in limits):
        return None
    if limits[0] == limits[1] or limits[2] == limits[3]:
        return None
    # Dates and custom tick formatters require their own labels; don't
    # misrepresent them as plain numbers in the terminal.
    from matplotlib.ticker import ScalarFormatter
    if not all(type(axis.get_major_formatter()) is ScalarFormatter for axis in (ax.xaxis, ax.yaxis)):
        return None
    return {'version': 1, 'title': ax.get_title()[:160], 'xlabel': ax.get_xlabel()[:120],
            'ylabel': ax.get_ylabel()[:120], 'limits': limits, 'series': series}


def install():
    from IPython import get_ipython
    from IPython.core.formatters import BaseFormatter
    from matplotlib.figure import Figure

    def format_figure(figure):
        try:
            value = describe(figure)
            encoded = json.dumps(value, allow_nan=False) if value else None
            return encoded if encoded and len(encoded) <= 200_000 else None
        except Exception:
            return None  # The normal PNG formatter remains independent.

    formatter = BaseFormatter()
    formatter.for_type(Figure, format_figure)
    get_ipython().display_formatter.formatters[MIME] = formatter
