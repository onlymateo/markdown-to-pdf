# md2pdf

Convertit un fichier Markdown en PDF, avec un rendu fidèle : le HTML généré est imprimé
par un vrai moteur de navigateur (Chrome, Chromium ou Edge en mode headless).

## Fonctionnalités

- Markdown CommonMark + GFM : tableaux (alignements), ~~barré~~, listes de tâches, liens automatiques
- Coloration syntaxique (Pygments), notes de bas de page, listes de définitions, typographie
- Formules mathématiques `$...$` / `$$...$$` (KaTeX) et diagrammes ` ```mermaid `
- Front matter YAML (`title`, `author`, `lang`), table des matières (`--toc`)
- Signets PDF générés depuis les titres, numéros de page, liens cliquables
- Images relatives résolues par rapport au fichier `.md`
- Format de page, marges, orientation et CSS personnalisables

> KaTeX et Mermaid sont chargés depuis un CDN uniquement si le document en contient :
> une connexion internet est alors nécessaire.

## Installation

Prérequis : Python 3.10+ et Google Chrome, Chromium ou Microsoft Edge.

```bash
pip install -r requirements.txt
```

## Utilisation

```bash
python md2pdf.py document.md                     # -> document.pdf
python md2pdf.py document.md -o sortie.pdf --toc
python md2pdf.py *.md -o pdf/                    # plusieurs fichiers vers un dossier
python md2pdf.py doc.md --page-size Letter --landscape --margin "15mm"
python md2pdf.py doc.md --css mon-style.css --keep-html
```

| Option | Description |
|---|---|
| `-o, --output` | PDF de sortie, ou dossier si plusieurs entrées |
| `--toc` | Ajoute une table des matières (titres h1–h3) |
| `--title` | Titre du document (sinon front matter, sinon premier `#`) |
| `--css` | Feuille de style à la place de `style.css` |
| `--page-size`, `--margin`, `--landscape` | Mise en page |
| `--browser` | Chemin du navigateur (ou variable `MD2PDF_BROWSER`) |
| `--keep-html` | Conserve le HTML intermédiaire à côté du PDF |

Un exemple complet est disponible dans [examples/demo.md](examples/demo.md).
