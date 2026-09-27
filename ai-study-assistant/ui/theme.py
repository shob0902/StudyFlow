# Global CSS: the StudyFlow design system (violet accents, neumorphic surfaces on a soft lavender canvas) injected
# into the Streamlit page. Every colour, radius and shadow is a token on :root, so the look is
# changed here and nowhere else.
import streamlit as st
GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{
--primary:#6D4AFF;--primary-dark:#5535D9;--primary-light:#EEE9FF;--primary-soft:#F6F3FF;
--blue:#4F7BFF;--blue-light:#E8EEFF;
--bg:#F7F8FC;--card:#FFFFFF;--surface:rgba(255,255,255,.78);--glass:rgba(255,255,255,.66);--glass-border:rgba(255,255,255,.75);
--text:#17152B;--muted:#67657C;--faint:#9A98AC;--border:rgba(110,90,180,.14);--border-strong:rgba(110,90,180,.26);
--success:#138A4B;--success-soft:#E6F6EC;--warning:#B45309;--warning-soft:#FEF3E2;--danger:#C2334D;--danger-soft:#FDECEF;--amber:#F5B544;
--grad:linear-gradient(135deg,#6D4AFF 0%,#5B6CFF 55%,#4F7BFF 100%);
--grad-soft:linear-gradient(135deg,#F3EEFF 0%,#EAF0FF 100%);
--radius-xl:28px;--radius-lg:22px;--radius:18px;--radius-sm:12px;
--shadow-sm:0 2px 10px rgba(80,60,150,.06);--shadow:0 10px 40px rgba(80,60,150,.08);--shadow-lg:0 18px 50px rgba(80,60,150,.14);
--ring:0 0 0 3px rgba(109,74,255,.28);
/* neumorphism: one surface colour, lit from the top-left */
--neu-bg:#EEF0F8;--neu-light:rgba(255,255,255,.95);--neu-dark:rgba(160,156,206,.5);
--neu-raised-sm:4px 4px 10px var(--neu-dark),-4px -4px 10px var(--neu-light);
--neu-raised:8px 8px 18px var(--neu-dark),-8px -8px 18px var(--neu-light);
--neu-raised-lg:12px 12px 28px var(--neu-dark),-12px -12px 28px var(--neu-light);
--neu-inset:inset 4px 4px 9px var(--neu-dark),inset -4px -4px 9px var(--neu-light);
--neu-inset-sm:inset 2px 2px 5px var(--neu-dark),inset -2px -2px 5px var(--neu-light);
--neu-accent:6px 6px 16px rgba(109,74,255,.35),-6px -6px 14px var(--neu-light);
}
@keyframes saFadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes saPop{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:none}}
@keyframes saGrowBar{from{width:0}}
@keyframes saPulse{0%{box-shadow:0 0 0 0 rgba(109,74,255,.35)}70%{box-shadow:0 0 0 10px rgba(109,74,255,0)}100%{box-shadow:0 0 0 0 rgba(109,74,255,0)}}
@keyframes saFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}

/* ---------- canvas & typography ---------- */
html,body,.stApp,[data-testid="stAppViewContainer"],button,input,textarea,select{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif!important;}
.stApp{color:var(--text);background:
 radial-gradient(900px 520px at 6% -8%,rgba(141,110,255,.18),transparent 60%),
 radial-gradient(760px 480px at 100% 4%,rgba(79,123,255,.14),transparent 60%),
 radial-gradient(700px 520px at 60% 108%,rgba(181,160,255,.16),transparent 60%),
 radial-gradient(rgba(109,74,255,.06) 1px,transparent 1px) 0 0/26px 26px,
 var(--bg);background-attachment:fixed;}
[data-testid="stHeader"]{background:transparent;}
/* no animation here: any animation on this column traps the full-screen loading board (components/flap_loader.py)
   inside it, under the sidebar. Cards and heroes keep their own entrance animations. */
