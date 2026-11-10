#!/usr/bin/env python3
"""md2pdf - convertit un fichier Markdown en PDF.

Pipeline : Markdown --(markdown-it-py + plugins)--> HTML + CSS --(Chrome/Edge headless)--> PDF.

Le rendu est fait par un vrai moteur de navigateur, ce qui garantit une mise en page
fidèle (tableaux, code coloré, images, emojis, polices, formules KaTeX, diagrammes Mermaid).
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

HERE = Path(__file__).resolve().parent
DEFAULT_CSS = HERE / "style.css"

KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"


# --------------------------------------------------------------------------- Markdown -> HTML
def _highlight(code: str, lang: str, _attrs: str) -> str:
    if lang == "mermaid":
        return f'<pre class="mermaid">{html.escape(code)}</pre>'
    try:
        lexer = get_lexer_by_name(lang) if lang else None
    except ClassNotFound:
        lexer = None
    if lexer is None:
        return ""  # markdown-it utilise alors son rendu par défaut
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


def build_parser() -> MarkdownIt:
    md = (
        MarkdownIt("gfm-like", {"html": True, "linkify": True, "typographer": True,
                                "highlight": _highlight})
        .use(front_matter_plugin)
        .use(footnote_plugin)
        .use(deflist_plugin)
        .use(tasklists_plugin)
        .use(dollarmath_plugin, double_inline=True)
        .use(anchors_plugin, max_level=6, permalink=False)
    )
    # Le rendu mermaid/pygments renvoie déjà son propre <pre> : on évite le double emballage.
    default_fence = md.renderer.rules["fence"]

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        lang = tok.info.strip().split()[0] if tok.info.strip() else ""
        if lang == "mermaid":
            return _highlight(tok.content, "mermaid", "")
        return default_fence(tokens, idx, options, env)

    md.add_render_rule("fence", fence)
    md.add_render_rule("math_inline", lambda s, t, i, o, e: f'<span class="math">\\({html.escape(t[i].content)}\\)</span>')
    md.add_render_rule("math_inline_double", lambda s, t, i, o, e: f'<div class="math">\\[{html.escape(t[i].content)}\\]</div>')
    md.add_render_rule("math_block", lambda s, t, i, o, e: f'<div class="math">\\[{html.escape(t[i].content)}\\]</div>\n')
    md.add_render_rule("math_block_label", lambda s, t, i, o, e: f'<div class="math">\\[{html.escape(t[i].content)}\\]</div>\n')
    return md


def parse_front_matter(tokens) -> dict:
    for tok in tokens:
        if tok.type == "front_matter":
            meta = {}
            for line in tok.content.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip().strip("'\"")
            return meta
    return {}


def build_toc(tokens) -> str:
    items = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag in ("h1", "h2", "h3"):
            level = int(tok.tag[1])
            text = tokens[i + 1].content
            items.append(f'<li class="toc-l{level}"><a href="#{tok.attrs.get("id", "")}">'
                         f"{html.escape(text)}</a></li>")
    return f'<nav class="toc"><h2>Table des matières</h2><ul>{"".join(items)}</ul></nav>' if items else ""


def markdown_to_html(src: str, base_dir: Path, css: str, title: str | None, toc: bool) -> str:
    md = build_parser()
    env: dict = {}
    tokens = md.parse(src, env)
    body = md.renderer.render(tokens, md.options, env)
    meta = parse_front_matter(tokens)
    if not title:
        title = meta.get("title")
    if not title:
        m = re.search(r"^#\s+(.+)$", src, re.M)
        title = m.group(1).strip() if m else "Document"

    has_math = any(t.type.startswith("math") for t in tokens) or 'class="math' in body
    has_mermaid = 'class="mermaid"' in body

    head = []
    if has_math:
        head.append(f'<link rel="stylesheet" href="{KATEX}/katex.min.css">'
                    f'<script defer src="{KATEX}/katex.min.js"></script>'
                    f'<script defer src="{KATEX}/contrib/auto-render.min.js"></script>')
    if has_mermaid:
        head.append(f'<script src="{MERMAID}"></script>')

    ready_script = """
<script>
window.addEventListener('load', async () => {
  try {
    if (window.renderMathInElement) {
      renderMathInElement(document.body, {delimiters: [
        {left: '\\\\[', right: '\\\\]', display: true},
        {left: '\\\\(', right: '\\\\)', display: false}], throwOnError: false});
    }
    if (window.mermaid) {
      mermaid.initialize({startOnLoad: false, theme: 'neutral'});
      await mermaid.run({querySelector: '.mermaid'});
    }
  } finally { document.title = '__MD2PDF_READY__' + document.title; }
});
</script>"""

    pyg_css = HtmlFormatter(style="default").get_style_defs("pre")
    base_href = base_dir.resolve().as_uri() + "/"
    meta_author = f'<meta name="author" content="{html.escape(meta["author"])}">' if "author" in meta else ""
    return f"""<!doctype html>
