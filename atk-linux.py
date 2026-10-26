#!/usr/bin/env python3
"""Painel do Attack Shark X11 para Linux. Usa o mousectl por baixo.
Uso:  python3 atk-linux.py            abre o painel
      python3 atk-linux.py --instalar cria o atalho no menu de aplicativos
"""
import json, os, secrets, shutil, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOME = os.path.expanduser("~")
MC = shutil.which("mousectl") or os.path.join(HOME, ".local/bin/mousectl")
TOKEN = secrets.token_urlsafe(16)
ping = [0.0]
ASSETS = os.path.join(HOME, ".local/share/atk-linux")
PROFILES = os.path.join(HOME, ".config/atk-linux/profiles.json")


def load_profiles():
    try:
        return json.load(open(PROFILES, encoding="utf-8"))
    except Exception:
        return {}


def save_profiles(d):
    os.makedirs(os.path.dirname(PROFILES), exist_ok=True)
    json.dump(d, open(PROFILES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def asset(name):
    if os.path.isdir(ASSETS):
        for f in sorted(os.listdir(ASSETS), key=lambda x: not x.endswith(".svg")):
            if f.startswith(name + "."):
                return os.path.join(ASSETS, f)


def run(args):
    try:
        p = subprocess.run([MC] + args, capture_output=True, text=True, timeout=20)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)


def get_state():
    rc, out, err = run(["status", "--json"])
    try:
        d = json.loads(out)
        return d["mice"][0] if d.get("mice") else {"none": True}
    except Exception:
        return {"error": {"message": (err or out or "mousectl não respondeu").strip()}}


def set_value(key, value):
    if isinstance(value, bool):
        vals = ["on", "true", "1"] if value else ["off", "false", "0"]
    else:
        vals = [str(value)]
    err = ""
    for v in vals:
        for argv in (["set", key, v], ["set", key + "=" + v]):
            rc, out, e = run(argv)
            if rc == 0:
                return {"ok": True}
            err = (e or out).strip()
            if "permission" in err.lower():
                return {"ok": False, "error": err}
    return {"ok": False, "error": err}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def ok(self):
        return self.headers.get("Host", "").startswith("127.0.0.1") and \
            self.headers.get("X-Token") == TOKEN

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/asset/mouse", "/asset/logo", "/asset/logo-dark") and self.headers.get("Host", "").startswith("127.0.0.1"):
            f = asset("atk-" + path.split("/")[-1])
            if not f:
                return self.send(404, "")
            ext = f.rsplit(".", 1)[-1].lower()
            ct = {"svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
            return self.send(200, open(f, "rb").read(), ct)
        if path == "/":
            return self.send(200, HTML.replace("__TOKEN__", TOKEN), "text/html")
        if not self.ok():
            return self.send(403, "{}")
        if path == "/api/ping":
            ping[0] = time.time()
            return self.send(200, "{}")
        if path == "/api/profiles":
            return self.send(200, json.dumps(load_profiles()))
        if path == "/api/state":
            return self.send(200, json.dumps(get_state()))
        self.send(404, "{}")

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.ok():
            return self.send(403, "{}")
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n) or b"{}")
        if path == "/api/set":
            return self.send(200, json.dumps(set_value(d["key"], d["value"])))
        if path == "/api/profile":
            p = load_profiles()
            p[d["name"]] = d["settings"]
            save_profiles(p)
            return self.send(200, json.dumps({"ok": True}))
        if path == "/api/profile/delete":
            p = load_profiles()
            p.pop(d["name"], None)
            save_profiles(p)
            return self.send(200, json.dumps({"ok": True}))
        if path == "/api/apply":
            falhas = [k for k, v in d["settings"].items() if not set_value(k, v)["ok"]]
            return self.send(200, json.dumps({"ok": not falhas, "falhas": falhas}))
        self.send(404, "{}")


