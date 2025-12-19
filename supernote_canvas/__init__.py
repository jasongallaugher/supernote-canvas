"""
Supernote Canvas: capture Supernote tablet sketches into Jupyter notebooks.

Provides a `%diagram` line magic that:
- Shows an iframe with your Supernote web UI (live view).
- Captures screenshots via multiple methods (priority order):
  1. USB/ADB capture (local environments, default)
  2. File upload widget (remote environments like Colab)
  3. Folder-based capture (local fallback, looks in ~/Desktop)
- Copies captured images into a `diagrams/` folder in the current working directory.
- Prints ready-to-use Markdown plus a preview image.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
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
ADB_DEVICE_SERIAL: Optional[str] = os.getenv("SUPERNOTE_CANVAS_ADB_DEVICE", None)


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


def _is_adb_available() -> bool:
    """Return True if ADB is available in PATH."""
    try:
        result = subprocess.run(
            ["adb", "version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_device_connected() -> bool:
    """Return True if an ADB device is connected."""
    if not _is_adb_available():
        return False

    try:
        cmd = ["adb", "devices"]
        if ADB_DEVICE_SERIAL:
            cmd.extend(["-s", ADB_DEVICE_SERIAL])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return False

        # Parse output: should have at least one device line (not just "List of devices")
        lines = result.stdout.strip().split("\n")[1:]  # Skip header
        devices = [line for line in lines if line.strip() and "device" in line]
        return len(devices) > 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def _capture_via_adb() -> Optional[bytes]:
    """
    Capture screenshot via ADB and return as bytes, or None on failure.

    Uses `adb exec-out screencap -p` to capture directly to stdout.
    """
    if not _is_adb_available() or not _is_device_connected():
        return None

    try:
        cmd = ["adb"]
        if ADB_DEVICE_SERIAL:
            cmd.extend(["-s", ADB_DEVICE_SERIAL])
        cmd.extend(["exec-out", "screencap", "-p"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
            check=True,
        )
        if result.stdout and len(result.stdout) > 0:
            return result.stdout
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception):
        pass

    return None


def _is_remote_environment() -> bool:
    """
    Detect if running in a remote/hosted environment (Colab, JupyterHub, etc.).

    Checks for common indicators of remote environments.
    """
    # Check for Colab
    try:
        import google.colab  # type: ignore
        return True
    except ImportError:
        pass

    # Check for JupyterHub (common env vars)
    if os.getenv("JUPYTERHUB_USER") or os.getenv("JUPYTERHUB_API_URL"):
        return True

    # Check if we can't access local filesystem reliably
    # (heuristic: if ADB device check fails and we're not on a typical local path)
    # This is a fallback heuristic
    return False


def _process_and_save_image(
    image_data: bytes, source_path: Optional[str] = None
) -> Optional[str]:
    """
    Process image data and save to diagrams folder.

    Args:
        image_data: Image bytes to save
        source_path: Optional source file path (for extension detection)

    Returns:
        Path to saved file, or None on failure.
    """
    # Determine extension
    if source_path:
        src_ext = os.path.splitext(source_path)[1] or ".png"
    else:
        # Try to detect from image data, default to PNG
        src_ext = ".png"
        try:
            from PIL import Image  # type: ignore

            with Image.open(io.BytesIO(image_data)) as img:
                # Map PIL format to extension
                format_map = {"PNG": ".png", "JPEG": ".jpg", "JPEG2000": ".jpg"}
                src_ext = format_map.get(img.format, ".png")
        except Exception:
            pass

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"diagram_{timestamp}{src_ext}"

    try:
        os.makedirs(DIAGRAM_DIR, exist_ok=True)
    except OSError as exc:
        print(f"Could not create diagrams directory '{DIAGRAM_DIR}': {exc}")
        return None

    dest_path = os.path.join(DIAGRAM_DIR, filename)

    try:
        # Write image data to file
        with open(dest_path, "wb") as f:
            f.write(image_data)

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

        return dest_path
    except OSError as exc:
        print(f"Failed to save image to '{dest_path}': {exc}")
        return None


def _display_captured_image(dest_path: str) -> None:
    """Display the captured image with Markdown instructions and clipboard copy."""
    # Lazy import for display functions
    try:
        from IPython.display import HTML, Image as IPImage, display  # type: ignore
        import json
    except Exception:
        print("Failed to import display dependencies")
        return

    # Build Markdown pointing to the new file.
    md = f"![Diagram]({dest_path})"

    # Escape markdown for JavaScript using JSON encoding (safest method)
    js_safe_md = json.dumps(md)

    # Create copy button with JavaScript
    copy_button_html = f"""
    <button 
        onclick="navigator.clipboard.writeText({js_safe_md}).then(() => {{
            this.textContent = '✓ Copied!';
            this.style.backgroundColor = '#28a745';
            setTimeout(() => {{
                this.textContent = '📋 Copy Markdown';
                this.style.backgroundColor = '';
            }}, 2000);
        }}).catch(err => {{
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = {js_safe_md};
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {{
                document.execCommand('copy');
                this.textContent = '✓ Copied!';
                this.style.backgroundColor = '#28a745';
                setTimeout(() => {{
                    this.textContent = '📋 Copy Markdown';
                    this.style.backgroundColor = '';
                }}, 2000);
            }} catch (err) {{
                alert('Failed to copy. Please copy manually.');
            }}
            document.body.removeChild(textarea);
        }});"
        style="
            padding: 6px 12px;
            margin: 8px 0;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-family: sans-serif;
        "
        onmouseover="this.style.backgroundColor='#0056b3'"
        onmouseout="this.style.backgroundColor='#007bff'"
    >
        📋 Copy Markdown
    </button>
    """

    # Display Markdown instructions with copy button.
    display(HTML("<strong>Markdown to copy into a new markdown cell:</strong>"))
    # Render as <code> block; escaping minimal HTML special chars.
    safe_md = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    display(HTML(f"<code>{safe_md}</code>"))
    display(HTML(copy_button_html))
    display(HTML("<strong>Preview (for reference only):</strong>"))

    try:
        display(IPImage(filename=dest_path, width=800))
    except Exception as exc:  # pragma: no cover - environment/display specific
        print(f"Could not display image preview: {exc}")

    print("Markdown (click button above to copy, or copy manually):")
    print(md)


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

    # Detect environment and available methods
    is_remote = _is_remote_environment()
    adb_available = _is_adb_available() and _is_device_connected()

    # Build instruction text based on environment
    if is_remote:
        instruction_text = (
            "Draw on your Supernote. Click <strong>📸 Capture</strong> to upload a screenshot."
        )
    elif adb_available:
        instruction_text = (
            "Draw on your Supernote. Click <strong>📸 Capture</strong> to capture via USB."
        )
    else:
        instruction_text = (
            "Draw on your Supernote, then take an OS screenshot (Cmd/Ctrl+Shift+4). "
            "Click <strong>📸 Capture</strong> when ready."
        )

    # Build iframe HTML with a small heading and instructions.
    # Include a refresh button to reload the iframe (helps with browser security prompts)
    import time
    iframe_id = f"supernote_iframe_{int(time.time() * 1000)}"
    iframe_html = f"""
    <div style="border: 1px solid #ccc; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
      <h4 style="margin-top: 0; font-family: sans-serif;">
        Supernote Canvas
      </h4>
      <p style="margin: 4px 0 10px; font-family: sans-serif; font-size: 13px; color: #555;">
        {instruction_text}
      </p>
      <button 
        onclick="
          const iframe = document.getElementById('{iframe_id}');
          const originalSrc = '{SUPERNOTE_URL}';
          iframe.src = '';
          setTimeout(() => {{
            iframe.src = originalSrc + (originalSrc.includes('?') ? '&' : '?') + '_t=' + Date.now();
          }}, 100);
        "
        style="
          padding: 4px 8px;
          margin-bottom: 8px;
          background-color: #f8f9fa;
          border: 1px solid #ddd;
          border-radius: 3px;
          cursor: pointer;
          font-size: 12px;
          font-family: sans-serif;
        "
        onmouseover="this.style.backgroundColor='#e9ecef'"
        onmouseout="this.style.backgroundColor='#f8f9fa'"
      >
        🔄 Refresh iframe
      </button>
      <p style="margin: 4px 0 8px; font-family: sans-serif; font-size: 11px; color: #999;">
        If blocked, try: reload the Jupyter page (Cmd/Ctrl+R) or use Chrome with <code>--allow-running-insecure-content</code>
      </p>
      <div id="{iframe_id}_container" style="position: relative; width: 100%;">
        <button 
          onclick="
            const container = document.getElementById('{iframe_id}_container');
            const iframe = document.getElementById('{iframe_id}');
            if (container.style.position === 'fixed') {{
              // Exit fullscreen
              container.style.position = 'relative';
              container.style.top = 'auto';
              container.style.left = 'auto';
              container.style.width = '100%';
              container.style.height = 'auto';
              container.style.zIndex = 'auto';
              container.style.backgroundColor = 'transparent';
              iframe.style.height = '80vh';
              this.textContent = '⛶ Fullscreen';
            }} else {{
              // Enter fullscreen
              container.style.position = 'fixed';
              container.style.top = '0';
              container.style.left = '0';
              container.style.width = '100vw';
              container.style.height = '100vh';
              container.style.zIndex = '9999';
              container.style.backgroundColor = 'rgba(0,0,0,0.9)';
              iframe.style.height = '100vh';
              this.textContent = '✕ Exit Fullscreen';
            }}
          "
          style="
            position: absolute;
            top: 8px;
            right: 8px;
            padding: 6px 12px;
            background-color: rgba(0,0,0,0.7);
            color: white;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-family: sans-serif;
            z-index: 10000;
          "
          onmouseover="this.style.backgroundColor='rgba(0,0,0,0.9)'"
          onmouseout="this.style.backgroundColor='rgba(0,0,0,0.7)'"
        >
          ⛶ Fullscreen
        </button>
        <iframe
          id="{iframe_id}"
          src="{SUPERNOTE_URL}"
          width="100%"
          height="80vh"
          style="border: 1px solid #aaa; border-radius: 4px; min-height: 600px;"
          allow="camera; microphone; fullscreen"
          referrerpolicy="no-referrer-when-downgrade"
          loading="lazy"
        ></iframe>
      </div>
    </div>
    """

    iframe = widgets.HTML(value=iframe_html)

    capture_btn = widgets.Button(
        description="📸 Capture",
        button_style="primary",
        tooltip="Capture screenshot and save to ./diagrams folder.",
    )
    close_btn = widgets.Button(
        description="❌ Close",
        button_style="danger",
        tooltip="Close this Supernote Canvas panel.",
    )

    # Add file upload widget for remote environments
    upload_widget = None
    if is_remote:
        upload_widget = widgets.FileUpload(
            accept="image/*",
            multiple=False,
            description="Upload screenshot",
            button_style="info",
        )

    output = widgets.Output()

    # Build container children
    container_children = [iframe]
    if is_remote and upload_widget:
        container_children.append(
            widgets.HBox(
                [capture_btn, upload_widget, close_btn],
                layout=widgets.Layout(padding="10px 0 10px 0"),
            )
        )
    else:
        container_children.append(
            widgets.HBox(
                [capture_btn, close_btn],
                layout=widgets.Layout(padding="10px 0 10px 0"),
            )
        )
    container_children.append(output)

    container = widgets.VBox(
        children=container_children,
        layout=widgets.Layout(border="1px solid #ddd", padding="6px"),
    )

    def _on_capture_click(_btn: widgets.Button) -> None:
        """Handle the Capture button click with priority-based method selection."""
        output.clear_output()

        with output:
            image_data: Optional[bytes] = None
            source_path: Optional[str] = None
            capture_method = ""

            # Priority 1: Try ADB capture (local environments only)
            if not is_remote and adb_available:
                print("Capturing via USB (ADB)...")
                image_data = _capture_via_adb()
                if image_data:
                    capture_method = "USB (ADB)"
                    print(f"✓ Captured via {capture_method}")

            # Priority 2: Try file upload (remote environments)
            if image_data is None and is_remote and upload_widget:
                try:
                    # FileUpload widget value is a dict with file metadata
                    if upload_widget.value:
                        # Handle different possible structures
                        if isinstance(upload_widget.value, dict):
                            # Get the first (and only) uploaded file
                            file_list = list(upload_widget.value.values())
                            if file_list:
                                uploaded_file = file_list[0]
                                # Handle both dict format and tuple format
                                if isinstance(uploaded_file, dict):
                                    image_data = uploaded_file.get("content")
                                    source_path = uploaded_file.get("metadata", {}).get("name", "")
                                elif isinstance(uploaded_file, tuple) and len(uploaded_file) >= 2:
                                    # Format: (content, metadata)
                                    image_data = uploaded_file[0]
                                    source_path = uploaded_file[1].get("name", "") if len(uploaded_file) > 1 else ""
                                
                                if image_data:
                                    capture_method = "file upload"
                                    print(f"✓ Captured via {capture_method}")
                except Exception as exc:
                    print(f"Error reading uploaded file: {exc}")
                    import traceback
                    traceback.print_exc()

            # Priority 3: Fallback to folder-based method (local environments)
            if image_data is None and not is_remote:
                print("Trying folder-based capture...")
                src = _latest_screenshot(SCREENSHOT_DIR)
                if src:
                    try:
                        with open(src, "rb") as f:
                            image_data = f.read()
                        source_path = src
                        capture_method = "folder"
                        print(f"✓ Captured via {capture_method} from '{SCREENSHOT_DIR}'")
                    except OSError as exc:
                        print(f"Failed to read screenshot file: {exc}")

            # If we still don't have image data, show error
            if image_data is None:
                if is_remote:
                    print(
                        "No screenshot uploaded.\n"
                        "Please use the file upload widget above to select a screenshot file."
                    )
                else:
                    if adb_available:
                        print(
                            f"ADB capture failed. No screenshot files found in '{SCREENSHOT_DIR}'.\n"
                            "Make sure you have taken a screenshot as .png, .jpg, or .jpeg, "
                            "or check your USB connection."
                        )
                    else:
                        print(
                            f"No screenshot files found in '{SCREENSHOT_DIR}'.\n"
                            "Make sure you have taken a screenshot as .png, .jpg, or .jpeg."
                        )
                return

            # Process and save the image
            dest_path = _process_and_save_image(image_data, source_path)
            if dest_path is None:
                return

            # Display the result
            if capture_method:
                print(f"Captured via {capture_method}\n")
            _display_captured_image(dest_path)

    def _on_close_click(_btn: widgets.Button) -> None:
        """Handle the Close button click: close the container widget."""
        # Close the entire container so it disappears from the notebook output.
        container.close()

    def _on_upload_change(change: dict) -> None:
        """Handle file upload change - auto-trigger capture when file is uploaded."""
        if change["new"] and upload_widget and upload_widget.value:
            # File was uploaded, automatically trigger capture
            _on_capture_click(capture_btn)

    capture_btn.on_click(_on_capture_click)
    close_btn.on_click(_on_close_click)
    if upload_widget:
        upload_widget.observe(_on_upload_change, names="value")

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


