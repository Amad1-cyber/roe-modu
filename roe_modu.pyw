"""ROE MODU - control panel for the Rubies of Eventide local/public server.

Start/stop the server, launch the game against it (localhost by default), manage accounts and characters, see the live
player count, and optionally publish through a free Cloudflare Tunnel. Pure standard library (tkinter).
"""
import ctypes, json, os, re, subprocess, sys, threading, time, urllib.request, base64, winreg
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import roe_store as store

APP = 'ROE MODU'
MODU_FILE = os.path.join(BASE, 'modu.json')
STATUS_FILE = os.path.join(BASE, 'status.json')
TOOLS = os.path.join(BASE, 'tools')
REG_PATH = r'SOFTWARE\Cyber Warrior\LithtechRubies'
CF_URL = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
HOST_RE = re.compile(r'^[A-Za-z0-9.\-]{1,253}$')
NO_WINDOW = 0x08000000
BG, PANEL, FG, ACCENT, GOOD, BAD = '#1d1b24', '#2a2733', '#f2ede7', '#eead78', '#6fcf7f', '#e5675f'

MODU_DEFAULT = {'game_dir': '', 'windowed': True, 'autostart': True, 'stop_on_exit': False, 'remote_addr': '',
                'cloudflared': os.path.join(TOOLS, 'cloudflared.exe'), 'tunnel_name': '', 'credentials_file': '',
                'login_host': '', 'game_host': ''}


def load_modu():
    d = dict(MODU_DEFAULT)
    try:
        with open(MODU_FILE, encoding='utf-8-sig') as f:
            d.update(json.load(f))
    except (OSError, ValueError):
        pass
    return d


def save_modu(d):
    with open(MODU_FILE, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2)


# ------------------------------------------------------------------ system helpers
def find_game_dir(cfg):
    cands = [cfg.get('game_dir', '')]
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as k:
            cands.append(winreg.QueryValueEx(k, 'SourceDirectory')[0])
    except OSError:
        pass
    cands.append(os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Rubies of Eventide'))
    for c in cands:
        if c and os.path.isfile(os.path.join(c, 'Lithtech.exe')) and os.path.isfile(os.path.join(c, 'rez', 'CShell.dll')):
            return c
    return ''


def read_login_server():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as k:
            return winreg.QueryValueEx(k, 'LoginServer')[0]
    except OSError:
        return ''


def set_login_server(host):
    """Point the client at `host`. Needs admin once (HKLM); elevates through a UAC prompt if required."""
    if not HOST_RE.match(host):
        raise ValueError('Enter a host name or IP address (letters, digits, dots, dashes).')
    if read_login_server() == host:
        return
    try:
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_32KEY) as k:
            winreg.SetValueEx(k, 'LoginServer', 0, winreg.REG_SZ, host)
        return
    except PermissionError:
        pass
    script = ("$b=[Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine','Registry32');"
              f"$k=$b.CreateSubKey('{REG_PATH}');$k.SetValue('LoginServer','{host}','String');$k.Dispose()")
    enc = base64.b64encode(script.encode('utf-16-le')).decode()
    ctypes.windll.shell32.ShellExecuteW(None, 'runas', 'powershell.exe',
                                        f'-NoProfile -WindowStyle Hidden -EncodedCommand {enc}', None, 0)
    for _ in range(40):
        time.sleep(0.5)
        if read_login_server() == host:
            return
    raise RuntimeError('Windows did not apply the login address (was the administrator prompt declined?).')


def server_status():
    try:
        with open(STATUS_FILE, encoding='utf-8') as f:
            st = json.load(f)
        return st if time.time() - st['updated'] < 6 else None
    except (OSError, ValueError, KeyError):
        return None


def process_running(image):
    out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {image}', '/NH'], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return image.lower() in out.lower()