def instalar():
    dest = os.path.join(HOME, ".local/bin/atk-linux")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy(os.path.abspath(__file__), dest)
    os.chmod(dest, 0o755)
    os.makedirs(ASSETS, exist_ok=True)
    for d in (os.path.dirname(os.path.abspath(__file__)), os.path.join(HOME, "Downloads")):
        for f in os.listdir(d):
            if f.startswith(("atk-logo.", "atk-logo-dark.", "atk-mouse.")):
                shutil.copy(os.path.join(d, f), os.path.join(ASSETS, f))
    logo = asset("atk-logo")
    apps = os.path.join(HOME, ".local/share/applications")
    os.makedirs(apps, exist_ok=True)
    with open(os.path.join(apps, "atk-linux.desktop"), "w") as f:
        f.write("[Desktop Entry]\nType=Application\nName=Attack Shark X11\n"
                "Comment=Configurar o mouse Attack Shark X11\n"
                f"Exec=python3 {dest}\nIcon={logo or 'input-mouse'}\nTerminal=false\n"
                "Categories=Utility;Settings;\n")
    for velho in (os.path.join(HOME, ".local/bin/atk-linux-v2"), os.path.join(apps, "atk-linux-v2.desktop")):
        if os.path.exists(velho):
            os.remove(velho)
    print("Pronto. Procure 'Attack Shark X11' no menu de aplicativos.")


