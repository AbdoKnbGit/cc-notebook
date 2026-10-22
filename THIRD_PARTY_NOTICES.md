# Third-party notices

The plugin vendors the terminal text renderer from [beautiful-mermaid](https://github.com/lukilabs/beautiful-mermaid) 1.1.3, copyright 2026 Craft Docs, under the MIT license. Its full license is retained at `hooks/notebook/vendor/LICENSE.beautiful-mermaid`.

The transcript SVG renderer uses beautiful-mermaid 0.1.3, pinned as the build-only alias `beautiful-mermaid-svg`, with Dagre and Graphlib. This compact version fits Claude's 1 MiB hook-module limit; it does not bundle ELK. Their MIT licences are retained in `hooks/lib/vendor/`. `npm run build:rich` regenerates both bundles from locked dependencies and verifies their size. End users do not need Node or npm.

The transcript hooks (`hooks/lib/`, `hooks/sel.tsx` and the transcript portion of `hooks/register.tsx`), Typst templates and themes (`render/`), drawing skill (`skills/intelligent-ui/`), renderer tests and six gallery fixtures are adapted from [Intelligent UI](https://github.com/razorback16/cc-intelligent-ui) 0.3.2, MIT, copyright 2026 razorback16. The full licence is retained at `render/LICENSE.intelligent-ui`. Integration changes, Mermaid preprocessing and notebook connections are maintained here. Vendored Typst packages retain their source and individual licences; see [their notices](render/THIRD-PARTY-NOTICES.md), including LGPL-3.0-or-later CeTZ/cetz-plot.

The notebook's image transport design was informed by [claude-show-your-work](https://github.com/iamumeransari/claude-show-your-work). Notebook rendering also draws on design studies of claude-image-view, Prismantis and the author's local claudex. Their application code is not included. Notebook integration, block parsing, Raster encoding and the Unicode math fallback are independently implemented. The transcript renderer includes the show-your-work terminal cell-size probe described in its retained notices.

Pillow, Matplotlib and Jupyter are installed Python dependencies with their own upstream licenses. Typst/MiTeX is an optional separately installed math/SVG renderer, not a bundled executable.