def scan_content(game_dir):
    """Inventory of what the *client* data contains (the original NPC/quest/item server data is not part of it)."""
    rez = os.path.join(game_dir, 'rez')
    out = {'zones': [], 'models': {}, 'icons': {}, 'info_pages': 0}
    wdir = os.path.join(rez, 'Worlds')
    if os.path.isdir(wdir):
        out['zones'] = sorted(f[:-4] for f in os.listdir(wdir) if f.lower().endswith('.dat'))
    for sub in ('Models', 'ModelTextures', 'Interface', 'Sprites', 'Music', 'ClientFX', 'FX'):
        p = os.path.join(rez, sub)
        n = sum(len(fs) for _, _, fs in os.walk(p)) if os.path.isdir(p) else 0
        out['models'][sub] = n
    ic = os.path.join(rez, 'Interface', 'Icon')
    if os.path.isdir(ic):
        for d in os.listdir(ic):
            out['icons'][d] = len(os.listdir(os.path.join(ic, d)))
    info = os.path.join(game_dir, 'Crsm', 'info')
    out['info_pages'] = len(os.listdir(info)) if os.path.isdir(info) else 0
    return out


# ------------------------------------------------------------------ the app
class Modu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'{APP} - Rubies of Eventide server')
        self.geometry('860x620')
        self.minsize(780, 560)
        self.configure(bg=BG)
        self.cfg = load_modu()
        self.server = None          # subprocess we started
        self.tunnel = None
        self._style()
        self._header()
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=10, pady=(0, 6))
        self._tab_play()
        self._tab_accounts()
        self._tab_characters()
        self._tab_public()
        self._tab_content()
        self._tab_log()
        self.msg = tk.StringVar(value='Ready.')
        tk.Label(self, textvariable=self.msg, anchor='w', bg=BG, fg=ACCENT, font=('Segoe UI', 9)).pack(fill='x', padx=12, pady=(0, 8))
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.after(300, self.tick)
        if self.cfg['autostart'] and not server_status():
            self.after(600, self.start_server)

    # ---- styling / helpers
    def _style(self):
        st = ttk.Style(self)
        st.theme_use('clam')
        st.configure('.', background=BG, foreground=FG, fieldbackground=PANEL, font=('Segoe UI', 10))
        st.configure('TNotebook', background=BG, borderwidth=0)
        st.configure('TNotebook.Tab', background=PANEL, foreground=FG, padding=(14, 6))
        st.map('TNotebook.Tab', background=[('selected', ACCENT)], foreground=[('selected', '#1d1b24')])
        st.configure('TFrame', background=BG)
        st.configure('TLabel', background=BG, foreground=FG)
        st.configure('TCheckbutton', background=BG, foreground=FG)
        st.configure('TRadiobutton', background=BG, foreground=FG)
        st.configure('TButton', background=PANEL, foreground=FG, padding=(12, 6), borderwidth=0)
        st.map('TButton', background=[('active', '#3b3748')])
        st.configure('Play.TButton', background=ACCENT, foreground='#1d1b24', font=('Segoe UI', 13, 'bold'), padding=(24, 12))
        st.map('Play.TButton', background=[('active', '#f5c093')])
        st.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24, borderwidth=0)
        st.configure('Treeview.Heading', background='#3b3748', foreground=FG)
        st.configure('TEntry', fieldbackground=PANEL, foreground=FG, insertcolor=FG)

    def say(self, text):
        self.msg.set(text)

    def run_bg(self, fn, done=None):
        def work():
            try:
                res, err = fn(), None
            except Exception as e:  # shown to the user, never swallowed
                res, err = None, e
            self.after(0, lambda: (done(res, err) if done else (self.say(f'Error: {err}') if err else None)))
        threading.Thread(target=work, daemon=True).start()

    def _header(self):
        f = tk.Frame(self, bg=BG)
        f.pack(fill='x', padx=14, pady=(12, 8))
        tk.Label(f, text='ROE MODU', bg=BG, fg=ACCENT, font=('Segoe UI', 24, 'bold')).pack(side='left')
        tk.Label(f, text='Rubies of Eventide server', bg=BG, fg=FG, font=('Segoe UI', 10)).pack(side='left', padx=12, pady=(10, 0))
        right = tk.Frame(f, bg=BG)
        right.pack(side='right')
        self.dot = tk.Canvas(right, width=16, height=16, bg=BG, highlightthickness=0)
        self.dot.pack(side='left', padx=(0, 6))
        self.dot_id = self.dot.create_oval(2, 2, 14, 14, fill=BAD, outline='')
        self.status_lbl = tk.Label(right, text='Server stopped', bg=BG, fg=FG, font=('Segoe UI', 10, 'bold'))
        self.status_lbl.pack(side='left')
        self.players_lbl = tk.Label(right, text='Players online: 0', bg=PANEL, fg=GOOD, font=('Segoe UI', 10, 'bold'), padx=10, pady=3)
        self.players_lbl.pack(side='left', padx=(14, 0))

    def _page(self, title):
        fr = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(fr, text=title)
        return fr

    # ---- PLAY tab
    def _tab_play(self):
        fr = self._page('Play')
        ttk.Label(fr, text='Play on your own server', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(fr, text='Starts the server if needed, points the game at it (localhost by default) and launches Rubies of Eventide.',
                  wraplength=780).pack(anchor='w', pady=(2, 10))
        row = ttk.Frame(fr)
        row.pack(anchor='w', pady=4)
        ttk.Button(row, text='PLAY', style='Play.TButton', command=self.play_local).pack(side='left')
        ttk.Button(row, text='Start server', command=self.start_server).pack(side='left', padx=(16, 4))
        ttk.Button(row, text='Stop server', command=self.stop_server).pack(side='left', padx=4)
        ttk.Button(row, text='Restart server', command=self.restart_server).pack(side='left', padx=4)
        opts = ttk.Frame(fr)
        opts.pack(anchor='w', pady=(10, 4))
        self.v_windowed = tk.BooleanVar(value=self.cfg['windowed'])
        self.v_autostart = tk.BooleanVar(value=self.cfg['autostart'])
        self.v_stoponexit = tk.BooleanVar(value=self.cfg['stop_on_exit'])
        ttk.Checkbutton(opts, text='Windowed mode (recommended: the engine quits with "Lost focus" if a fullscreen game loses focus)',
                        variable=self.v_windowed, command=self.save_opts).pack(anchor='w')
        ttk.Checkbutton(opts, text='Start the server automatically when ROE MODU opens', variable=self.v_autostart, command=self.save_opts).pack(anchor='w')
        ttk.Checkbutton(opts, text='Stop the server when ROE MODU closes', variable=self.v_stoponexit, command=self.save_opts).pack(anchor='w')
        ttk.Separator(fr).pack(fill='x', pady=14)
        ttk.Label(fr, text='Join someone else\'s server', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(fr, text='Enter the host name or IP the server owner gave you (for Cloudflare servers, see the Public tab).', wraplength=780).pack(anchor='w', pady=(2, 6))
        jr = ttk.Frame(fr)
        jr.pack(anchor='w')
        self.v_remote = tk.StringVar(value=self.cfg['remote_addr'])
        ttk.Entry(jr, textvariable=self.v_remote, width=36).pack(side='left')
        ttk.Button(jr, text='Join server', command=self.play_remote).pack(side='left', padx=8)
        self.play_info = tk.StringVar()
        ttk.Label(fr, textvariable=self.play_info, foreground=ACCENT).pack(anchor='w', pady=(14, 0))

    def save_opts(self):
        self.cfg.update(windowed=self.v_windowed.get(), autostart=self.v_autostart.get(), stop_on_exit=self.v_stoponexit.get(),
                        remote_addr=self.v_remote.get().strip())
        save_modu(self.cfg)

    # ---- ACCOUNTS tab
    def _tab_accounts(self):
        fr = self._page('Accounts')
        self.acc_tree = ttk.Treeview(fr, columns=('name',), show='headings', height=9)
        self.acc_tree.heading('name', text='Account')
        self.acc_tree.pack(fill='x')
        form = ttk.Frame(fr)
        form.pack(anchor='w', pady=10)
        self.v_acc, self.v_pw = tk.StringVar(), tk.StringVar()
        ttk.Label(form, text='Account').grid(row=0, column=0, sticky='w')
        ttk.Entry(form, textvariable=self.v_acc, width=22).grid(row=0, column=1, padx=6)
        ttk.Label(form, text='Password').grid(row=0, column=2, sticky='w', padx=(10, 0))
        ttk.Entry(form, textvariable=self.v_pw, width=22, show='*').grid(row=0, column=3, padx=6)
        bar = ttk.Frame(fr)
        bar.pack(anchor='w')
        ttk.Button(bar, text='Create account', command=self.acc_create).pack(side='left')
        ttk.Button(bar, text='Set password', command=self.acc_setpw).pack(side='left', padx=6)
        ttk.Button(bar, text='Delete selected', command=self.acc_delete).pack(side='left')
        self.v_open = tk.BooleanVar(value=store.load_config()['open_registration'])
        ttk.Checkbutton(fr, text='Open registration: logging in with a new name creates that account (fine for solo play; turn OFF for a public server)',
                        variable=self.v_open, command=self.toggle_open).pack(anchor='w', pady=(14, 0))
        ttk.Label(fr, text='Passwords are stored as salted PBKDF2 hashes in accounts.json. Changes apply immediately.').pack(anchor='w', pady=(6, 0))

    def acc_create(self):
        try:
            store.create_account(self.v_acc.get().strip(), self.v_pw.get())
            self.say(f'Account {self.v_acc.get().strip()} created.')
            self.v_pw.set('')
        except ValueError as e:
            messagebox.showwarning(APP, str(e))
        self.refresh_lists()

    def acc_setpw(self):
        try:
            store.set_password(self.v_acc.get().strip(), self.v_pw.get())
            self.say('Password updated.')
            self.v_pw.set('')
        except ValueError as e:
            messagebox.showwarning(APP, str(e))

    def acc_delete(self):
        sel = self.acc_tree.selection()
        if sel and messagebox.askyesno(APP, 'Delete the selected account (its characters stay on disk)?'):
            store.delete_account(self.acc_tree.item(sel[0])['values'][0])
            self.refresh_lists()

    def toggle_open(self):
        cfg = store.load_config()
        cfg['open_registration'] = self.v_open.get()
        store.save_config(cfg)
        self.say('Open registration ' + ('ON' if cfg['open_registration'] else 'OFF') + ' (restart the server to apply).')

    # ---- CHARACTERS tab
    def _tab_characters(self):
        fr = self._page('Characters')
        self.ch_tree = ttk.Treeview(fr, columns=('acct', 'first', 'last', 'created'), show='headings', height=14)
        for c, t, w in (('acct', 'Account', 150), ('first', 'First name', 150), ('last', 'Last name', 150), ('created', 'Created', 170)):
            self.ch_tree.heading(c, text=t)
            self.ch_tree.column(c, width=w)
        self.ch_tree.pack(fill='both', expand=True)
        ttk.Button(fr, text='Delete selected character', command=self.ch_delete).pack(anchor='w', pady=8)

    def ch_delete(self):
        sel = self.ch_tree.selection()
        if sel and messagebox.askyesno(APP, 'Permanently delete this character?'):
            acct, first = self.ch_tree.item(sel[0])['values'][:2]
            store.delete_character(str(acct), str(first))
            self.refresh_lists()

    # ---- PUBLIC / CLOUDFLARE tab
    def _tab_public(self):
        fr = self._page('Public / Cloudflare')
        ttk.Label(fr, text='Server address settings', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(fr, text='Localhost is the default and needs no setup. Change these only to host for other people.', wraplength=780).pack(anchor='w', pady=(2, 8))
        c = store.load_config()
        g = ttk.Frame(fr)
        g.pack(anchor='w')
        self.v_bind = tk.StringVar(value=c['bind'])
        self.v_adv = tk.StringVar(value=c['advertise_host'])
        self.v_lp, self.v_gp = tk.StringVar(value=str(c['login_port'])), tk.StringVar(value=str(c['game_port']))
        rows = (('Listen on', self.v_bind, '127.0.0.1 = this PC only (default) | 0.0.0.0 = all networks'),
                ('Advertised host', self.v_adv, 'what clients connect to for the game server (localhost for Cloudflare Tunnel setups)'),
                ('Login port', self.v_lp, 'the client always uses 3142 for login'), ('Game port', self.v_gp, ''))
        for i, (lbl, var, hint) in enumerate(rows):
            ttk.Label(g, text=lbl).grid(row=i, column=0, sticky='w', pady=2)
            ttk.Entry(g, textvariable=var, width=26).grid(row=i, column=1, padx=8)
            ttk.Label(g, text=hint, foreground='#9d97a8').grid(row=i, column=2, sticky='w')
        ttk.Button(fr, text='Save server settings', command=self.save_server_cfg).pack(anchor='w', pady=8)
        ttk.Separator(fr).pack(fill='x', pady=8)
        ttk.Label(fr, text='Free Cloudflare Tunnel (optional)', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(fr, text='The game uses raw TCP, so use a Cloudflare Tunnel (free) - not a Worker. Players run "cloudflared access tcp" once per port. '
                           'Full steps are in README.md.', wraplength=780).pack(anchor='w', pady=(2, 8))
        self.cf_vars = {}
        cg = ttk.Frame(fr)
        cg.pack(anchor='w')
        for i, (key, lbl) in enumerate((('cloudflared', 'cloudflared.exe'), ('tunnel_name', 'Tunnel name'), ('credentials_file', 'Credentials .json'),
                                        ('login_host', 'Login hostname'), ('game_host', 'Game hostname'))):
            v = tk.StringVar(value=self.cfg[key])
            self.cf_vars[key] = v
            ttk.Label(cg, text=lbl).grid(row=i, column=0, sticky='w', pady=2)
            ttk.Entry(cg, textvariable=v, width=60).grid(row=i, column=1, padx=8)
        cb = ttk.Frame(fr)
        cb.pack(anchor='w', pady=8)
        ttk.Button(cb, text='Download cloudflared', command=self.cf_download).pack(side='left')
        ttk.Button(cb, text='Write tunnel config', command=self.cf_write).pack(side='left', padx=6)
        ttk.Button(cb, text='Start tunnel', command=self.cf_start).pack(side='left')
        ttk.Button(cb, text='Stop tunnel', command=self.cf_stop).pack(side='left', padx=6)

    def save_server_cfg(self):
        try:
            c = store.load_config()
            c.update(bind=self.v_bind.get().strip(), advertise_host=self.v_adv.get().strip(),
                     login_port=int(self.v_lp.get()), game_port=int(self.v_gp.get()))
            if not HOST_RE.match(c['advertise_host']):
                raise ValueError('Advertised host must be a host name or IP.')
            store.save_config(c)
            self.say('Saved. Restart the server to apply.')
        except ValueError as e:
            messagebox.showwarning(APP, str(e))

    def cf_collect(self):
        for k, v in self.cf_vars.items():
            self.cfg[k] = v.get().strip()
        save_modu(self.cfg)

    def cf_download(self):
        def work():
            os.makedirs(TOOLS, exist_ok=True)
            dest = os.path.join(TOOLS, 'cloudflared.exe')
            urllib.request.urlretrieve(CF_URL, dest + '.part')
            os.replace(dest + '.part', dest)
            return dest
        self.say('Downloading cloudflared from github.com/cloudflare/cloudflared ...')
        self.run_bg(work, lambda r, e: (self.cf_vars['cloudflared'].set(r), self.cf_collect(), self.say('cloudflared downloaded.')) if not e else self.say(f'Download failed: {e}'))

    def cf_write(self):
        self.cf_collect()
        c = store.load_config()
        need = [k for k in ('tunnel_name', 'credentials_file', 'login_host', 'game_host') if not self.cfg[k]]
        if need:
            messagebox.showinfo(APP, 'Fill in: ' + ', '.join(need) + '\n\nCreate them first with the cloudflared commands in README.md.')
            return
        yml = (f'tunnel: {self.cfg["tunnel_name"]}\ncredentials-file: {self.cfg["credentials_file"]}\ningress:\n'
               f'  - hostname: {self.cfg["login_host"]}\n    service: tcp://localhost:{c["login_port"]}\n'
               f'  - hostname: {self.cfg["game_host"]}\n    service: tcp://localhost:{c["game_port"]}\n  - service: http_status:404\n')
        with open(os.path.join(BASE, 'cloudflared-config.yml'), 'w', encoding='utf-8') as f:
            f.write(yml)
        self.say('Wrote cloudflared-config.yml')

    def cf_start(self):
        self.cf_collect()
        exe, cfgp = self.cfg['cloudflared'], os.path.join(BASE, 'cloudflared-config.yml')
        if not os.path.isfile(exe) or not os.path.isfile(cfgp):
            messagebox.showinfo(APP, 'Download cloudflared and write the tunnel config first.')
            return
        self.tunnel = subprocess.Popen([exe, 'tunnel', '--config', cfgp, 'run'], creationflags=NO_WINDOW,
                                       stdout=open(os.path.join(BASE, 'tunnel.log'), 'a'), stderr=subprocess.STDOUT)
        self.say('Cloudflare tunnel started (see tunnel.log).')

    def cf_stop(self):
        if self.tunnel and self.tunnel.poll() is None:
            self.tunnel.terminate()
            self.say('Tunnel stopped.')

    # ---- CONTENT tab
    def _tab_content(self):
        fr = self._page('Content')
        ttk.Label(fr, text='What the game client actually contains', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(fr, text='The original NPC, monster, item, quest and town-population data lived only on the shut-down servers and is not in the client. '
                           'This lists the building blocks the client does have, which new content can be authored from.', wraplength=780).pack(anchor='w', pady=(2, 8))
        self.content_txt = tk.Text(fr, height=18, bg=PANEL, fg=FG, relief='flat', font=('Consolas', 10))
        self.content_txt.pack(fill='both', expand=True)
        ttk.Button(fr, text='Rescan client data', command=self.rescan).pack(anchor='w', pady=8)

    def rescan(self):
        gd = find_game_dir(self.cfg)
        if not gd:
            self.say('Game folder not found.')
            return
        self.say('Scanning client data ...')
        def done(res, err):
            if err:
                self.say(f'Scan failed: {err}')
                return
            t = self.content_txt
            t.delete('1.0', 'end')
            t.insert('end', f'Game folder: {gd}\n\nZones (rez\\Worlds): {len(res["zones"])}\n  ' + ', '.join(res['zones']) + '\n\nAsset counts:\n')
            for k, v in res['models'].items():
                t.insert('end', f'  {k:<16}{v:>6} files\n')
            t.insert('end', '\nIcon sets (rez\\Interface\\Icon):\n')
            for k, v in sorted(res['icons'].items()):
                t.insert('end', f'  {k:<16}{v:>6} icons\n')
            t.insert('end', f'\nClass/skill/race info pages (Crsm\\info): {res["info_pages"]}\n')
            self.say('Scan complete.')
        self.run_bg(lambda: scan_content(gd), done)

    # ---- LOG tab
    def _tab_log(self):
        fr = self._page('Log')
        self.log_txt = tk.Text(fr, bg=PANEL, fg=FG, relief='flat', font=('Consolas', 9), wrap='none')
        self.log_txt.pack(fill='both', expand=True)
        self._log_size = -1

    def refresh_log(self):
        try:
            size = os.path.getsize(store.LOG_FILE)
        except OSError:
            return
        if size == self._log_size:
            return
        self._log_size = size
        with open(store.LOG_FILE, 'rb') as f:
            f.seek(max(0, size - 12000))
            text = f.read().decode('utf-8', 'replace')
        self.log_txt.delete('1.0', 'end')
        self.log_txt.insert('end', text)
        self.log_txt.see('end')

    # ---- server control
    def start_server(self):
        if server_status():
            self.say('Server already running.')
            return
        py = sys.executable.replace('pythonw.exe', 'python.exe')
        self.server = subprocess.Popen([py, os.path.join(BASE, 'roe_server.py')], cwd=BASE, creationflags=NO_WINDOW | 0x00000200)
        self.say('Starting server ...')

    def stop_server(self):
        st = server_status()
        if st:
            subprocess.run(['taskkill', '/PID', str(st['pid']), '/F'], capture_output=True, creationflags=NO_WINDOW)
            try:
                os.remove(STATUS_FILE)
            except OSError:
                pass
            self.say('Server stopped.')
        else:
            self.say('Server is not running.')

    def restart_server(self):
        self.stop_server()
        self.after(1200, self.start_server)

    # ---- launching the game
    def launch_game(self):
        gd = find_game_dir(self.cfg)
        if not gd:
            messagebox.showerror(APP, 'Rubies of Eventide was not found. Install the client first (Rubies of Eventide 0.95).')
            return
        if process_running('Lithtech.exe'):
            messagebox.showinfo(APP, 'The game is already running. Close it first to switch servers.')
            return
        self.save_opts()
        win = '1' if self.cfg['windowed'] else '0'
        subprocess.Popen([os.path.join(gd, 'Lithtech.exe'), '-rez', 'engine.rez', '-rez', 'rez', '+windowed', win], cwd=gd)

    def play_local(self):
        def work():
            if not server_status():
                self.after(0, self.start_server)
                for _ in range(40):
                    time.sleep(0.5)
                    if server_status():
                        break
                else:
                    raise RuntimeError('The server did not start (see the Log tab).')
            set_login_server('127.0.0.1')
        self.say('Preparing ...')
        self.run_bg(work, lambda r, e: self.say(f'Error: {e}') if e else (self.launch_game(), self.say('Game launched on localhost. Log in with any account name + password.')))

    def play_remote(self):
        addr = self.v_remote.get().strip()
        if not HOST_RE.match(addr):
            messagebox.showwarning(APP, 'Enter the server host name or IP address.')
            return
        self.say('Preparing ...')
        self.run_bg(lambda: set_login_server(addr), lambda r, e: self.say(f'Error: {e}') if e else (self.launch_game(), self.say(f'Game launched for {addr}.')))

    # ---- periodic refresh
    def refresh_lists(self):
        self.acc_tree.delete(*self.acc_tree.get_children())
        for a in store.list_accounts():
            self.acc_tree.insert('', 'end', values=(a,))
        self.ch_tree.delete(*self.ch_tree.get_children())
        for acct, chars in sorted(store.all_characters().items()):
            for c in chars:
                self.ch_tree.insert('', 'end', values=(acct, c['first'], c.get('last', ''), c.get('created', '')))

    def tick(self):
        st = server_status()
        if st:
            up = int(time.time() - st['started'])
            self.dot.itemconfig(self.dot_id, fill=GOOD)
            self.status_lbl.config(text=f'Server running  {st["bind"]}:{st["login_port"]}  up {up // 60}m{up % 60:02d}s')
            names = ', '.join(st['players'][:6])
            self.players_lbl.config(text=f'Players online: {st["online"]}' + (f'  ({names})' if names else ''))
            self.play_info.set(f'Login {st["advertise"]}:{st["login_port"]}   Game port {st["game_port"]}   Client login address: {read_login_server() or "(not set)"}')
        else:
            self.dot.itemconfig(self.dot_id, fill=BAD)
            self.status_lbl.config(text='Server stopped')
            self.players_lbl.config(text='Players online: 0')
            self.play_info.set('Server is not running. Press PLAY or Start server.')
        self.refresh_log()
        if int(time.time()) % 4 == 0:
            self.refresh_lists()
        self.after(1000, self.tick)

    def on_close(self):
        self.save_opts()
        if self.cfg['stop_on_exit']:
            self.stop_server()
        self.cf_stop()
        self.destroy()


if __name__ == '__main__':
    app = Modu()
    if '--selftest' in sys.argv:
        app.after(2500, app.destroy)
    app.mainloop()