def main():
    if "--instalar" in sys.argv:
        return instalar()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", 47821), H)
    except OSError:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    start = time.time()

    def watchdog():
        while True:
            time.sleep(3)
            if ping[0] and time.time() - ping[0] > 20:
                os._exit(0)
            if not ping[0] and time.time() - start > 60:
                os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    for b in ("brave-browser", "google-chrome", "chromium", "chromium-browser", "brave"):
        p = shutil.which(b)
        if p:
            subprocess.Popen([p, f"--app={url}", "--window-size=980,700"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
    else:
        webbrowser.open(url)
    srv.serve_forever()


HTML = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Attack Shark X11</title><link rel="icon" href="/asset/logo"><script>document.documentElement.dataset.theme=localStorage.getItem('th')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');document.documentElement.classList.toggle('nospl',localStorage.getItem('spl')===new Date().toDateString())</script>
<style>
:root{--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mut:#86868b;--line:rgba(0,0,0,.08);--hot:#ff6a13;--ok:#34c759;--bad:#ff3b30;--ac:#0a7aff;--side:rgba(246,246,248,.7);--hov:rgba(0,0,0,.05);--off:#e3e3e8;--fld:#ececf0;--sh:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.06);--glass:rgba(255,255,255,.62)}
[data-theme=dark]{--bg:#000;--card:#1c1c1e;--ink:#f5f5f7;--mut:#98989d;--line:rgba(255,255,255,.1);--ac:#0a84ff;--side:rgba(28,28,30,.7);--hov:rgba(255,255,255,.07);--off:#39393d;--fld:#2c2c2e;--sh:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);--glass:rgba(44,44,46,.6)}
*{box-sizing:border-box}
body{margin:0;display:flex;height:100vh;color:var(--ink);font:14px/1.45 -apple-system,"SF Pro Text","Inter","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased;background:radial-gradient(700px 480px at 0 0,color-mix(in srgb,var(--hot) 16%,transparent),transparent) fixed,var(--bg)}
aside{width:232px;background:var(--side);-webkit-backdrop-filter:saturate(180%) blur(30px);backdrop-filter:saturate(180%) blur(30px);border-right:1px solid var(--line);padding:22px 12px;display:flex;flex-direction:column;gap:3px}
.logo{display:flex;align-items:center;margin:0 10px 18px;font-weight:700;font-size:15px}.logo img{height:26px;max-width:150px}.logo img.inv,#spl img.inv{filter:brightness(0) invert(1)}
.dev{background:var(--card);border-radius:12px;padding:11px 13px;margin-bottom:12px;font-size:12px;color:var(--mut);box-shadow:var(--sh)}.dev b{display:block;font-size:14px;font-weight:600;color:var(--ink)}
nav button{all:unset;display:flex;align-items:center;gap:10px;width:100%;padding:7px 10px;border-radius:9px;cursor:pointer;font-weight:500;transition:background .15s,transform .12s}
nav button:hover{background:var(--hov)}nav button:active{transform:scale(.97)}nav button.on{background:var(--ac);color:#fff}
.ic{width:24px;height:24px;border-radius:6px;display:grid;place-items:center;flex:none}.ic svg{width:15px;height:15px}
:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
main{flex:1;overflow:auto;padding:30px 38px}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:16px}
header h2{margin:0;font-size:30px;font-weight:700;letter-spacing:-.025em}header small{color:var(--mut);font-size:13px}
.bat,.tg{display:flex;align-items:center;gap:10px;height:34px;padding:0 14px;border-radius:980px;background:var(--card);box-shadow:var(--sh);font-weight:500;font-variant-numeric:tabular-nums}
.tg{all:unset;display:flex;align-items:center;justify-content:center;height:34px;padding:0 16px;border-radius:980px;background:var(--card);box-shadow:var(--sh);font-weight:500;cursor:pointer;transition:transform .12s}
.tg:active,.btn:active{transform:scale(.95)}.sv{background:var(--ac);color:#fff}
#tg{width:34px;padding:0}#tg svg{width:16px;height:16px;fill:currentColor;stroke:currentColor;stroke-width:0}
[data-theme=dark] .i-moon,html:not([data-theme=dark]) .i-sun{display:none}
.bar{position:relative;width:46px;height:16px;border:1.5px solid var(--mut);border-radius:5px;padding:1px}
.bar::after{content:"";position:absolute;right:-5px;top:3px;width:3px;height:6px;background:var(--mut);border-radius:0 2px 2px 0}
.bar b{display:block;height:100%;background:var(--ok);border-radius:3px;animation:fill 1s ease backwards}
.bolt{position:absolute;left:50%;top:50%;width:13px;height:13px;transform:translate(-50%,-50%);fill:#fff;stroke:#14171c;stroke-width:1.4;stroke-linejoin:round;animation:pop .4s ease backwards}
.card{background:var(--card);border-radius:16px;box-shadow:var(--sh);padding:4px 20px}
.row{display:flex;align-items:center;gap:14px;padding:12px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}
.row>label,.row>b{width:160px;flex:none;font-weight:500}.row small{display:block;color:var(--mut);font-size:12px;font-weight:400}
.row output{width:96px;text-align:right;color:var(--mut);font-variant-numeric:tabular-nums}.ro{color:var(--mut);margin-left:auto}
input[type=range]{-webkit-appearance:none;appearance:none;flex:1;height:28px;background:transparent;cursor:pointer}
input[type=range]::-webkit-slider-runnable-track{height:4px;border-radius:2px;background:linear-gradient(90deg,var(--ac) var(--p,0%),var(--off) var(--p,0%))}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;margin-top:-9px;border-radius:50%;background:#fff;box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 2px 6px rgba(0,0,0,.3);transition:transform .15s}
input[type=range]:active::-webkit-slider-thumb{transform:scale(1.12)}input[type=range]:disabled{opacity:.4}
input[type=color]{width:30px;height:30px;border-radius:50%;border:2px solid var(--card);box-shadow:0 0 0 1px var(--line);padding:0;background:none;cursor:pointer}
input[type=color]::-webkit-color-swatch-wrapper{padding:0}input[type=color]::-webkit-color-swatch{border:0;border-radius:50%}
input[type=radio]{accent-color:var(--ac);width:18px;height:18px}
select{padding:7px 12px;border:0;border-radius:8px;background:var(--fld);color:var(--ink);font:inherit}
.seg{display:flex;gap:2px;padding:2px;border-radius:10px;background:var(--fld)}
.seg button{all:unset;padding:6px 15px;border-radius:8px;cursor:pointer;font-weight:500;transition:background .2s,box-shadow .2s}
.seg button.on{background:var(--card);box-shadow:0 1px 3px rgba(0,0,0,.2);font-weight:600}[data-theme=dark] .seg button.on{background:#636366}
.sw{all:unset;width:46px;height:28px;border-radius:14px;background:var(--off);position:relative;cursor:pointer;flex:none;transition:background .25s}
.sw::after{content:"";position:absolute;top:2px;left:2px;width:24px;height:24px;border-radius:50%;background:#fff;box-shadow:0 2px 4px rgba(0,0,0,.3);transition:left .3s cubic-bezier(.3,1.5,.5,1)}
.sw.on{background:var(--ok)}.sw.on::after{left:20px}
.btn{all:unset;cursor:pointer;padding:7px 16px;border-radius:980px;background:var(--ac);color:#fff;font-weight:500;transition:transform .12s}.btn.ghost{background:var(--fld);color:var(--ink)}
#pn{flex:1;padding:8px 12px;border:0;border-radius:8px;background:var(--fld);color:var(--ink);font:inherit}
.stage{position:relative;height:520px;display:flex;align-items:center;justify-content:center}.stage img,.stage svg{height:470px;max-width:60%;object-fit:contain}
.co{all:unset;position:absolute;background:var(--glass);-webkit-backdrop-filter:blur(20px) saturate(180%);backdrop-filter:blur(20px) saturate(180%);border:1px solid var(--line);border-radius:16px;padding:10px 16px;box-shadow:var(--sh);cursor:pointer}
.co small{display:block;color:var(--mut);font-size:12px}.co b{font-size:17px;font-weight:600}
.ban{display:flex;justify-content:space-between;align-items:center;gap:12px;color:#14171c;background:#fff4e5;border-radius:12px;padding:12px 16px;margin-bottom:14px}
#msg{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:rgba(30,30,32,.88);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);color:#fff;padding:10px 18px;border-radius:980px;box-shadow:0 8px 30px rgba(0,0,0,.3);opacity:0;transition:opacity .2s;max-width:80%;pointer-events:none}
#msg.show{opacity:1}#msg.err{background:var(--bad)}
#spl{position:fixed;inset:0;z-index:99;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;animation:splout .4s ease 1.1s forwards}
#spl img,#spl span{height:76px;max-width:60%;font-size:34px;font-weight:800;letter-spacing:.08em;animation:spin 1s cubic-bezier(.2,1.2,.3,1) backwards}
#spl i{display:block;height:3px;width:170px;border-radius:2px;background:linear-gradient(90deg,transparent,var(--hot),transparent);animation:sweep 1.1s ease .35s backwards}
#prog{position:fixed;top:0;left:232px;right:0;height:3px;z-index:50}#prog i{display:block;height:100%;width:0;background:var(--ac);transition:width .25s}#prog[hidden]{display:none}
.nospl #spl{display:none}
@keyframes spin{from{opacity:0;transform:scale(.7);filter:blur(8px)}}@keyframes sweep{from{transform:scaleX(0);opacity:0}}@keyframes splout{to{opacity:0;visibility:hidden}}
@keyframes up{from{opacity:0;transform:translateY(10px)}}@keyframes flt{50%{transform:translateY(-8px)}}@keyframes pop{from{opacity:0;transform:scale(.85)}}@keyframes glow{0%,100%{opacity:.3;transform:scale(.95)}50%{opacity:.55;transform:scale(1.06)}}@keyframes fill{from{width:0}}
#body>*{animation:up .4s cubic-bezier(.2,.8,.2,1) backwards}
.stage::before{content:"";position:absolute;width:320px;height:320px;border-radius:50%;background:radial-gradient(circle,var(--glow,var(--hot)),transparent 68%);filter:blur(34px);animation:glow 5s ease-in-out infinite}
.stage img,.stage svg{position:relative;animation:flt 6s ease-in-out infinite}
.co{animation:pop .5s cubic-bezier(.2,1.4,.4,1) backwards;transition:transform .2s,box-shadow .2s}.co:hover{transform:translateY(-3px)}
.co:nth-child(3){animation-delay:.12s}.co:nth-child(4){animation-delay:.24s}.co:nth-child(5){animation-delay:.36s}
::view-transition-old(root),::view-transition-new(root){animation:none;mix-blend-mode:normal}::view-transition-new(root){z-index:2}
@media(prefers-reduced-motion:reduce){*,::before{animation:none!important;transition:none!important}}
@media(max-width:700px){aside{width:64px}nav button{font-size:0}.row>label,.row>b{width:90px}}
</style></head><body>
<aside><div class="logo"><img class="lg" alt="Attack Shark"></div><div class="dev" id="dev"></div><nav id="nav"></nav></aside>
<main><header><div><h2 id="ttl">Attack Shark X11</h2><small id="sub">Procurando o mouse…</small></div><div style="display:flex;gap:10px;align-items:center"><button class="tg sv" data-act="save">Salvar</button><button class="tg" id="tg" aria-label="Alternar tema"><svg class="i-moon" viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg><svg class="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" stroke-width="2" stroke-linecap="round"/></svg></button><div class="bat" id="bat">–</div></div></header>
<div id="ban"></div><div id="body"></div></main><div id="msg"></div><div id="prog" hidden><i></i></div>
<div id="spl"><img class="lg" alt="Attack Shark"><i></i></div>
<script>
const TK="__TOKEN__",$=s=>document.querySelector(s);
const rg=(a,b,s)=>{const o=[];for(let v=a;v<=b+1e-9;v+=s)o.push(+v.toFixed(1));return o};
const DPI=[...rg(50,10000,50),...rg(10100,20000,100),...rg(20200,26000,200)];
const L={debounce:rg(4,50,2),sleep:rg(.5,30,.5),'sleep.deep':rg(1,60,1),'light.brightness':rg(1,8,1),'light.speed':rg(1,5,1)};
for(let i=1;i<=8;i++)L['dpi.stage'+i]=DPI;
const TABS={home:'Início',dpi:'DPI',perf:'Desempenho',luz:'Iluminação',en:'Energia',perfis:'Perfis'};
const MODES={off:'Desligada',static:'Fixa',breathing:'Respiração',neon:'Neon',colorbreathing:'Respiração colorida',staticdpi:'Cor do nível de DPI',breathingdpi:'Respiração do nível de DPI'};
const BST={charging:'carregando',discharging:'em uso',full:'carga completa',unknown:''};
let M={},S={},tab='home',tm;
async function api(p,body){const r=await fetch(p,{method:body?'POST':'GET',headers:{'X-Token':TK},body:body?JSON.stringify(body):undefined});return r.json()}
function toast(t,e){const m=$('#msg');m.textContent=t;m.className='show'+(e?' err':'');clearTimeout(tm);tm=setTimeout(()=>m.className='',e?6000:1600)}
const sl=(k,u)=>{const v=L[k],c=S[k];return `<input type=range min=0 max=${v.length-1} value=${Math.max(0,v.indexOf(c))} style="--p:${Math.max(0,v.indexOf(c))/(v.length-1)*100}%" data-k="${k}" ${c==='off'?'disabled':''} aria-label="${k}"><output>${c==='off'?'desligado':c+' '+u}</output>`};
const sw=(k,on,x='')=>`<button class="sw ${on?'on':''}" data-k="${k}" ${x} role=switch aria-checked=${!!on}></button>`;
const seg=(k,vals,fmt=v=>v)=>`<div class=seg>${vals.map(v=>`<button data-k="${k}" data-v="${v}" class="${S[k]==v?'on':''}">${fmt(v)}</button>`).join('')}</div>`;
const row=(t,h,c)=>`<div class=row><label>${t}${h?`<small>${h}</small>`:''}</label>${c}</div>`;
const BOLT='<svg class=bolt viewBox="0 0 24 24" aria-label="carregando"><path d="M13.5 2 5 13.5h6L10 22l9-12h-6.2z"/></svg>';
const glow=()=>{const m=S['light.mode'];if(m==='off')return'transparent';const c=/dpi$/.test(m)?S['dpi.stage'+S['dpi.active']+'.color']:S['light.color'];return c||'#ff6a13'};
const fr=m=>/permission|permiss/i.test(m)?'Sem permissão para acessar o mouse. Rode "mousectl install-udev" e reconecte o dongle.':/time|sleep|respond|answer|busy|unavailable|no data|temporar|input\/output/i.test(m)?'O mouse parece estar dormindo. Mexa nele ou clique em um botão e tente de novo.':m;
const bs=b=>M.link&&M.link!=='dongle'&&b.state!=='full'?'carregando':(BST[b.state]||'');
const MSVG='<svg viewBox="0 0 200 320" role=img aria-label="Mouse"><path d="M100 10C50 10 28 60 28 130v80c0 60 30 100 72 100s72-40 72-100v-80C172 60 150 10 100 10z" fill="#1c1f26" stroke="#3a404b" stroke-width="3"/><path d="M100 14v110M30 128c30 14 110 14 140 0" fill="none" stroke="#3a404b" stroke-width="3"/><rect x="92" y="52" width="16" height="34" rx="8" fill="#ff6a13"/></svg>';
function body(){
 $('#ttl').textContent=tab==='home'?'Attack Shark X11':TABS[tab];
 if(tab==='perfis')return perfis();
 if(tab==='home'){const c=(k,l,v,st,x='')=>`<button class=co style="${st}" ${k[0]==='!'?`data-act="${k.slice(1)}"`:`data-tab="${k}"`}><small>${l}</small><b ${x}>${v}</b></button>`;
  $('#body').innerHTML=`<div class=stage id=stage style="--glow:${glow()}"><img src="/asset/mouse" alt="Attack Shark X11" onerror="this.outerHTML=MSVG">`+c('perf','Taxa de polling',S.polling+' Hz','left:4%;top:20%')+c('perf','Debounce',S.debounce+' ms','left:4%;top:62%')+c('!nextdpi','DPI ativo · alternar',S['dpi.stage'+S['dpi.active']]+' DPI','right:4%;top:20%','id=dpiv')+c('luz','Iluminação',MODES[S['light.mode']]||'','right:4%;top:62%')+`</div>`;return}
 let h='';
 if(tab==='dpi'){for(let i=1;i<=8;i++){const k='dpi.stage'+i,off=S[k]==='off';
  h+=`<div class=row><input type=radio name=act data-k="dpi.active" data-v=${i} ${S['dpi.active']==i?'checked':''} ${off?'disabled':''} aria-label="Nível ${i} ativo"><b style="width:70px">Nível ${i}</b>${sl(k,'DPI')}<input type=color data-k="${k}.color" value="${S[k+'.color']||'#ffffff'}" aria-label="Cor do nível ${i}">${sw(k,!off,'data-stage=1')}</div>`}}
 if(tab==='perf')h=row('Taxa de polling','quanto maior, mais responsivo',seg('polling',[125,250,500,1000],v=>v+' Hz'))
  +row('Angle snap','corrige linhas retas',sw('angle_snap',S.angle_snap))
  +row('Ripple control','suaviza tremores',sw('ripple',S.ripple))
  +row('Debounce','tempo anti clique duplo',sl('debounce','ms'))
  +row('Motion sync','só leitura',`<span class=ro>${S.motion_sync?'ligado':'desligado'}</span>`)
  +row('Lift-off distance','só leitura',`<span class=ro>${S.lod}</span>`);
 if(tab==='luz')h=row('Modo','',`<select data-k="light.mode">${Object.entries(MODES).map(([k,v])=>`<option value=${k} ${S['light.mode']===k?'selected':''}>${v}</option>`).join('')}</select>`)
  +row('Cor','',`<input type=color data-k="light.color" value="${S['light.color']||'#ffffff'}">`)
  +row('Brilho','',sl('light.brightness','/8'))+row('Velocidade','',sl('light.speed','/5'));
 if(tab==='en')h=row('Suspender por inatividade','',sl('sleep','min'))+row('Sono profundo','',sl('sleep.deep','min'));
 $('#body').innerHTML=`<div class=card>${h}</div>`;
}
function head(){
 const b=M.battery;$('#dev').innerHTML='<b>Attack Shark X11</b>'+(b?b.percent+'% '+bs(b):'sem leitura');$('#bat').innerHTML=b?`<span>${b.percent}%</span><span class=bar><b style="width:${b.percent}%"></b>${bs(b)==='carregando'?BOLT:''}</span><small>${bs(b)}</small>`:'–';
 $('#sub').textContent=M.link?(M.link==='dongle'?'Conectado pelo dongle':'Conectado por cabo'):'';
 const e=M.none?'Mouse não encontrado. Conecte o dongle ou o cabo.':M.error&&fr(String(M.error.message||M.error.code||JSON.stringify(M.error)));
 $('#ban').innerHTML=e?`<div class=ban><span>${e}</span><button class=btn data-act=retry>Tentar de novo</button></div>`:'';
}
async function load(full){M=await api('/api/state');S=M.settings||S;head();if(full)body()}
async function send(k,v){const r=await api('/api/set',{key:k,value:v});if(r.ok)toast('Salvo');else toast(fr(r.error||'Não foi possível salvar'),1);await load(true)}
const IC={home:['#0a84ff','<path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>'],dpi:['#ff9f0a','<circle cx="12" cy="12" r="7.5" fill="none" stroke-width="2"/><circle cx="12" cy="12" r="2.4"/>'],perf:['#34c759','<path d="M13.5 2 5 13.5h6L10 22l9-12h-6.2z"/>'],luz:['#bf5af2','<circle cx="12" cy="12" r="4"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" stroke-width="2" stroke-linecap="round"/>'],en:['#ff453a','<rect x="3" y="8" width="16" height="9" rx="2.5" fill="none" stroke-width="2"/><rect x="20.5" y="11" width="1.8" height="3" rx=".9"/><rect x="6" y="11" width="7" height="3" rx="1"/>'],perfis:['#5e5ce6','<circle cx="12" cy="8" r="3.6"/><path d="M5 20c0-4 3.2-6 7-6s7 2 7 6z"/>']};
$('#nav').innerHTML=Object.entries(TABS).map(([k,v])=>`<button data-tab=${k} class="${k===tab?'on':''}"><span class=ic style="background:${IC[k][0]}"><svg viewBox="0 0 24 24" fill="#fff" stroke="#fff" stroke-width="0">${IC[k][1]}</svg></span>${v}</button>`).join('');
document.addEventListener('click',e=>{const t=e.target.closest('button');if(!t)return;if(t.dataset.act)return act(t);
 if(t.dataset.tab){tab=t.dataset.tab;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.tab===tab));return body()}
 if(t.classList.contains('sw')){const k=t.dataset.k;if(t.dataset.stage)return send(k,S[k]==='off'?800:'off');return send(k,!S[k])}
 if(t.dataset.v&&t.dataset.k)send(t.dataset.k,isNaN(t.dataset.v)?t.dataset.v:+t.dataset.v)});
document.addEventListener('input',e=>{const t=e.target;if(t.type==='range'){t.style.setProperty('--p',t.value/t.max*100+'%');const k=t.dataset.k,u=t.nextSibling.textContent.split(' ').slice(1).join(' ');t.nextSibling.textContent=L[k][t.value]+' '+u}});
document.addEventListener('change',e=>{const t=e.target,k=t.dataset.k;if(!k)return;
 if(t.type==='range')send(k,L[k][t.value]);else if(t.type==='radio')send(k,+t.dataset.v);else send(k,t.value)});
const esc=s=>s.replace(/[&<>"']/g,c=>'&#'+c.charCodeAt(0)+';');
async function perfis(){const P=await api('/api/profiles'),n=Object.keys(P);window.PF=P;
 $('#body').innerHTML=`<div class=card><div class=row><label>Novo perfil<small>guarda as configurações atuais</small></label><input id=pn placeholder="Ex.: FPS competitivo" maxlength=30><button class=btn data-act=savep>Salvar perfil</button></div>`+(n.length?n.map(k=>`<div class=row><b style="flex:1">${esc(k)}</b><span class=ro>${P[k]['dpi.stage'+P[k]['dpi.active']]} DPI · ${P[k].polling} Hz</span><button class=btn data-act=apply data-n="${esc(k)}">Aplicar</button><button class="btn ghost" data-act=del data-n="${esc(k)}">Excluir</button></div>`).join(''):`<div class=row><span class=ro style="margin:0">Nenhum perfil salvo ainda.</span></div>`)+`</div>`}
async function act(t){const a=t.dataset.act;
 if(a==='save'){await load(true);return toast('Tudo salvo no mouse')}
 if(a==='savep'){const n=$('#pn').value.trim();if(!n)return toast('Dê um nome ao perfil',1);const s={};for(const k in S)if(!['motion_sync','lod'].includes(k))s[k]=S[k];await api('/api/profile',{name:n,settings:s});toast('Perfil salvo');return perfis()}
 if(a==='del'){await api('/api/profile/delete',{name:t.dataset.n});return perfis()}
 if(a==='retry'){await load(true);return}
 if(a==='nextdpi'){const on=[1,2,3,4,5,6,7,8].filter(i=>S['dpi.stage'+i]!=='off'),n=on[(on.indexOf(+S['dpi.active'])+1)%on.length]||on[0];
  const r=await api('/api/set',{key:'dpi.active',value:n});if(!r.ok)return toast(fr(r.error||'Não consegui trocar o nível'),1);
  S['dpi.active']=n;$('#dpiv').textContent=S['dpi.stage'+n]+' DPI';$('#stage').style.setProperty('--glow',glow());return toast('Nível '+n+' · '+S['dpi.stage'+n]+' DPI')}
 if(a==='apply'){const P=PF[t.dataset.n],ks=Object.keys(P).filter(k=>JSON.stringify(P[k])!==JSON.stringify(S[k]));
  if(!ks.length)return toast('Esse perfil já está aplicado');
  const pg=$('#prog'),bar=pg.firstElementChild,bad=[];pg.hidden=false;
  for(let i=0;i<ks.length;i++){bar.style.width=(i/ks.length*100)+'%';toast(`Aplicando ${i+1}/${ks.length}…`);const r=await api('/api/set',{key:ks[i],value:P[ks[i]]});if(!r.ok)bad.push(ks[i])}
  bar.style.width='100%';setTimeout(()=>{pg.hidden=true;bar.style.width=0},600);await load(true);toast(bad.length?'Falhou: '+bad.join(', '):'Perfil aplicado',!!bad.length)}}
const lg=()=>{const dk=document.documentElement.dataset.theme==='dark';document.querySelectorAll('img.lg').forEach(i=>{i.classList.remove('inv');i.dataset.f='';i.onerror=()=>{if(dk&&!i.dataset.f){i.dataset.f=1;i.classList.add('inv');i.src='/asset/logo'}else i.replaceWith(Object.assign(document.createElement('span'),{textContent:'ATTACK SHARK'}))};i.src=dk?'/asset/logo-dark':'/asset/logo'})};
const th=()=>{const d=document.documentElement;d.dataset.theme=localStorage.getItem('th')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');lg()};
$('#tg').onclick=e=>{const nx=document.documentElement.dataset.theme==='dark'?'light':'dark',go=()=>{localStorage.setItem('th',nx);th()};
 if(!document.startViewTransition||matchMedia('(prefers-reduced-motion:reduce)').matches)return go();
 const r=e.currentTarget.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,R=Math.hypot(Math.max(x,innerWidth-x),Math.max(y,innerHeight-y));
 document.startViewTransition(go).ready.then(()=>document.documentElement.animate({clipPath:[`circle(0 at ${x}px ${y}px)`,`circle(${R}px at ${x}px ${y}px)`]},{duration:700,easing:'ease-in-out',pseudoElement:'::view-transition-new(root)'}))};th();
if(matchMedia('(prefers-reduced-motion:reduce)').matches||document.documentElement.classList.contains('nospl'))$('#spl').remove();else{localStorage.setItem('spl',new Date().toDateString());setTimeout(()=>$('#spl').remove(),1600)}
load(true);setInterval(()=>load(false),10000);setInterval(()=>api('/api/ping'),5000);api('/api/ping');
</script></body></html>"""

if __name__ == "__main__":
    main()
