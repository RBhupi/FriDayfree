"""Streamlit helpers shared by every page. No business logic."""
import sqlite3
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from fridayfree.modules.errors import ValidationError
from fridayfree.utils.export import df_to_markdown, markdown_filename


@dataclass
class AppContext:
    conn: sqlite3.Connection
    fy: dict            # the fiscal year selected in the sidebar
    person: dict        # None until Settings -> Person is filled in
    today: date

    @property
    def rate(self):
        return self.person["rate_dollar"] if self.person else None


def run_action(action, success: str = None) -> bool:
    """Run a service call; show ValidationError text instead of a traceback. True when it worked."""
    try:
        action()
    except ValidationError as exc:
        st.error(str(exc))
        return False
    if success:
        flash(success)
    return True


def queue_widget_values(queue_key: str, **values) -> None:
    """Park values for widgets that already exist this run; apply_queued_values() writes them next run.

    Streamlit refuses `st.session_state[k] = v` once the widget with key k has been created, so anything a
    button wants to pre-fill has to travel through one rerun.
    """
    st.session_state[queue_key] = values
    st.rerun()


def apply_queued_values(queue_key: str, key_for=lambda name: name) -> None:
    """Call at the top of a page, before any of its widgets are created."""
    for name, value in (st.session_state.pop(queue_key, None) or {}).items():
        st.session_state[key_for(name)] = value


def flash(message: str) -> None:
    """Queue a success message that survives the next st.rerun()."""
    st.session_state.setdefault("_flash", []).append(message)


def show_flashes() -> None:
    for message in st.session_state.pop("_flash", []):
        st.success(message)


def show_warnings(warnings) -> None:
    for warning in warnings:
        st.warning(warning, icon="⚠️")


def export_controls(df: pd.DataFrame, stem: str, today: date) -> None:
    """Copy-as-markdown (the code block has a copy button) and download as .md."""
    with st.expander("Export as markdown"):
        markdown = df_to_markdown(df)
        st.download_button(
            "Download .md", markdown, file_name=markdown_filename(stem, today), mime="text/markdown",
            key=f"dl_{stem}",
        )
        st.code(markdown, language="markdown")


# Copy-to-clipboard button ------------------------------------------------------------------------
# The text arrives through `data` and is only ever used as a string, never as HTML.

_COPY_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const button = parentElement.querySelector("button");
  button.textContent = data.label;
  button.title = data.text;
  button.onclick = async () => {
    let copied = true;
    try {
      await navigator.clipboard.writeText(data.text);
    } catch (err) {
      const area = document.createElement("textarea");
      area.value = data.text;
      document.body.appendChild(area);
      area.select();
      copied = document.execCommand("copy");
      area.remove();
    }
    button.textContent = copied ? "Copied ✓" : "Copy failed — select the text instead";
    setTimeout(() => { button.textContent = data.label; }, 1500);
  };
}
"""

_COPY_CSS = """
button {
  font: inherit; font-size: 0.875rem; line-height: 1.6; cursor: pointer; white-space: nowrap;
  padding: 0.25rem 0.75rem; border-radius: 0.5rem; width: 100%;
  color: var(--st-text-color, inherit);
  background: var(--st-secondary-background-color, transparent);
  border: 1px solid var(--st-border-color, rgba(128, 128, 128, 0.4));
}
button:hover { border-color: var(--st-primary-color, #ff4b4b); color: var(--st-primary-color, #ff4b4b); }
"""

_copy_renderers = {}


def _copy_renderer():
    """Register the component once per Streamlit runtime (tests start several)."""
    manager = st.components.v2.get_bidi_component_manager()
    if id(manager) not in _copy_renderers:
        _copy_renderers[id(manager)] = st.components.v2.component(
            "copy_button", html='<button type="button"></button>', css=_COPY_CSS, js=_COPY_JS
        )
    return _copy_renderers[id(manager)]


def copy_button(text: str, key: str, label: str = "Copy cost code") -> None:
    """A button that puts `text` on the clipboard, e.g. the Dayforce charge string of a project."""
    _copy_renderer()(data={"text": text, "label": label}, key=key)
