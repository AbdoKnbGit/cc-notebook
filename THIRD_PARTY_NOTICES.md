# Third-party notices

The plugin vendors the terminal text renderer from [beautiful-mermaid](https://github.com/lukilabs/beautiful-mermaid) 1.1.3, copyright 2026 Craft Docs, under the MIT license. Its full license is retained at `hooks/notebook/vendor/LICENSE.beautiful-mermaid`. `npm run build:rich` regenerates the bundle from the locked dependency. The SVG/ELK renderer is not included in this bundle. esbuild is a build dependency.

The notebook's image transport design was informed by [claude-show-your-work](https://github.com/iamumeransari/claude-show-your-work). Rich rendering also draws on design studies of claude-image-view, Prismantis and the author's local claudex. Their application code and global conversation hooks are not included. Notebook integration, block parsing, Raster encoding and the Unicode math fallback are independently implemented.

Pillow, Matplotlib and Jupyter are installed Python dependencies with their own upstream licenses. Typst/MiTeX is an optional separately installed math/SVG renderer, not a bundled executable.