<html lang="{html.escape(meta.get('lang', 'fr'))}">
<head>
<meta charset="utf-8">
<base href="{base_href}">
<title>{html.escape(title)}</title>
{meta_author}
<style>{css}
{pyg_css}</style>
{''.join(head)}
</head>
<body>
<article class="markdown-body">
{build_toc(tokens) if toc else ''}
{body}
</article>
{ready_script}
</body>
</html>"""


# --------------------------------------------------------------------------- HTML -> PDF
def find_browser(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("MD2PDF_BROWSER")
    if env:
        return env
    for name in ("chrome", "google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "msedge", "microsoft-edge"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    sys.exit("Erreur : aucun navigateur Chrome/Chromium/Edge trouvé. "
             "Utilisez --browser CHEMIN ou la variable MD2PDF_BROWSER.")


def html_to_pdf(html_path: Path, pdf_path: Path, browser: str, timeout: int) -> None:
    with tempfile.TemporaryDirectory(prefix="md2pdf-profile-", ignore_cleanup_errors=True) as profile:
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions",
            "--allow-file-access-from-files", f"--user-data-dir={profile}",
            "--run-all-compositor-stages-before-draw", "--virtual-time-budget=15000",
            "--no-pdf-header-footer", "--generate-pdf-document-outline",
            f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri(),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        # Sous Windows, msedge.exe/chrome.exe peut rendre la main avant d'avoir écrit le PDF :
        # on attend que le fichier existe et que sa taille se stabilise.
        deadline, last, stable = time.monotonic() + timeout, -1, 0
        while time.monotonic() < deadline:
            size = pdf_path.stat().st_size if pdf_path.exists() else -1
            stable = stable + 1 if size > 0 and size == last else 0
            if stable >= 3:
                break
            last = size
            time.sleep(0.3)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        sys.exit(f"Erreur : échec de la génération du PDF.\n{res.stderr.strip()}")


# --------------------------------------------------------------------------- CLI
def page_css(size: str, margin: str, landscape: bool) -> str:
    orient = " landscape" if landscape else ""
    return (f"@page {{ size: {size}{orient}; margin: {margin}; "
            f"@bottom-center {{ content: counter(page) ' / ' counter(pages); "
            f"font-size: 9pt; color: #888; }} }}\n")


def convert(src: Path, out: Path, *, css_path: Path, browser: str | None, title: str | None,
            toc: bool, size: str, margin: str, landscape: bool, keep_html: bool,
            timeout: int) -> Path:
    text = src.read_text(encoding="utf-8-sig")
    css = page_css(size, margin, landscape) + css_path.read_text(encoding="utf-8")
    doc = markdown_to_html(text, src.parent, css, title, toc)
    out.parent.mkdir(parents=True, exist_ok=True)
    if keep_html:
        out.with_suffix(".html").write_text(doc, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="md2pdf-") as tmp:
        html_path = Path(tmp) / "doc.html"
        html_path.write_text(doc, encoding="utf-8")
        tmp_pdf = Path(tmp) / "out.pdf"
        html_to_pdf(html_path, tmp_pdf, find_browser(browser), timeout)
        shutil.move(str(tmp_pdf), out)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Convertit un ou plusieurs fichiers Markdown en PDF.")
    ap.add_argument("inputs", nargs="+", type=Path, help="fichier(s) .md")
    ap.add_argument("-o", "--output", type=Path,
                    help="fichier PDF de sortie (un seul input) ou dossier de sortie")
    ap.add_argument("--css", type=Path, default=DEFAULT_CSS, help="feuille de style personnalisée")
    ap.add_argument("--title", help="titre du document (sinon front matter ou premier # titre)")
    ap.add_argument("--toc", action="store_true", help="ajoute une table des matières")
    ap.add_argument("--page-size", default="A4", help="A4, Letter, A3... (défaut A4)")
    ap.add_argument("--margin", default="18mm 16mm 20mm 16mm", help="marges CSS (défaut 18mm 16mm 20mm 16mm)")
    ap.add_argument("--landscape", action="store_true", help="orientation paysage")
    ap.add_argument("--browser", help="chemin de Chrome/Chromium/Edge")
    ap.add_argument("--keep-html", action="store_true", help="conserve le HTML intermédiaire")
    ap.add_argument("--timeout", type=int, default=120, help="délai max en secondes (défaut 120)")
    args = ap.parse_args(argv)

    multi = len(args.inputs) > 1 or (args.output and args.output.suffix.lower() != ".pdf")
    for src in args.inputs:
        if not src.is_file():
            sys.exit(f"Erreur : fichier introuvable : {src}")
        if args.output and not multi:
            out = args.output
        elif args.output:
            out = args.output / (src.stem + ".pdf")
        else:
            out = src.with_suffix(".pdf")
        convert(src, out.resolve(), css_path=args.css, browser=args.browser, title=args.title,
                toc=args.toc, size=args.page_size, margin=args.margin, landscape=args.landscape,
                keep_html=args.keep_html, timeout=args.timeout)
        print(f"{src} -> {out}")


if __name__ == "__main__":
    main()
