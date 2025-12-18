"""
Supernote Canvas: capture Supernote tablet sketches into Jupyter notebooks.

Provides a `%diagram` line magic that:
- Shows an iframe with your Supernote web UI.
- Lets you capture the latest screenshot from a folder (default: ~/Desktop).
- Copies it into a `diagrams/` folder in the current working directory.
- Prints ready-to-use Markdown plus a preview image.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from typing import Optional

# Default configuration (can be overridden via env var or by editing the module
# after import). The default URL is intentionally a non-personal placeholder;
# most users should override this to point at their own Supernote web UI.
SUPERNOTE_URL: str = os.getenv(
    "SUPERNOTE_CANVAS_URL",
    "http://192.168.0.100:8080",  # example private-LAN address; customize as needed
)
SCREENSHOT_DIR: str = os.path.expanduser("~/Desktop")
DIAGRAM_DIR: str = "diagrams"


def _in_ipython() -> bool:
    """Return True if running inside IPython (including Jupyter)."""
    try:
        from IPython import get_ipython  # type: ignore

        return get_ipython() is not None
    except Exception:
        return False


def _latest_screenshot(path: str) -> Optional[str]:
    """
    Return the most recent screenshot file in `path` by modification time.

    Considers files with extensions: .png, .jpg, .jpeg (case-insensitive).
    Returns absolute path, or None if no matching files are found.
    """
    exts = {".png", ".jpg", ".jpeg"}
    try:
        candidates = []
        for name in os.listdir(path):
            _, ext = os.path.splitext(name)
            if ext.lower() in exts:
                full = os.path.join(path, name)
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                candidates.append((mtime, full))
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0], reverse=True)
    return os.path.abspath(candidates[0][1])


def latest_screenshot(path: str) -> Optional[str]:
    """
    Public helper: return the most recent screenshot file in `path`, or None.

    This simply forwards to the internal `_latest_screenshot`.
    """
    return _latest_screenshot(path)


def draw() -> None:
    """
    Build and display the Supernote Canvas UI widget.

    Intended to be called from the `%diagram` line magic or directly from
    a Jupyter/IPython environment.
    """
    if not _in_ipython():
        # Fail gracefully if not in IPython/Jupyter.
        print("Supernote Canvas UI can only be displayed inside IPython/Jupyter.")
        return

    # Lazy imports so that importing the package outside Jupyter does not crash.
    try:
        import ipywidgets as widgets  # type: ignore
        from IPython.display import HTML, Image as IPImage, display  # type: ignore
    except Exception as exc:  # pragma: no cover - environment specific
        print("Failed to import Jupyter display dependencies:", exc)
        return

    # Build iframe HTML with a small heading and instructions.
    iframe_html = f"""
    <div style="border: 1px solid #ccc; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
      <h4 style="margin-top: 0; font-family: sans-serif;">
        Supernote Canvas
      </h4>
      <p style="margin: 4px 0 10px; font-family: sans-serif; font-size: 13px; color: #555;">
        Draw on your Supernote, then take an OS screenshot (Cmd/Ctrl+Shift+4).
        When you are ready, click <strong>📸 Capture latest screenshot</strong> below.
      </p>
      <iframe
        src="{SUPERNOTE_URL}"
        width="100%"
        height="600px"
        style="border: 1px solid #aaa; border-radius: 4px;"
      ></iframe>
    </div>
    """

    iframe = widgets.HTML(value=iframe_html)

    capture_btn = widgets.Button(
        description="📸 Capture latest screenshot",
        button_style="primary",
        tooltip="Copy the most recent screenshot into ./diagrams and show Markdown.",
    )
    close_btn = widgets.Button(
        description="❌ Close",
        button_style="danger",
        tooltip="Close this Supernote Canvas panel.",
    )

    output = widgets.Output()

    container = widgets.VBox(
        children=[
            iframe,
            widgets.HBox(
                [capture_btn, close_btn],
                layout=widgets.Layout(padding="10px 0 10px 0"),
            ),
            output,
        ],
        layout=widgets.Layout(border="1px solid #ddd", padding="6px"),
    )

    def _on_capture_click(_btn: widgets.Button) -> None:
        """Handle the Capture button click."""
        output.clear_output()

        with output:
            src = _latest_screenshot(SCREENSHOT_DIR)
            if src is None:
                print(
                    f"No screenshot files found in '{SCREENSHOT_DIR}'.\n"
                    "Make sure you have taken a screenshot as .png, .jpg, or .jpeg."
                )
                return

            # Determine destination path and extension.
            src_ext = os.path.splitext(src)[1] or ".png"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"diagram_{timestamp}{src_ext}"

            try:
                os.makedirs(DIAGRAM_DIR, exist_ok=True)
            except OSError as exc:
                print(f"Could not create diagrams directory '{DIAGRAM_DIR}': {exc}")
                return

            dest_path = os.path.join(DIAGRAM_DIR, filename)

            try:
                shutil.copy2(src, dest_path)
            except OSError as exc:
                print(f"Failed to copy screenshot to '{dest_path}': {exc}")
                return

            # Attempt to honor EXIF orientation flags using Pillow, if available.
            try:
                from PIL import Image, ImageOps  # type: ignore

                try:
                    with Image.open(dest_path) as img:
                        rotated = ImageOps.exif_transpose(img)
                        rotated.save(dest_path)
                except Exception as exc:
                    # If anything goes wrong with EXIF-based rotation, continue without failing.
                    print(f"Could not apply EXIF-based rotation: {exc}")
            except Exception:
                # Pillow is not installed or failed to import; skip EXIF handling.
                pass

            # Build Markdown pointing to the new file.
            md = f"![Diagram]({dest_path})"

            # Display Markdown instructions and preview.
            display(HTML("<strong>Markdown to copy into a new markdown cell:</strong>"))
            # Render as <code> block; escaping minimal HTML special chars.
            safe_md = (
                md.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            display(HTML(f"<code>{safe_md}</code>"))
            display(HTML("<strong>Preview (for reference only):</strong>"))

            try:
                display(IPImage(filename=dest_path, width=800))
            except Exception as exc:  # pragma: no cover - environment/display specific
                print(f"Could not display image preview: {exc}")

            print("Copy this markdown into a new markdown cell:")
            print(md)

    def _on_close_click(_btn: widgets.Button) -> None:
        """Handle the Close button click: close the container widget."""
        # Close the entire container so it disappears from the notebook output.
        container.close()

    capture_btn.on_click(_on_capture_click)
    close_btn.on_click(_on_close_click)

    display(container)


def _register_line_magic(ipython=None) -> None:
    """
    Register the `%diagram` line magic with the current IPython instance.

    Safe to call multiple times; will do nothing outside IPython.
    """
    if not _in_ipython():
        return

    try:
        from IPython import get_ipython  # type: ignore
    except Exception:
        return

    # Prefer explicit ipython instance if provided, else fall back to global.
    shell = ipython or get_ipython()
    if shell is None:
        return

    def diagram(line: str = "") -> None:
        """Launch the Supernote drawing helper UI."""
        # Ignore the line argument; provided for IPython's magic signature.
        draw()

    # Register as a line magic named "diagram".
    try:
        shell.register_magic_function(diagram, magic_kind="line", magic_name="diagram")
    except Exception:
        # Fallback: try decorator-based registration if available.
        try:
            from IPython.core.magic import register_line_magic  # type: ignore

            @register_line_magic  # type: ignore[misc]
            def diagram_magic(line: str = "") -> None:
                """Launch the Supernote drawing helper UI."""
                draw()

            _ = diagram_magic  # silence unused warning
        except Exception:
            # If this also fails, just give up silently; importing the module should still work.
            return


def load_ipython_extension(ipython) -> None:
    """
    IPython extension entry point.

    Allows: `%load_ext supernote_canvas` followed by `%diagram`.
    """
    _register_line_magic(ipython)


# When imported inside IPython, eagerly register the magic for convenience.
try:  # pragma: no cover - depends on environment
    if _in_ipython():
        _register_line_magic()
except Exception:
    # Never crash just because magic registration failed.
    pass


