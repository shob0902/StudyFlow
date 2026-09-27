# Icons for the HTML cards. st.html strips inline SVG, so these use the Material Symbols font
# Streamlit already ships for its own widget icons, which also keeps the cards and the buttons in
# one icon set. Each icon is decorative and hidden from screen readers.
NAMES = {
    "sparkles": "auto_awesome",
    "flame": "local_fire_department",
    "target": "track_changes",
    "code": "code",
    "repeat": "replay",
    "check": "check",
    "x": "close",
    "file": "description",
    "calendar": "calendar_month",
    "chart": "insights",
    "book": "menu_book",
    "clock": "schedule",
    "layers": "layers",
    "upload": "upload_file",
    "message": "chat",
}
# An icon that inherits the surrounding text colour.
def icon(name: str, size: int = 18) -> str:
    return (
        f"<span class='sa-mi' aria-hidden='true' style='font-size:{size}px'>"
        f"{NAMES.get(name, NAMES['sparkles'])}</span>"
    )
