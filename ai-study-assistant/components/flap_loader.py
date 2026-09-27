# Split-flap "departure board" loading overlay. Pure HTML + CSS: st.markdown does not run scripts, so every
# flip is a CSS keyframe built here in Python. Shown once per page load (session), not on ordinary reruns.
import html
import random
import string
import time
import streamlit as st

SHOW_ON_EVERY_RERUN = False  # True = replay the board on every rerun, not just on page load / refresh
DEFAULT_STATUS = "Gate 4 · Preparing your dashboard"
STATE_KEY = "board_shown_at"  # when this session first showed the board (a refresh starts a new session)
FLIP = 0.08         # seconds for one flap to fall (at the default 2.5s duration; shorter durations scale down)
LETTER_STEP = 0.10  # seconds between flips while a letter cycles; also the left-to-right settle stagger
FADE = 0.3          # seconds for the final fade-out
COUNTER = (" 00", " 25", " 50", " 75", " 99", "100")
# StudyFlow palette (ui/theme.py tokens, with fallbacks since this renders before inject_styles()).
THEMES = {
    "light": {  # the app's lavender canvas with raised white tiles
        "bg": "var(--neu-bg,#EEF0F8)", "tile": "#FFFFFF", "ink": "var(--text,#17152B)",
        "accent": "var(--primary,#6D4AFF)", "hinge": "rgba(110,90,180,.16)", "muted": "var(--muted,#67657C)",
        "shadow": "var(--neu-raised-sm,4px 4px 10px rgba(160,156,206,.5),-4px -4px 10px rgba(255,255,255,.95))",
    },
    "dark": {  # deep indigo version of the same palette
        "bg": "#17152B", "tile": "#221F3A", "ink": "#F4F2FF", "accent": "#A48EFF",
        "hinge": "#110F22", "muted": "#9A98AC", "shadow": "0 0 0 1px rgba(164,142,255,.10)",
    },
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@700&display=swap');
/* Streamlit wraps each element in a container: take this one out of the flow so it leaves no gap */
[data-testid="stElementContainer"]:has(.sf-overlay),.element-container:has(.sf-overlay){position:absolute!important;width:0!important;height:0!important;margin:0!important}/* full-screen board above Streamlit's header and sidebar; the app keeps loading underneath */
.sf-overlay{position:fixed;inset:0;z-index:999999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:0 16px;
  background:var(--sf-bg);font-family:'JetBrains Mono','IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;
  --w:min(44px,calc((100vw - 32px - (var(--n) - 1) * 8px) / var(--n)));--h:calc(var(--w) * 1.36)}
.sf-row{display:flex;gap:8px}
/* one tile; the strip inside stacks every character the tile will show, and steps through them */
.sf-t{position:relative;width:var(--w);height:var(--h);overflow:hidden;border-radius:10px;background:var(--sf-tile);
  box-shadow:var(--sf-shadow);perspective:calc(var(--h) * 4)}
.sf-strip{position:absolute;top:0;left:0;right:0;display:flex;flex-direction:column}
.sf-strip span{display:block;height:var(--h);line-height:var(--h);text-align:center;color:var(--sf-ink);font-weight:700;font-size:calc(var(--w) * .72)}
.sf-acc .sf-strip span{color:var(--sf-accent)}
/* the falling top flap: carries the old character's top half down, parked edge-on (-90deg) between flips */
.sf-leaf{position:absolute;top:0;left:0;right:0;height:50%;overflow:hidden;background:var(--sf-tile);border-radius:10px 10px 0 0;
  transform-origin:50% 100%;transform:rotateX(-90deg);-webkit-backface-visibility:hidden;backface-visibility:hidden}
/* the split between top and bottom flap */
.sf-t::after{content:"";position:absolute;left:0;right:0;top:50%;height:1px;margin-top:-.5px;background:var(--sf-hinge);z-index:2}
.sf-status{margin-top:10px;font-family:'Inter',-apple-system,'Segoe UI',sans-serif;font-size:13px;font-weight:500;color:var(--sf-muted)}
.sf-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
/* reduced motion: no flipping, the tiles sit on their final characters (inline transform) and the board just fades */
@media (prefers-reduced-motion:reduce){.sf-strip,.sf-leaf{animation:none!important}}
</style>
"""


# Show the board if this page load hasn't finished showing it yet. Call right after st.set_page_config().
def show_flap_loader(text: str = "LOADING", duration: float = 2.5, theme: str = "light",
                     status: str = DEFAULT_STATUS) -> None:
    now = time.time()
    started = st.session_state.get(STATE_KEY)
    if started is None or SHOW_ON_EVERY_RERUN:
        started = st.session_state[STATE_KEY] = now
    # A rerun inside the first `duration` seconds re-sends identical HTML (same seed), so the animation
    # carries on instead of vanishing; after that the element is simply not rendered any more.
    if now - started >= duration:
        return
    st.markdown(build_html(text, duration, theme, status, seed=started), unsafe_allow_html=True)


def build_html(text: str, duration: float, theme: str, status: str, seed: float = 0) -> str:
    duration = max(1.0, float(duration))
    k = min(1.0, duration / 2.5)  # compress the schedule for short durations
    flip = FLIP * k
    rng = random.Random(seed)
    palette = THEMES.get(theme, THEMES["light"])
    word = (text.upper()[:12] or " ")
    anim = f"{duration:g}s linear 0s both"
    keyframes, letters, digits = [], [], []
    for j, ch in enumerate(word):
        kf, tile = _tile(f"w{j}", _letter_events(ch, j, k, rng), duration, flip, anim)
        keyframes.append(kf)
        letters.append(tile)
    for p in range(4):
        events = _counter_events(p, k, duration) if p < 3 else [(0.0, "%")]
        kf, tile = _tile(f"c{p}", events, duration, flip, anim, extra_class=" sf-acc")
        keyframes.append(kf)
        digits.append(tile)
    fade_at = (duration - FADE) / duration * 100
    keyframes.append(f"@keyframes sf-fade{{0%,{fade_at:.3f}%{{opacity:1;visibility:visible}}"
                     "100%{opacity:0;visibility:hidden}}")
    tokens = "".join(f"--sf-{name}:{value};" for name, value in palette.items())
    overlay_style = f"{tokens}--n:{max(len(word), 4)};animation:sf-fade {anim}"
    status_html = f"<div class='sf-status' aria-hidden='true'>{html.escape(status)}</div>" if status else ""
    markup = (
        f"<div class='sf-overlay' role='status' aria-live='polite' style='{overlay_style}'>"
        f"<div class='sf-row' aria-hidden='true'>{''.join(letters)}</div>"
        f"<div class='sf-row' aria-hidden='true'>{''.join(digits)}</div>"
        f"{status_html}<span class='sf-sr'>{html.escape(text.capitalize())}</span></div>"
    )
    css = CSS.replace("</style>", "\n".join(keyframes) + "\n</style>")
    # No blank lines or indented lines, or Markdown would end the HTML block / treat it as code.
    return "\n".join(line.strip() for line in (css + markup).splitlines() if line.strip())


# A letter tile: blank, then a few random letters, then the real letter. Tile j rolls one letter more
# than tile j-1, so the word settles left to right, one LETTER_STEP apart.
def _letter_events(ch: str, j: int, k: float, rng: random.Random) -> list[tuple[float, str]]:
    if ch == " ":
        return [(0.0, " ")]
    rolls, prev = [], " "
    for _ in range(4 + j):
        prev = rng.choice([c for c in string.ascii_uppercase if c not in (prev, ch)])
        rolls.append(prev)
    start, step = 0.15 * k, LETTER_STEP * k
    return [(0.0, " ")] + [(start + s * step, c) for s, c in enumerate(rolls + [ch])]


# One digit of the percentage: flips only when its character changes, 00 -> 25 -> 50 -> 75 -> 99 -> 100.
def _counter_events(p: int, k: float, duration: float) -> list[tuple[float, str]]:
    first, last = 0.25 * k, duration - FADE - 0.35 * k
    events = [(0.0, COUNTER[0][p])]
    for n in range(1, len(COUNTER)):
        if COUNTER[n][p] != events[-1][1]:
            events.append((first + (n - 1) * (last - first) / 4 + p * 0.04 * k, COUNTER[n][p]))
    return events


# One tile's markup plus its keyframes. The face strip jumps to the new character at the start of a flip
# (step-end); the leaf pops up showing the old character and falls in 3 steps; its own strip catches up
# once it is edge-on again, ready for the next flip.
def _tile(name: str, events: list[tuple[float, str]], total: float, flip: float, anim: str,
          extra_class: str = "") -> tuple[str, str]:
    chars = [c for _, c in events]
    m = len(chars)
    cells = "".join(f"<span>{'&nbsp;' if c == ' ' else html.escape(c)}</span>" for c in chars)
    final = _shift(m - 1, m)
    if m == 1:
        return "", f"<div class='sf-t{extra_class}'><span class='sf-strip'>{cells}</span></div>"
    face = [f"0%{{transform:{_shift(0, m)};animation-timing-function:step-end}}"]
    leaf_strip = list(face)
    leaf_turn = ["0%{transform:rotateX(-90deg);animation-timing-function:step-end}"]
    for i, (t, _) in enumerate(events[1:], 1):
        face.append(f"{_pct(t, total)}{{transform:{_shift(i, m)};animation-timing-function:step-end}}")
        leaf_strip.append(f"{_pct(t + flip, total)}{{transform:{_shift(i, m)};animation-timing-function:step-end}}")
        leaf_turn.append(f"{_pct(t, total)}{{transform:rotateX(0deg);animation-timing-function:steps(3,end)}}")
        leaf_turn.append(f"{_pct(t + flip, total)}{{transform:rotateX(-90deg);animation-timing-function:step-end}}")
    face.append(f"100%{{transform:{final}}}")
    leaf_strip.append(f"100%{{transform:{final}}}")
    leaf_turn.append("100%{transform:rotateX(-90deg)}")
    kf = (f"@keyframes sf-f-{name}{{{''.join(face)}}}"
          f"@keyframes sf-l-{name}{{{''.join(leaf_strip)}}}"
          f"@keyframes sf-r-{name}{{{''.join(leaf_turn)}}}")
    tile = (f"<div class='sf-t{extra_class}'>"
            f"<span class='sf-strip' style='transform:{final};animation:sf-f-{name} {anim}'>{cells}</span>"
            f"<span class='sf-leaf' style='animation:sf-r-{name} {anim}'>"
            f"<span class='sf-strip' style='transform:{final};animation:sf-l-{name} {anim}'>{cells}</span></span></div>")
    return kf, tile


def _shift(i: int, m: int) -> str:
    return f"translateY({-i * 100 / m:.4f}%)"


def _pct(t: float, total: float) -> str:
    return f"{max(0.0, min(100.0, t / total * 100)):.3f}%"