.block-container,[data-testid="stMainBlockContainer"]{max-width:1200px;padding-top:2.6rem;padding-bottom:4rem;}
[data-testid="stHeading"] h1,[data-testid="stHeading"] h2,[data-testid="stHeading"] h3,[data-testid="stHeading"] h4{color:var(--text);letter-spacing:-.02em;font-weight:700;}
[data-testid="stHeading"] h2{font-size:1.35rem;}
[data-testid="stHeading"] h3{font-size:1.08rem;}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{color:var(--text);}
button [data-testid="stMarkdownContainer"] p{color:inherit;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p,.stCaption{color:var(--muted)!important;}
a{color:var(--primary-dark);}
.sa-mi{font-family:'Material Symbols Rounded'!important;font-weight:normal;font-style:normal;line-height:1;letter-spacing:normal;text-transform:none;display:inline-block;white-space:nowrap;direction:ltr;font-feature-settings:'liga';-webkit-font-feature-settings:'liga';-webkit-font-smoothing:antialiased;vertical-align:middle;user-select:none;}
hr,[data-testid="stDivider"]{border-color:var(--border)!important;}
:focus-visible{outline:none;box-shadow:var(--ring)!important;border-radius:10px;}

/* ---------- buttons ---------- */
button[data-testid^="stBaseButton"]{border-radius:12px!important;font-weight:600!important;min-height:2.5rem;transition:transform .16s ease,box-shadow .2s ease,background .2s ease,border-color .2s ease!important;}
button[data-testid^="stBaseButton"]:hover{transform:scale(1.015);}
button[data-testid^="stBaseButton"]:active{transform:scale(.99);}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--grad)!important;border:none!important;color:#fff!important;box-shadow:0 6px 18px rgba(109,74,255,.28);}
button[data-testid="stBaseButton-primary"]:hover,button[data-testid="stBaseButton-primaryFormSubmit"]:hover{box-shadow:0 10px 24px rgba(109,74,255,.34);}
button[data-testid="stBaseButton-secondary"],button[data-testid="stBaseButton-secondaryFormSubmit"]{background:var(--surface)!important;border:1px solid var(--border-strong)!important;color:var(--text)!important;}
button[data-testid="stBaseButton-secondary"]:hover,button[data-testid="stBaseButton-secondaryFormSubmit"]:hover{border-color:var(--primary)!important;color:var(--primary-dark)!important;background:#fff!important;}
button[data-testid="stBaseButton-tertiary"]{color:var(--muted)!important;}
button[data-testid="stBaseButton-tertiary"]:hover{color:var(--primary-dark)!important;background:var(--primary-soft)!important;}

/* ---------- inputs ---------- */
div[data-baseweb="input"],div[data-baseweb="textarea"],div[data-baseweb="select"]>div,[data-testid="stNumberInput"] div[data-baseweb="input"],[data-testid="stDateInput"] div[data-baseweb="input"]{border-radius:12px!important;border-color:var(--border-strong)!important;background:#fff!important;transition:box-shadow .2s ease,border-color .2s ease;}
div[data-baseweb="input"]:focus-within,div[data-baseweb="textarea"]:focus-within,div[data-baseweb="select"]>div:focus-within{border-color:var(--primary)!important;box-shadow:var(--ring);}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{color:var(--text);}
[data-testid="stWidgetLabel"] p{color:var(--text);font-weight:600;font-size:.9rem;}
[data-testid="stForm"]{background:var(--surface);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid var(--border)!important;border-radius:var(--radius-lg)!important;box-shadow:var(--shadow);padding:1.2rem 1.3rem!important;}
[data-testid="stFileUploaderDropzone"]{background:var(--primary-soft)!important;border:1.5px dashed rgba(109,74,255,.45)!important;border-radius:var(--radius)!important;transition:background .2s ease,border-color .2s ease;}
[data-testid="stFileUploaderDropzone"]:hover{background:var(--primary-light)!important;border-color:var(--primary)!important;}
[data-testid="stProgress"] div[role="progressbar"]>div>div>div{background:var(--grad)!important;}
[data-testid="stProgress"] div[role="progressbar"]>div>div{background:var(--primary-light)!important;border-radius:999px;}
[data-testid="stCheckbox"] label span:first-child{border-radius:6px;}

/* ---------- quiz options ---------- */
[class*="st-key-qcard"],[class*="st-key-docq_"]{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.1rem .7rem;box-shadow:var(--shadow-sm);transition:box-shadow .2s ease,border-color .2s ease;}
[class*="st-key-qcard"]:hover,[class*="st-key-docq_"]:hover{box-shadow:var(--shadow);border-color:var(--border-strong);}
[class*="st-key-qcard"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),[data-testid="stRadio"]{width:100%!important;}
[data-testid="stRadio"] [role="radiogroup"]{gap:.45rem;width:100%;}
[data-testid="stRadioOption"],[data-testid="stRadio"] label[data-baseweb="radio"]{background:var(--primary-soft);border:1.5px solid transparent;border-radius:12px;padding:.6rem .85rem;margin:0;width:100%;box-sizing:border-box;transition:background .15s ease,border-color .15s ease;cursor:pointer;}
[data-testid="stRadioOption"]:hover,[data-testid="stRadio"] label[data-baseweb="radio"]:hover{border-color:rgba(109,74,255,.35);background:#fff;}
[data-testid="stRadioOption"]:has(input:checked),[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:var(--primary-light);border-color:var(--primary);}

/* ---------- containers, alerts, tabs ---------- */
[data-testid="stExpander"] details{border-radius:var(--radius)!important;border:1px solid var(--border)!important;background:var(--surface);box-shadow:var(--shadow-sm);}
[data-testid="stExpander"] summary{font-weight:600;color:var(--text);}
[data-testid="stExpander"] summary:hover{color:var(--primary-dark);}
[data-testid="stAlert"]{border-radius:14px;border:1px solid var(--border);animation:saPop .3s ease both;}
[data-testid="stPopoverBody"],div[data-baseweb="popover"]>div{border-radius:var(--radius)!important;border:1px solid var(--border)!important;box-shadow:var(--shadow-lg)!important;}
[data-testid="stTabs"] button[role="tab"]{border-radius:10px 10px 0 0;font-weight:600;color:var(--muted);}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"]{color:var(--primary-dark);}
[data-testid="stCode"] pre,[data-testid="stCodeBlock"] pre{border-radius:14px!important;}
[data-testid="stStatusWidget"],[data-testid="stExpander"]:has([data-testid="stStatusWidget"]){border-radius:var(--radius);}
[data-testid="stIFrame"],iframe{border-radius:var(--radius-lg);}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:rgba(255,255,255,.62)!important;backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);border-right:1px solid var(--glass-border);box-shadow:4px 0 30px rgba(80,60,150,.06);}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:.4rem;}
.sa-brand{display:flex;align-items:center;gap:.7rem;padding:.2rem .2rem 1rem;}
.sa-brand .logo{width:2.4rem;height:2.4rem;border-radius:12px;display:grid;place-items:center;background:var(--grad);color:#fff;box-shadow:0 6px 16px rgba(109,74,255,.3);flex:none;}
.sa-brand .name{font-weight:800;font-size:1.12rem;letter-spacing:-.02em;color:var(--text);line-height:1.1;}
.sa-brand .tag{font-size:.74rem;color:var(--muted);font-weight:500;}
.sa-nav-label{font-size:.68rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin:.9rem 0 .3rem .55rem;}
[class*="st-key-sa_navgroup"]{gap:.15rem!important;}
[class*="st-key-sa_navgroup"] button{justify-content:flex-start!important;min-height:2.35rem!important;padding:.35rem .7rem!important;border-radius:12px!important;font-weight:500!important;font-size:.92rem!important;border:none!important;box-shadow:none!important;transform:none!important;transition:background .18s ease,color .18s ease!important;}
[class*="st-key-sa_navgroup"] button>div,[class*="st-key-histitem"] button>div,[class*="st-key-sa_search_results"] button>div,[class*="st-key-sa_ai_card"] button>div{justify-content:flex-start!important;width:100%;}
[class*="st-key-sa_navgroup"] button p,[class*="st-key-histitem"] button p{text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-tertiary"]{color:var(--muted)!important;background:transparent!important;}
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-tertiary"]:hover{background:rgba(109,74,255,.07)!important;color:var(--text)!important;}
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-primary"]{background:var(--primary-light)!important;color:var(--primary-dark)!important;font-weight:650!important;position:relative;}
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-primary"]::before{content:"";position:absolute;left:-.1rem;top:22%;bottom:22%;width:3px;border-radius:3px;background:var(--primary);}
[class*="st-key-sa_navgroup"] button [data-testid="stIconMaterial"]{font-size:1.15rem;}
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"]{color:var(--primary);}
[class*="st-key-sa_sidebar_history"]{margin-top:.4rem;}
.sa-side-head{background:var(--grad);color:#fff;border-radius:var(--radius);padding:.9rem 1rem;box-shadow:var(--shadow);}
.sa-side-head .t{font-weight:700;font-size:1rem;}
.sa-side-row{display:flex;justify-content:space-between;gap:.5rem;padding:.4rem 0;border-bottom:1px dashed var(--border);font-size:.86rem;color:var(--text);}
.sa-side-row span:first-child{color:var(--muted);}
.sa-side-row span:last-child{font-weight:600;text-align:right;}
.sa-side-head .sa-side-row{border-bottom-color:rgba(255,255,255,.25);color:#fff;}
.sa-side-head .sa-side-row span:first-child{color:rgba(255,255,255,.8);}
.sa-user{display:flex;align-items:center;gap:.7rem;background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:.7rem .8rem;box-shadow:var(--shadow-sm);}
.sa-user img,.sa-user .avatar{width:2.5rem;height:2.5rem;border-radius:50%;flex:none;object-fit:cover;border:2px solid var(--primary-light);}
.sa-user .avatar{display:grid;place-items:center;background:var(--grad);color:#fff;font-weight:700;}
.sa-user .who{min-width:0;}
.sa-user .who .n{font-weight:650;color:var(--text);font-size:.92rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sa-user .who .e{font-size:.76rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sa-hist-group{font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:.8rem 0 .2rem .3rem;}
.sa-hist-meta{font-size:.72rem;color:var(--muted);}
.sa-hist-empty{background:var(--primary-soft);border:1px dashed var(--border-strong);border-radius:14px;padding:.9rem;font-size:.84rem;text-align:center;color:var(--muted);}
[class*="st-key-histitem"] button[data-testid^="stBaseButton"]{border-radius:10px!important;justify-content:flex-start!important;text-align:left!important;font-weight:500!important;padding:.3rem .6rem!important;min-height:0!important;box-shadow:none!important;transform:none!important;}
[class*="st-key-histitem"] button[data-testid="stBaseButton-secondary"]{background:transparent!important;border-color:transparent!important;color:var(--text)!important;}
[class*="st-key-histitem"]:hover button[data-testid="stBaseButton-secondary"]{background:rgba(109,74,255,.07)!important;}
[class*="st-key-histitem"] button[data-testid="stBaseButton-primary"]{background:var(--primary-light)!important;color:var(--primary-dark)!important;}
[class*="st-key-histitem"] [data-testid="stPopover"] button{opacity:0;transition:opacity .15s ease;}
[class*="st-key-histitem"]:hover [data-testid="stPopover"] button,[class*="st-key-histitem"] [data-testid="stPopover"] button:focus{opacity:1;}
[class*="st-key-histitem"] [data-testid="stHorizontalBlock"]{gap:.15rem;align-items:center;}
[class*="st-key-histitem"]{gap:0!important;}
[class*="st-key-histitem"] .sa-hist-meta{margin:.05rem 0 .45rem .8rem;}
[class*="st-key-coding_editor_"] textarea{font-family:'JetBrains Mono',Consolas,'Cascadia Code',ui-monospace,monospace!important;font-size:.92rem!important;line-height:1.55!important;tab-size:4;white-space:pre;}
[class*="st-key-sa_code_editor_js"]{height:0!important;min-height:0!important;overflow:hidden;margin:0!important;padding:0!important;}
[class*="st-key-sa_cookie"]{height:0!important;min-height:0!important;overflow:hidden;margin:0!important;padding:0!important;}

/* ---------- top header ---------- */
[class*="st-key-sa_header"]{background:var(--glass);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:var(--radius-lg);box-shadow:var(--shadow);padding:.75rem 1rem .75rem 1.3rem;margin-bottom:1.4rem;}
[class*="st-key-sa_header"] [data-testid="stHorizontalBlock"]{align-items:center;}
.sa-page-title{font-size:1.4rem;font-weight:750;letter-spacing:-.025em;color:var(--text);line-height:1.2;margin:0;}
.sa-page-sub{font-size:.86rem;color:var(--muted);margin-top:.15rem;}
[class*="st-key-sa_search"] div[data-baseweb="input"]{border-radius:999px!important;background:rgba(246,243,255,.9)!important;border-color:transparent!important;}
[class*="st-key-sa_search"] div[data-baseweb="input"]:focus-within{background:#fff!important;border-color:var(--primary)!important;}
.sa-head-avatar{display:flex;justify-content:flex-end;}
.sa-head-avatar img,.sa-head-avatar .avatar{width:2.5rem;height:2.5rem;border-radius:50%;object-fit:cover;border:2px solid #fff;box-shadow:var(--shadow-sm);}
.sa-head-avatar .avatar{display:grid;place-items:center;background:var(--grad);color:#fff;font-weight:700;}
[class*="st-key-sa_search_results"]{background:#fff;border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow-lg);padding:.9rem 1rem;margin:-.6rem 0 1.4rem;animation:saPop .2s ease both;}
[class*="st-key-sa_search_results"] button{justify-content:flex-start!important;}

/* ---------- dashboard ---------- */
[class*="st-key-sa_hero"]{position:relative;overflow:hidden;background:linear-gradient(120deg,rgba(255,255,255,.9) 0%,rgba(243,238,255,.92) 55%,rgba(232,238,255,.92) 100%);border:1px solid var(--glass-border);border-radius:var(--radius-xl);box-shadow:var(--shadow);padding:1.9rem 2rem 1.6rem;margin-bottom:1.3rem;}
[class*="st-key-sa_hero"]::after{content:"";position:absolute;right:-90px;top:-110px;width:320px;height:320px;border-radius:50%;background:radial-gradient(circle,rgba(109,74,255,.22),transparent 65%);pointer-events:none;}
[class*="st-key-sa_hero"] [data-testid="stHorizontalBlock"]{max-width:420px;}
.sa-hello{font-size:clamp(1.55rem,3vw,2.1rem);font-weight:800;letter-spacing:-.03em;color:var(--text);margin:0;line-height:1.15;}
.sa-hello-sub{font-size:1.02rem;font-weight:600;color:var(--primary-dark);margin:.35rem 0 .2rem;}
.sa-hello-msg{color:var(--muted);font-size:.95rem;margin:0 0 .9rem;max-width:560px;}
.sa-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin:0 0 1.4rem;}
.sa-stat{background:var(--surface);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--glass-border);border-radius:var(--radius-lg);padding:1.05rem 1.15rem;box-shadow:var(--shadow);transition:transform .2s ease,box-shadow .2s ease;animation:saFadeUp .45s ease both;}
.sa-stat:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);}
.sa-stat .top{display:flex;align-items:center;gap:.55rem;color:var(--muted);font-size:.82rem;font-weight:600;}
.sa-stat .top .l{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;}
.sa-stat .ic{flex:none;width:2rem;height:2rem;border-radius:10px;display:grid;place-items:center;background:var(--primary-light);color:var(--primary);}
.sa-stat .ic.blue{background:var(--blue-light);color:var(--blue);}
.sa-stat .ic.warm{background:#FFF1E3;color:#E0772B;}
.sa-stat .ic.green{background:var(--success-soft);color:var(--success);}
.sa-stat .v{font-size:1.65rem;font-weight:800;letter-spacing:-.03em;color:var(--text);margin:.55rem 0 .1rem;line-height:1.1;}
.sa-stat .d{font-size:.78rem;color:var(--muted);}
.sa-mini{height:5px;border-radius:999px;background:var(--primary-light);margin-top:.65rem;overflow:hidden;}
.sa-mini span{display:block;height:100%;border-radius:999px;background:var(--grad);animation:saGrowBar .8s ease both;}
.sa-section-head{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;margin:.2rem 0 .7rem;}
.sa-section-head h3{font-size:1.05rem;font-weight:700;letter-spacing:-.015em;color:var(--text);margin:0;}
.sa-section-head span{font-size:.8rem;color:var(--muted);}
[class*="st-key-sa_panel"],[class*="st-key-sa_plan_card"]{background:var(--surface);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--glass-border);border-radius:var(--radius-lg);box-shadow:var(--shadow);padding:1.2rem 1.25rem;margin-bottom:1.1rem;}
[class*="st-key-sa_cont_"]{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.05rem .9rem;box-shadow:var(--shadow-sm);transition:transform .2s ease,box-shadow .2s ease;height:100%;}
[class*="st-key-sa_cont_"]:hover{transform:translateY(-2px);box-shadow:var(--shadow);}
.sa-cont .subj{display:inline-flex;align-items:center;gap:.35rem;font-size:.72rem;font-weight:650;color:var(--primary-dark);background:var(--primary-light);padding:.18rem .55rem;border-radius:999px;}
.sa-cont .ttl{font-weight:700;color:var(--text);font-size:.98rem;margin:.55rem 0 .2rem;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.sa-cont .meta{font-size:.76rem;color:var(--muted);display:flex;flex-wrap:wrap;justify-content:space-between;gap:.15rem .6rem;margin-top:.55rem;}
.sa-cont .track{height:6px;border-radius:999px;background:var(--primary-light);overflow:hidden;margin-top:.5rem;}
.sa-cont .track span{display:block;height:100%;border-radius:999px;background:var(--grad);animation:saGrowBar .8s ease both;}
[class*="st-key-sa_ai_card"]{position:relative;overflow:hidden;background:var(--grad);border-radius:var(--radius-lg);padding:1.3rem 1.25rem 1.1rem;box-shadow:0 16px 40px rgba(91,80,255,.3);margin-bottom:1.1rem;}
[class*="st-key-sa_ai_card"]::after{content:"";position:absolute;right:-60px;bottom:-80px;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.28),transparent 65%);pointer-events:none;}
.sa-ai{color:#fff;position:relative;z-index:1;}
.sa-ai .k{display:inline-flex;align-items:center;gap:.4rem;font-weight:700;font-size:.95rem;}
.sa-ai .q{font-size:1.18rem;font-weight:750;letter-spacing:-.02em;margin:.45rem 0 .25rem;line-height:1.3;}
.sa-ai .s{font-size:.85rem;opacity:.88;margin:0 0 .8rem;}
[class*="st-key-sa_ai_card"] button{background:rgba(255,255,255,.16)!important;border:1px solid rgba(255,255,255,.35)!important;color:#fff!important;justify-content:flex-start!important;box-shadow:none!important;backdrop-filter:blur(8px);position:relative;z-index:1;}
[class*="st-key-sa_ai_card"] button:hover{background:rgba(255,255,255,.26)!important;}
[class*="st-key-sa_ai_card"] button p{color:#fff!important;}
.sa-timeline{position:relative;margin:.2rem 0 0;padding:0;list-style:none;}
.sa-tl-day{font-size:.72rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);margin:.8rem 0 .4rem;}
.sa-tl-day:first-child{margin-top:0;}
.sa-tl-item{position:relative;display:flex;gap:.7rem;align-items:flex-start;padding:0 0 .75rem;}
.sa-tl-item:not(:last-child)::before{content:"";position:absolute;left:.8rem;top:1.7rem;bottom:.1rem;width:2px;background:var(--primary-light);}
.sa-tl-dot{width:1.65rem;height:1.65rem;border-radius:50%;flex:none;display:grid;place-items:center;background:var(--primary-light);color:var(--primary);}
.sa-tl-dot.good{background:var(--success-soft);color:var(--success);}
.sa-tl-dot.bad{background:var(--danger-soft);color:var(--danger);}
.sa-tl-dot.blue{background:var(--blue-light);color:var(--blue);}
.sa-tl-text{font-size:.86rem;color:var(--text);line-height:1.35;padding-top:.15rem;}
.sa-tl-text small{display:block;color:var(--muted);font-size:.74rem;margin-top:.1rem;}
.sa-empty{text-align:center;padding:1.8rem 1.2rem;background:var(--primary-soft);border:1px dashed var(--border-strong);border-radius:var(--radius-lg);}
.sa-empty .ic{width:3rem;height:3rem;border-radius:16px;margin:0 auto .7rem;display:grid;place-items:center;background:#fff;color:var(--primary);box-shadow:var(--shadow-sm);}
.sa-empty .t{font-weight:700;color:var(--text);font-size:1rem;}
.sa-empty .m{color:var(--muted);font-size:.88rem;margin:.3rem auto 0;max-width:420px;line-height:1.5;}
.sa-note{display:flex;gap:.75rem;align-items:flex-start;padding:.7rem .75rem;border-radius:14px;transition:background .18s ease;}
.sa-note:hover{background:var(--primary-soft);}
.sa-note .ic{width:2.2rem;height:2.2rem;border-radius:11px;flex:none;display:grid;place-items:center;background:var(--blue-light);color:var(--blue);}
.sa-note .t{font-weight:650;font-size:.9rem;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sa-note .p{font-size:.8rem;color:var(--muted);margin-top:.1rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.sa-note .w{font-size:.72rem;color:var(--faint);margin-top:.2rem;}
.sa-note>div{min-width:0;}

/* ---------- documents ---------- */
[class*="st-key-sa_doc_"]{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1rem .8rem;box-shadow:var(--shadow-sm);transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;height:100%;}
[class*="st-key-sa_doc_"]:hover{transform:translateY(-2px);box-shadow:var(--shadow);}
[class*="st-key-sa_doc_sel"]{border-color:var(--primary);box-shadow:0 0 0 3px rgba(109,74,255,.14),var(--shadow);}
.sa-doc{display:flex;gap:.75rem;align-items:flex-start;}
.sa-doc .ic{width:2.6rem;height:2.6rem;border-radius:12px;flex:none;display:grid;place-items:center;background:var(--primary-light);color:var(--primary);}
.sa-doc .n{font-weight:650;color:var(--text);font-size:.92rem;word-break:break-word;line-height:1.3;}
.sa-doc .m{font-size:.76rem;color:var(--muted);margin-top:.2rem;}
.sa-doc-tags{display:flex;flex-wrap:wrap;gap:.3rem;margin:.6rem 0 .1rem;}
.sa-doc-tags span{font-size:.7rem;background:var(--primary-soft);color:var(--primary-dark);border-radius:999px;padding:.12rem .5rem;}
[class*="st-key-sa_attach"]{margin:0 0 .8rem;}
[class*="st-key-sa_attach"] [data-testid="stPopover"] button{border-radius:14px!important;border:1.5px dashed rgba(109,74,255,.45)!important;background:var(--primary-soft)!important;color:var(--primary-dark)!important;font-weight:600!important;}
[class*="st-key-sa_attach"] [data-testid="stPopover"] button:hover{background:var(--primary-light)!important;border-style:solid!important;}

/* ---------- review flashcard ---------- */
.sa-flash{position:relative;overflow:hidden;background:var(--grad);color:#fff;border-radius:var(--radius-xl);padding:2.4rem 1.8rem;text-align:center;box-shadow:0 20px 50px rgba(91,80,255,.28);margin:.4rem 0 1rem;animation:saPop .35s ease both;}
.sa-flash::after{content:"";position:absolute;inset:auto -80px -120px auto;width:300px;height:300px;border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.25),transparent 65%);}
.sa-flash .count{font-size:.78rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;opacity:.85;}
.sa-flash .c{font-size:clamp(1.5rem,4vw,2.2rem);font-weight:800;letter-spacing:-.03em;margin:.6rem 0 .3rem;line-height:1.2;}
.sa-flash .s{font-size:.9rem;opacity:.88;}
.sa-flash .prompt{margin:1.1rem auto 0;max-width:460px;font-size:.92rem;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);border-radius:14px;padding:.7rem .9rem;}
[class*="st-key-sa_grades"] button{min-height:2.8rem;}

/* ---------- learn / tutor ---------- */
[class*="st-key-sa_composer"] [data-testid="stForm"]{border-radius:var(--radius-xl)!important;padding:1.1rem 1.2rem!important;box-shadow:var(--shadow-lg);}
[class*="st-key-sa_composer"] [data-testid="stTextInput"] div[data-baseweb="input"]{border-radius:16px!important;min-height:3.1rem;background:var(--primary-soft)!important;border-color:transparent!important;}
[class*="st-key-sa_composer"] [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within{background:#fff!important;border-color:var(--primary)!important;}
[class*="st-key-sa_composer"] input{font-size:1rem!important;}
[class*="st-key-suggest_"] button,[class*="st-key-sa_suggest"] button{border-radius:999px!important;font-weight:500!important;font-size:.86rem!important;background:#fff!important;}
.sa-hero{animation:saFadeUp .5s ease both;}
.sa-badge{display:inline-flex;align-items:center;gap:.35rem;padding:.28rem .7rem;border-radius:999px;background:var(--primary-light);color:var(--primary-dark);font-weight:650;font-size:.72rem;letter-spacing:.05em;}
.sa-title{font-size:clamp(1.9rem,4.6vw,2.7rem);font-weight:800;line-height:1.08;letter-spacing:-.035em;margin:.6rem 0 .45rem;background:linear-gradient(90deg,#2A1C7A,#6D4AFF 60%,#4F7BFF);-webkit-background-clip:text;background-clip:text;color:transparent;}
.sa-sub{color:var(--muted);font-size:1rem;margin:0 0 .9rem;line-height:1.55;}
.sa-chips{display:flex;flex-wrap:wrap;gap:.45rem;}
.sa-chip{display:inline-flex;align-items:center;gap:.35rem;padding:.3rem .7rem;border-radius:999px;background:#fff;border:1px solid var(--border);color:var(--text);font-weight:550;font-size:.84rem;box-shadow:var(--shadow-sm);}
.sa-chip.good{background:var(--success-soft);border-color:rgba(19,138,75,.2);color:#0E6B3A;}
.sa-chip.warn{background:var(--warning-soft);border-color:rgba(180,83,9,.2);color:#8A4108;}
.sa-float{display:inline-block;animation:saFloat 3s ease-in-out infinite;}
.sa-stepper{display:flex;gap:.3rem;align-items:center;flex-wrap:wrap;background:var(--surface);backdrop-filter:blur(14px);border:1px solid var(--glass-border);border-radius:999px;padding:.4rem .5rem;box-shadow:var(--shadow);}
.sa-step{display:flex;align-items:center;gap:.4rem;padding:.32rem .7rem;border-radius:999px;font-weight:600;font-size:.82rem;color:var(--faint);transition:all .3s ease;}
.sa-step .dot{width:1.55rem;height:1.55rem;border-radius:50%;display:grid;place-items:center;background:var(--primary-soft);font-size:.74rem;}
.sa-step.done{color:var(--primary-dark);}
.sa-step.done .dot{background:var(--primary-light);}
.sa-step.active{background:var(--grad);color:#fff;animation:saPulse 2s infinite;}
.sa-step.active .dot{background:rgba(255,255,255,.25);}
.sa-arrow{color:var(--border-strong);font-weight:700;}
.sa-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:1.05rem 1.15rem;box-shadow:var(--shadow-sm);animation:saFadeUp .45s ease both;transition:transform .2s ease,box-shadow .2s ease;}
.sa-card:hover{transform:translateY(-2px);box-shadow:var(--shadow);}
.sa-card h4{margin:0 0 .45rem;color:var(--primary-dark);font-size:.95rem;font-weight:700;display:flex;align-items:center;gap:.45rem;}
.sa-card p{margin:0;color:var(--text);line-height:1.65;font-size:.94rem;}
.sa-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:.9rem;margin:.4rem 0 1rem;}
.sa-analogy{background:var(--grad-soft);border:1px dashed rgba(109,74,255,.35);}
.sa-simpler{border-left:4px solid var(--amber);}
.sa-topic{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;}
.sa-topic .name{font-size:1.4rem;font-weight:800;letter-spacing:-.025em;color:var(--text);margin-top:.35rem;}
.sa-flip-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin:.4rem 0 1rem;}
.sa-flip{perspective:1000px;height:230px;outline:none;cursor:pointer;animation:saFadeUp .45s ease both;border-radius:var(--radius-lg);}
.sa-flip-inner{position:relative;width:100%;height:100%;transition:transform .7s cubic-bezier(.2,.8,.2,1);transform-style:preserve-3d;}
.sa-flip:hover .sa-flip-inner,.sa-flip:focus .sa-flip-inner,.sa-flip:focus-within .sa-flip-inner{transform:rotateY(180deg);}
.sa-face{position:absolute;inset:0;border-radius:var(--radius-lg);padding:1.1rem;backface-visibility:hidden;-webkit-backface-visibility:hidden;box-shadow:var(--shadow);display:flex;flex-direction:column;}
.sa-front{background:var(--grad);color:#fff;justify-content:center;align-items:center;text-align:center;}
.sa-front .num{font-size:2.6rem;font-weight:800;letter-spacing:-.03em;opacity:.9;}
.sa-front .ttl{font-weight:700;font-size:1.02rem;margin-top:.5rem;}
.sa-front .hint{font-size:.74rem;opacity:.82;margin-top:.6rem;}
.sa-back{background:#fff;border:1px solid var(--border-strong);color:var(--text);transform:rotateY(180deg);overflow-y:auto;line-height:1.55;font-size:.92rem;}
.sa-back b{color:var(--primary-dark);margin-bottom:.35rem;}
.sa-quiz-intro{display:flex;align-items:center;gap:.9rem;background:var(--grad-soft);border:1px solid var(--border);border-radius:var(--radius);padding:.85rem 1rem;margin-bottom:.9rem;}
.sa-quiz-intro .big{width:2.7rem;height:2.7rem;flex:none;border-radius:14px;display:grid;place-items:center;background:var(--grad);color:#fff;font-size:1.2rem;font-weight:800;}
.sa-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;margin:.6rem 0;}
.sa-tile{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:.9rem;text-align:center;box-shadow:var(--shadow-sm);animation:saPop .4s ease both;}
.sa-tile .num{font-size:1.8rem;font-weight:800;letter-spacing:-.03em;color:var(--primary-dark);}
.sa-tile .lbl{font-size:.72rem;font-weight:650;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;}
.sa-tile.bad .num{color:var(--danger);}
.sa-banner{border-radius:14px;padding:.85rem 1.05rem;font-weight:600;margin:.6rem 0;animation:saPop .35s ease both;}
.sa-banner.pass{background:var(--success-soft);border:1px solid rgba(19,138,75,.25);color:#0E6B3A;}
.sa-banner.retry{background:var(--warning-soft);border:1px solid rgba(180,83,9,.25);color:#8A4108;}
.sa-banner.stop{background:var(--danger-soft);border:1px solid rgba(194,51,77,.25);color:#9B2439;}
.sa-label{font-weight:700;color:var(--primary-dark);margin:.8rem 0 .35rem;font-size:.84rem;}
.sa-result{border-radius:14px;padding:.8rem 1rem;margin:.5rem 0;background:#fff;border:1px solid var(--border);border-left:4px solid var(--success);}
.sa-result.wrong{border-left-color:var(--danger);}
.sa-result .q{font-weight:650;margin-bottom:.3rem;color:var(--text);}
.sa-result .icon{display:inline-block;margin-right:.45rem;padding:.08rem .5rem;border-radius:999px;font-size:.68rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;vertical-align:.1rem;background:var(--success-soft);color:var(--success);}
.sa-result.wrong .icon{background:var(--danger-soft);color:var(--danger);}
.sa-result .ans{font-size:.9rem;line-height:1.55;color:var(--text);}
.sa-result .why{font-size:.85rem;color:var(--muted);margin-top:.3rem;}
.sa-next{position:relative;border-radius:var(--radius-lg);padding:1.5px;background:var(--grad);box-shadow:0 14px 40px rgba(91,80,255,.2);animation:saPop .4s ease both;}
.sa-next-inner{position:relative;background:#fff;border-radius:calc(var(--radius-lg) - 1.5px);padding:1.15rem 1.25rem;}
.sa-next .kicker{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--primary);}
.sa-next .topic{font-size:1.45rem;font-weight:800;letter-spacing:-.025em;color:var(--text);margin:.2rem 0 .5rem;}
.sa-transcript{display:flex;flex-direction:column;gap:.7rem;margin:.6rem 0 1rem;}
.sa-msg{border-radius:18px;padding:.8rem 1rem;box-shadow:var(--shadow-sm);max-width:85%;}
.sa-msg.user{background:var(--grad);color:#fff;margin-left:auto;border-bottom-right-radius:6px;}
.sa-msg.user .sa-msg-label,.sa-msg.user .sa-msg-body{color:#fff;}
.sa-msg.assistant{background:#fff;border:1px solid var(--border);margin-right:auto;border-bottom-left-radius:6px;}
.sa-msg-label{font-size:.68rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--primary);margin-bottom:.3rem;}
.sa-msg-body{color:var(--text);line-height:1.6;font-size:.92rem;}

/* ---------- data bits ---------- */
.sa-bar{display:flex;align-items:center;gap:.7rem;margin:.45rem 0;}
.sa-bar .lbl{flex:0 0 auto;min-width:9rem;max-width:45%;font-weight:550;font-size:.88rem;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sa-bar .track{flex:1;height:.5rem;border-radius:999px;background:var(--primary-light);overflow:hidden;}
.sa-bar .fill{display:block;height:100%;border-radius:999px;background:var(--grad);animation:saGrowBar .7s ease both;}
.sa-bar .val{flex:0 0 auto;font-weight:700;font-size:.82rem;color:var(--primary-dark);min-width:2.6rem;text-align:right;}
.sa-bar.weak .fill{background:linear-gradient(90deg,#E0567A,#F08BA0);}
.sa-bar.learning .fill{background:linear-gradient(90deg,#E89B2C,#F5C46E);}
.sa-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.8rem;margin:.5rem 0 1rem;}
.sa-metric{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:.9rem 1rem;box-shadow:var(--shadow-sm);transition:transform .2s ease,box-shadow .2s ease;}
.sa-metric:hover{transform:translateY(-2px);box-shadow:var(--shadow);}
.sa-metric .v{font-size:1.45rem;font-weight:800;letter-spacing:-.03em;color:var(--text);line-height:1.15;word-break:break-word;}
.sa-metric .k{font-size:.72rem;font-weight:650;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-top:.2rem;}
.sa-metric .sub{font-size:.76rem;color:var(--muted);margin-top:.15rem;}
.sa-metric.warn .v{color:var(--danger);}
.sa-pill{display:inline-block;padding:.12rem .55rem;border-radius:999px;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;}
.sa-pill.mastered{background:var(--success-soft);color:#0E6B3A;}
.sa-pill.proficient{background:var(--blue-light);color:#2A55C9;}
.sa-pill.learning{background:var(--warning-soft);color:#8A4108;}
.sa-pill.weak,.sa-pill.critical{background:var(--danger-soft);color:#9B2439;}
.sa-pill.unknown{background:#F0EFF5;color:#5F5D72;}
.sa-pill.high{background:#FFE9DA;color:#9A4A12;}
.sa-pill.medium{background:var(--warning-soft);color:#8A4108;}
.sa-pill.low{background:var(--primary-light);color:var(--primary-dark);}
.sa-due .sa-pill{flex:0 0 auto;min-width:4.6rem;text-align:center;}
.sa-cite{background:var(--primary-soft);border-left:3px solid var(--primary);border-radius:0 12px 12px 0;padding:.5rem .8rem;margin:.3rem 0;font-size:.82rem;color:var(--text);}
.sa-cite b{color:var(--primary-dark);}
.sa-due{display:flex;align-items:center;gap:.6rem;background:#fff;border:1px solid var(--border);border-radius:12px;padding:.55rem .8rem;margin:.35rem 0;transition:border-color .18s ease;}
.sa-due:hover{border-color:var(--border-strong);}
.sa-due .nm{font-weight:600;flex:1;font-size:.9rem;color:var(--text);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.sa-due span:last-child{color:var(--muted);}
.sa-sandbox{border-radius:12px;padding:.6rem .9rem;font-size:.82rem;margin:.4rem 0 .9rem;}
.sa-sandbox.docker{background:var(--success-soft);border:1px solid rgba(19,138,75,.22);color:#0E6B3A;}
.sa-sandbox.subprocess{background:var(--warning-soft);border:1px solid rgba(180,83,9,.22);color:#8A4108;}
.sa-sandbox.disabled,.sa-sandbox.unavailable{background:var(--danger-soft);border:1px solid rgba(194,51,77,.22);color:#9B2439;}
[class*="st-key-planrow_"],[class*="st-key-plan_"]{background:#fff;border:1px solid var(--border);border-radius:14px;padding:.55rem .8rem;margin:.3rem 0;}
[class*="st-key-concept_"]{background:#fff;border:1px solid var(--border);border-radius:14px;padding:.6rem .9rem;margin:.4rem 0;}

/* ---------- login ---------- */
.sa-login{max-width:520px;margin:4vh auto 0;text-align:center;animation:saFadeUp .5s ease both;}
.sa-login .sa-brand{justify-content:center;padding-bottom:.4rem;}
.sa-login .sa-title{margin-top:.6rem;}
.sa-login p.tag{color:var(--muted);font-size:1.02rem;margin:.1rem 0 1.4rem;}
.sa-login .panel{background:var(--glass);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:var(--radius-xl);padding:1.7rem 1.5rem;box-shadow:var(--shadow-lg);}
.sa-google-btn{display:inline-flex;align-items:center;justify-content:center;gap:.65rem;padding:.8rem 1.5rem;border-radius:14px;background:var(--grad);color:#fff!important;font-weight:650;text-decoration:none!important;box-shadow:0 10px 26px rgba(109,74,255,.32);transition:transform .16s ease,box-shadow .2s ease;}
.sa-google-btn:hover{transform:scale(1.02);box-shadow:0 14px 30px rgba(109,74,255,.38);}
.sa-google-btn:focus-visible{box-shadow:var(--ring),0 10px 26px rgba(109,74,255,.32)!important;}
.sa-google-btn .g{width:1.4rem;height:1.4rem;border-radius:50%;background:#fff;display:grid;place-items:center;font-weight:800;color:var(--primary);font-size:.85rem;}
.sa-login .note{font-size:.82rem;color:var(--muted);margin-top:1rem;line-height:1.5;}
.sa-login .perms{display:flex;gap:.45rem;justify-content:center;flex-wrap:wrap;margin-top:1.1rem;}

/* ---------- neumorphism layer ----------
   Surfaces share the canvas colour and are shaped only by light: raised elements carry a
   white highlight top-left and a lavender shadow bottom-right; pressed ones (inputs, tracks,
   the active nav item, a chosen answer) sink in with inset shadows. The violet gradient is
   kept for primary actions and the AI card so they still read as the main thing to press. */
.stApp{background:radial-gradient(900px 520px at 6% -8%,rgba(141,110,255,.08),transparent 60%),radial-gradient(760px 480px at 100% 4%,rgba(79,123,255,.06),transparent 60%),var(--neu-bg)!important;}
[data-testid="stSidebar"]{background:var(--neu-bg)!important;backdrop-filter:none;-webkit-backdrop-filter:none;border-right:none;box-shadow:6px 0 18px var(--neu-dark);}
[class*="st-key-sa_header"],[class*="st-key-sa_hero"],[class*="st-key-sa_panel"],[class*="st-key-sa_plan_card"],[data-testid="stForm"],.sa-login .panel{background:var(--neu-bg)!important;backdrop-filter:none;-webkit-backdrop-filter:none;border:none!important;box-shadow:var(--neu-raised)!important;}
[class*="st-key-sa_hero"]{box-shadow:var(--neu-raised-lg)!important;}
[class*="st-key-sa_hero"]::after{background:radial-gradient(circle,rgba(109,74,255,.12),transparent 65%);}
.sa-stat,.sa-card,.sa-metric,.sa-tile,.sa-user,.sa-quiz-intro,.sa-stepper,.sa-result,[class*="st-key-sa_cont_"],[class*="st-key-sa_doc_"],[class*="st-key-qcard"],[class*="st-key-docq_"],[data-testid="stExpander"] details,[class*="st-key-planrow_"],[class*="st-key-plan_"],[class*="st-key-concept_"]{background:var(--neu-bg)!important;backdrop-filter:none;-webkit-backdrop-filter:none;border:none!important;box-shadow:var(--neu-raised-sm)!important;}
.sa-result{border-left:4px solid var(--success)!important;}.sa-result.wrong{border-left-color:var(--danger)!important;}
.sa-simpler{border-left:4px solid var(--amber)!important;}
.sa-stat:hover,.sa-card:hover,.sa-metric:hover,[class*="st-key-sa_cont_"]:hover,[class*="st-key-sa_doc_"]:hover,[class*="st-key-qcard"]:hover,[class*="st-key-docq_"]:hover{box-shadow:var(--neu-raised)!important;}
[class*="st-key-sa_doc_sel"]{box-shadow:var(--neu-inset)!important;}
.sa-analogy{background:var(--neu-bg)!important;box-shadow:var(--neu-inset)!important;}
.sa-due,.sa-chip,.sa-stat .ic,.sa-doc .ic,.sa-note .ic,.sa-empty .ic,.sa-tl-dot,.sa-step .dot,.sa-head-avatar img,.sa-head-avatar .avatar{border:none!important;box-shadow:var(--neu-raised-sm)!important;}
.sa-due,.sa-chip{background:var(--neu-bg)!important;}
.sa-due:hover{box-shadow:var(--neu-raised)!important;}
.sa-note:hover{background:transparent;box-shadow:var(--neu-inset-sm);}
.sa-empty,.sa-hist-empty,.sa-cite,.sa-doc-tags span,.sa-cont .subj,.sa-badge{background:var(--neu-bg)!important;border:none!important;box-shadow:var(--neu-inset-sm);}
.sa-empty{box-shadow:var(--neu-inset);}
.sa-brand .logo,.sa-quiz-intro .big,.sa-step.active{box-shadow:var(--neu-accent)!important;}
.sa-mini,.sa-cont .track,.sa-bar .track,[data-testid="stProgress"] div[role="progressbar"]>div>div{background:var(--neu-bg)!important;box-shadow:var(--neu-inset-sm);}
.sa-mini,.sa-cont .track{height:7px;}
/* inputs are wells pressed into the surface */
div[data-baseweb="input"],div[data-baseweb="textarea"],div[data-baseweb="select"]>div,[data-testid="stNumberInput"] div[data-baseweb="input"],[data-testid="stDateInput"] div[data-baseweb="input"],[class*="st-key-sa_search"] div[data-baseweb="input"],[class*="st-key-sa_composer"] [data-testid="stTextInput"] div[data-baseweb="input"]{background:var(--neu-bg)!important;border-color:transparent!important;box-shadow:var(--neu-inset)!important;}
div[data-baseweb="input"] input,div[data-baseweb="textarea"] textarea,div[data-baseweb="select"] div{background:transparent!important;}
div[data-baseweb="input"]:focus-within,div[data-baseweb="textarea"]:focus-within,div[data-baseweb="select"]>div:focus-within,[class*="st-key-sa_search"] div[data-baseweb="input"]:focus-within,[class*="st-key-sa_composer"] [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within{background:var(--neu-bg)!important;border-color:transparent!important;box-shadow:var(--neu-inset),var(--ring)!important;}
[data-testid="stFileUploaderDropzone"]{background:var(--neu-bg)!important;border:1.5px dashed rgba(109,74,255,.35)!important;box-shadow:var(--neu-inset)!important;}
/* buttons: raised at rest, pressed while held */
button[data-testid="stBaseButton-secondary"],button[data-testid="stBaseButton-secondaryFormSubmit"],[data-testid="stPopover"] button,[class*="st-key-sa_attach"] [data-testid="stPopover"] button{background:var(--neu-bg)!important;border:none!important;box-shadow:var(--neu-raised-sm)!important;}
button[data-testid="stBaseButton-secondary"]:hover,button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,[data-testid="stPopover"] button:hover{background:var(--neu-bg)!important;box-shadow:var(--neu-raised)!important;transform:none;}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{box-shadow:var(--neu-accent)!important;}
button[data-testid^="stBaseButton"]:hover{transform:none;}
button[data-testid^="stBaseButton"]:active{transform:none;box-shadow:var(--neu-inset)!important;}
button[data-testid="stBaseButton-primary"]:active,button[data-testid="stBaseButton-primaryFormSubmit"]:active{box-shadow:inset 4px 4px 10px rgba(40,20,140,.35),inset -3px -3px 8px rgba(255,255,255,.25)!important;}
button:disabled{box-shadow:var(--neu-inset-sm)!important;}
/* navigation: the current page sits pressed in */
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-tertiary"]:hover{background:var(--neu-bg)!important;box-shadow:var(--neu-raised-sm)!important;}
[class*="st-key-sa_navgroup"] button[data-testid="stBaseButton-primary"],[class*="st-key-histitem"] button[data-testid="stBaseButton-primary"]{background:var(--neu-bg)!important;box-shadow:var(--neu-inset)!important;}
[class*="st-key-histitem"] button[data-testid="stBaseButton-secondary"]{box-shadow:none!important;}
[class*="st-key-histitem"]:hover button[data-testid="stBaseButton-secondary"]{background:var(--neu-bg)!important;box-shadow:var(--neu-raised-sm)!important;}
/* answers: raised choices, the picked one pressed */
[data-testid="stRadioOption"],[data-testid="stRadio"] label[data-baseweb="radio"]{background:var(--neu-bg)!important;border:1.5px solid transparent;box-shadow:var(--neu-raised-sm);}
[data-testid="stRadioOption"]:hover,[data-testid="stRadio"] label[data-baseweb="radio"]:hover{background:var(--neu-bg)!important;box-shadow:var(--neu-raised);}
[data-testid="stRadioOption"]:has(input:checked),[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked){background:var(--neu-bg)!important;border-color:rgba(109,74,255,.55);box-shadow:var(--neu-inset);}
[data-testid="stTabs"] [role="tablist"]{gap:.4rem;}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"]{box-shadow:var(--neu-inset-sm);border-radius:10px;}
[class*="st-key-sa_ai_card"],.sa-flash{box-shadow:10px 10px 26px rgba(91,80,255,.35),-10px -10px 24px var(--neu-light)!important;}
/* on the violet card the same idea works in its own colours: soft-lit glass chips */
[class*="st-key-sa_ai_card"] button[data-testid^="stBaseButton"]{background:rgba(255,255,255,.14)!important;color:#fff!important;border:1px solid rgba(255,255,255,.28)!important;box-shadow:4px 4px 10px rgba(40,20,140,.28),-3px -3px 8px rgba(255,255,255,.14)!important;}
[class*="st-key-sa_ai_card"] button[data-testid^="stBaseButton"]:hover{background:rgba(255,255,255,.22)!important;}
[class*="st-key-sa_ai_card"] button[data-testid^="stBaseButton"]:active{box-shadow:inset 3px 3px 8px rgba(40,20,140,.35),inset -2px -2px 6px rgba(255,255,255,.18)!important;}
[data-testid="stAlert"]{border:none;box-shadow:var(--neu-inset-sm);}

/* ---------- responsive ---------- */
@media (max-width:1024px){.block-container,[data-testid="stMainBlockContainer"]{padding-left:1.4rem;padding-right:1.4rem;}.sa-stats{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media (max-width:640px){
.block-container,[data-testid="stMainBlockContainer"]{padding:2.8rem 1rem 3rem;}
.sa-stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem;}
.sa-stat{padding:.85rem;}.sa-stat .v{font-size:1.35rem;}
[class*="st-key-sa_hero"]{padding:1.3rem 1.2rem 1.1rem;border-radius:var(--radius-lg);}
[class*="st-key-sa_header"]{padding:.7rem .8rem;}
.sa-head-avatar{display:none;}
.sa-tiles{grid-template-columns:repeat(3,minmax(0,1fr));}.sa-tile .num{font-size:1.4rem;}
.sa-stepper{border-radius:16px;}.sa-arrow{display:none;}
.sa-bar .lbl{min-width:6.5rem;}
.sa-msg{max-width:100%;}
.sa-flash{padding:1.8rem 1.2rem;}
}
@media (max-width:400px){.sa-stat .top{font-size:.76rem;}.sa-stat .ic{width:1.7rem;height:1.7rem;}}
@media (max-width:340px){.sa-stats{grid-template-columns:1fr;}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;}}
</style>
"""
# Inject the global CSS into the page once per rerun.
def inject_styles() -> None:
    st.html(GLOBAL_CSS)
