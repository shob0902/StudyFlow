# Code-editor keys for the coding practice text area, which Streamlit renders as a plain textarea.
#
#   Enter            new line at the same indentation; one level deeper after a line ending in
#                    ':' or an opening bracket, one level shallower after return/pass/break/...
#   Tab / Shift+Tab  indent / dedent (the selected lines, or insert four spaces at the cursor)
#   Backspace        in leading spaces, removes a whole indent level
#   Esc, then Tab    leaves the editor, so keyboard users are never trapped in it
#
# The handler is injected once into the page itself (not into Streamlit's helper iframe, which can
# be recreated on any rerun) and a MutationObserver attaches it to each new editor. Edits go
# through execCommand('insertText'), which keeps undo working and fires the input events React
# listens for, so Streamlit sees every change.
import json
import streamlit as st
EDITOR_SELECTOR = '[class*="st-key-coding_editor_"] textarea'
INDENT = "    "
PAGE_SCRIPT = r"""
(function () {
  const INDENT = __INDENT__;
  const SELECTOR = __SELECTOR__;
  const OPENERS = /[:\[{(]\s*(#.*)?$/;
  const ENDERS = /^\s*(return|pass|break|continue|raise)\b/;
  function edit(ta, text) {
    if (!document.execCommand("insertText", false, text)) {
      ta.setRangeText(text, ta.selectionStart, ta.selectionEnd, "end");
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }
  function onKey(e) {
    const ta = e.target;
    if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") { ta.dataset.saEscape = "1"; return; }
    const escaped = ta.dataset.saEscape === "1";
    delete ta.dataset.saEscape;
    const value = ta.value, start = ta.selectionStart, end = ta.selectionEnd;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    if (e.key === "Enter" && !e.shiftKey) {
      const line = value.slice(lineStart, start);
      let indent = (line.match(/^[ \t]*/) || [""])[0];
      if (OPENERS.test(line)) indent += INDENT;
      else if (ENDERS.test(line)) indent = indent.slice(0, Math.max(0, indent.length - INDENT.length));
      e.preventDefault();
      edit(ta, "\n" + indent);
    } else if (e.key === "Tab" && !escaped) {
      e.preventDefault();
      if (start === end && !e.shiftKey) { edit(ta, INDENT); return; }
      const blockEnd = value.indexOf("\n", end - (end > start && value[end - 1] === "\n" ? 1 : 0));
      const stop = blockEnd === -1 ? value.length : blockEnd;
      const lines = value.slice(lineStart, stop).split("\n");
      const changed = lines.map(function (l) {
        return e.shiftKey ? l.replace(/^( {1,4}|\t)/, "") : INDENT + l;
      }).join("\n");
      ta.setSelectionRange(lineStart, stop);
      edit(ta, changed);
      ta.setSelectionRange(lineStart, lineStart + changed.length);
    } else if (e.key === "Backspace" && start === end) {
      const before = value.slice(lineStart, start);
      if (before.length && /^ +$/.test(before)) {
        e.preventDefault();
        ta.setSelectionRange(start - (before.length % INDENT.length || INDENT.length), start);
        if (!document.execCommand("delete")) edit(ta, "");
      }
    }
  }
  function attach() {
    document.querySelectorAll(SELECTOR).forEach(function (ta) {
      if (ta.dataset.saCode) return;
      ta.dataset.saCode = "1";
      ta.spellcheck = false;
      ta.setAttribute("autocapitalize", "off");
      ta.setAttribute("autocomplete", "off");
      ta.addEventListener("keydown", onKey);
    });
  }
  attach();
  new MutationObserver(attach).observe(document.body, { childList: true, subtree: true });
})();
"""
# The page script with its settings filled in.
def page_script() -> str:
    return PAGE_SCRIPT.replace("__INDENT__", json.dumps(INDENT)).replace(
        "__SELECTOR__", json.dumps(EDITOR_SELECTOR)
    )
# Turn the coding text area into a small code editor. Safe to call on every run: the page keeps
# a flag, so the handler is only ever installed once.
def enable() -> None:
    loader = (
        "<script>(function(){"
        # The helper frame is invisible, so keep it out of the Tab order and the accessibility tree.
        "try{window.frameElement.tabIndex=-1;window.frameElement.setAttribute('aria-hidden','true');}catch(e){}"
        "const w=window.parent;if(!w||w.__saCodeEditor)return;"
        "w.__saCodeEditor=true;const s=w.document.createElement('script');"
        f"s.textContent={json.dumps(page_script())};w.document.head.appendChild(s);}})();</script>"
    )
    with st.container(key="sa_code_editor_js"):
        if hasattr(st, "iframe"):
            st.iframe(loader, height=1)
        else:
            import streamlit.components.v1 as components
            components.html(loader, height=0, width=0)
