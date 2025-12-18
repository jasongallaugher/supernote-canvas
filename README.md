# Supernote Canvas

Supernote Canvas is a tiny helper for Jupyter notebooks that makes it easy to bring sketches from your Supernote tablet into your notebook as images. It provides a `%diagram` line magic that shows your Supernote web UI in an iframe, then helps you capture the latest OS screenshot into a local `diagrams/` folder and gives you ready-to-paste Markdown.

You keep using your normal OS screenshot tooling (for example, Cmd+Shift+4 on macOS). Supernote Canvas just finds the most recent screenshot, copies it into your project, prints the Markdown you need, and shows a preview.

## Installation (local development)

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

This installs `supernote-canvas` in editable mode so you can tweak the code as needed.

## Usage in a Jupyter notebook

In a notebook cell:

```python
import supernote_canvas
%diagram
```

Or, using the IPython extension entry point:

```python
%load_ext supernote_canvas
%diagram
```

This will:

1. Show an iframe with your Supernote web UI (default URL: `http://192.168.2.148:8080`) and a short instruction line saying “Draw on Supernote, then screenshot (Cmd/Ctrl+Shift+4)”.
2. Provide two buttons:
   - **📸 Capture latest screenshot** – looks in a configurable screenshot folder (default: `~/Desktop`) for the most recent `.png`, `.jpg`, or `.jpeg` file, copies it into a `diagrams/` folder in the current working directory, and constructs a Markdown image link.
   - **❌ Close** – closes the widget container.

When you click **Capture**:

1. Supernote Canvas scans your screenshot folder for the most recent screenshot.
2. It copies the file into `./diagrams/` as `diagram_YYYYmmdd_HHMMSS.ext` (preserving the original extension when possible).
3. In the cell output it:
   - Renders a bold heading: **“Markdown to copy into a new markdown cell:”**.
   - Shows the Markdown line in a `<code>` block, like:

     ```markdown
     ![Diagram](diagrams/diagram_20250101_123456.png)
     ```

   - Renders a bold heading: **“Preview (for reference only):”**.
   - Displays an image preview of the captured diagram.
   - Prints a final line: `Copy this markdown into a new markdown cell:` followed by the same Markdown text.

You then manually create a new Markdown cell, paste the provided Markdown, and run the cell to embed your Supernote diagram in the notebook.

## Configuration

You will almost always want to tell Supernote Canvas where your Supernote web UI lives, and (optionally) where to look for screenshots and where to save diagrams.

- **Supernote web UI URL**

  By default, `SUPERNOTE_URL` is a generic private‑LAN placeholder. You should override it to your own device’s URL.

  In a notebook cell:

  ```python
  import supernote_canvas

  supernote_canvas.SUPERNOTE_URL = "http://192.168.1.23:8080"  # your Supernote's IP/port
  ```

  Or via environment variable (useful in Colab / hosted environments):

  ```bash
  export SUPERNOTE_CANVAS_URL="http://192.168.1.23:8080"
  ```

- **Screenshot source directory**

  By default, Supernote Canvas looks for screenshots in `~/Desktop` on the machine running the kernel:

  ```python
  supernote_canvas.SCREENSHOT_DIR = "/path/to/your/screenshots"
  ```

  In Colab or other hosted Jupyter setups, this usually needs to be set to wherever you upload or save screenshots inside the runtime (for example, `/content` in Colab).

- **Diagrams output directory**

  By default, diagrams are saved into a `diagrams/` folder in the current working directory. You can change that if you prefer:

  ```python
  supernote_canvas.DIAGRAM_DIR = "images/diagrams"
  ```

These configuration knobs let you keep the library generic and public‑repo‑friendly, while still pointing at your own Supernote and filesystem layout when you actually use it.


