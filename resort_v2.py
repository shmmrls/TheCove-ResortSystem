"""
The Cove RESORT - Reservation & Management System  (v3 - centered windows + modals)
Python + Tkinter + SQLite + Pillow + Matplotlib

Install once:   python -m pip install pillow matplotlib
Run:            python resort_v2.py

Default logins:  admin / admin123   (full access, incl. Promo Codes, Staff & Reports)
                 staff / staff123   (front desk)
"""
import os
import csv
import math
import shutil
import sqlite3
import hashlib
import random
import calendar as pycal
import datetime as dt
import uuid
import tkinter as tk
import tkinter.font as tkfont
import backup_tools as backups
from tkinter import ttk, messagebox, filedialog


from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageOps
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

matplotlib.rcParams["font.family"] = ["Segoe UI", "Arial", "DejaVu Sans"]

# ============================================================ config / theme
BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "resort_images")
ASSETS_DIR = os.path.join(BASE, "assets") 
DB_PATH = os.path.join(BASE, "resort.db")
BACKUP_DIR = os.path.join(BASE, "backups")
LOG_PATH = os.path.join(BASE, "activity.log")
os.makedirs(IMG_DIR, exist_ok=True)

RESORT = "The Cove RESORT"
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")  
LOGO_WELCOME_PATH = os.path.join(ASSETS_DIR, "logo_welcome.png")  
VAT = 0.12
WEEKEND_MULT = 1.15          # Fri & Sat nights cost 15% more
BACKUP_KEEP = 5
DEFAULT_METHOD = "Cash"
DEFAULT_PROMOS = [("WELCOME10", 10, "Welcome offer for first-time guests"),
                  ("SUMMER15", 15, "Summer season discount"),
                  ("VIP20", 20, "For VIP guests")]

# Palette
INK     = "#000501"
OCEAN   = "#0B3C49"    # sidebar + primary buttons
OCEAN2  = "#14505F"    # hover
TEAL    = "#0B3C49"    # primary
AQUA    = "#8FCBD3"
CREAM   = "#F5EFE0"
GOLD    = "#FFCA55"
CORAL   = GOLD         # call-to-action buttons now use gold
DANGER  = "#C8553D"    # delete / cancel only (destructive actions need their own colour)
BG      = "#F2F6F6"
WHITE   = "#FFFFFF"
BORDER  = "#DDE6E7"
MUTED   = "#5A6F75"
SEAFOAM = CREAM
TINT = {"teal": "#E4F3F5", "coral": "#FFF1CC", "gold": CREAM, "ocean": "#DCE8EC"}
SAND, SAND_D = BG, BORDER
F = "Segoe UI"
FH = F

STATUS_COLORS = {"Reserved": GOLD, "Checked-in": OCEAN, "Checked-out": AQUA, "Cancelled": "#D98880"}
ROW_TINT = {"Reserved": "#FFF6DB", "Checked-in": "#E4F3F5", "Checked-out": BG, "Cancelled": "#FCEDEA"}
CHART_COLORS = [OCEAN, GOLD, AQUA, "#3E7C8A", "#E2A93B", "#6FAAB4", "#1F5A68", "#C9B27C"]
METHODS = ["Cash", "GCash", "Card", "Bank Transfer"]

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row


# ============================================================ small helpers
def q(sql, args=()):
    return conn.execute(sql, args).fetchall()


def q1(sql, args=()):
    return conn.execute(sql, args).fetchone()


def ex(sql, args=()):
    cur = conn.execute(sql, args)
    conn.commit()
    return cur


def money(x):
    return f"₱{float(x):,.2f}"

def vat_label():
    """Text for the VAT line on invoices and summaries, e.g. 'VAT 12%'."""
    return f"VAT {VAT * 100:g}%"

def today():
    return dt.date.today()


def pdate(s):
    return dt.date.fromisoformat(s)


def ref(bid):
    return f"RB-{int(bid):05d}"


def hash_pw(p):
    return hashlib.sha256(("azure_salt" + p).encode()).hexdigest()


def slug(t):
    return "".join(c.lower() if c.isalnum() else "_" for c in t).strip("_")


def shade(hexc, f):
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * f))) for c in (r, g, b))

def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def readable(bg, fg):
    """Keep fg if it has enough contrast on bg, otherwise flip to INK/WHITE."""
    try:
        a, b = sorted((_lum(bg), _lum(fg)), reverse=True)
        if (a + 0.05) / (b + 0.05) >= 3.5:
            return fg
        return INK if _lum(bg) > 0.4 else WHITE
    except ValueError:
        return fg

def center_window(win, w=None, h=None, parent=None):
    """Put `win` in the middle of the screen, or in the middle of `parent` when it is visible."""
    win.update_idletasks()
    w = w or win.winfo_reqwidth()
    h = h or win.winfo_reqheight()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    try:
        if parent is None or not parent.winfo_viewable():
            raise tk.TclError("no visible parent")
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    except tk.TclError:
        x, y = (sw - w) // 2, (sh - h) // 2 - 20
    x = max(0, min(x, sw - w))
    y = max(0, min(y, sh - h - 40))      # keep clear of the taskbar
    win.geometry(f"{w}x{h}+{x}+{y}")

def style_titlebar(win, bg=OCEAN, fg=WHITE):
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
 
        def bgr(h):
            h = h.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            return ctypes.c_int(r | (g << 8) | (b << 16))
 
        for attr, col in ((35, bg), (36, fg), (34, bg)):   # caption, text, border
            c = bgr(col)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(c), ctypes.sizeof(c))
    except Exception:
        pass

# ============================================================ pictures
THEMES = {  # sky top, sky bottom, sea, sand
    "Garden Room": ((170, 224, 196), (250, 240, 200), (44, 130, 120), (233, 214, 170)),
    "Deluxe Sea View": ((255, 196, 128), (250, 130, 100), (18, 100, 130), (236, 210, 165)),
    "Family Cottage": ((150, 205, 240), (255, 232, 190), (30, 130, 160), (240, 220, 175)),
    "Pool Villa": ((110, 180, 235), (200, 240, 245), (40, 170, 190), (244, 228, 190)),
    "Overwater Bungalow": ((255, 160, 120), (255, 214, 140), (10, 120, 140), (236, 205, 160)),
}

def fullscreen(win):
    try:
        win.state("zoomed")                       # Windows
    except tk.TclError:
        try:
            win.attributes("-zoomed", True)       # Linux
        except tk.TclError:
            win.geometry(f"{win.winfo_screenwidth()}x{win.winfo_screenheight()}+0+0")


def _font(size):
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _palm(d, x, y, height):
    pts = [(x + 26 * (t / 10) ** 2, y - height * t / 10) for t in range(11)]
    for i in range(10):
        d.line([pts[i], pts[i + 1]], fill=(80, 52, 34, 255), width=max(3, 10 - i))
    tx, ty = pts[-1]
    L = height * 0.5
    for a in (-170, -140, -110, -75, -45, -12, 15, 190):
        rad = math.radians(a)
        ex_, ey_ = tx + L * math.cos(rad), ty + L * math.sin(rad) + L * 0.38
        cx, cy = tx + L * 0.55 * math.cos(rad), ty + L * 0.6 * math.sin(rad) - L * 0.28
        curve = []
        for k in range(13):
            t = k / 12
            curve.append(((1 - t) ** 2 * tx + 2 * (1 - t) * t * cx + t * t * ex_,
                          (1 - t) ** 2 * ty + 2 * (1 - t) * t * cy + t * t * ey_))
        d.line(curve, fill=(24, 104, 74, 255), width=6, joint="curve")
        d.line(curve, fill=(40, 140, 96, 255), width=2, joint="curve")


def make_scene(title, kind, path, size=(480, 320)):
    w, h = size
    top, bot, sea, sand = THEMES.get(kind, THEMES["Garden Room"])
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    hor = int(h * 0.58)
    for y in range(hor):
        t = y / hor
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    for y in range(hor, h):
        t = (y - hor) / (h - hor)
        d.line([(0, y), (w, y)], fill=tuple(int(sea[i] * (1 - t * 0.4)) for i in range(3)))
    o = ImageDraw.Draw(img, "RGBA")
    sx, sy = int(w * 0.72), int(hor * 0.6)
    for r, a in ((78, 35), (56, 60), (36, 255)):
        o.ellipse((sx - r, sy - r, sx + r, sy + r), fill=(255, 238, 176, a))
    rnd = random.Random(title)
    for i in range(16):
        y = hor + 6 + i * (h * 0.24 / 16)
        half = 8 + i * 3 + rnd.randint(0, 10)
        o.line([(sx - half, y), (sx + half, y)], fill=(255, 240, 190, 130), width=2)
    o.polygon([(0, h), (0, int(h * .87)), (int(w * .5), int(h * .8)), (w, int(h * .89)), (w, h)],
              fill=sand + (255,))
    _palm(o, int(w * 0.18), int(h * 0.92), int(h * 0.62))
    _palm(o, int(w * 0.86), int(h * 0.94), int(h * 0.44))
    o.rectangle((0, h - 44, w, h), fill=(11, 60, 73, 190))
    o.text((16, h - 22), title, fill="white", font=_font(max(15, h // 16)), anchor="lm")
    img.save(path)

def img_path(stored):
    """Turn what's in the database (a filename, or an old full path) into a path on THIS pc."""
    if not stored:
        return ""
    name = os.path.basename(stored.replace("\\", "/"))     # works for Windows and Linux paths
    return os.path.join(IMG_DIR, name)


def migrate_image_paths():
    """One-time cleanup: turn old absolute paths in rooms.image into plain filenames."""
    for r in q("SELECT id, image FROM rooms"):
        old = r["image"] or ""
        new = os.path.basename(old.replace("\\", "/"))
        if new != old:
            conn.execute("UPDATE rooms SET image=? WHERE id=?", (new, r["id"]))
    conn.commit()

def room_image(r):
    p = img_path(r["image"])
    if p and os.path.exists(p):
        return p
    p = os.path.join(IMG_DIR, slug(r["name"]) + ".png")
    if not os.path.exists(p):
        make_scene(r["name"], r["name"], p)
    return p

def load_photo(path, size, radius=0):
    try:
        img = ImageOps.fit(Image.open(path).convert("RGB"), size)
    except Exception:
        img = Image.new("RGB", size, "#dddddd")
    if radius:
        S = 4
        mask = Image.new("L", (size[0] * S, size[1] * S), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] * S - 1, size[1] * S - 1), radius * S, fill=255)
        img = img.convert("RGBA")
        img.putalpha(mask.resize(size, Image.LANCZOS))
    return ImageTk.PhotoImage(img)

def logo_photo(path, height):
    """Load the logo at a given height, keeping its proportions (no crop, no circle)."""
    try:
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        img = img.resize((max(1, round(w * height / h)), height), Image.LANCZOS)
    except Exception:
        img = Image.new("RGBA", (height, height), TEAL)   # fallback if the file is missing
    return ImageTk.PhotoImage(img)

# ============================================================ database
def init_db():
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE,
        password TEXT, role TEXT, fullname TEXT);
    CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY, number TEXT UNIQUE, name TEXT,
        capacity INTEGER, rate REAL, description TEXT, amenities TEXT, image TEXT,
        status TEXT DEFAULT 'Active', hk TEXT DEFAULT 'Clean');
    CREATE TABLE IF NOT EXISTS guests(id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT,
        address TEXT, id_no TEXT, vip INTEGER DEFAULT 0, notes TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, guest_id INTEGER, room_id INTEGER,
        check_in TEXT, check_out TEXT, adults INTEGER, children INTEGER, status TEXT,
        rate REAL, room_total REAL, addons_total REAL, discount REAL, tax REAL, total REAL,
        promo TEXT, notes TEXT, created TEXT, staff TEXT);
    CREATE TABLE IF NOT EXISTS booking_addons(id INTEGER PRIMARY KEY, booking_id INTEGER,
        name TEXT, qty INTEGER, price REAL);
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, booking_id INTEGER,
        amount REAL, method TEXT, kind TEXT, date TEXT, staff TEXT);
    CREATE TABLE IF NOT EXISTS addons(id INTEGER PRIMARY KEY, name TEXT UNIQUE, price REAL);
    CREATE TABLE IF NOT EXISTS promos(id INTEGER PRIMARY KEY, code TEXT UNIQUE, percent REAL,
        active INTEGER DEFAULT 1, expires TEXT, max_uses INTEGER DEFAULT 0,
        min_nights INTEGER DEFAULT 0, note TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    if not q1("SELECT 1 FROM users"):
        ex("INSERT INTO users(username,password,role,fullname) VALUES(?,?,?,?)",
           ("admin", hash_pw("admin123"), "admin", "Resort Manager"))
        ex("INSERT INTO users(username,password,role,fullname) VALUES(?,?,?,?)",
           ("staff", hash_pw("staff123"), "staff", "Front Desk"))
    if not q1("SELECT 1 FROM promos"):
        for code, pct, note in DEFAULT_PROMOS:
            conn.execute("INSERT INTO promos(code,percent,active,note,created) VALUES(?,?,?,?,?)",
                         (code, pct, 1, note, today().isoformat()))
        conn.commit()
    if not q1("SELECT 1 FROM addons"):
        for n, p in [("Breakfast Buffet", 350), ("Island Hopping Tour", 1800), ("Couples Massage", 1500),
                     ("Airport Transfer", 1200), ("Extra Bed", 800), ("Snorkeling Set", 400),
                     ("Bonfire Night", 1000), ("Kayak Rental", 500)]:
            conn.execute("INSERT INTO addons(name,price) VALUES(?,?)", (n, p))
        conn.commit()
    if not q1("SELECT 1 FROM rooms"):
        info = {
            "Garden Room": (2, 3500, "Cozy room facing the tropical garden with a private veranda.",
                            "Aircon • WiFi • Smart TV • Veranda"),
            "Deluxe Sea View": (3, 5500, "Spacious deluxe room with a king bed and a balcony overlooking the sea.",
                                "Aircon • WiFi • Balcony • Mini bar"),
            "Family Cottage": (5, 8500, "Two-bedroom cottage with a small kitchen, perfect for families.",
                               "Aircon • WiFi • Kitchenette • 2 Bedrooms"),
            "Pool Villa": (4, 12000, "Private villa with its own plunge pool and outdoor lounge area.",
                           "Private pool • WiFi • Butler • Outdoor shower"),
            "Overwater Bungalow": (2, 15500, "Stay above the crystal-clear lagoon with a glass floor panel.",
                                   "Glass floor • Sun deck • Jacuzzi • Breakfast"),
        }
        layout = [("101", "Garden Room"), ("102", "Garden Room"), ("103", "Garden Room"),
                  ("201", "Deluxe Sea View"), ("202", "Deluxe Sea View"), ("203", "Deluxe Sea View"),
                  ("301", "Family Cottage"), ("302", "Family Cottage"),
                  ("401", "Pool Villa"), ("402", "Pool Villa"),
                  ("501", "Overwater Bungalow"), ("502", "Overwater Bungalow")]
        for num, t in layout:
            cap, rate, desc, am = info[t]
            p = os.path.join(IMG_DIR, slug(t) + ".png")
            if not os.path.exists(p):
                make_scene(t, t, p)
            conn.execute("INSERT INTO rooms(number,name,capacity,rate,description,amenities,image) "
                         "VALUES(?,?,?,?,?,?,?)", (num, t, cap, rate, desc, am, os.path.basename(p)))
        conn.commit()

    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN actual_out TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass                                   # column already exists
    conn.execute("UPDATE bookings SET actual_out=? WHERE status='Checked-out' "
                 "AND actual_out IS NULL AND check_out>?", (today().isoformat(), today().isoformat()))
    conn.commit()

def load_settings():
    """Read the settings table into the module-level constants.
    These names are assigned here, not just read, so they must be declared `global`."""
    global VAT, WEEKEND_MULT, BACKUP_KEEP, DEFAULT_METHOD
    saved = {r["key"]: r["value"] for r in q("SELECT key, value FROM settings")}
    try:
        VAT = float(saved.get("vat", 12)) / 100
        WEEKEND_MULT = 1 + float(saved.get("weekend", 15)) / 100
        BACKUP_KEEP = int(float(saved.get("keep", 5)))
    except ValueError:
        pass                                    # junk in the table: keep the current values
    method = saved.get("pay_method", "Cash")
    DEFAULT_METHOD = method if method in METHODS else "Cash"

BOOKING_SQL = """
SELECT b.*, g.name AS guest, g.phone AS phone, r.number AS room_no, r.name AS room_type,
       (SELECT COALESCE(SUM(amount),0) FROM payments p WHERE p.booking_id=b.id) AS paid
FROM bookings b JOIN guests g ON g.id=b.guest_id JOIN rooms r ON r.id=b.room_id """


# ---------------------------------------------------------------- promo codes
def promo_info(code):
    return q1("SELECT * FROM promos WHERE code=?", (code.strip().upper(),)) if code else None


def promo_used(code):
    return q1("SELECT COUNT(*) FROM bookings WHERE promo=? AND status!='Cancelled'", (code,))[0]


def promo_status(p):
    if not p["active"]:
        return "Disabled"
    if p["expires"] and pdate(p["expires"]) < today():
        return "Expired"
    if p["max_uses"] and promo_used(p["code"]) >= p["max_uses"]:
        return "Used up"
    return "Active"


def check_promo(code, nights):
    """Returns (percent, error_message)."""
    p = promo_info(code)
    if not p:
        return 0, "That promo code does not exist."
    st = promo_status(p)
    if st != "Active":
        return 0, f"This promo code is {st.lower()}."
    if nights < (p["min_nights"] or 0):
        return 0, f"This code needs a stay of at least {p['min_nights']} night(s)."
    return p["percent"], ""


def promo_pct(code):
    p = promo_info(code or "")
    return p["percent"] if p else 0


# ---------------------------------------------------------------- pricing
def pricing(rate, ci, co, addons, pct):
    nights = (co - ci).days
    room = sum(rate * (WEEKEND_MULT if (ci + dt.timedelta(days=i)).weekday() in (4, 5) else 1.0)
               for i in range(nights))
    add = sum(qty * price for _, qty, price in addons)
    sub = room + add
    disc = sub * pct / 100
    tax = (sub - disc) * VAT
    return {"nights": nights, "room": room, "addons": add, "discount": disc,
            "tax": tax, "total": sub - disc + tax}


def room_free(room_id, ci, co, exclude=None):
    sql = ("SELECT COUNT(*) FROM bookings WHERE room_id=? AND status IN ('Reserved','Checked-in') "
           "AND check_in<? AND check_out>?")
    args = [room_id, co.isoformat(), ci.isoformat()]
    if exclude:
        sql += " AND id!=?"
        args.append(exclude)
    return q1(sql, args)[0] == 0


def available_rooms(ci, co, guests, rtype="All", exclude=None):
    rows = q("SELECT * FROM rooms WHERE status='Active' AND capacity>=? ORDER BY rate, number", (guests,))
    return [r for r in rows if (rtype == "All" or r["name"] == rtype) and room_free(r["id"], ci, co, exclude)]


def recalc_booking(bid):
    b = q1("SELECT * FROM bookings WHERE id=?", (bid,))
    addons = [(a["name"], a["qty"], a["price"]) for a in
              q("SELECT name,qty,price FROM booking_addons WHERE booking_id=?", (bid,))]
    p = pricing(b["rate"], pdate(b["check_in"]), pdate(b["check_out"]), addons, promo_pct(b["promo"]))
    ex("UPDATE bookings SET room_total=?,addons_total=?,discount=?,tax=?,total=? WHERE id=?",
       (p["room"], p["addons"], p["discount"], p["tax"], p["total"], bid))


def occupied_count(day, statuses=("Reserved", "Checked-in", "Checked-out")):
    ph = ",".join("?" * len(statuses))
    return q1(f"SELECT COUNT(*) FROM bookings WHERE status IN ({ph}) AND check_in<=? "
              "AND COALESCE(actual_out, check_out)>?",
              (*statuses, day.isoformat(), day.isoformat()))[0]

def active_rooms():
    return max(1, q1("SELECT COUNT(*) FROM rooms WHERE status='Active'")[0])


def seed_demo(staff):
    rnd = random.Random()
    names = ["Maria Santos", "Juan Dela Cruz", "Angela Reyes", "Mark Villanueva", "Sofia Ramirez",
             "Paolo Garcia", "Bea Mendoza", "Carlo Bautista", "Trisha Navarro", "Migo Fernandez",
             "Lea Castillo", "Ryan Aquino", "Nina Torres", "Jomar Pascual"]
    gids = []
    for i, n in enumerate(names):
        cur = ex("INSERT INTO guests(name,phone,email,vip,created) VALUES(?,?,?,?,?)",
                 (n, "09" + str(rnd.randint(100000000, 999999999)),
                  n.split()[0].lower() + "@mail.com", 1 if i % 6 == 0 else 0, today().isoformat()))
        gids.append(cur.lastrowid)
    rooms = q("SELECT * FROM rooms")
    addons = q("SELECT * FROM addons")
    made = tries = 0
    while made < 55 and tries < 600:
        tries += 1
        room = rnd.choice(rooms)
        ci = today() + dt.timedelta(days=rnd.randint(-80, 28))
        co = ci + dt.timedelta(days=rnd.randint(1, 5))
        if not room_free(room["id"], ci, co):
            continue
        chosen = [(a["name"], rnd.randint(1, 3), a["price"]) for a in rnd.sample(addons, rnd.randint(0, 3))]
        promo = rnd.choice(["", "", "", "WELCOME10"])
        pr = pricing(room["rate"], ci, co, chosen, promo_pct(promo))
        status = "Checked-out" if co <= today() else ("Checked-in" if ci <= today() else "Reserved")
        cur = ex("INSERT INTO bookings(guest_id,room_id,check_in,check_out,adults,children,status,rate,"
                 "room_total,addons_total,discount,tax,total,promo,notes,created,staff) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (rnd.choice(gids), room["id"], ci.isoformat(), co.isoformat(),
                  rnd.randint(1, min(2, room["capacity"])), 0, status, room["rate"], pr["room"],
                  pr["addons"], pr["discount"], pr["tax"], pr["total"], promo, "",
                  (ci - dt.timedelta(days=rnd.randint(3, 20))).isoformat(), staff))
        bid = cur.lastrowid
        for n, qt, pz in chosen:
            conn.execute("INSERT INTO booking_addons(booking_id,name,qty,price) VALUES(?,?,?,?)",
                         (bid, n, qt, pz))
        if status == "Reserved":
            amt, dte = round(pr["total"] * 0.3, 2), today() - dt.timedelta(days=rnd.randint(0, 5))
        else:
            amt, dte = pr["total"], min(co, today())
        conn.execute("INSERT INTO payments(booking_id,amount,method,kind,date,staff) VALUES(?,?,?,?,?,?)",
                     (bid, amt, rnd.choice(METHODS), "Deposit" if status == "Reserved" else "Payment",
                      dte.isoformat(), staff))
        conn.commit()
        made += 1


# ============================================================ modern widgets
_img_cache = {}


def rounded_img(w, h, r, fill, bg, border=None, bw=0):
    """Anti-aliased rounded rectangle as a PhotoImage."""
    w, h = max(2, int(w)), max(2, int(h))
    r = max(1, min(int(r), w // 2, h // 2))
    key = (w, h, r, fill, bg, border, bw)
    if key in _img_cache:
        return _img_cache[key]
    if len(_img_cache) > 400:
        _img_cache.clear()
    S = 4
    im = Image.new("RGB", (w * S, h * S), bg)
    d = ImageDraw.Draw(im)
    if border and bw:
        d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), r * S, fill=border)
        d.rounded_rectangle((bw * S, bw * S, w * S - 1 - bw * S, h * S - 1 - bw * S),
                            max(1, r - bw) * S, fill=fill)
    else:
        d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), r * S, fill=fill)
    ph = ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))
    _img_cache[key] = ph
    return ph


class Card(tk.Frame):
    """Rounded white card. Put widgets in card.body.
    fit=True  -> height follows content (use with fill='x' / grid).
    fit=False -> stretches to the space given by the parent (use with expand=True)."""

    def __init__(self, parent, fill=WHITE, radius=16, pad=14, border=BORDER, bw=1,
                 fit=False, width=1, height=1, bg=None):
        self.outer_bg = bg or parent.cget("bg")
        super().__init__(parent, bg=self.outer_bg)
        self.fill, self.radius, self.pad, self.border, self.bw, self.fit = fill, radius, pad, border, bw, fit
        self.canvas = tk.Canvas(self, bg=self.outer_bg, highlightthickness=0, bd=0, width=width, height=height)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=fill)
        self._bgitem = self.canvas.create_image(0, 0, anchor="nw")
        self._win = self.canvas.create_window(pad, pad, window=self.body, anchor="nw")
        self._size = (0, 0)
        self._req_h = height
        self.canvas.bind("<Configure>", self._on_canvas)
        if fit:
            self.body.bind("<Configure>", lambda e: self._sync_height())
            self.after_idle(self._fit)      # first measurement, once the contents are laid out

    def _on_canvas(self, e):
        self._size = (e.width, e.height)
        self._paint()
        kw = {"width": max(1, e.width - 2 * self.pad)}
        if not self.fit:
            kw["height"] = max(1, e.height - 2 * self.pad)
        self.canvas.itemconfig(self._win, **kw)

    def _sync_height(self):
        need = self.body.winfo_reqheight() + 2 * self.pad
        if abs(need - self._req_h) > 1:
            self._req_h = need
            self.canvas.config(height=need)

    def _fit(self):
        try:
            if not self.winfo_exists():
                return
            self.body.update_idletasks()    # make sure pack/grid inside the body has run
            self._sync_height()
        except tk.TclError:
            pass

    def _paint(self):
        w, h = self._size
        if w < 4 or h < 4:
            return
        self._ph = rounded_img(w, h, self.radius, self.fill, self.outer_bg, self.border, self.bw)
        self.canvas.itemconfig(self._bgitem, image=self._ph)
        self.canvas.tag_lower(self._bgitem)

    def set_border(self, color, bw=None):
        self.border = color
        if bw is not None:
            self.bw = bw
        self._paint()

_icon_cache = {}


def draw_icon(name, size, color):
    """Crisp anti-aliased icon with a transparent background. Add more icons here later."""
    key = (name, size, color)
    if key in _icon_cache:
        return _icon_cache[key]
    S = 8                                            # draw big, then shrink = smooth edges
    N = size * S
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if name == "search":
        lw = max(2 * S, round(size * 0.12 * S))      # stroke width
        c, r = 0.42 * N, 0.29 * N                    # lens centre + radius
        d.ellipse((c - r, c - r, c + r, c + r), outline=color, width=lw)
        a = r * 0.7071                               # handle starts on the lens edge (45 degrees)
        x1, y1, x2, y2 = c + a, c + a, 0.88 * N, 0.88 * N
        d.line([(x1, y1), (x2, y2)], fill=color, width=lw)
        d.ellipse((x2 - lw / 2, y2 - lw / 2, x2 + lw / 2, y2 + lw / 2), fill=color)   # rounded tip
    ph = ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS))
    _icon_cache[key] = ph
    return ph

class RButton(tk.Canvas):
    """Rounded, flat, hover-aware button (also used for pills when command=None).
    icon="search" draws an icon to the left of the text."""

    def __init__(self, parent, text="", command=None, color=TEAL, fg=WHITE, hover=None, padx=18,
                 height=38, radius=11, font=(F, 10, "bold"), align="center", bg=None, width=None,
                 icon=None, icon_size=16, gap=8):
        fg = readable(color, fg)
        bg = bg or parent.cget("bg")
        self._f = tkfont.Font(font=font)
        extra = (icon_size + gap) if icon else 0
        w = width or self._f.measure(text) + extra + 2 * padx
        super().__init__(parent, width=w, height=height, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2" if command else "arrow")
        self.bgc, self.command, self.radius, self.padx, self.align = bg, command, radius, padx, align
        self.base, self.hover = color, hover or shade(color, 0.9)
        self.fg, self.font, self.text, self.cur = fg, font, text, color
        self.icon_name, self.icon_size, self.gap = icon, icon_size, gap
        self._bw, self._bh = w, height          # renamed: tkinter reserves self._w
        self._img = self.create_image(0, 0, anchor="nw")
        self._txt = self.create_text(0, 0, text=text, fill=fg, font=font, anchor="w" if align == "w" else "center")
        self._ico = self.create_image(0, 0, anchor="w") if icon else None
        self._make_icon()
        self.bind("<Configure>", self._conf)
        if command:
            self.bind("<Enter>", lambda e: self._set(self.hover))
            self.bind("<Leave>", lambda e: self._set(self.base))
            self.bind("<ButtonRelease-1>", self._click)

    def _make_icon(self):
        if self._ico is not None:
            self._icph = draw_icon(self.icon_name, self.icon_size, self.fg)   # keep a reference
            self.itemconfig(self._ico, image=self._icph)

    def _conf(self, e):
        self._bw, self._bh = e.width, e.height
        self._paint()

    def _set(self, c):
        self.cur = c
        self._paint()

    def _paint(self):
        w, h = self._bw, self._bh
        if w < 4 or h < 4:
            return
        self._ph = rounded_img(w, h, self.radius, self.cur, self.bgc)
        self.itemconfig(self._img, image=self._ph)
        if self._ico is not None:                     # icon + text, centred together as one group
            tw = tkfont.Font(font=self.font).measure(self.text)
            x0 = self.padx if self.align == "w" else (w - (self.icon_size + self.gap + tw)) / 2
            self.coords(self._ico, x0, h / 2)
            self.coords(self._txt, x0 + self.icon_size + self.gap, h / 2)
            self.itemconfig(self._txt, anchor="w")
        elif self.align == "w":
            self.coords(self._txt, self.padx, h / 2)
        else:
            self.coords(self._txt, w / 2, h / 2)
        self.itemconfig(self._txt, text=self.text, fill=self.fg, font=self.font)

    def _click(self, e):
        if 0 <= e.x <= self._bw and 0 <= e.y <= self._bh and self.command:
            self.command()

    def set_text(self, t):
        self.text = t
        self._paint()

    def set_style(self, color=None, fg=None, font=None, hover=None):
        if color:
            self.base, self.cur = color, color
            self.hover = hover or shade(color, 0.9)
        if fg:
            self.fg = fg
        self.fg = readable(self.base, self.fg)
        if font:
            self.font = font
        self._make_icon()
        self._paint()

def btn(parent, text, cmd, color=TEAL, fg=WHITE, **kw):
    return RButton(parent, text, cmd, color=color, fg=fg, **kw)


def pill(parent, text, color, fg=WHITE):
    return RButton(parent, text, None, color=color, fg=fg, height=24, radius=12, padx=12, font=(F, 8, "bold"))


def avatar(parent, text, size=40, fill=TEAL, fg=WHITE, bg=None, font=None, dx=0, dy=-2):
    bg = bg or parent.cget("bg")
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
    c._ph = rounded_img(size, size, size // 2, fill, bg)
    c.create_image(0, 0, anchor="nw", image=c._ph)
    c.create_text(size / 2 + dx, size / 2 + dy, text=text, fill=fg,
                  font=font or (F, max(9, size // 3), "bold"), anchor="center")
    return c

def lbl_entry(parent, label, value="", bg=WHITE, width=None):
    tk.Label(parent, text=label, bg=bg, fg=MUTED, anchor="w", font=(F, 9)).pack(fill="x")
    e = ttk.Entry(parent, width=width) if width else ttk.Entry(parent)
    e.pack(fill="x", pady=(2, 9))
    if value not in (None, ""):
        e.insert(0, value)
    return e


def page_title(parent, title, sub=""):
    f = tk.Frame(parent, bg=BG)
    f.pack(fill="x", padx=26, pady=(20, 12))
    left = tk.Frame(f, bg=BG)
    left.pack(side="left")
    f.title_lbl = tk.Label(left, text=title, font=(F, 22, "bold"), bg=BG, fg=INK)
    f.title_lbl.pack(anchor="w")
    if sub:
        tk.Label(left, text=sub, font=(F, 10), bg=BG, fg=MUTED).pack(anchor="w")
    return f

def _sort_key(v):
    """Sort numbers, ₱ amounts, %, dates and text sensibly."""
    s = str(v).strip()
    t = s.replace("₱", "").replace(",", "").replace("%", "").replace("★", "").strip()
    try:
        return (0, float(t), "")
    except ValueError:
        pass
    try:
        return (0, dt.date.fromisoformat(s).toordinal(), "")
    except ValueError:
        pass
    if " / " in s:                                   # promo usage like "3 / 10"
        try:
            return (0, float(s.split(" / ")[0]), "")
        except ValueError:
            pass
    return (1, 0, s.lower())                         # text (and "-" / "No expiry") after numbers

def make_tree(parent, cols, heads, widths, height=None, natural=False):
    rows = height or 10
    card = Card(parent, radius=16, pad=8, width=(sum(widths) + 40) if natural else 200,
                height=rows * 38 + 56)
    tree = ttk.Treeview(card.body, columns=cols, show="headings", height=rows)
    state = {"col": None, "rev": False}

    def apply_sort():
        col = state["col"]
        if col is None:
            return
        items = [(_sort_key(tree.set(i, col)), i) for i in tree.get_children("")]
        items.sort(key=lambda x: x[0], reverse=state["rev"])
        for idx, (_, i) in enumerate(items):
            tree.move(i, "", idx)
        for c, h in zip(cols, heads):
            arrow = (" ▼" if state["rev"] else " ▲") if c == col else ""
            tree.heading(c, text=h.upper() + arrow)

    def sort_by(col):
        state["rev"] = (not state["rev"]) if state["col"] == col else False
        state["col"] = col
        apply_sort()

    for c, h, w in zip(cols, heads, widths):
        tree.heading(c, text=h.upper(), command=lambda c=c: sort_by(c))
        tree.column(c, width=w, anchor="center")
    tree.resort = apply_sort                 # call after reloading rows to keep the sort
    sb = ttk.Scrollbar(card.body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    for st, col in ROW_TINT.items():
        tree.tag_configure(st, background=col)
    return card, tree

def style_ax(ax, grid_axis="y"):
    ax.set_facecolor(WHITE)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#D5DEE0")
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.grid(axis=grid_axis, color="#E8EEEF", linewidth=1)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)


def rrect(c, x1, y1, x2, y2, r=8, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=WHITE):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", self._wheel_on)
        self.canvas.bind("<Leave>", self._wheel_off)
        self.inner.bind("<Enter>", self._wheel_on)
        self.bind("<Destroy>", self._on_destroy)

    # (names are _wheel_on/_wheel_off on purpose: tkinter itself uses _bind/_unbind internally)
    def _wheel_on(self, _=None):
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def _wheel_off(self, _=None):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(ev)

    def _on_destroy(self, e):
        if e.widget is self:
            self._wheel_off()


class DateEntry(tk.Frame):
    """Entry + calendar popup."""

    def __init__(self, parent, value=None, bg=WHITE, on_change=None, min_date=None):
        super().__init__(parent, bg=bg)
        self.on_change = on_change
        self.min_date = min_date
        self.var = tk.StringVar(value=value or today().isoformat())
        e = ttk.Entry(self, textvariable=self.var, width=11)
        e.pack(side="left", fill="x", expand=True)
        if on_change:
            e.bind("<KeyRelease>", lambda ev: on_change())
        tk.Button(self, text="📅", relief="flat", bg=bg, bd=0, cursor="hand2", activebackground=bg,
                  command=self.open).pack(side="left", padx=3)
        self.top = None

    def get(self):
        return self.var.get().strip()

    def set(self, v):
        self.var.set(v)

    def date(self):
        return pdate(self.get())

    def open(self):
        if self.top and self.top.winfo_exists():
            self.top.destroy()
        try:
            cur = self.date()
        except ValueError:
            cur = today()
        self.y, self.m = cur.year, cur.month
        self.top = tk.Toplevel(self)
        self.top.overrideredirect(True)
        self.top.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 2}")
        self.top.configure(bg=OCEAN, padx=1, pady=1)
        self.body = tk.Frame(self.top, bg=WHITE, padx=6, pady=6)
        self.body.pack()
        self.draw()

    def shift(self, delta):
        self.m += delta
        if self.m > 12:
            self.m, self.y = 1, self.y + 1
        if self.m < 1:
            self.m, self.y = 12, self.y - 1
        self.draw()

    def pick(self, d):
        self.var.set(dt.date(self.y, self.m, d).isoformat())
        self.top.destroy()
        if self.on_change:
            self.on_change()

    def draw(self):
        for w in self.body.winfo_children():
            w.destroy()
        head = tk.Frame(self.body, bg=WHITE)
        head.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 4))
        can_back = self.min_date is None or (self.y, self.m) > (self.min_date.year, self.min_date.month)
        tk.Button(head, text="◀", bg=WHITE, fg=OCEAN if can_back else "#C5D0D3", relief="flat", bd=0,
                  state="normal" if can_back else "disabled",
                  command=lambda: self.shift(-1)).pack(side="left")
        tk.Label(head, text=f"{pycal.month_name[self.m]} {self.y}", bg=WHITE, fg=INK,
                 font=(F, 10, "bold"), width=16).pack(side="left")
        tk.Button(head, text="▶", bg=WHITE, fg=OCEAN, relief="flat", bd=0, command=lambda: self.shift(1)).pack(side="left")
        tk.Button(head, text="✕", bg=WHITE, fg=MUTED, relief="flat", bd=0, command=self.top.destroy).pack(side="right")
        for i, d in enumerate("MTWTFSS"):
            tk.Label(self.body, text=d, bg=WHITE, fg=MUTED, font=(F, 9, "bold"), width=4).grid(row=1, column=i)
        for r, week in enumerate(pycal.monthcalendar(self.y, self.m)):
            for c, d in enumerate(week):
                if d == 0:
                    continue
                day = dt.date(self.y, self.m, d)
                is_today = day == today()
                blocked = self.min_date is not None and day < self.min_date
                if blocked:
                    tk.Label(self.body, text=str(d), width=3, bg=WHITE, fg="#C5D0D3",
                             font=(F, 9)).grid(row=r + 2, column=c, padx=1, pady=1)
                    continue
                tk.Button(self.body, text=str(d), width=3, relief="flat", bd=0,
                          bg=OCEAN if is_today else WHITE, activebackground=SEAFOAM,
                          fg=WHITE if is_today else (MUTED if c >= 5 else INK), cursor="hand2",
                          command=lambda d=d: self.pick(d)).grid(row=r + 2, column=c, padx=1, pady=1)

class Stepper(tk.Frame):
    """Modern  [ − | 2 | + ]  number picker. Use .get() like an Entry."""

    def __init__(self, parent, value=1, lo=0, hi=10, on_change=None, bg=WHITE, width=112, height=36):
        super().__init__(parent, bg=WHITE, width=width, height=height,
                         highlightthickness=1, highlightbackground="#D3DEE0", highlightcolor=TEAL)
        self.pack_propagate(False)
        self.lo, self.hi, self.on_change, self.value = lo, hi, on_change, value
        self.minus = self._btn("−", -1, "left")
        self.plus = self._btn("+", 1, "right")
        self.lbl = tk.Label(self, text=str(value), bg=WHITE, fg=INK, font=(F, 11, "bold"))
        self.lbl.pack(side="left", fill="both", expand=True)
        self._state()
        self.bind("<MouseWheel>", lambda e: self.step(1 if e.delta > 0 else -1))
        self.lbl.bind("<MouseWheel>", lambda e: self.step(1 if e.delta > 0 else -1))

    def _btn(self, text, d, side):
        b = tk.Label(self, text=text, width=3, bg=BG, fg=TEAL, font=(F, 13, "bold"), cursor="hand2")
        b.pack(side=side, fill="y")
        b.bind("<Button-1>", lambda e: self.step(d))
        b.bind("<Enter>", lambda e: b.config(bg="#E7EEEF") if b.cget("fg") == TEAL else None)
        b.bind("<Leave>", lambda e: b.config(bg=BG))
        return b

    def _state(self):
        self.minus.config(fg=TEAL if self.value > self.lo else "#B8C7CB")
        self.plus.config(fg=TEAL if self.value < self.hi else "#B8C7CB")

    def step(self, d):
        v = max(self.lo, min(self.hi, self.value + d))
        if v != self.value:
            self.value = v
            self.lbl.config(text=str(v))
            self._state()
            if self.on_change:
                self.on_change()

    def get(self):
        return str(self.value)
    
class Dialog(tk.Toplevel):
    """Modal window: opens centered over the app, blocks the window behind it, Esc closes it.
    Set self.dlg_size = (w, h) in a subclass to force a fixed size; otherwise it fits its content."""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.withdraw()                         # stay hidden until it has been centered
        self.title(title)
        self.configure(bg=WHITE)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.body = tk.Frame(self, bg=WHITE, padx=20, pady=16)    # was 26 / 22
        self.body.pack(fill="both", expand=True)
        self.result = False
        self.dlg_size = None
        self.bind("<Escape>", lambda e: self.destroy())
        self.after_idle(self._show)

    def _show(self):
        if not self.winfo_exists():
            return
        w, h = self.dlg_size or (None, None)
        center_window(self, w, h, self.master.winfo_toplevel())
        self.deiconify()
        style_titlebar(self)
        self.lift()
        self.focus_force()
        self.after(30, self._grab)

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

def form_grid(parent):
    """Two equal columns. Fill it with grid_entry() / grid_cell()."""
    g = tk.Frame(parent, bg=WHITE)
    g.pack(fill="x")
    g.grid_columnconfigure((0, 1), weight=1, uniform="fg")
    return g
 
 
def grid_cell(g, row, col, label, span=1):
    """A labelled slot in the form grid. Returns the frame to put your widget in."""
    px = (0, 0) if span == 2 else ((0, 6) if col == 0 else (6, 0))
    cell = tk.Frame(g, bg=WHITE)
    cell.grid(row=row, column=col, columnspan=span, sticky="new", padx=px, pady=(0, 10))
    tk.Label(cell, text=label, bg=WHITE, fg=MUTED, font=(F, 9), anchor="w").pack(fill="x", pady=(0, 3))
    return cell
 
 
def grid_entry(g, row, col, label, value="", span=1, show=None):
    cell = grid_cell(g, row, col, label, span)
    e = ttk.Entry(cell, show=show or "")
    e.pack(fill="x")
    if value not in (None, ""):
        e.insert(0, str(value))
    return e
 
 
def hint(parent, text):
    """Small grey helper text under a field (pass entry.master to put it under that entry)."""
    tk.Label(parent, text=text, bg=WHITE, fg=MUTED, font=(F, 8), anchor="w").pack(fill="x", pady=(2, 0))
 
 
class FormDialog(Dialog):
    """Base for input pop-ups: icon header, rounded section cards, Cancel / Save footer.
    Usage:  super().__init__(parent, title, icon, heading, sub)
            p = self.panel("Section name") ... build fields ...
            self.footer("Save", self.save, left=("Delete", self.delete))   # left= is optional
            self.finish()                                                   # always last"""
    W = 460
 
    def __init__(self, parent, title, icon, heading, sub="", tint=None, fg=TEAL, width=None):
        super().__init__(parent, title)
        self.configure(bg=BG)
        self.body.configure(bg=BG, padx=18, pady=16)
        self._cards = []
        tk.Frame(self.body, bg=BG, width=width or self.W, height=1).pack()      # minimum width
 
        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x", pady=(0, 12))
        avatar(head, icon, 44, tint or TINT["teal"], fg, bg=BG, font=(F, 16), dy=-1).pack(side="left")
        t = tk.Frame(head, bg=BG)
        t.pack(side="left", padx=12)
        tk.Label(t, text=heading, font=(F, 16, "bold"), bg=BG, fg=INK).pack(anchor="w")
        if sub:
            tk.Label(t, text=sub, font=(F, 9), bg=BG, fg=MUTED).pack(anchor="w")
 
    def panel(self, title=None):
        c = Card(self.body, fit=True, pad=14, radius=16)
        c.pack(fill="x", pady=(0, 10))
        self._cards.append(c)
        if title:
            tk.Label(c.body, text=title.upper(), font=(F, 8, "bold"), bg=WHITE, fg=MUTED).pack(anchor="w", pady=(0, 8))
        return c.body
 
    def footer(self, yes_text, yes_cmd, left=None):
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        items = []
        if left:
            items.append((left[0], left[1], "#FCEDEA", DANGER, 1))       # soft red (Delete)
        items.append(("Cancel", self.destroy, TINT["ocean"], INK, 1))
        items.append((yes_text, yes_cmd, TEAL, WHITE, 2))
        for i, (text, cmd, col, fg, w) in enumerate(items):
            row.grid_columnconfigure(i, weight=w, uniform="fb")
            btn(row, text, cmd, col, fg, height=40).grid(
                row=0, column=i, sticky="ew",
                padx=(0 if i == 0 else 4, 0 if i == len(items) - 1 else 4))
        self.bind("<Return>", lambda e: yes_cmd())
 
    def finish(self):
        """Measure the cards so the pop-up opens at the right height."""
        for c in self._cards:
            c._fit()

# ============================================================ invoice
def invoice_text(bid):
    b = q1(BOOKING_SQL + " WHERE b.id=?", (bid,))
    addons = q("SELECT name,qty,price FROM booking_addons WHERE booking_id=?", (bid,))
    pays = q("SELECT amount,method,kind,date FROM payments WHERE booking_id=? ORDER BY id", (bid,))
    W = 48
    line = "-" * W
    out = [RESORT.center(W), "Guest Invoice / Folio".center(W), line,
           f"Booking No : {ref(bid)}", f"Guest      : {b['guest']}", f"Phone      : {b['phone']}",
           f"Room       : {b['room_no']} - {b['room_type']}",
           f"Check-in   : {b['check_in']}", f"Check-out  : {b['check_out']}",
           f"Guests     : {b['adults']} adult(s), {b['children']} child(ren)",
           f"Status     : {b['status']}", line]
    n = (pdate(b["check_out"]) - pdate(b["check_in"])).days
    out.append(f"{'Room x ' + str(n) + ' night(s)':<30}{money(b['room_total']):>18}")
    for a in addons:
        out.append(f"{(a['name'] + ' x' + str(a['qty']))[:30]:<30}{money(a['qty'] * a['price']):>18}")
    if b["discount"]:
        out.append(f"{'Discount (' + (b['promo'] or '') + ')':<30}{'-' + money(b['discount']):>18}")
    out.append(f"{vat_label():<30}{money(b['tax']):>18}")
    out += [line, f"{'TOTAL':<30}{money(b['total']):>18}", line, "Payments:"]
    for p in pays:
        out.append(f"  {p['date']}  {p['method']:<14}{money(p['amount']):>16}")
    if not pays:
        out.append("  (none yet)")
    out += [line, f"{'Total paid':<30}{money(b['paid']):>18}",
            f"{'BALANCE DUE':<30}{money(b['total'] - b['paid']):>18}", line,
            "Thank you for staying with us!".center(W)]
    return "\n".join(out)


def show_invoice(parent, bid):
    d = Dialog(parent, f"Invoice {ref(bid)}")
    txt = invoice_text(bid)
    box = tk.Frame(d.body, bg=WHITE)
    box.pack(fill="both", expand=True)
    t = tk.Text(box, font=("Consolas", 10), bd=0, bg=WHITE, fg=INK, width=50, height=26,
                padx=10, pady=10, wrap="none")
    sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    t.insert("1.0", txt)
    t.config(state="disabled")

    def save():
        f = filedialog.asksaveasfilename(parent=d, defaultextension=".txt", initialfile=f"invoice_{ref(bid)}.txt")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(txt)
    row = tk.Frame(d.body, bg=WHITE)
    row.pack(pady=(12, 0))
    btn(row, "Save as .txt", save).pack(side="left", padx=4)
    btn(row, "Close", d.destroy, "#9FB4BC").pack(side="left", padx=4)


# ============================================================ ttk style
def setup_style(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    root.option_add("*TCombobox*Listbox.font", (F, 10))
    root.option_add("*TCombobox*Listbox.selectBackground", TEAL)
    root.option_add("*TCombobox*Listbox.selectForeground", WHITE)
    s.configure(".", font=(F, 10))
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("Treeview", rowheight=38, font=(F, 10), background=WHITE, fieldbackground=WHITE,
                foreground=INK, borderwidth=0, relief="flat")
    s.configure("Treeview.Heading", font=(F, 8, "bold"), background="#F1F5F6", foreground=MUTED,
                relief="flat", padding=(8, 10), borderwidth=0)
    s.map("Treeview.Heading", background=[("active", "#E7EEEF")])
    s.map("Treeview", background=[("selected", TEAL)], foreground=[("selected", WHITE)])
    for name in ("TEntry", "TSpinbox"):
        s.configure(name, fieldbackground=WHITE, foreground=INK, bordercolor="#D3DEE0", lightcolor="#D3DEE0",
                    darkcolor="#D3DEE0", padding=7, insertcolor=INK)
        s.map(name, bordercolor=[("focus", TEAL)], lightcolor=[("focus", TEAL)], darkcolor=[("focus", TEAL)])
    s.map("TEntry", fieldbackground=[("disabled", "#EEF3F4")], foreground=[("disabled", MUTED)])
    s.configure("TCombobox", fieldbackground=WHITE, background=WHITE, foreground=INK, bordercolor="#D3DEE0",
                lightcolor="#D3DEE0", darkcolor="#D3DEE0", arrowcolor=MUTED, padding=6)
    s.map("TCombobox", fieldbackground=[("readonly", WHITE)], foreground=[("readonly", INK)],
          bordercolor=[("focus", TEAL)], selectbackground=[("readonly", WHITE)],
          selectforeground=[("readonly", INK)], background=[("readonly", WHITE)])
    s.configure("Vertical.TScrollbar", troughcolor=BG, background="#C9D6D9", bordercolor=BG, lightcolor=BG,
                darkcolor=BG, arrowcolor=MUTED, relief="flat", gripcount=0)
    s.map("Vertical.TScrollbar", background=[("active", "#AFC0C4")])
    s.configure("W.TCheckbutton", background=WHITE, foreground=INK, font=(F, 10))
    s.map("W.TCheckbutton", background=[("active", WHITE)])


# ============================================================ login

class Slideshow(tk.Label):
    """Auto-playing crossfade slideshow. Drop your own photos in assets/slides/ (png/jpg);
    if the folder is empty it uses the generated room scenes."""

    def __init__(self, parent, size, interval=4000, steps=14):
        super().__init__(parent, bd=0, bg=OCEAN)
        self.size, self.interval, self.steps, self.i, self._job = size, interval, steps, 0, None
        self.imgs = [ImageOps.fit(Image.open(p).convert("RGB"), size) for p in self._paths(size)]
        self._show(self.imgs[0])
        if len(self.imgs) > 1:
            self._job = self.after(interval, self._fade, 0)
        self.bind("<Destroy>", self._stop)

    @staticmethod
    def _paths(size):
        folder = os.path.join(ASSETS_DIR, "slides")
        found = []
        if os.path.isdir(folder):
            found = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                           if f.lower().endswith((".png", ".jpg", ".jpeg")))
        if found:
            return found
        out = []
        for kind in THEMES:
            p = os.path.join(IMG_DIR, "slide_" + slug(kind) + ".png")
            if not os.path.exists(p):
                make_scene(kind, kind, p, size)
            out.append(p)
        return out

    def _show(self, pil):
        self._ph = ImageTk.PhotoImage(pil)       # keep a reference
        self.config(image=self._ph)

    def _fade(self, step):
        if not self.winfo_exists():
            return
        a = self.imgs[self.i]
        b = self.imgs[(self.i + 1) % len(self.imgs)]
        self._show(Image.blend(a, b, step / self.steps))
        if step < self.steps:
            self._job = self.after(40, self._fade, step + 1)
        else:
            self.i = (self.i + 1) % len(self.imgs)
            self._job = self.after(self.interval, self._fade, 0)

    def _stop(self, e=None):
        if e is not None and e.widget is not self:
            return
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass

class RField(tk.Frame):
    """Label + pill-shaped input. Use .get() / .focus() like an Entry."""

    def __init__(self, parent, label, show=None, width=380, height=50, bg=WHITE):
        super().__init__(parent, bg=bg)
        self.w, self.h, self.bgc, self.show = width, height, bg, show
        tk.Label(self, text=label, bg=bg, fg=TEAL, font=(F, 10, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 6))
        self.cv = tk.Canvas(self, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.cv.pack()
        self._img = self.cv.create_image(0, 0, anchor="nw")
        self.entry = tk.Entry(self.cv, bd=0, relief="flat", bg=BG, fg=INK,
                              insertbackground=INK, font=(F, 12), show=show or "")
        right = 70 if show else 22
        self.cv.create_window(22, height / 2, window=self.entry, anchor="w", width=width - 22 - right)
        if show:
            self.tog = self.cv.create_text(width - 22, height / 2, text="SHOW", anchor="e",
                                           fill=TEAL, font=(F, 8, "bold"), tags="tog")
            self.cv.tag_bind("tog", "<Button-1>", self._toggle)
            self.cv.tag_bind("tog", "<Enter>", lambda e: self.cv.config(cursor="hand2"))
            self.cv.tag_bind("tog", "<Leave>", lambda e: self.cv.config(cursor=""))
        self._paint(False)
        self.entry.bind("<FocusIn>", lambda e: self._paint(True))
        self.entry.bind("<FocusOut>", lambda e: self._paint(False))

    def _paint(self, focus):
        self._ph = rounded_img(self.w, self.h, self.h // 2, BG, self.bgc,
                               TEAL if focus else AQUA, 2 if focus else 1)
        self.cv.itemconfig(self._img, image=self._ph)
        self.cv.tag_lower(self._img)

    def _toggle(self, _=None):
        hidden = self.entry.cget("show") != ""
        self.entry.config(show="" if hidden else self.show)
        self.cv.itemconfig(self.tog, text="HIDE" if hidden else "SHOW")

    def get(self):
        return self.entry.get()

    def focus(self):
        self.entry.focus_set()

class Login(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(RESORT + " - Sign in")
        self.configure(bg=WHITE)
        setup_style(self)
        fullscreen(self)
        self.update_idletasks()
        self.user = None
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()

        # left: slideshow (fixed-width panel, image centered and cropped)
        left_w = int(sw * 0.58)
        left = tk.Frame(self, bg=TEAL, width=left_w)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        Slideshow(left, (left_w, sh)).place(relx=0.5, rely=0.5, anchor="center")

        # right: form
        right = tk.Frame(self, bg=WHITE)
        right.pack(side="right", fill="both", expand=True)
        form = tk.Frame(right, bg=WHITE)
        form.place(relx=0.5, rely=0.5, anchor="center")

        self.logo_img = logo_photo(LOGO_WELCOME_PATH, 80)      # keep a reference on self!
        tk.Label(form, image=self.logo_img, bg=WHITE, bd=0).pack(anchor="w", pady=(0, 26))
        tk.Label(form, text="Welcome back", font=(F, 30, "bold"), bg=WHITE, fg=INK).pack(anchor="w")
        tk.Frame(form, bg=GOLD, width=56, height=4).pack(anchor="w", pady=(8, 10))
        tk.Label(form, text="Sign in to The Cove reservation system", font=(F, 11),
                 bg=WHITE, fg=TEAL).pack(anchor="w", pady=(0, 30))

        self.e_user = RField(form, "Username")
        self.e_user.pack(pady=(0, 18))
        self.e_pass = RField(form, "Password", show="•")
        self.e_pass.pack(pady=(0, 28))

        btn(form, "Sign in", self.go, TEAL, WHITE, height=52, radius=26,
            font=(F, 12, "bold")).pack(fill="x")
        tk.Label(form, text="admin / admin123   •   staff / staff123", font=(F, 9),
                 bg=WHITE, fg=TEAL).pack(pady=(22, 0))

        self.bind("<Return>", lambda e: self.go())
        self.bind("<Escape>", lambda e: self.destroy())
        self.e_user.focus()

    def go(self):
        r = q1("SELECT username, role, fullname FROM users WHERE username=? AND password=?",
               (self.e_user.get().strip(), hash_pw(self.e_pass.get())))
        if r:
            self.user = (r["username"], r["role"], r["fullname"])
            backups.log_action(LOG_PATH, self.user[0], "Signed in") 
            self.destroy()
        else:
            messagebox.showerror("Sign in failed", "Wrong username or password.")

# ============================================================ pages
class Page(tk.Frame):
    def __init__(self, app):
        super().__init__(app.content, bg=BG)
        self.app = app

    def refresh(self):
        pass

def autofit(lbl, container, text_fn, max_size, min_size=7, weight="bold", reserve=0):
    """Shrink lbl's font until text_fn() fits inside container's width.
    reserve = pixels in the container used by other things (icons, padding)."""
    font = tkfont.Font(family=F, size=max_size, weight=weight)
    lbl.config(font=font)

    def fit(_=None):
        avail = container.winfo_width() - reserve
        if avail <= 1:
            return
        text = text_fn()
        size = max_size
        font.configure(size=size)
        while size > min_size and font.measure(text) > avail:
            size -= 1
            font.configure(size=size)

    container.bind("<Configure>", fit, add="+")
    return fit

def kpi_card(parent, col, icon, label, tint, color=INK):
    card = Card(parent, fit=True, pad=14, radius=18)
    card.grid(row=0, column=col, padx=6, sticky="ew")

    top = tk.Frame(card.body, bg=WHITE)
    top.pack(fill="x")
    avatar(top, icon, 34, TINT[tint], INK, font=(F, 12)).pack(side="left")
    lab = tk.Label(top, text=label, bg=WHITE, fg=MUTED, anchor="w")
    lab.pack(side="left", padx=8)
    # reserve = avatar (34) + label padding (16) + a little safety margin
    autofit(lab, top, lambda: label, max_size=9, min_size=6, reserve=34 + 16 + 6)

    v = tk.StringVar(value="-")
    val = tk.Label(card.body, textvariable=v, bg=WHITE, fg=color, anchor="w")
    val.pack(anchor="w", pady=(12, 0), fill="x")
    fit_val = autofit(val, card.body, v.get, max_size=20, min_size=10, reserve=6)
    v.trace_add("write", lambda *a: fit_val())     # re-fit whenever the number changes
    return v

# ------------------------------------------------------------ dashboard
class DashboardPage(Page):
    def __init__(self, app):
        super().__init__(app)
        self.head = page_title(self, "Dashboard", "Here's what's happening at the resort today")
        btn(self.head, "＋  New reservation", lambda: app.new_booking(), CORAL).pack(side="right")
        if app.role == "admin":
            btn(self.head, "Load demo data", self.demo, CREAM, INK).pack(side="right", padx=(0, 8))
        tk.Label(self.head, text=today().strftime("%A, %d %B %Y"), bg=CREAM, fg=INK,
                 font=(F, 9, "bold"), padx=14, pady=8).pack(side="right", padx=(0, 12))
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=20)
        self.kpi = {}
        for i, (key, icon, label, tint) in enumerate([
                ("arr", "🛬", "Arrivals today", "teal"), ("dep", "🛫", "Departures today", "coral"),
                ("inh", "👥", "In-house guests", "ocean"), ("occ", "📊", "Occupancy tonight", "gold"),
                ("rev", "💰", "Collected this month", "teal"), ("due", "🧾", "Outstanding balance", "coral")]):
            row.grid_columnconfigure(i, weight=1, uniform="k")
            self.kpi[key] = kpi_card(row, i, icon, label, tint)
        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=26, pady=(12, 18))
        right = tk.Frame(mid, bg=BG, width=440)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        left = Card(mid, pad=12)
        left.pack(side="left", fill="both", expand=True)
        self.fig = Figure(figsize=(5, 3), dpi=100, facecolor=WHITE)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=left.body)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        tk.Label(right, text="Today's arrivals  (double-click for details)", font=(F, 11, "bold"), bg=BG, fg=INK).pack(anchor="w", pady=(0, 6))
        f1, self.t_arr = make_tree(right, ("ref", "guest", "room"), ("Ref", "Guest", "Room"), (80, 210, 90), 4)
        f1.pack(fill="both", expand=True)
        tk.Label(right, text="Today's departures", font=(F, 11, "bold"), bg=BG, fg=INK).pack(anchor="w", pady=(14, 6))
        f2, self.t_dep = make_tree(right, ("ref", "guest", "room"), ("Ref", "Guest", "Room"), (80, 210, 90), 4)
        f2.pack(fill="both", expand=True)
        for tree in (self.t_arr, self.t_dep):
            tree.bind("<Double-1>", lambda e, t=tree: self.open_details(t, e))
        self.empty = {}
        for tree, msg in ((self.t_arr, "No arrivals today"), (self.t_dep, "No departures today")):
            self.empty[tree] = tk.Label(tree, text=msg, bg=WHITE, fg=MUTED, font=(F, 10))

    def open_details(self, tree, e):
        row = tree.identify_row(e.y)
        if row:
            BookingDetailDialog(self.app, int(row))

    def demo(self):
        if messagebox.askyesno("Demo data", "Add sample guests and bookings for testing?"):
            seed_demo(self.app.username)
            self.refresh()

    def refresh(self):
        h = dt.datetime.now().hour
        greet = "Good morning" if h < 12 else ("Good afternoon" if h < 18 else "Good evening")
        self.head.title_lbl.config(text=f"{greet}, {self.app.fullname.split()[0]} 👋")
        t = today().isoformat()
        arr = q(BOOKING_SQL + " WHERE b.status='Reserved' AND b.check_in=?", (t,))
        dep = q(BOOKING_SQL + " WHERE b.status='Checked-in' AND b.check_out=?", (t,))
        inh = q1("SELECT COALESCE(SUM(adults+children),0) FROM bookings WHERE status='Checked-in'")[0]
        occ = occupied_count(today(), ("Reserved", "Checked-in"))
        month = today().strftime("%Y-%m")
        rev = q1("SELECT COALESCE(SUM(amount),0) FROM payments WHERE substr(date,1,7)=?", (month,))[0]
        due = sum(b["total"] - b["paid"] for b in q(BOOKING_SQL + " WHERE b.status IN ('Reserved','Checked-in')"))
        self.kpi["arr"].set(str(len(arr)))
        self.kpi["dep"].set(str(len(dep)))
        self.kpi["inh"].set(str(inh))
        self.kpi["occ"].set(f"{occ / active_rooms() * 100:.0f}%")
        self.kpi["rev"].set(money(rev))
        self.kpi["due"].set(money(due))
        for tree, rows in ((self.t_arr, arr), (self.t_dep, dep)):
            tree.delete(*tree.get_children())
            for b in rows:
                tree.insert("", "end", iid=str(b["id"]), values=(ref(b["id"]), b["guest"], b["room_no"]))
            if rows:
                self.empty[tree].place_forget()
            else:
                self.empty[tree].place(relx=0.5, rely=0.55, anchor="center")
        days = [today() + dt.timedelta(days=i) for i in range(14)]
        vals = [occupied_count(d, ("Reserved", "Checked-in")) / active_rooms() * 100 for d in days]
        self.ax.clear()
        style_ax(self.ax)
        bars = self.ax.bar([d.strftime("%d\n%a") for d in days], vals, width=0.6,
                           color=[GOLD if v >= 90 else OCEAN for v in vals])
        self.ax.bar_label(bars, labels=[f"{v:.0f}%" if v else "" for v in vals],
                          padding=3, color=INK, fontsize=8)
        self.ax.set_ylim(0, 105)
        self.ax.set_title("Occupancy - next 14 days", loc="left", fontweight="bold", color=INK, fontsize=12, pad=14)
        self.fig.tight_layout()
        self.canvas.draw()


# ------------------------------------------------------------ new reservation (modal)
class BookingPage(Page):
    """New reservation, shown inside the main window (no pop-up)."""

    def __init__(self, app):
        super().__init__(app)
        self.photos, self.cards = [], {}

    def on_guests(self):
        self.auto_search()

    def start(self, room=None, check_in=None, check_out=None, guest=None):
        """Called every time the user opens 'New Reservation' (optionally pre-filled)."""
        if getattr(self, "_job", None):
            self.after_cancel(self._job)
            self._job = None
        for w in self.winfo_children():          # wipe the previous form
            w.destroy()
        self.photos, self.cards = [], {}
        self.sel_room = room
        self.ci = self.co = None
        self.promo_pct, self.promo_code, self.touched = 0, "", False


        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=26, pady=(20, 18))

        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="New reservation", font=(F, 22, "bold"), bg=BG, fg=INK).pack(side="left")
        tk.Label(head, text="Search availability, pick a room, confirm", font=(F, 10), bg=BG,
                 fg=MUTED).pack(side="left", padx=14, pady=(10, 0))
        btn(head, "Cancel", lambda: self.app.show("dash"), "#E7EEEF", INK, height=34, padx=14).pack(side="right")
        
        content = tk.Frame(self.body, bg=BG)
        content.pack(fill="both", expand=True)
        right = Card(content, width=400, pad=4)
        right.pack(side="right", fill="y", padx=(14, 0))
        left = tk.Frame(content, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        # ---- search bar: live results
        bar_card = Card(left, fit=True, pad=14)
        bar_card.pack(fill="x")
        bar = bar_card.body
        for col, txt in enumerate(("Check-in", "Check-out", "Adults", "Children", "Room type")):
            tk.Label(bar, text=txt, bg=WHITE, fg=MUTED, font=(F, 9)).grid(
                row=0, column=col, sticky="w", padx=(0 if col == 0 else 14, 0), pady=(0, 3))
        ci = check_in or today()
        co = check_out or (ci + dt.timedelta(days=2))
        self.d_in = DateEntry(bar, ci.isoformat(), on_change=self.auto_search, min_date=today())
        self.d_in.grid(row=1, column=0, sticky="w")
        self.d_out = DateEntry(bar, co.isoformat(), on_change=self.auto_search, min_date=today())
        self.d_out.grid(row=1, column=1, sticky="w", padx=(14, 0))
        self.adults = Stepper(bar, 2, 1, 10, on_change=self.on_guests)
        self.adults.grid(row=1, column=2, sticky="w", padx=(14, 0))
        self.kids = Stepper(bar, 0, 0, 10, on_change=self.on_guests)
        self.kids.grid(row=1, column=3, sticky="w", padx=(14, 0))
        self.rtype = ttk.Combobox(bar, state="readonly", width=18)
        self.rtype.grid(row=1, column=4, sticky="w", padx=(14, 0))
        self.rtype.bind("<<ComboboxSelected>>", lambda e: self.auto_search())

        # search a specific room (number, type, amenity...)
        tk.Label(bar, text="Search room", bg=WHITE, fg=MUTED, font=(F, 9)).grid(
            row=2, column=0, columnspan=5, sticky="w", pady=(12, 3))
        self.q_var = tk.StringVar()
        self.q_var.trace_add("write", lambda *a: self.auto_search())
        ttk.Entry(bar, textvariable=self.q_var).grid(row=3, column=0, columnspan=5, sticky="ew")

        # right: stay summary (never wraps, never gets cut)
        bar.grid_columnconfigure(5, weight=1)
        hint = tk.Frame(bar, bg=WHITE)
        hint.grid(row=0, column=5, rowspan=4, sticky="ne", padx=(16, 4))
        self.hint_main = tk.Label(hint, text="", bg=WHITE, fg=TEAL, font=(F, 16, "bold"), anchor="e")
        self.hint_main.pack(anchor="e")
        self.hint_sub = tk.Label(hint, text="", bg=WHITE, fg=MUTED, font=(F, 9), anchor="e")
        self.hint_sub.pack(anchor="e")

        # full-width warning banner (hidden unless something is wrong)
        self.warn = tk.Label(bar, text="", bg="#FDEEEA", fg=DANGER, font=(F, 10, "bold"),
                             anchor="w", padx=14, pady=8)
        self.warn.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(12, 0))
        self.warn.grid_remove()
        self.res = ScrollFrame(left, bg=BG)
        self.res.pack(fill="both", expand=True, pady=(12, 0))

        # ---- right column: summary + confirm pinned at the bottom, form scrolls above it
        foot = tk.Frame(right.body, bg=WHITE, padx=14, pady=8)
        foot.pack(side="bottom", fill="x")
        self.sum_lbl = tk.Label(foot, text="Select a room to see the price.", justify="left", anchor="w",
                                font=("Consolas", 9), bg=SEAFOAM, fg=INK, padx=12, pady=10)
        self.sum_lbl.pack(fill="x")
        btn(foot, "Confirm reservation", self.confirm, CORAL, height=44).pack(fill="x", pady=(8, 0))

        sf = ScrollFrame(right.body, bg=WHITE)
        sf.pack(fill="both", expand=True)
        p = tk.Frame(sf.inner, bg=WHITE, padx=14, pady=10)
        p.pack(fill="both", expand=True)
        tk.Label(p, text="Guest details", font=(F, 13, "bold"), bg=WHITE, fg=INK).pack(anchor="w", pady=(0, 8))
        tk.Label(p, text="Returning guest? pick one", bg=WHITE, fg=MUTED, font=(F, 9)).pack(anchor="w")
        self.g_pick = ttk.Combobox(p, state="readonly")
        self.g_pick.pack(fill="x", pady=(2, 9))
        self.g_pick.bind("<<ComboboxSelected>>", self.fill_guest)
        self.g_name = lbl_entry(p, "Full name *")
        self.g_phone = lbl_entry(p, "Phone *")
        self.g_email = lbl_entry(p, "Email")
        tk.Label(p, text="Add-ons & activities", font=(F, 13, "bold"), bg=WHITE, fg=INK).pack(anchor="w", pady=(8, 6))
        self.addon_rows = []
        for a in q("SELECT * FROM addons ORDER BY id"):
            row = tk.Frame(p, bg=WHITE)
            row.pack(fill="x", pady=1)
            v, qv = tk.IntVar(), tk.StringVar(value="1")
            ttk.Checkbutton(row, text=f"{a['name']}  ({money(a['price'])})", variable=v,
                            style="W.TCheckbutton", command=self.summary).pack(side="left")
            ttk.Spinbox(row, from_=1, to=20, width=3, textvariable=qv, command=self.summary).pack(side="right")
            self.addon_rows.append((a, v, qv))
        tk.Label(p, text="Promo code", bg=WHITE, fg=MUTED, font=(F, 9)).pack(anchor="w", pady=(10, 0))
        pr = tk.Frame(p, bg=WHITE)
        pr.pack(fill="x", pady=(2, 8))
        self.promo = ttk.Entry(pr)
        self.promo.pack(side="left", fill="x", expand=True)
        btn(pr, "Apply", self.apply_promo, TEAL, height=34).pack(side="left", padx=(8, 0))
        self.promo_msg = tk.Label(p, text="", bg=WHITE, font=(F, 9), anchor="w")
        self.promo_msg.pack(fill="x", pady=(0, 6))
        self.promo.bind("<KeyRelease>", self.promo_edited)

        tk.Label(p, text="Deposit now (₱)", bg=WHITE, fg=MUTED, font=(F, 9)).pack(anchor="w")
        self.dep = ttk.Entry(p)
        self.dep.pack(fill="x", pady=(2, 8))
        self.dep.bind("<KeyRelease>", lambda e: setattr(self, "touched", True))
        tk.Label(p, text="Payment method", bg=WHITE, fg=MUTED, font=(F, 9)).pack(anchor="w")
        self.method = ttk.Combobox(p, values=METHODS, state="readonly")
        self.method.set(DEFAULT_METHOD)
        self.method.pack(fill="x", pady=(2, 8))
        self.notes = lbl_entry(p, "Special requests")

        # ---- fill lists / pre-fills, then show the first results
        types = [r["name"] for r in q("SELECT DISTINCT name FROM rooms ORDER BY name")]
        self.rtype.config(values=["All"] + types)
        self.rtype.set(room["name"] if room else "All")
        self.g_pick.config(values=[f"{g['name']} • {g['phone']}" for g in q("SELECT name,phone FROM guests ORDER BY name")])
        if guest:
            for e, v in ((self.g_name, guest["name"]), (self.g_phone, guest["phone"]), (self.g_email, guest["email"] or "")):
                e.insert(0, v)
        self.search(silent=True)

    def auto_search(self, *_):
        try:
            nxt = self.d_in.date() + dt.timedelta(days=1)
            self.d_out.min_date = max(today() + dt.timedelta(days=1), nxt)
            if self.d_out.date() <= self.d_in.date():      # push check-out forward automatically
                self.d_out.set(nxt.isoformat())
        except ValueError:
            pass
        if getattr(self, "_job", None):
            self.after_cancel(self._job)
        self._job = self.after(350, lambda: self.search(silent=True))

    def set_hint(self, main, sub="", bad=False):
        if bad:
            self.hint_main.config(text="")
            self.hint_sub.config(text="")
            self.warn.config(text="⚠  " + main + (f"  •  {sub}" if sub else ""))
            self.warn.grid()
        else:
            self.warn.grid_remove()
            self.hint_main.config(text=main)
            self.hint_sub.config(text=sub)

    def clear_results(self):
        for w in self.res.inner.winfo_children():
            w.destroy()
        self.photos.clear()
        self.cards.clear()
        self.sel_room = None
        self.summary()

    def fill_guest(self, _=None):
        phone = self.g_pick.get().split(" • ")[-1]
        g = q1("SELECT * FROM guests WHERE phone=?", (phone,))
        if g:
            for e, v in ((self.g_name, g["name"]), (self.g_phone, g["phone"]), (self.g_email, g["email"] or "")):
                e.delete(0, "end")
                e.insert(0, v)

    def search(self, silent=False):
        try:
            ci, co = self.d_in.date(), self.d_out.date()
            guests = int(self.adults.get()) + int(self.kids.get())
        except ValueError:
            self.set_hint("Check the dates", "Use YYYY-MM-DD and whole numbers", True)
            self.clear_results()
            if not silent:
                messagebox.showwarning("Invalid", "Use dates as YYYY-MM-DD and numbers for guests.", parent=self)
            return
        if co <= ci:
            self.set_hint("Check-out must be after check-in", "", True)
            self.clear_results()
            if not silent:
                messagebox.showwarning("Dates", "Check-out must be after check-in.", parent=self)
            return
        if ci < today():
            self.set_hint("Check-in is in the past", "", True)
            self.clear_results()
            if not silent:
                messagebox.showwarning("Dates", "Check-in cannot be in the past.", parent=self)
            return
        self.ci, self.co = ci, co
        n = (co - ci).days
        self.set_hint(f"{n} night{'s' if n != 1 else ''}", f"{guests} guest{'s' if guests != 1 else ''}")
        if self.promo_code:                       # re-validate promo for the new stay length
            pct, msg = check_promo(self.promo_code, (co - ci).days)
            if msg:
                self.promo_pct, self.promo_code = 0, ""
                self.promo.delete(0, "end")
                self.set_promo_msg(msg)
                if not silent:
                    messagebox.showinfo("Promo removed", msg, parent=self)
            else:
                self.promo_pct = pct
        rooms = available_rooms(ci, co, guests, self.rtype.get() or "All")
        kw = self.q_var.get().strip().lower()
        if kw:
            rooms = [r for r in rooms if kw in " ".join(
                (r["number"], r["name"], r["description"] or "", r["amenities"] or "")).lower()]
        for w in self.res.inner.winfo_children():
            w.destroy()
        self.photos.clear()
        self.cards.clear()
        dropped = None
        if self.sel_room and self.sel_room["id"] not in [r["id"] for r in rooms]:
            dropped = self.sel_room
            self.sel_room = None
        self.guests = guests

        if dropped:
            if dropped["capacity"] < guests:
                why = (f"Room {dropped['number']} ({dropped['name']}) fits only "
                       f"{dropped['capacity']} guests, but this reservation has {guests}.")
            else:
                why = f"Room {dropped['number']} ({dropped['name']}) is not available for those dates."
            tk.Label(self.res.inner, text="⚠  " + why + " Please choose another room.",
                     bg="#FFF8E1", fg=INK, font=(F, 10), anchor="w", justify="left",
                     wraplength=560, padx=12, pady=8).pack(fill="x", pady=(0, 6))

        if not rooms:
            biggest = q1("SELECT MAX(capacity) FROM rooms WHERE status='Active'")[0] or 0
            if guests > biggest:
                msg = (f"😕  No single room fits {guests} guests (the largest fits {biggest}).\n"
                       "Reduce the guest count, or make two separate reservations.")
            elif kw:
                msg = f"😕  No available rooms match “{kw}”.\nTry a different keyword or clear the search."
            else:
                msg = "😕  No rooms available for those dates / guests.\nTry other dates or a different room type."
            tk.Label(self.res.inner, text=msg, bg=BG, fg=MUTED, font=(F, 11), pady=40).pack()
        for r in rooms:
            card = Card(self.res.inner, fit=True, pad=12)
            card.pack(fill="x", pady=6)
            b = card.body
            ph = load_photo(room_image(r), (180, 120), 12)
            self.photos.append(ph)
            tk.Label(b, image=ph, bg=WHITE).pack(side="left", padx=(0, 12))
            side = tk.Frame(b, bg=WHITE)
            side.pack(side="right", padx=(8, 0))
            info = tk.Frame(b, bg=WHITE)
            info.pack(side="left", fill="both", expand=True)
            tk.Label(info, text=f"{r['name']}", font=(F, 12, "bold"), bg=WHITE, fg=INK, anchor="w").pack(fill="x")
            tk.Label(info, text=f"Room {r['number']}  •  👥 up to {r['capacity']} guests", bg=WHITE, fg=MUTED,
                     anchor="w", font=(F, 9)).pack(fill="x")
            tk.Label(info, text=r["description"], wraplength=230, justify="left", bg=WHITE, fg=INK,
                     anchor="w", font=(F, 9)).pack(fill="x", pady=3)
            tk.Label(info, text=r["amenities"], bg=WHITE, fg=TEAL, anchor="w", font=(F, 8, "bold"),
                     wraplength=230, justify="left").pack(fill="x")
            pr = pricing(r["rate"], ci, co, [], 0)
            tk.Label(side, text=money(r["rate"]).replace(".00", ""), font=(F, 15, "bold"), bg=WHITE, fg=CORAL).pack()
            tk.Label(side, text="per night", bg=WHITE, fg=MUTED, font=(F, 8)).pack()
            tk.Label(side, text=f"{pr['nights']} night(s)  •  {money(pr['room']).replace('.00', '')}", bg=WHITE,
                     fg=INK, font=(F, 9)).pack(pady=6)
            btn(side, "Select", lambda r=r: self.select(r), TEAL, height=34).pack(fill="x")
            self.cards[r["id"]] = card
        if self.sel_room:
            self.select(self.sel_room)
        else:
            self.summary()

    def select(self, r):
        self.sel_room = r
        for rid, c in self.cards.items():
            c.set_border(CORAL if rid == r["id"] else BORDER, 2 if rid == r["id"] else 1)
        self.touched = False
        self.summary()

    def addons(self):
        out = []
        for a, v, qv in self.addon_rows:
            if v.get():
                try:
                    n = max(1, int(qv.get()))
                except ValueError:
                    n = 1
                out.append((a["name"], n, a["price"]))
        return out

    def set_promo_msg(self, text, ok=False):
        self.promo_msg.config(text=text, fg=TEAL if ok else DANGER)

    def promo_edited(self, _=None):
        """Typing in the box removes any applied discount until Apply is clicked again."""
        if self.promo.get().strip().upper() != self.promo_code:
            self.promo_pct, self.promo_code = 0, ""
            self.promo_msg.config(text="")
            self.summary()

    def apply_promo(self):
        """Returns True if the box is empty or the code is valid and applied."""
        code = self.promo.get().strip().upper()
        if not code:
            self.promo_pct, self.promo_code = 0, ""
            self.promo_msg.config(text="")
        elif not self.ci:
            self.set_promo_msg("Pick valid dates first, then apply the code.")
            return False
        else:
            pct, msg = check_promo(code, (self.co - self.ci).days)
            if msg:
                self.promo_pct, self.promo_code = 0, ""
                self.promo.delete(0, "end")          # don't leave a dead code in the box
                self.set_promo_msg(msg)
                self.summary()
                return False
            self.promo_pct, self.promo_code = pct, code
            self.set_promo_msg(f"✔ {code}: {pct:g}% off", True)
        self.summary()
        return True

    def summary(self):
        if not self.sel_room or not self.ci:
            self.sum_lbl.config(text="Select a room to see the price.")
            return
        r = self.sel_room
        p = pricing(r["rate"], self.ci, self.co, self.addons(), self.promo_pct)
        lines = [f"{r['name']} {r['number']}", f"{self.ci} -> {self.co} ({p['nights']} nights)",
                 "-" * 34, f"{'Room':<16}{money(p['room']):>18}", f"{'Add-ons':<16}{money(p['addons']):>18}"]
        if p["discount"]:
            lines.append(f"{'Discount':<16}{'-' + money(p['discount']):>18}")
        lines += [f"{vat_label():<16}{money(p['tax']):>18}", "-" * 34, f"{'TOTAL':<16}{money(p['total']):>18}"]
        self.sum_lbl.config(text="\n".join(lines))
        if not self.touched:
            self.dep.delete(0, "end")
            self.dep.insert(0, f"{p['total'] * 0.3:.2f}")

    def confirm(self):
        if not self.sel_room:
            messagebox.showwarning("Room", "Select a room first.", parent=self)
            return
        try:
            adults, kids = int(self.adults.get()), int(self.kids.get())
        except ValueError:
            messagebox.showwarning("Guests", "Adults and children must be numbers.", parent=self)
            return
        if (self.ci is None or self.d_in.get() != self.ci.isoformat()
                or self.d_out.get() != self.co.isoformat()):
            messagebox.showwarning("Dates", "Please enter valid dates first (see the note at the top right).", parent=self)
            return
        if adults + kids > self.sel_room["capacity"]:
            messagebox.showwarning(
                "Too many guests",
                f"Room {self.sel_room['number']} ({self.sel_room['name']}) fits up to "
                f"{self.sel_room['capacity']} guests, but you entered {adults + kids}.\n\n"
                "Choose a larger room or reduce the number of guests.", parent=self)
            self.search(silent=True)
            return
        name, phone = self.g_name.get().strip(), self.g_phone.get().strip()
        if not name or not phone:
            messagebox.showwarning("Guest", "Guest name and phone are required.", parent=self)
            return
        if self.promo.get().strip().upper() != self.promo_code:     # typed but not applied
            if not self.apply_promo():
                messagebox.showwarning("Promo code", self.promo_msg.cget("text") or "Invalid promo code.", parent=self)
                return
        if self.promo_code:
            pct, msg = check_promo(self.promo_code, (self.co - self.ci).days)
            if msg:
                messagebox.showwarning("Promo code", msg, parent=self)
                self.promo_pct, self.promo_code = 0, ""
                self.promo.delete(0, "end")
                self.summary()
                return
            self.promo_pct = pct
        p = pricing(self.sel_room["rate"], self.ci, self.co, self.addons(), self.promo_pct)
        try:
            dep = float(self.dep.get() or 0)
        except ValueError:
            messagebox.showwarning("Deposit", "Deposit must be a number.", parent=self)
            return
        if dep < 0 or dep > p["total"] + 0.01:
            messagebox.showwarning("Deposit", "Deposit cannot be negative or more than the total.", parent=self)
            return
        if not room_free(self.sel_room["id"], self.ci, self.co):
            messagebox.showerror("Unavailable", "Sorry, that room was just booked.", parent=self)
            self.search()
            return
        g = q1("SELECT id FROM guests WHERE phone=?", (phone,))
        if g:
            gid = g["id"]
            ex("UPDATE guests SET name=?, email=? WHERE id=?", (name, self.g_email.get().strip(), gid))
        else:
            gid = ex("INSERT INTO guests(name,phone,email,created) VALUES(?,?,?,?)",
                     (name, phone, self.g_email.get().strip(), today().isoformat())).lastrowid
        promo = self.promo_code if self.promo_pct else ""
        bid = ex("INSERT INTO bookings(guest_id,room_id,check_in,check_out,adults,children,status,rate,"
                 "room_total,addons_total,discount,tax,total,promo,notes,created,staff) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (gid, self.sel_room["id"], self.ci.isoformat(), self.co.isoformat(), adults,
                  kids, "Reserved", self.sel_room["rate"], p["room"], p["addons"],
                  p["discount"], p["tax"], p["total"], promo, self.notes.get().strip(),
                  today().isoformat(), self.app.username)).lastrowid
        for n, qt, pz in self.addons():
            conn.execute("INSERT INTO booking_addons(booking_id,name,qty,price) VALUES(?,?,?,?)", (bid, n, qt, pz))
        if dep > 0:
            conn.execute("INSERT INTO payments(booking_id,amount,method,kind,date,staff) VALUES(?,?,?,?,?,?)",
                         (bid, dep, self.method.get(), "Deposit", today().isoformat(), self.app.username))
        conn.commit()
        show_invoice(self.app, bid)
        self.app.show("res")          # go to the Reservations list


# ------------------------------------------------------------ rooms
class RoomDialog(FormDialog):
    def __init__(self, page, room=None):
        r = room
        super().__init__(page, "Edit Room" if r else "Add Room", "🛏",
                         "Edit room" if r else "Add a room",
                         f"Room {r['number']} • {r['name']}" if r else "Add a new room or villa to the resort")
        self.page, self.room = page, room
 
        p = self.panel("Details")
        g = form_grid(p)
        self.num = grid_entry(g, 0, 0, "Room number", r["number"] if r else "")
        cell = grid_cell(g, 0, 1, "Room type")
        types = [x["name"] for x in q("SELECT DISTINCT name FROM rooms ORDER BY name")]
        self.type = ttk.Combobox(cell, values=types)
        self.type.set(r["name"] if r else "")
        self.type.pack(fill="x")
 
        cell = grid_cell(g, 1, 0, "Capacity (guests)")
        cap = int(r["capacity"]) if r else 2
        self.cap = Stepper(cell, cap, 1, max(20, cap))
        self.cap.pack(anchor="w")
        self.rate = grid_entry(g, 1, 1, "Rate per night (₱)", f"{r['rate']:.2f}" if r else "")
        self.desc = grid_entry(g, 2, 0, "Description", r["description"] if r else "", span=2)
        self.am = grid_entry(g, 3, 0, "Amenities", r["amenities"] if r else "", span=2)
        hint(self.am.master, "Separate items with  •   e.g. Aircon • WiFi • Balcony")
        cell = grid_cell(g, 4, 0, "Status", span=2)
        self.status = Segmented(cell, ["Active", "Maintenance"], r["status"] if r else "Active")
        self.status.pack(fill="x")
 
        p2 = self.panel("Picture")
        row = tk.Frame(p2, bg=WHITE)
        row.pack(fill="x")
        self.image = r["image"] if r else ""
        self._prev = None
        self.prev = tk.Label(row, bg=BG, fg=MUTED, font=(F, 8), width=20, height=6, text="No picture yet")
        self.prev.pack(side="left")
        side = tk.Frame(row, bg=WHITE)
        side.pack(side="left", fill="x", expand=True, padx=14)
        self.pic_lbl = tk.Label(side, bg=WHITE, fg=MUTED, font=(F, 9), anchor="w", justify="left", wraplength=230)
        self.pic_lbl.pack(fill="x", pady=(0, 8))
        btn(side, "Choose picture…", self.pick, TINT["ocean"], INK, height=34).pack(anchor="w")
        self.show_pic(f"Current: {r['image']}" if (r and r["image"]) else "No picture selected")
 
        self.footer("Save room", self.save, left=("Delete", self.delete) if r else None)
        self.finish()
 
    def show_pic(self, text, good=False):
        """Update the preview thumbnail and the status text next to 'Choose picture'."""
        p = img_path(self.image) if self.image else ""
        if p and os.path.exists(p):
            self._prev = load_photo(p, (150, 96), 10)      # keep a reference on self!
            self.prev.config(image=self._prev, text="", width=150, height=96)
        else:
            self._prev = None
            self.prev.config(image="", text="No picture yet", width=20, height=6)
        self.pic_lbl.config(text=text, fg=TEAL if good else MUTED,
                            font=(F, 9, "bold") if good else (F, 9))
 
    def pick(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if f:
            name = f"custom_{uuid.uuid4().hex[:8]}" + os.path.splitext(f)[1].lower()
            shutil.copy(f, os.path.join(IMG_DIR, name))
            self.image = name
            self.show_pic(f"✔ Uploaded: {os.path.basename(f)}\nClick Save to apply it.", good=True)
 
    def save(self):
        if (self.room and self.status.get() == "Maintenance" and self.room["status"] != "Maintenance"
                and not can_set_maintenance(self, self.room["id"])):
            return
        try:
            vals = (self.num.get().strip(), self.type.get().strip(), int(self.cap.get()),
                    float(self.rate.get()), self.desc.get().strip(), self.am.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid", "Capacity and rate must be numbers.", parent=self)
            return
        if not vals[0] or not vals[1] or vals[2] < 1 or vals[3] <= 0:
            messagebox.showwarning("Invalid", "Fill in all fields correctly.", parent=self)
            return
        img = self.image
        if not img or not os.path.exists(img_path(img)):
            img = slug(vals[1]) + ".png"           # filename only
            if not os.path.exists(img_path(img)):
                make_scene(vals[1], vals[1], img_path(img))
        try:
            if self.room:
                ex("UPDATE rooms SET number=?,name=?,capacity=?,rate=?,description=?,amenities=?,image=?,status=? "
                   "WHERE id=?", vals + (img, self.status.get(), self.room["id"]))
            else:
                ex("INSERT INTO rooms(number,name,capacity,rate,description,amenities,image,status) "
                   "VALUES(?,?,?,?,?,?,?,?)", vals + (img, self.status.get()))
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "That room number already exists.", parent=self)
            return
        self.destroy()
        self.page.refresh()
 
    def delete(self):
        if q1("SELECT 1 FROM bookings WHERE room_id=?", (self.room["id"],)):
            messagebox.showwarning("In use", "This room has booking history. Set it to Maintenance instead.", parent=self)
            return
        if confirm_delete(self, "room", f"Delete Room {self.room['number']} ({self.room['name']})? "
                                        "This action cannot be undone."):
            ex("DELETE FROM rooms WHERE id=?", (self.room["id"],))
            self.destroy()
            self.page.refresh()

class ConfirmDialog(Dialog):
    """Styled yes/no pop-up. Use through confirm(...)."""

    def __init__(self, parent, title, message, yes="Yes", no="Cancel",
                 icon="❓", danger=False, detail=""):
        super().__init__(parent, title)
        # no fixed size: the window grows to fit everything, so nothing gets cut off
        b = self.body
        b.configure(padx=30, pady=26)
        tk.Frame(b, bg=WHITE, width=360, height=1).pack()     # minimum width only

        accent = DANGER if danger else TEAL
        tint = "#FCEDEA" if danger else TINT["teal"]
        avatar(b, icon, 56, tint, accent, bg=WHITE, font=(F, 20), dy=0).pack(pady=(0, 12))
        tk.Label(b, text=title, font=(F, 15, "bold"), bg=WHITE, fg=INK).pack()
        tk.Label(b, text=message, font=(F, 10), bg=WHITE, fg=MUTED,
                 wraplength=340, justify="center").pack(pady=(6, 0))
        if detail:
            tk.Label(b, text=detail, font=("Consolas", 9), bg=SEAFOAM, fg=INK, justify="left",
                     padx=12, pady=8).pack(fill="x", pady=(12, 0))

        row = tk.Frame(b, bg=WHITE)
        row.pack(fill="x", pady=(20, 0))
        row.grid_columnconfigure((0, 1), weight=1, uniform="cf")
        btn(row, no, self.destroy, "#E7EEEF", INK, height=40).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        btn(row, yes, self._yes, accent, WHITE, height=40).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.bind("<Return>", lambda e: self._yes())

    def _yes(self):
        self.result = True
        self.destroy()
        
def confirm(parent, title, message, **kw):
    """Drop-in replacement for messagebox.askyesno. Returns True / False."""
    d = ConfirmDialog(parent, title, message, **kw)
    d.wait_window()
    return d.result


def confirm_delete(parent, what, message="This action cannot be undone.", detail=""):
    """Red, styled delete confirmation. Returns True / False."""
    return confirm(parent, f"Delete {what}?", message, yes="Delete", no="Cancel",
                   icon="🗑", danger=True, detail=detail)

class AlertDialog(Dialog):
    """Styled one-button message: warning / error / info / success."""
    KINDS = {   # icon, icon colour, circle tint, button colour
        "warning": ("⚠", "#9A6B00", "#FFF1CC", GOLD),
        "error":   ("✖", DANGER,    "#FCEDEA", DANGER),
        "info":    ("ℹ", TEAL,      TINT["teal"], TEAL),
        "success": ("✔", TEAL,      TINT["teal"], TEAL),
    }

    def __init__(self, parent, title, message, kind="warning", button="OK"):
        super().__init__(parent, title)
        icon, icon_fg, tint, btn_col = self.KINDS[kind]
        b = self.body
        b.configure(padx=30, pady=26)
        tk.Frame(b, bg=WHITE, width=360, height=1).pack()        # minimum width only
        avatar(b, icon, 56, tint, icon_fg, bg=WHITE, font=(F, 20), dy=0).pack(pady=(0, 12))
        tk.Label(b, text=title, font=(F, 15, "bold"), bg=WHITE, fg=INK).pack()
        tk.Label(b, text=message, font=(F, 10), bg=WHITE, fg=MUTED,
                 wraplength=340, justify="center").pack(pady=(6, 0))
        btn(b, button, self.destroy, btn_col, WHITE, height=40).pack(fill="x", pady=(20, 0))
        self.bind("<Return>", lambda e: self.destroy())


def _alert(kind):
    def show(title, message, **kw):
        parent = kw.get("parent") or tk._default_root
        k = "success" if (kind == "info" and title in ("Saved", "Copied", "Promo applied")) else kind
        AlertDialog(parent, title, message, k).wait_window()
        return "ok"
    return show


def _ask_yes_no(title, message, **kw):
    parent = kw.get("parent") or tk._default_root
    return confirm(parent, title, message, yes="Yes", no="Cancel", icon="❓")


# replace the plain Windows pop-ups everywhere in the app
messagebox.showwarning = _alert("warning")
messagebox.showerror = _alert("error")
messagebox.showinfo = _alert("info")
messagebox.askyesno = _ask_yes_no   

def room_state(r):
    if r["status"] == "Maintenance":
        return "Maintenance", "#8AA1AB"
    t = today().isoformat()
    b = q1("SELECT status FROM bookings WHERE room_id=? AND status IN ('Reserved','Checked-in') "
           "AND check_in<=? AND check_out>? ORDER BY status DESC LIMIT 1", (r["id"], t, t))
    if b and b["status"] == "Checked-in":
        return "Occupied", OCEAN
    if b:
        return "Booked tonight", GOLD
    return "Available", AQUA

def can_set_maintenance(parent, room_id):
    """Guard before switching a room to Maintenance. Returns True if it's OK to proceed."""
    inhouse = q1(BOOKING_SQL + " WHERE b.room_id=? AND b.status='Checked-in'", (room_id,))
    if inhouse:
        messagebox.showwarning(
            "Guest in room",
            f"{inhouse['guest']} is checked in (until {inhouse['check_out']}).\n"
            "Check them out or move them to another room first.", parent=parent)
        return False
    upcoming = q(BOOKING_SQL + " WHERE b.room_id=? AND b.status='Reserved' AND b.check_out>? "
                 "ORDER BY b.check_in", (room_id, today().isoformat()))
    if not upcoming:
        return True
    lines = [f"{ref(b['id'])}  {b['check_in']} → {b['check_out']}  {b['guest'][:16]}"
             for b in upcoming[:6]]
    if len(upcoming) > 6:
        lines.append(f"... and {len(upcoming) - 6} more")
    return confirm(parent, "Room has reservations",
                   f"{len(upcoming)} upcoming reservation(s) use this room. They will stay, but "
                   "check-in will be blocked until you move those guests to another room.",
                   yes="Set maintenance", no="Cancel", icon="🔧", danger=True,
                   detail="\n".join(lines))

class RoomsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Rooms & Villas", "Live status of every room")
        if app.role == "admin":
            btn(head, "＋  Add room", lambda: RoomDialog(self), CORAL).pack(side="right")
        self.sf = ScrollFrame(self, bg=BG)
        self.sf.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.photos = []

    def refresh(self):
        for w in self.sf.inner.winfo_children():
            w.destroy()
        self.photos.clear()
        rooms = q("SELECT * FROM rooms ORDER BY number")
        cols = 3
        for c in range(cols):
            self.sf.inner.grid_columnconfigure(c, weight=1, uniform="rc")
        for i, r in enumerate(rooms):
            card = Card(self.sf.inner, fit=True, pad=12)
            card.grid(row=i // cols, column=i % cols, padx=7, pady=7, sticky="nsew")
            b = card.body
            ph = load_photo(room_image(r), (270, 160), 12)
            self.photos.append(ph)
            tk.Label(b, image=ph, bg=WHITE).pack()
            state, color = room_state(r)
            top = tk.Frame(b, bg=WHITE)
            top.pack(fill="x", pady=(10, 0))
            tk.Label(top, text=f"Room {r['number']}", font=(F, 13, "bold"), bg=WHITE, fg=INK).pack(side="left")
            pill(top, state, color, INK if color == GOLD else WHITE).pack(side="right")
            tk.Label(b, text=r["name"], bg=WHITE, fg=TEAL, font=(F, 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(b, text=f"👥 {r['capacity']} guests   •   {money(r['rate'])}/night", bg=WHITE, fg=INK,
                     anchor="w", font=(F, 9)).pack(fill="x", pady=(2, 0))
            tk.Label(b, text=f"🧹 Housekeeping: {r['hk']}", bg=WHITE, fg=MUTED, anchor="w",
                     font=(F, 9)).pack(fill="x")
            row = tk.Frame(b, bg=WHITE)
            row.pack(fill="x", pady=(10, 0))
            if r["status"] == "Active":
                btn(row, "Book this room", lambda r=r: self.app.new_booking(room=r), TEAL,
                    height=32).pack(side="left", fill="x", expand=True)
            if self.app.role == "admin":
                btn(row, "Edit", lambda r=r: RoomDialog(self, r), "#E7EEEF", INK,
                    height=32).pack(side="left", fill="x", expand=(r["status"] != "Active"), padx=(8, 0))


# ------------------------------------------------------------ bookings
class BookingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Reservations", "Double-click a reservation to open its details")
        btn(head, "＋  New reservation", lambda: app.new_booking(), CORAL).pack(side="right")
        fc = Card(self, fit=True, pad=10)
        fc.pack(fill="x", padx=26)
        top = fc.body
        tk.Label(top, text="Search", bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left")
        self.s = tk.StringVar()
        self.s.trace_add("write", lambda *a: self.load())
        ttk.Entry(top, textvariable=self.s, width=28).pack(side="left", padx=8)
        tk.Label(top, text="Status", bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left", padx=(14, 0))
        self.st = ttk.Combobox(top, values=["All", "Reserved", "Checked-in", "Checked-out", "Cancelled"],
                               state="readonly", width=13)
        self.st.set("All")
        self.st.pack(side="left", padx=8)
        self.st.bind("<<ComboboxSelected>>", lambda e: self.load())
        cols = ("ref", "guest", "room", "ci", "co", "n", "total", "paid", "bal", "status")
        f, self.tree = make_tree(self, cols, ("Ref", "Guest", "Room", "Check-in", "Check-out", "Nights",
                                              "Total", "Paid", "Balance", "Status"),
                                 (74, 140, 130, 84, 84, 46, 88, 88, 88, 80))
        f.pack(fill="both", expand=True, padx=26, pady=12)
        self.tree.bind("<Double-1>", self.on_dbl)
        bt = tk.Frame(self, bg=BG)
        bt.pack(fill="x", padx=26, pady=(0, 16))
        for text, cmd, col in [("Details", self.details, "#6D9DC5"),
                               ("Check-in", self.check_in, TEAL), ("Check-out", self.check_out, OCEAN),
                               ("Add payment", self.pay, TEAL), ("Add charge", self.charge, OCEAN),
                               ("Change dates", self.dates, "#6D9DC5"), ("Move room", self.move, "#6D9DC5"),
                               ("Invoice", self.invoice, GOLD), ("Cancel", self.cancel, DANGER)]:
            btn(bt, text, cmd, col, INK if col == GOLD else WHITE, height=36, padx=12).pack(side="left", padx=(0, 8))

    def load(self):
        keep = self.tree.selection()
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        s = f"%{self.s.get().strip()}%"
        sql = BOOKING_SQL + (" WHERE (g.name LIKE ? OR g.phone LIKE ? OR r.number LIKE ? "
                             "OR ('RB-'||printf('%05d',b.id)) LIKE ?)")
        args = [s, s, s, s]
        if self.st.get() != "All":
            sql += " AND b.status=?"
            args.append(self.st.get())
        for b in q(sql + " ORDER BY b.check_in DESC, b.id DESC", args):
            n = (pdate(b["check_out"]) - pdate(b["check_in"])).days
            self.tree.insert("", "end", iid=str(b["id"]), tags=(b["status"],),
                             values=(ref(b["id"]), b["guest"], f"{b['room_no']} {b['room_type']}",
                                     b["check_in"], b["check_out"], n, money(b["total"]), money(b["paid"]),
                                     money(b["total"] - b["paid"]), b["status"]))
        self.tree.resort()                       # re-apply the user's sort
        self.tree.yview_moveto(top)
        for iid in keep:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)

    refresh = load

    def on_dbl(self, e):
        row = self.tree.identify_row(e.y)
        if row:
            self.tree.selection_set(row)
            self.details(int(row))

    def sel(self):
        s = self.tree.selection()
        if not s:
            messagebox.showinfo("Select", "Select a reservation first.")
            return None
        return int(s[0])

    def get(self, bid):
        return q1(BOOKING_SQL + " WHERE b.id=?", (bid,))

    # every action takes an optional booking id so the details pop-up can call it too
    def details(self, bid=None):
        bid = bid or self.sel()
        if bid:
            BookingDetailDialog(self.app, bid)

    def check_in(self, bid=None):
        bid = bid or self.sel()
        if not bid:
            return
        b = self.get(bid)
        if b["status"] != "Reserved":
            messagebox.showinfo("Check-in", "Only 'Reserved' bookings can be checked in.")
            return
        room = q1("SELECT * FROM rooms WHERE id=?", (b["room_id"],))
        if room["status"] == "Maintenance":
            messagebox.showwarning("Room", "That room is under maintenance. Move the guest to another room.")
            return
        occupant = q1(BOOKING_SQL + " WHERE b.room_id=? AND b.status='Checked-in' AND b.id!=?",
                      (b["room_id"], bid))
        if occupant:
            messagebox.showwarning(
                "Room still occupied",
                f"{occupant['guest']} is still checked in to Room {room['number']} "
                f"(departs {occupant['check_out']}).\n"
                "Check them out first, or move this guest to another room.", parent=self)
            return
        
        # collect warnings (shown inside the same dialog)
        warns = []
        early = (pdate(b["check_in"]) - today()).days
        if early > 0:
            warns.append(f"Early arrival: booked for {b['check_in']} ({early} day{'s' if early != 1 else ''} early).")
        if room["hk"] != "Clean":
            warns.append(f"Room {room['number']} is marked '{room['hk']}', not Clean.")

        bal = b["total"] - b["paid"]
        detail = (f"{'Guest':<9}{b['guest'][:24]}\n"
                  f"{'Room':<9}{b['room_no']} {b['room_type']}\n"
                  f"{'Stay':<9}{b['check_in']} → {b['check_out']}\n"
                  f"{'Guests':<9}{b['adults']} adult(s), {b['children']} child(ren)\n"
                  f"{'Balance':<9}{money(max(bal, 0))}")

        if warns:
            msg = "\n".join("⚠ " + w for w in warns) + "\n\nCheck in anyway?"
        else:
            msg = "The guest will be marked as in-house."

        if not confirm(self, "Check in guest?", msg,
                       yes="Check in anyway" if warns else "Check in",
                       no="Cancel", icon="🔑", detail=detail):
            return
        ex("UPDATE bookings SET status='Checked-in' WHERE id=?", (bid,))
        backups.log_action(LOG_PATH, self.app.username, f"Checked in {ref(bid)} ({b['guest']})")
        self.load()

    def check_out(self, bid=None):
        bid = bid or self.sel()
        if not bid:
            return
        b = self.get(bid)
        if b["status"] != "Checked-in":
            messagebox.showinfo("Check-out", "Only checked-in guests can be checked out.")
            return
        bal = b["total"] - b["paid"]
        owes = bal > 0.009
        left_early = today() < pdate(b["check_out"])
        detail = (f"{'Guest':<9}{b['guest'][:24]}\n"
                  f"{'Room':<9}{b['room_no']} {b['room_type']}\n"
                  f"{'Total':<9}{money(b['total'])}\n"
                  f"{'Paid':<9}{money(b['paid'])}\n"
                  f"{'Balance':<9}{money(max(bal, 0))}")
        msg = ("There is an outstanding balance. You'll be asked to collect payment next."
               if owes else "The room will be marked Dirty and the invoice will open.")
        if left_early:
            msg = (f"Early departure: booked until {b['check_out']}. The room is released from today, "
                   "but the full stay stays billed.\n\n") + msg
        if not confirm(self, "Check out guest?", msg,
                       yes="Collect & check out" if owes else "Check out",
                       no="Cancel", icon="🚪", detail=detail):
            return
        if owes and not PaymentDialog(self, bid, bal).ok():
            return
        if left_early:
            ex("UPDATE bookings SET status='Checked-out', actual_out=? WHERE id=?",
               (today().isoformat(), bid))
        else:
            ex("UPDATE bookings SET status='Checked-out' WHERE id=?", (bid,))
        ex("UPDATE rooms SET hk='Dirty' WHERE id=?", (b["room_id"],))
        backups.log_action(LOG_PATH, self.app.username, f"Checked out {ref(bid)} ({b['guest']})")
        self.load()
        show_invoice(self.app, bid)

    def pay(self, bid=None):
        bid = bid or self.sel()
        if bid:
            b = self.get(bid)
            if b["status"] == "Cancelled":
                messagebox.showinfo("Payment", "This booking is cancelled.")
                return
            if PaymentDialog(self, bid, max(0, b["total"] - b["paid"])).ok():
                self.load()

    def charge(self, bid=None):
        bid = bid or self.sel()
        if bid:
            b = self.get(bid)
            if b["status"] in ("Cancelled", "Checked-out"):
                messagebox.showinfo("Charge", "Cannot add charges to this booking.")
                return
            if ChargeDialog(self, bid).result:
                self.load()

    def dates(self, bid=None):
        bid = bid or self.sel()
        if bid:
            b = self.get(bid)
            if b["status"] not in ("Reserved", "Checked-in"):
                messagebox.showinfo("Dates", "Only active bookings can be changed.")
                return
            if DatesDialog(self, b).result:
                self.load()

    def move(self, bid=None):
        bid = bid or self.sel()
        if bid:
            b = self.get(bid)
            if b["status"] not in ("Reserved", "Checked-in"):
                messagebox.showinfo("Move", "Only active bookings can be moved.")
                return
            if MoveDialog(self, b).result:
                self.load()

    def invoice(self, bid=None):
        bid = bid or self.sel()
        if bid:
            show_invoice(self.app, bid)

    def cancel(self, bid=None):
        bid = bid or self.sel()
        if not bid:
            return
        b = self.get(bid)
        if b["status"] != "Reserved":
            messagebox.showinfo("Cancel", "Only 'Reserved' bookings can be cancelled.")
            return
        days = (pdate(b["check_in"]) - today()).days
        penalty = 0 if days >= 3 else min(b["paid"], b["rate"])
        refund = b["paid"] - penalty
        policy = ("Free cancellation (3+ days before arrival)." if days >= 3 else
                  "Late cancellation: first night is non-refundable.")
        if confirm(self, "Cancel booking?", policy, yes="Cancel booking", no="Keep it",
            icon="⚠", danger=True,
            detail=f"Paid    {money(b['paid'])}\nRefund  {money(refund)}\nKept    {money(penalty)}"):
            if refund > 0:
                ex("INSERT INTO payments(booking_id,amount,method,kind,date,staff) VALUES(?,?,?,?,?,?)",
                   (bid, -refund, "Refund", "Refund", today().isoformat(), self.app.username))
                backups.log_action(LOG_PATH, self.app.username, f"Refunded {money(refund)} on {ref(bid)}")
            ex("UPDATE bookings SET status='Cancelled', total=? WHERE id=?", (penalty, bid))
            backups.log_action(LOG_PATH, self.app.username, f"Cancelled {ref(bid)} ({b['guest']})")
            self.load()

def dialog_header(parent, icon, title, sub="", tint=None, fg=TEAL, dy=-2):
    row = tk.Frame(parent, bg=WHITE)
    row.pack(fill="x", pady=(0, 10))
    avatar(row, icon, 38, tint or TINT["teal"], fg, bg=WHITE, font=(F, 14), dy=dy).pack(side="left")
    t = tk.Frame(row, bg=WHITE)
    t.pack(side="left", padx=10)
    tk.Label(t, text=title, font=(F, 13, "bold"), bg=WHITE, fg=INK).pack(anchor="w")
    if sub:
        tk.Label(t, text=sub, font=(F, 9), bg=WHITE, fg=MUTED).pack(anchor="w")


def dialog_buttons(parent, yes_text, yes_cmd, no_cmd, color=TEAL):
    row = tk.Frame(parent, bg=WHITE)
    row.pack(fill="x", pady=(12, 0))
    row.grid_columnconfigure(0, weight=1, uniform="db")     # Cancel = 1 part
    row.grid_columnconfigure(1, weight=2, uniform="db")     # main action = 2 parts
    btn(row, "Cancel", no_cmd, "#E7EEEF", INK, height=36).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    btn(row, yes_text, yes_cmd, color, WHITE, height=36).grid(row=0, column=1, sticky="ew", padx=(6, 0))


def info_box(parent, text, mono=False):
    lb = tk.Label(parent, text=text, justify="left", anchor="w", bg=SEAFOAM, fg=INK,
                  font=("Consolas", 9) if mono else (F, 10), padx=12, pady=8)
    lb.pack(fill="x", pady=(0, 8))
    return lb


def stat_row(parent, items):
    """Several label/value pairs side by side in one compact box."""
    row = tk.Frame(parent, bg=SEAFOAM)
    row.pack(fill="x", pady=(0, 10))
    for i, (k, v) in enumerate(items):
        row.grid_columnconfigure(i, weight=1, uniform="st")
        cell = tk.Frame(row, bg=SEAFOAM)
        cell.grid(row=0, column=i, sticky="w", padx=12, pady=8)
        tk.Label(cell, text=k, bg=SEAFOAM, fg=MUTED, font=(F, 8)).pack(anchor="w")
        tk.Label(cell, text=v, bg=SEAFOAM, fg=INK, font=(F, 10, "bold")).pack(anchor="w")

class Segmented(tk.Frame):
    """Row of pill buttons, one selected. Use .get() like an Entry."""

    def __init__(self, parent, options, value=None, bg=WHITE):
        super().__init__(parent, bg=bg)
        self.value, self.b = value or options[0], {}
        for i, o in enumerate(options):
            self.grid_columnconfigure(i, weight=1, uniform="seg")
            b = RButton(self, o, lambda o=o: self.set(o), color="#E7EEEF", fg=INK, height=36,
                        radius=10, font=(F, 9, "bold"), padx=6, bg=bg)
            b.grid(row=0, column=i, sticky="ew", padx=2)
            self.b[o] = b
        self.set(self.value)

    def set(self, v):
        self.value = v
        for o, b in self.b.items():
            on = o == v
            b.set_style(TEAL if on else "#E7EEEF", WHITE if on else INK)

    def get(self):
        return self.value

class PaymentDialog(Dialog):
    def __init__(self, page, bid, default):
        super().__init__(page, "Add Payment")
        self.bid = bid
        b = q1(BOOKING_SQL + " WHERE b.id=?", (bid,))
        body = self.body
        tk.Frame(body, bg=WHITE, width=400, height=1).pack()
        dialog_header(body, "₱", "Add payment", f"{ref(bid)}  •  {b['guest']}", dy=-2)
        stat_row(body, [("Total", money(b["total"])), ("Paid", money(b["paid"])),
                        ("Balance", money(b["total"] - b["paid"]))])
        self.amt = lbl_entry(body, "Amount (₱)", f"{default:.2f}")
        tk.Label(body, text="Method", bg=WHITE, fg=MUTED, anchor="w", font=(F, 9)).pack(fill="x")
        self.m = Segmented(body, METHODS, DEFAULT_METHOD)
        self.m.pack(fill="x", pady=(4, 0))
        dialog_buttons(body, "Save payment", self.save, self.destroy)
        self.bind("<Return>", lambda e: self.save())

    def save(self):
        try:
            a = float(self.amt.get())
            assert a > 0
        except (ValueError, AssertionError):
            messagebox.showwarning("Invalid", "Enter a valid amount.", parent=self)
            return
        ex("INSERT INTO payments(booking_id,amount,method,kind,date,staff) VALUES(?,?,?,?,?,?)",
           (self.bid, a, self.m.get(), "Payment", today().isoformat(), self.master.app.username))
        backups.log_action(LOG_PATH, self.master.app.username,
                           f"Payment {money(a)} ({self.m.get()}) on {ref(self.bid)}")
        self.result = True
        self.destroy()

    def ok(self):
        self.wait_window()
        return self.result
    
class ChargeDialog(Dialog):
    def __init__(self, page, bid):
        super().__init__(page, "Add Charge")
        self.bid = bid
        self.items = q("SELECT * FROM addons ORDER BY name")
        body = self.body
        tk.Frame(body, bg=WHITE, width=340, height=1).pack()
        dialog_header(body, "🧾", "Add a charge", f"{ref(bid)}  •  added to the guest folio",
                      TINT["coral"], "#9A6B00", dy=-4)
        tk.Label(body, text="Add-on / activity", bg=WHITE, fg=MUTED, anchor="w", font=(F, 9)).pack(fill="x")
        self.c = ttk.Combobox(body, state="readonly",
                              values=[f"{a['name']} ({money(a['price'])})" for a in self.items])
        self.c.current(0)
        self.c.pack(fill="x", pady=(2, 10))
        self.c.bind("<<ComboboxSelected>>", lambda e: self.upd())

        g = tk.Frame(body, bg=WHITE)
        g.pack(fill="x")
        g.grid_columnconfigure(1, weight=1)
        tk.Label(g, text="Quantity", bg=WHITE, fg=MUTED, font=(F, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(g, text="Line total", bg=WHITE, fg=MUTED, font=(F, 9)).grid(row=0, column=1, sticky="w", padx=(14, 0))
        self.qty = Stepper(g, 1, 1, 20, on_change=self.upd)
        self.qty.grid(row=1, column=0, sticky="w", pady=(2, 0))
        box = tk.Frame(g, bg=SEAFOAM)
        box.grid(row=1, column=1, sticky="nsew", padx=(14, 0), pady=(2, 0))
        self.total = tk.Label(box, bg=SEAFOAM, fg=INK, font=(F, 12, "bold"), anchor="w")
        self.total.pack(anchor="w", padx=12, pady=(3, 0))
        self.calc = tk.Label(box, bg=SEAFOAM, fg=MUTED, font=(F, 8), anchor="w")
        self.calc.pack(anchor="w", padx=12, pady=(0, 3))

        dialog_buttons(body, "Add to folio", self.save, self.destroy)
        self.upd()
        self.bind("<Return>", lambda e: self.save())
        self.wait_window()

    def upd(self):
        a = self.items[self.c.current()]
        n = int(self.qty.get())
        self.total.config(text=money(n * a["price"]))
        self.calc.config(text=f"{n} × {money(a['price'])}  •  before VAT")

    def save(self):
        a = self.items[self.c.current()]
        ex("INSERT INTO booking_addons(booking_id,name,qty,price) VALUES(?,?,?,?)",
           (self.bid, a["name"], int(self.qty.get()), a["price"]))
        recalc_booking(self.bid)
        backups.log_action(LOG_PATH, self.master.app.username,
                           f"Added charge {a['name']} x{int(self.qty.get())} to {ref(self.bid)}")
        self.result = True
        self.destroy()

class DatesDialog(Dialog):
    def __init__(self, page, b):
        super().__init__(page, "Change Dates")
        self.b = b
        body = self.body
        tk.Frame(body, bg=WHITE, width=340, height=1).pack()
        dialog_header(body, "📅", "Change dates",
                      f"{ref(b['id'])}  •  Room {b['room_no']}  •  {b['guest']}", TINT["ocean"], OCEAN, dy=-4)

        grid = tk.Frame(body, bg=WHITE)
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 2), weight=1, uniform="dt")
        tk.Label(grid, text="Check-in", bg=WHITE, fg=MUTED, font=(F, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(grid, text="Check-out", bg=WHITE, fg=MUTED, font=(F, 9)).grid(row=0, column=2, sticky="w")
        self.ci = DateEntry(grid, b["check_in"], on_change=self.upd)
        self.ci.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        tk.Label(grid, text="→", bg=WHITE, fg=MUTED, font=(F, 12)).grid(row=1, column=1, padx=10, pady=(2, 0))
        self.co = DateEntry(grid, b["check_out"], on_change=self.upd)
        self.co.grid(row=1, column=2, sticky="ew", pady=(2, 0))

        # quick extend
        ext = tk.Frame(body, bg=WHITE)
        ext.pack(fill="x", pady=(8, 0))
        tk.Label(ext, text="Extend stay", bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left", padx=(0, 8))
        for n in (1, 2, 3):
            btn(ext, f"+{n} night" + ("s" if n > 1 else ""), lambda n=n: self.extend(n), "#E7EEEF", INK,
                height=28, padx=10, radius=8, font=(F, 9, "bold")).pack(side="left", padx=(0, 6))

        self.info = tk.Label(body, text="", anchor="w", bg=SEAFOAM, fg=INK, font=(F, 10), padx=12, pady=8)
        self.info.pack(fill="x", pady=(10, 0))
        dialog_buttons(body, "Save changes", self.save, self.destroy)
        self.upd()
        self.bind("<Return>", lambda e: self.save())
        self.wait_window()

    def extend(self, n):
        """Set check-out to the ORIGINAL check-out + n nights."""
        self.co.set((pdate(self.b["check_out"]) + dt.timedelta(days=n)).isoformat())
        self.upd()

    def upd(self):
        try:
            ci, co = self.ci.date(), self.co.date()
        except ValueError:
            self.info.config(text="Use the format YYYY-MM-DD", fg=DANGER)
            return
        n = (co - ci).days
        if n <= 0:
            self.info.config(text="Check-out must be after check-in", fg=DANGER)
        else:
            p = pricing(self.b["rate"], ci, co, [], 0)
            self.info.config(text=f"{n} night{'s' if n != 1 else ''}   •   room {money(p['room'])}", fg=INK)

    def save(self):
        try:
            ci, co = self.ci.date(), self.co.date()
        except ValueError:
            messagebox.showwarning("Invalid", "Use YYYY-MM-DD.", parent=self)
            return
        if co <= ci:
            messagebox.showwarning("Dates", "Check-out must be after check-in.", parent=self)
            return
        room = q1("SELECT number, status FROM rooms WHERE id=?", (self.b["room_id"],))
        if room["status"] == "Maintenance" and (ci < pdate(self.b["check_in"]) or co > pdate(self.b["check_out"])):
            messagebox.showwarning("Maintenance",
                                   f"Room {room['number']} is under maintenance, so the stay can't be extended. "
                                   "Move the guest to another room instead.", parent=self)
            return
        if not room_free(self.b["room_id"], ci, co, exclude=self.b["id"]):
            messagebox.showerror("Unavailable", "The room is not free for those dates.", parent=self)
            return
        ex("UPDATE bookings SET check_in=?, check_out=? WHERE id=?", (ci.isoformat(), co.isoformat(), self.b["id"]))
        recalc_booking(self.b["id"])
        backups.log_action(LOG_PATH, self.master.app.username,
                           f"Changed dates of {ref(self.b['id'])}: {self.b['check_in']} to {self.b['check_out']}"
                           f" -> {ci.isoformat()} to {co.isoformat()}")
        self.result = True
        self.destroy()

class MoveDialog(Dialog):
    def __init__(self, page, b):
        super().__init__(page, "Move Room")
        self.b = b
        guests = b["adults"] + b["children"]
        self.rooms = [r for r in available_rooms(pdate(b["check_in"]), pdate(b["check_out"]), guests, exclude=b["id"])
                      if r["id"] != b["room_id"]]
        body = self.body
        tk.Frame(body, bg=WHITE, width=400, height=1).pack()
        dialog_header(body, "🛏", "Move guest",
                      f"{ref(b['id'])}  •  now in Room {b['room_no']} ({b['room_type']})", TINT["teal"], TEAL, dy=-5)
        if not self.rooms:
            info_box(body, "No other rooms are free for these dates and guest count.")
            btn(body, "Close", self.destroy, "#E7EEEF", INK, height=40).pack(fill="x")
        else:
            tk.Label(body, text="Move to", bg=WHITE, fg=MUTED, font=(F, 9)).pack(anchor="w")
            self.c = ttk.Combobox(body, state="readonly", width=42,
                                  values=[f"{r['number']} - {r['name']} ({money(r['rate'])}/night)" for r in self.rooms])
            self.c.current(0)
            self.c.pack(fill="x", pady=(2, 12))
            self.c.bind("<<ComboboxSelected>>", lambda e: self.upd())
            self.note = info_box(body, "")
            self.note.pack_configure(pady=(0, 0))
            dialog_buttons(body, "Move guest", self.save, self.destroy)
            self.upd()
        self.wait_window()

    def upd(self):
        r = self.rooms[self.c.current()]
        old = self.b["rate"]
        if r["rate"] == old:
            self.note.config(text=f"Same rate: {money(old)}/night. Total stays the same.")
        else:
            word = "higher" if r["rate"] > old else "lower"
            self.note.config(text=f"Rate changes {money(old)} → {money(r['rate'])}/night ({word}).\n"
                                  "The reservation total is recalculated.")

    def save(self):
        r = self.rooms[self.c.current()]
        ex("UPDATE bookings SET room_id=?, rate=? WHERE id=?", (r["id"], r["rate"], self.b["id"]))
        recalc_booking(self.b["id"])
        backups.log_action(LOG_PATH, self.master.app.username,
                           f"Moved {ref(self.b['id'])} from Room {self.b['room_no']} to Room {r['number']}")
        self.result = True
        self.destroy()

class BookingDetailDialog(Dialog):
    """One reservation in a pop-up. The middle part scrolls when there are many add-ons."""
    W = 500
    SOFT = "#E7EEEF"
 
    def __init__(self, app, bid):
        super().__init__(app, f"Reservation {ref(bid)}")
        self.app, self.bid = app, bid
        self.configure(bg=BG)
        self.body.configure(bg=BG, padx=18, pady=16)
        self._cards = []
 
        b = q1(BOOKING_SQL + " WHERE b.id=?", (bid,))
        addons = q("SELECT name,qty,price FROM booking_addons WHERE booking_id=?", (bid,))
        n = (pdate(b["check_out"]) - pdate(b["check_in"])).days
        bal = b["total"] - b["paid"]
        st = b["status"]
        body = self.body
        tk.Frame(body, bg=BG, width=self.W, height=1).pack()          # minimum width
 
        # ---------------- header (pinned top) ----------------
        self._head = head = tk.Frame(body, bg=BG)
        head.pack(fill="x", pady=(0, 12))
        left = tk.Frame(head, bg=BG)
        left.pack(side="left")
        tk.Label(left, text=ref(bid), font=(F, 18, "bold"), bg=BG, fg=INK).pack(anchor="w")
        tk.Label(left, text=f"Booked {b['created'] or '-'}  •  by {b['staff'] or '-'}",
                 font=(F, 9), bg=BG, fg=MUTED).pack(anchor="w")
        pill(head, st, STATUS_COLORS[st], INK if st == "Reserved" else WHITE).pack(side="right")
 
        # ---------------- pinned bottom (packed BEFORE the scroll area so it keeps its space) ----------------
        self._foot = foot = tk.Frame(body, bg=BG)
        foot.pack(side="bottom", fill="x")
        act = self._panel(body, side="bottom", pady=(10, 10))
        self._act_card = self._cards[-1]
 
        # ---------------- scrollable middle ----------------
        self.sf = ScrollFrame(body, bg=BG)
        self.sf.pack(fill="both", expand=True)
        mid = self.sf.inner
 
        # ---- card 1: guest + stay ----
        p = self._panel(mid)
        g = tk.Frame(p, bg=WHITE)
        g.pack(fill="x")
        initials = "".join(w[0] for w in b["guest"].split()[:2]).upper() or "?"
        avatar(g, initials, 44, TINT["teal"], TEAL, bg=WHITE).pack(side="left")
        t = tk.Frame(g, bg=WHITE)
        t.pack(side="left", padx=12)
        tk.Label(t, text=b["guest"], font=(F, 13, "bold"), bg=WHITE, fg=INK).pack(anchor="w")
        tk.Label(t, text=f"📞  {b['phone'] or '-'}", font=(F, 9), bg=WHITE, fg=MUTED).pack(anchor="w")
 
        self._divider(p)
 
        row = tk.Frame(p, bg=WHITE)
        row.pack(fill="x")
        row.grid_columnconfigure(0, weight=1, uniform="dt")
        row.grid_columnconfigure(2, weight=1, uniform="dt")
 
        def day(col, caption, iso, side):
            f = tk.Frame(row, bg=WHITE)
            f.grid(row=0, column=col, sticky=side)
            d = pdate(iso)
            tk.Label(f, text=caption, font=(F, 8, "bold"), bg=WHITE, fg=MUTED).pack(anchor=side)
            tk.Label(f, text=d.strftime("%a, %d %b"), font=(F, 13, "bold"), bg=WHITE, fg=INK).pack(anchor=side)
            tk.Label(f, text=d.strftime("%Y"), font=(F, 9), bg=WHITE, fg=MUTED).pack(anchor=side)
 
        day(0, "CHECK-IN", b["check_in"], "w")
        pill(row, f"{n} night{'s' if n != 1 else ''}", TINT["teal"], TEAL).grid(row=0, column=1, padx=14)
        day(2, "CHECK-OUT", b["check_out"], "e")
 
        self._divider(p)
 
        meta = tk.Frame(p, bg=WHITE)
        meta.pack(fill="x")
        meta.grid_columnconfigure((0, 1), weight=1, uniform="mt")
 
        def cell(r, c, icon, k, v, span=1):
            f = tk.Frame(meta, bg=WHITE)
            f.grid(row=r, column=c, columnspan=span, sticky="w", pady=4)
            avatar(f, icon, 30, TINT["ocean"], INK, bg=WHITE, font=(F, 10), dy=0).pack(side="left")
            tt = tk.Frame(f, bg=WHITE)
            tt.pack(side="left", padx=8)
            tk.Label(tt, text=k, font=(F, 8), bg=WHITE, fg=MUTED).pack(anchor="w")
            tk.Label(tt, text=v, font=(F, 10, "bold"), bg=WHITE, fg=INK,
                     wraplength=190 if span == 1 else 420, justify="left").pack(anchor="w")
 
        cell(0, 0, "🛏", "Room", f"{b['room_no']} • {b['room_type']}")
        cell(0, 1, "👥", "Guests", f"{b['adults']} adult(s), {b['children']} child(ren)")
        cell(1, 0, "🏷", "Promo", b["promo"] or "None")
        cell(1, 1, "₱", "Nightly rate", f"{money(b['rate'])}")
        if b["notes"]:
            cell(2, 0, "💬", "Requests", b["notes"], span=2)
 
        # ---- card 2: billing ----
        p = self._panel(mid)
        tk.Label(p, text="BILLING", font=(F, 8, "bold"), bg=WHITE, fg=MUTED).pack(anchor="w", pady=(0, 6))
        led = tk.Frame(p, bg=WHITE)
        led.pack(fill="x")
        led.grid_columnconfigure(0, weight=1)
        lines = [(f"Room × {n} night{'s' if n != 1 else ''}", money(b["room_total"]), INK)]
        for a in addons:
            lines.append((f"{a['name']} × {a['qty']}", money(a["qty"] * a["price"]), INK))
        if b["discount"]:
            lines.append((f"Discount ({b['promo']})", "−" + money(b["discount"]), TEAL))
        lines.append((vat_label(), money(b["tax"]), INK))
        for i, (k, v, col) in enumerate(lines):
            tk.Label(led, text=k, bg=WHITE, fg=MUTED, font=(F, 10), anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(led, text=v, bg=WHITE, fg=col, font=(F, 10), anchor="e").grid(row=i, column=1, sticky="e", pady=2)
 
        self._divider(p, pad=8)
        tot = tk.Frame(p, bg=WHITE)
        tot.pack(fill="x")
        tk.Label(tot, text="Total", font=(F, 12, "bold"), bg=WHITE, fg=INK).pack(side="left")
        tk.Label(tot, text=money(b["total"]), font=(F, 14, "bold"), bg=WHITE, fg=INK).pack(side="right")
 
        frac = max(0, min(1, b["paid"] / b["total"])) if b["total"] > 0 else 1
        bar = tk.Canvas(p, height=8, bg=WHITE, highlightthickness=0, bd=0)
        bar.pack(fill="x", pady=(12, 8))
 
        def paint(_=None):
            bar.delete("all")
            w = bar.winfo_width()
            if w < 10:
                return
            rrect(bar, 0, 0, w, 8, 4, fill=self.SOFT, outline="")
            if frac > 0:
                rrect(bar, 0, 0, max(8, w * frac), 8, 4, fill=TEAL, outline="")
        bar.bind("<Configure>", paint)
 
        pr = tk.Frame(p, bg=WHITE)
        pr.pack(fill="x")
        tk.Label(pr, text=f"Paid  {money(b['paid'])}", font=(F, 10), bg=WHITE, fg=MUTED).pack(side="left")
        if bal > 0.009:
            txt, fg_, bg_ = f"Balance due  {money(bal)}", DANGER, "#FCEDEA"
        elif bal < -0.009:
            txt, fg_, bg_ = f"Credit  {money(-bal)}", TEAL, TINT["teal"]
        else:
            txt, fg_, bg_ = "✔  Fully paid", TEAL, TINT["teal"]
        tk.Label(pr, text=txt, font=(F, 10, "bold"), bg=bg_, fg=fg_, padx=12, pady=4).pack(side="right")
 
        # ---- pinned: actions ----
        primary = []
        if st == "Reserved":
            primary.append(("Check-in", "check_in", TEAL, WHITE))
        if st == "Checked-in":
            primary.append(("Check-out", "check_out", TEAL, WHITE))
        if st != "Cancelled" and bal > 0.009:
            primary.append(("Add payment", "pay", GOLD, INK))
        secondary = []
        if st in ("Reserved", "Checked-in"):
            secondary += [("Add charge", "charge"), ("Change dates", "dates"), ("Move room", "move")]
        secondary.append(("Invoice", "invoice"))
 
        if primary:
            r1 = tk.Frame(act, bg=WHITE)
            r1.pack(fill="x", pady=(0, 8))
            for i, (text, name, col, fg) in enumerate(primary):
                r1.grid_columnconfigure(i, weight=1, uniform="pa")
                btn(r1, text, lambda nme=name: self.run(nme), col, fg, height=42,
                    font=(F, 10, "bold")).grid(row=0, column=i, sticky="ew",
                                               padx=(0 if i == 0 else 4, 4 if i < len(primary) - 1 else 0))
        r2 = tk.Frame(act, bg=WHITE)
        r2.pack(fill="x")
        for i, (text, name) in enumerate(secondary):
            r2.grid_columnconfigure(i, weight=1, uniform="se")
            btn(r2, text, lambda nme=name: self.run(nme), self.SOFT, INK, height=34, padx=6,
                font=(F, 9, "bold")).grid(row=0, column=i, sticky="ew",
                                          padx=(0 if i == 0 else 3, 3 if i < len(secondary) - 1 else 0))
 
        # ---- pinned: footer ----
        if st == "Reserved":
            foot.grid_columnconfigure((0, 1), weight=1, uniform="ft")
            btn(foot, "Cancel booking", lambda: self.run("cancel"), "#FCEDEA", DANGER,
                height=36).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            btn(foot, "Close", self.destroy, TINT["ocean"], INK,
                height=36).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        else:
            foot.grid_columnconfigure(0, weight=1)
            btn(foot, "Close", self.destroy, TINT["ocean"], INK, height=36).grid(row=0, column=0, sticky="ew")
 
    # ---- size the pop-up to its content, but never taller than the screen ----
    def _show(self):
        if not self.winfo_exists():
            return
        for c in self._cards:
            c._fit()
        self.update_idletasks()
        content_h = self.sf.inner.winfo_reqheight()                         # full height of the scrolling part
        other = self.body.winfo_reqheight() - self.sf.winfo_reqheight()     # header + buttons + padding
        avail = max(220, self.winfo_screenheight() - 150 - other)           # room left (title bar + taskbar)
        if content_h <= avail:
            self.sf.sb.pack_forget()                                        # everything fits: no scrollbar
        else:
            gap = self.sf.sb.winfo_reqwidth()                               # keep pinned parts aligned with the cards
            for w in (self._head, self._act_card, self._foot):
                w.pack_configure(padx=(0, gap))
        self.sf.canvas.config(height=min(content_h, avail))
        super()._show()
 
    # ---- small helpers ----
    def _panel(self, parent, side="top", pady=(0, 10)):
        c = Card(parent, fit=True, pad=14, radius=16)
        c.pack(fill="x", pady=pady, side=side)
        self._cards.append(c)
        return c.body
 
    @staticmethod
    def _divider(parent, pad=10):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=pad)
 
    def run(self, name):
        app, bid = self.app, self.bid
        self.destroy()                                   # release the modal, then run the action
        getattr(app.pages["res"], name)(bid)
        app.refresh_current()
        
# ------------------------------------------------------------ calendar
class CalendarPage(Page):
    def __init__(self, app):
        super().__init__(app)
        page_title(self, "Availability Calendar", "Click an empty day to book that room  •  click a booking bar for its details")
        fc = Card(self, fit=True, pad=10)
        fc.pack(fill="x", padx=26)
        top = fc.body
        btn(top, "◀", lambda: self.move(-7), "#E7EEEF", INK, height=32, padx=12).pack(side="left")
        btn(top, "Today", self.go_today, TEAL, height=32).pack(side="left", padx=6)
        btn(top, "▶", lambda: self.move(7), "#E7EEEF", INK, height=32, padx=12).pack(side="left")
        tk.Label(top, text="   Days shown", bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left")
        self.span = ttk.Combobox(top, values=["14", "21", "30"], state="readonly", width=4)
        self.span.set("21")
        self.span.pack(side="left", padx=8)
        self.span.bind("<<ComboboxSelected>>", lambda e: self.draw())
        for name in ("Checked-out", "Checked-in", "Reserved"):
            pill(top, name, STATUS_COLORS[name], INK if name == "Reserved" else WHITE).pack(side="right", padx=3)
        for text, col in (("Maintenance", DANGER), ("Available to book", TEAL)):
            item = tk.Frame(top, bg=WHITE)
            item.pack(side="right", padx=(0, 12))
            dot = tk.Canvas(item, width=10, height=10, bg=WHITE, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=col, outline="")
            dot.pack(side="left")
            tk.Label(item, text=text, bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left", padx=(5, 0))
        card = Card(self, pad=8)
        card.pack(fill="both", expand=True, padx=26, pady=12)
        self.canvas = tk.Canvas(card.body, bg=WHITE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.on_click)
        self.geo = None
        self.start = today() - dt.timedelta(days=3)

    def move(self, d):
        self.start += dt.timedelta(days=d)
        self.draw()

    def go_today(self):
        self.start = today() - dt.timedelta(days=3)
        self.draw()

    def refresh(self):
        self.draw()

    def on_click(self, e):
        if not self.geo:
            return
        c = self.canvas
        for item in c.find_overlapping(e.x, e.y, e.x, e.y):      # a booking bar was clicked -> its own handler
            if any(t.startswith("b") and t[1:].isdigit() for t in c.gettags(item)):
                return
        lw, hh, rh, cw, days, rooms = self.geo
        if e.x < lw or e.y < hh:
            return
        col, row = int((e.x - lw) // cw), int((e.y - hh) // rh)
        if not (0 <= col < days and 0 <= row < len(rooms)):
            return
        d, room = self.start + dt.timedelta(days=col), rooms[row]
        if d < today():
            messagebox.showinfo("Calendar", "A reservation cannot start in the past.")
            return
        if room["status"] != "Active":
            messagebox.showinfo("Calendar", f"Room {room['number']} is under maintenance.")
            return
        self.app.new_booking(room=room, check_in=d)

    def draw(self):
        c = self.canvas
        c.delete("all")
        W = max(c.winfo_width(), 900)
        lw, hh, rh = 200, 60, 38
        days = int(self.span.get())
        cw = (W - lw - 4) / days
        rooms = q("SELECT * FROM rooms ORDER BY number")
        self.geo = (lw, hh, rh, cw, days, rooms)
        H = hh + rh * len(rooms)
        idx = {r["id"]: i for i, r in enumerate(rooms)}
        end = self.start + dt.timedelta(days=days)
        for i in range(days):
            d = self.start + dt.timedelta(days=i)
            x = lw + i * cw
            if d.weekday() >= 5:
                c.create_rectangle(x, hh, x + cw, H, fill="#F6F9F9", outline="")
            c.create_line(x, hh, x, H, fill="#EDF2F3")
            c.create_text(x + cw / 2, 16, text=d.strftime("%b") if (i == 0 or d.day == 1) else "",
                          fill=MUTED, font=(F, 8, "bold"))
            c.create_text(x + cw / 2, 46, text=d.strftime("%a")[:2].upper(), fill=MUTED, font=(F, 8))
            if d == today():
                rrect(c, x + cw / 2 - 14, 22, x + cw / 2 + 14, 40, 9, fill=CORAL, outline="")
                c.create_text(x + cw / 2, 31, text=str(d.day), fill="white", font=(F, 10, "bold"))
            else:
                c.create_text(x + cw / 2, 31, text=str(d.day), fill=INK, font=(F, 10, "bold"))
        c.create_line(0, hh, W, hh, fill=BORDER)
        c.create_text(12, hh - 14, text="ROOM", anchor="w", fill=MUTED, font=(F, 8, "bold"))
        for i, r in enumerate(rooms):
            y = hh + i * rh
            maint = r["status"] != "Active"
            if maint:
                c.create_rectangle(0, y, W, y + rh, fill="#FCEDEA", outline="")
            c.create_line(0, y + rh, W, y + rh, fill="#EDF2F3")
            c.create_oval(12, y + rh / 2 - 4, 20, y + rh / 2 + 4, outline="",
                          fill=DANGER if maint else TEAL)
            # line 1: room number (keep this one)
            c.create_text(28, y + rh / 2 - 7, text=f"Room {r['number']}",
                          anchor="w", font=(F, 10, "bold"), fill=INK)
            c.create_text(28, y + rh / 2 + 9, text=r["name"],
                          anchor="w", font=(F, 8), fill=DANGER if maint else MUTED)
        rows = q(BOOKING_SQL + " WHERE b.status!='Cancelled' AND b.check_in<? AND b.check_out>?",
                 (end.isoformat(), self.start.isoformat()))
        for b in rows:
            if b["room_id"] not in idx:
                continue
            ci_d = pdate(b["check_in"])
            out_d = pdate(b["actual_out"]) if b["actual_out"] else pdate(b["check_out"])
            out_d = max(out_d, ci_d + dt.timedelta(days=1))      # a bar is at least one night wide
            if out_d <= self.start:
                continue
            y = hh + idx[b["room_id"]] * rh
            x1 = lw + ((ci_d - self.start).days + 0.5) * cw
            x2 = lw + ((out_d - self.start).days + 0.5) * cw
            x1, x2 = max(x1, lw), min(x2, lw + days * cw)
            tag = f"b{b['id']}"
            rrect(c, x1 + 1, y + 6, x2 - 1, y + rh - 6, 9, fill=STATUS_COLORS[b["status"]], outline="", tags=(tag,))
            room_w = x2 - x1
            if room_w > 40:
                name = b["guest"].split()[0] if room_w < 110 else b["guest"]
                c.create_text(x1 + 10, y + rh / 2, text=name, anchor="w",
                              fill=INK if b["status"] in ("Reserved", "Checked-out") else WHITE, font=(F, 9, "bold"), tags=(tag,))
            c.tag_bind(tag, "<Button-1>", lambda e, i=b["id"]: BookingDetailDialog(self.app, i))
        if self.start <= today() < end:
            x = lw + ((today() - self.start).days + 0.5) * cw
            c.create_line(x, hh, x, H, fill=DANGER, width=1, dash=(4, 3))


# ------------------------------------------------------------ guests
class GuestDialog(FormDialog):
    def __init__(self, page, g=None):
        super().__init__(page, "Edit Guest" if g else "Add Guest", "👤",
                         "Edit guest" if g else "Add a guest",
                         g["name"] if g else "Create a guest profile for future stays")
        self.page, self.g = page, g
 
        p = self.panel("Contact")
        grid = form_grid(p)
        self.name = grid_entry(grid, 0, 0, "Full name *", g["name"] if g else "", span=2)
        self.phone = grid_entry(grid, 1, 0, "Phone *", g["phone"] if g else "")
        self.email = grid_entry(grid, 1, 1, "Email", g["email"] if g else "")
        self.addr = grid_entry(grid, 2, 0, "Address", g["address"] if g else "", span=2)
 
        p = self.panel("Profile")
        grid = form_grid(p)
        self.idn = grid_entry(grid, 0, 0, "ID number", g["id_no"] if g else "")
        cell = grid_cell(grid, 0, 1, "VIP status")
        self.vip = Segmented(cell, ["Regular", "★ VIP"], "★ VIP" if (g and g["vip"]) else "Regular")
        self.vip.pack(fill="x")
        self.notes = grid_entry(grid, 1, 0, "Notes / preferences", g["notes"] if g else "", span=2)
 
        self.footer("Save guest", self.save)
        self.finish()
 
    def save(self):
        n, p = self.name.get().strip(), self.phone.get().strip()
        if not n or not p:
            messagebox.showwarning("Required", "Name and phone are required.", parent=self)
            return
 
        sql, args = "SELECT name FROM guests WHERE phone=?", [p]
        if self.g:                          # when editing, ignore the guest's own record
            sql += " AND id!=?"
            args.append(self.g["id"])
        dup = q1(sql, args)
        if dup:
            messagebox.showwarning(
                "Duplicate phone",
                f"{dup['name']} already uses this phone number.\n"
                "Search for that guest instead of adding a new one.", parent=self)
            return
        v = (n, p, self.email.get().strip(), self.addr.get().strip(), self.idn.get().strip(),
             self.notes.get().strip(), 1 if self.vip.get() == "★ VIP" else 0)
        if self.g:
            ex("UPDATE guests SET name=?,phone=?,email=?,address=?,id_no=?,notes=?,vip=? WHERE id=?", v + (self.g["id"],))
        else:
            ex("INSERT INTO guests(name,phone,email,address,id_no,notes,vip,created) VALUES(?,?,?,?,?,?,?,?)",
               v + (today().isoformat(),))
        self.destroy()
        self.page.refresh()

class GuestsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Guests", "Guest profiles, history and loyalty tiers")
        btn(head, "＋  Add guest", lambda: GuestDialog(self), CORAL).pack(side="right")
        fc = Card(self, fit=True, pad=10)
        fc.pack(fill="x", padx=26)
        tk.Label(fc.body, text="Search", bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left")
        self.s = tk.StringVar()
        self.s.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(fc.body, textvariable=self.s, width=32).pack(side="left", padx=8)
        cols = ("name", "phone", "email", "stays", "spent", "tier")
        f, self.tree = make_tree(self, cols, ("Name", "Phone", "Email", "Stays", "Total spent", "Tier"),
                                 (190, 120, 190, 70, 120, 100))
        f.pack(fill="both", expand=True, padx=26, pady=12)
        bt = tk.Frame(self, bg=BG)
        bt.pack(fill="x", padx=26, pady=(0, 16))
        btn(bt, "Book a stay", self.book, CORAL, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Edit", self.edit, OCEAN, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Stay history", self.history, TEAL, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Delete", self.delete, DANGER, height=36).pack(side="left")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        s = f"%{self.s.get().strip()}%"
        for g in q("SELECT g.*, (SELECT COUNT(*) FROM bookings b WHERE b.guest_id=g.id AND b.status!='Cancelled') AS stays,"
                   " (SELECT COALESCE(SUM(total),0) FROM bookings b WHERE b.guest_id=g.id AND b.status!='Cancelled') AS spent"
                   " FROM guests g WHERE g.name LIKE ? OR g.phone LIKE ? ORDER BY g.name", (s, s)):
            tier = "★ VIP" if g["vip"] else ("Gold" if g["spent"] >= 50000 else ("Silver" if g["spent"] >= 20000 else "Regular"))
            self.tree.insert("", "end", iid=str(g["id"]),
                             values=(g["name"], g["phone"], g["email"] or "", g["stays"], money(g["spent"]), tier))

    def sel(self):
        s = self.tree.selection()
        if not s:
            messagebox.showinfo("Select", "Select a guest first.")
            return None
        return q1("SELECT * FROM guests WHERE id=?", (int(s[0]),))

    def book(self):
        g = self.sel()
        if g:
            self.app.new_booking(guest=g)

    def edit(self):
        g = self.sel()
        if g:
            GuestDialog(self, g)

    def history(self):
        g = self.sel()
        if not g:
            return
        d = Dialog(self, f"Stay history - {g['name']}")
        tk.Label(d.body, text=f"Stay history  •  {g['name']}", font=(F, 14, "bold"), bg=WHITE, fg=INK).pack(anchor="w", pady=(0, 10))
        cols = ("ref", "room", "ci", "co", "total", "status")
        f, t = make_tree(d.body, cols, ("Ref", "Room", "Check-in", "Check-out", "Total", "Status"),
                         (80, 150, 90, 90, 100, 90), 7, natural=True)
        f.pack(fill="both", expand=True)
        for b in q(BOOKING_SQL + " WHERE b.guest_id=? ORDER BY b.check_in DESC", (g["id"],)):
            t.insert("", "end", iid=str(b["id"]), tags=(b["status"],),
                     values=(ref(b["id"]), f"{b['room_no']} {b['room_type']}",
                             b["check_in"], b["check_out"], money(b["total"]), b["status"]))
        t.bind("<Double-1>", lambda e: self._open_from_history(t, e, d))
        if g["notes"]:
            tk.Label(d.body, text="Notes: " + g["notes"], bg=WHITE, fg=MUTED, wraplength=560, justify="left").pack(anchor="w", pady=8)

    def _open_from_history(self, tree, e, dlg):
        row = tree.identify_row(e.y)
        if row:
            app = self.app
            dlg.destroy()
            BookingDetailDialog(app, int(row))

    def delete(self):
        g = self.sel()
        if not g:
            return
        if q1("SELECT 1 FROM bookings WHERE guest_id=?", (g["id"],)):
            messagebox.showwarning("In use", "This guest has bookings and cannot be deleted.")
            return
        if confirm_delete(self, "guest", f"Delete {g['name']}? This action cannot be undone."):
            ex("DELETE FROM guests WHERE id=?", (g["id"],))
            self.refresh()


# ------------------------------------------------------------ housekeeping
class HousekeepingPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Housekeeping", "Room cleaning & maintenance board")
        self.pills = {}
        for name, col, fg in (("Clean", TEAL, WHITE), ("In Progress", GOLD, INK), ("Dirty", DANGER, WHITE)):
            p = pill(head, f"{name}: 0", col, fg)
            p.pack(side="right", padx=4)
            self.pills[name] = p
        cols = ("room", "type", "hk", "state")
        f, self.tree = make_tree(self, cols, ("Room", "Type", "Housekeeping", "Today"), (90, 200, 140, 140))
        self.tree.tag_configure("Clean", background="#E6F6F3")
        self.tree.tag_configure("Dirty", background="#FCEDEA")
        self.tree.tag_configure("In Progress", background="#FFF8E1")
        f.pack(fill="both", expand=True, padx=26, pady=(0, 12))
        bt = tk.Frame(self, bg=BG)
        bt.pack(fill="x", padx=26, pady=(0, 16))
        btn(bt, "✔  Mark clean", lambda: self.set_hk("Clean"), TEAL, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "🧹  In progress", lambda: self.set_hk("In Progress"), GOLD, INK, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "✖  Mark dirty", lambda: self.set_hk("Dirty"), DANGER, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "🔧  Toggle maintenance", self.toggle_maint, OCEAN, height=36).pack(side="left")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        counts = {"Clean": 0, "In Progress": 0, "Dirty": 0}
        for r in q("SELECT * FROM rooms ORDER BY number"):
            state, _ = room_state(r)
            counts[r["hk"]] = counts.get(r["hk"], 0) + 1
            self.tree.insert("", "end", iid=str(r["id"]), tags=(r["hk"],),
                             values=(r["number"], r["name"], r["hk"], state))
        for k, p in self.pills.items():
            p.set_text(f"{k}: {counts.get(k, 0)}")

    def rid(self):
        s = self.tree.selection()
        if not s:
            messagebox.showinfo("Select", "Select a room first.")
            return None
        return int(s[0])

    def set_hk(self, v):
        r = self.rid()
        if r:
            ex("UPDATE rooms SET hk=? WHERE id=?", (v, r))
            self.refresh()

    def toggle_maint(self):
        r = self.rid()
        if r:
            cur = q1("SELECT status FROM rooms WHERE id=?", (r,))["status"]
            if cur != "Maintenance" and not can_set_maintenance(self, r):
                return
            ex("UPDATE rooms SET status=? WHERE id=?", ("Active" if cur == "Maintenance" else "Maintenance", r))
            self.refresh()


# ------------------------------------------------------------ promo codes (admin)
class PromoDialog(FormDialog):
    def __init__(self, page, p=None):
        used = promo_used(p["code"]) if p else 0
        super().__init__(page, "Edit promo code" if p else "New promo code", "🏷",
                         "Edit promo code" if p else "Create a promo code",
                         (f"Used on {used} reservation{'s' if used != 1 else ''}" if p
                          else "A discount guests can apply when booking"),
                         tint=TINT["coral"], fg="#9A6B00")
        self.page, self.p = page, p
 
        card = self.panel("Code & discount")
        g = form_grid(card)
        self.code = grid_entry(g, 0, 0, "Code", p["code"] if p else "")
        if used:
            self.code.config(state="disabled")
            hint(self.code.master, "Locked: already used on reservations")
        else:
            hint(self.code.master, "Letters and numbers, e.g. SUMMER25")
        self.pct = grid_entry(g, 0, 1, "Discount (%)", f"{p['percent']:g}" if p else "10")
 
        cell = grid_cell(g, 1, 0, "Expiry date", span=2)
        row = tk.Frame(cell, bg=WHITE)
        row.pack(fill="x")
        self.noexp = tk.IntVar(value=0 if (p and p["expires"]) else 1)
        self.exp = DateEntry(row, p["expires"] if (p and p["expires"]) else (today() + dt.timedelta(days=30)).isoformat())
        self.exp.pack(side="left")
        ttk.Checkbutton(row, text="No expiry", variable=self.noexp, style="W.TCheckbutton").pack(side="left", padx=14)
 
        card = self.panel("Rules")
        g = form_grid(card)
        self.maxu = grid_entry(g, 0, 0, "Usage limit", (p["max_uses"] or 0) if p else 0)
        hint(self.maxu.master, "0 = unlimited")
        self.minn = grid_entry(g, 0, 1, "Minimum nights", (p["min_nights"] or 0) if p else 0)
        hint(self.minn.master, "0 = no minimum")
        self.note = grid_entry(g, 1, 0, "Note (only staff see this)", (p["note"] or "") if p else "", span=2)
        cell = grid_cell(g, 2, 0, "Status", span=2)
        self.active = Segmented(cell, ["Active", "Disabled"], "Active" if (not p or p["active"]) else "Disabled")
        self.active.pack(fill="x")
 
        self.footer("Save promo code", self.save)
        self.finish()
 
    def save(self):
        code = self.code.get().strip().upper()
        if not code or not code.isalnum() or len(code) > 20:
            messagebox.showwarning("Code", "Use letters and numbers only (max 20 characters).", parent=self)
            return
        try:
            pct = float(self.pct.get())
            maxu = int(self.maxu.get() or 0)
            minn = int(self.minn.get() or 0)
            assert 0 < pct <= 100 and maxu >= 0 and minn >= 0
        except (ValueError, AssertionError):
            messagebox.showwarning("Invalid", "Discount must be 1-100 and the limits must be whole numbers (0 or more).", parent=self)
            return
        expires = None
        if not self.noexp.get():
            try:
                expires = self.exp.date().isoformat()
            except ValueError:
                messagebox.showwarning("Date", "Use the expiry date format YYYY-MM-DD.", parent=self)
                return
        active = 1 if self.active.get() == "Active" else 0
        vals = (code, pct, active, expires, maxu, minn, self.note.get().strip())
        try:
            if self.p:
                ex("UPDATE promos SET code=?,percent=?,active=?,expires=?,max_uses=?,min_nights=?,note=? WHERE id=?",
                   vals + (self.p["id"],))
            else:
                ex("INSERT INTO promos(code,percent,active,expires,max_uses,min_nights,note,created) VALUES(?,?,?,?,?,?,?,?)",
                   vals + (today().isoformat(),))
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "That promo code already exists.", parent=self)
            return
        backups.log_action(LOG_PATH, self.page.app.username,
                           f"{'Edited' if self.p else 'Created'} promo code {code} ({pct:g}%)")
        self.destroy()
        self.page.refresh()

class PromoPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Promo Codes", "Create and manage discount codes for reservations")
        btn(head, "＋  New promo code", lambda: PromoDialog(self), CORAL).pack(side="right")
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=20)
        self.k = []
        for i, (icon, label, tint) in enumerate([("🏷", "Active codes", "teal"),
                                                 ("🎟", "Times redeemed", "gold"),
                                                 ("💸", "Total discounts given", "coral")]):
            row.grid_columnconfigure(i, weight=1, uniform="pk")
            self.k.append(kpi_card(row, i, icon, label, tint))
        cols = ("code", "pct", "status", "exp", "uses", "minn", "note")
        f, self.tree = make_tree(self, cols, ("Code", "Discount", "Status", "Expires", "Used", "Min nights", "Note"),
                                 (120, 80, 90, 100, 90, 90, 260))
        for st, col in (("Active", "#E6F6F3"), ("Disabled", "#F3F6F7"), ("Expired", "#FCEDEA"), ("Used up", "#FFF8E1")):
            self.tree.tag_configure(st, background=col)
        f.pack(fill="both", expand=True, padx=26, pady=12)
        bt = tk.Frame(self, bg=BG)
        bt.pack(fill="x", padx=26, pady=(0, 16))
        btn(bt, "Edit", self.edit, OCEAN, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Enable / Disable", self.toggle, TEAL, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Copy code", self.copy, GOLD, INK, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Delete", self.delete, CORAL, height=36).pack(side="left")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        promos = q("SELECT * FROM promos ORDER BY code")
        active = 0
        for p in promos:
            st = promo_status(p)
            active += st == "Active"
            used = promo_used(p["code"])
            self.tree.insert("", "end", iid=str(p["id"]), tags=(st,),
                             values=(p["code"], f"{p['percent']:g}%", st, p["expires"] or "No expiry",
                                     f"{used} / {p['max_uses']}" if p["max_uses"] else f"{used} / ∞",
                                     p["min_nights"] or "-", p["note"] or ""))
        n, disc = q1("SELECT COUNT(*), COALESCE(SUM(discount),0) FROM bookings WHERE promo!='' AND promo IS NOT NULL "
                     "AND status!='Cancelled'")
        self.k[0].set(str(active))
        self.k[1].set(str(n))
        self.k[2].set(money(disc))

    def sel(self):
        s = self.tree.selection()
        if not s:
            messagebox.showinfo("Select", "Select a promo code first.")
            return None
        return q1("SELECT * FROM promos WHERE id=?", (int(s[0]),))

    def edit(self):
        p = self.sel()
        if p:
            PromoDialog(self, p)

    def toggle(self):
        p = self.sel()
        if p:
            ex("UPDATE promos SET active=? WHERE id=?", (0 if p["active"] else 1, p["id"]))
            backups.log_action(LOG_PATH, self.app.username,
                               f"{'Disabled' if p['active'] else 'Enabled'} promo code {p['code']}")
            self.refresh()

    def copy(self):
        p = self.sel()
        if p:
            self.clipboard_clear()
            self.clipboard_append(p["code"])
            messagebox.showinfo("Copied", f"{p['code']} copied to the clipboard.")

    def delete(self):
        p = self.sel()
        if not p:
            return
        if promo_used(p["code"]):
            messagebox.showwarning("In use", "This code was used on reservations. Disable it instead of deleting it.")
            return
        if confirm_delete(self, "promo code", f"Delete promo code {p['code']}? "
                                        "This action cannot be undone."):
            ex("DELETE FROM promos WHERE id=?", (p["id"],))
            backups.log_action(LOG_PATH, self.app.username, f"Deleted promo code {p['code']}")
            self.refresh()


class RestoreDialog(Dialog):
    def __init__(self, page):
        super().__init__(page, "Restore backup")
        self.page = page
        body = self.body
        tk.Frame(body, bg=WHITE, width=480, height=1).pack()
        dialog_header(body, "♻", "Restore a backup", "Replaces the current data with a saved copy",
                      TINT["coral"], "#9A6B00", dy=-3)
        names = backups.list_backups(BACKUP_DIR)[::-1]                    # newest first
        if not names:
            info_box(body, "No backups yet. Click 'Backup database' first.")
            btn(body, "Close", self.destroy, "#E7EEEF", INK, height=40).pack(fill="x")
            return
        f, self.tree = make_tree(body, ("file", "made", "size"), ("Backup", "Created", "Size"),
                                 (210, 150, 80), 6, natural=True)
        f.pack(fill="both", expand=True)
        for n in names:
            p = os.path.join(BACKUP_DIR, n)
            made = dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", iid=n, values=(n, made, f"{os.path.getsize(p) / 1024:,.0f} KB"))
        self.tree.selection_set(names[0])
        dialog_buttons(body, "Restore selected", self.go, self.destroy, DANGER)

    def go(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a backup first.", parent=self)
            return
        name = sel[0]
        if not confirm(self, "Restore this backup?",
                       "Everything entered since this backup was made will be lost, including bookings, "
                       "payments and staff accounts. A safety copy of the current data is saved first.",
                       yes="Restore", no="Cancel", icon="⚠", danger=True, detail=name):
            return
        try:
            safety = backups.restore_backup(conn, BACKUP_DIR, name)
        except backups.BackupError as e:                  # also catches RestoreError
            messagebox.showerror("Restore failed", str(e), parent=self)
            return
        init_db()                                    # adds any columns an older backup is missing
        load_settings()                               # reloads settings that may have been changed
        backups.log_action(LOG_PATH, self.page.app.username,
                      f"Restored database from {name} (safety copy: {os.path.basename(safety)})")
        self.destroy()
        messagebox.showinfo("Saved", "Backup restored.", parent=self.page)
        self.page.app.refresh_current()

# ------------------------------------------------------------ reports
class ReportsPage(Page):
    TYPES = ["Revenue by month", "Occupancy - last 30 days", "Most booked room types",
             "Add-on sales", "Payment methods", "Booking status"]

    def __init__(self, app):
        super().__init__(app)
        page_title(self, "Reports & Analytics", "Charts built from live reservation data")
        fc = Card(self, fit=True, pad=10)
        fc.pack(fill="x", padx=26)
        top = fc.body
        tk.Label(top, text="Report", bg=WHITE, fg=MUTED, font=(F, 9)).pack(side="left")
        self.rt = ttk.Combobox(top, values=self.TYPES, state="readonly", width=28)
        self.rt.current(0)
        self.rt.pack(side="left", padx=8)
        self.rt.bind("<<ComboboxSelected>>", lambda e: self.draw())
        btn(top, "Refresh", self.draw, TEAL, height=34).pack(side="left", padx=6)
        btn(top, "Export bookings CSV", self.export, GOLD, INK, height=34).pack(side="left")
        btn(top, "Backup database", self.backup, TEAL, height=34).pack(side="left", padx=(6, 0))
        btn(top, "Activity log", self.show_log, OCEAN, height=34).pack(side="left", padx=6)
        btn(top, "Restore backup", lambda: RestoreDialog(self), "#6D9DC5", height=34).pack(side="left")
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=20, pady=(12, 0))
        self.k = []
        for i, (icon, label, tint) in enumerate([("📒", "Total bookings", "ocean"), ("💰", "Total revenue", "teal"),
                                                 ("🌙", "Average stay", "gold"), ("✖", "Cancellation rate", "coral")]):
            row.grid_columnconfigure(i, weight=1, uniform="rk")
            self.k.append(kpi_card(row, i, icon, label, tint))
        card = Card(self, pad=12)
        card.pack(fill="both", expand=True, padx=26, pady=(12, 18))
        self.fig = Figure(figsize=(6, 4), dpi=100, facecolor=WHITE)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=card.body)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def refresh(self):
        self.draw()

    def draw(self):
        n = q1("SELECT COUNT(*) FROM bookings")[0]
        act = q1("SELECT COUNT(*), COALESCE(SUM(total),0), COALESCE(AVG(julianday(check_out)-julianday(check_in)),0) "
                 "FROM bookings WHERE status!='Cancelled'")
        canc = q1("SELECT COUNT(*) FROM bookings WHERE status='Cancelled'")[0]
        self.k[0].set(str(n))
        self.k[1].set(money(act[1]))
        self.k[2].set(f"{act[2]:.1f} nights")
        self.k[3].set(f"{(canc / n * 100 if n else 0):.0f}%")
        self.ax.clear()
        self.ax.axis("on")
        kind = self.rt.get()
        pie = kind in ("Payment methods", "Booking status")
        horiz = kind in ("Most booked room types", "Add-on sales")
        if not pie:
            style_ax(self.ax, "x" if horiz else "y")
        ok = True
        if kind == "Revenue by month":
            rows = q("SELECT substr(check_in,1,7) m, SUM(total) s FROM bookings WHERE status!='Cancelled' "
                     "GROUP BY m ORDER BY m DESC LIMIT 12")[::-1]
            ok = bool(rows)
            if ok:
                self.ax.bar([r["m"] for r in rows], [r["s"] for r in rows], color=TEAL, width=0.6)
                self.ax.set_ylabel("Revenue (₱)")
                self.ax.tick_params(axis="x", rotation=30)
        elif kind == "Occupancy - last 30 days":
            days = [today() - dt.timedelta(days=29 - i) for i in range(30)]
            vals = [occupied_count(d) / active_rooms() * 100 for d in days]
            ok = any(vals)
            if ok:
                self.ax.plot(range(30), vals, color=TEAL, linewidth=2.5)
                self.ax.fill_between(range(30), vals, color=TEAL, alpha=0.12)
                self.ax.set_ylim(0, 105)
                self.ax.set_ylabel("Occupancy %")
                self.ax.set_xticks(range(0, 30, 3))
                self.ax.set_xticklabels([days[i].strftime("%d %b") for i in range(0, 30, 3)])
        elif kind == "Most booked room types":
            rows = q("SELECT r.name n, COUNT(*) c FROM bookings b JOIN rooms r ON r.id=b.room_id "
                     "WHERE b.status!='Cancelled' GROUP BY r.name ORDER BY c DESC")
            ok = bool(rows)
            if ok:
                bars = self.ax.barh([r["n"] for r in rows], [r["c"] for r in rows], color=CHART_COLORS[:len(rows)], height=0.6)
                self.ax.invert_yaxis()
                self.ax.set_xlabel("Bookings")
                for b_, r in zip(bars, rows):
                    self.ax.text(b_.get_width() + 0.2, b_.get_y() + b_.get_height() / 2, str(r["c"]), va="center", color=INK)
        elif kind == "Add-on sales":
            rows = q("SELECT ba.name n, SUM(ba.qty*ba.price) s FROM booking_addons ba JOIN bookings b ON b.id=ba.booking_id "
                     "WHERE b.status!='Cancelled' GROUP BY ba.name ORDER BY s DESC")
            ok = bool(rows)
            if ok:
                self.ax.barh([r["n"] for r in rows], [r["s"] for r in rows], color=(CHART_COLORS * 2)[:len(rows)], height=0.6)
                self.ax.invert_yaxis()
                self.ax.set_xlabel("Sales (₱)")
        else:
            if kind == "Payment methods":
                rows = q("SELECT method n, SUM(amount) c FROM payments WHERE amount>0 GROUP BY method")
            else:
                rows = q("SELECT status n, COUNT(*) c FROM bookings GROUP BY status")
            ok = bool(rows)
            if ok:
                self.ax.pie([r["c"] for r in rows], labels=[r["n"] for r in rows], autopct="%1.0f%%", startangle=90,
                            colors=CHART_COLORS[:len(rows)], wedgeprops={"edgecolor": "white", "linewidth": 2, "width": 0.55},
                            textprops={"color": INK})
        if not ok:
            self.ax.clear()
            self.ax.axis("off")
            self.ax.text(0.5, 0.5, "No data yet - make bookings or load demo data from the Dashboard",
                         ha="center", va="center", color=MUTED, fontsize=12)
        else:
            self.ax.set_title(kind, loc="left", fontweight="bold", color=INK, fontsize=12, pad=14)
        self.fig.tight_layout()
        self.canvas.draw()

    def export(self):
        f = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="bookings_report.csv")
        if not f:
            return
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Ref", "Guest", "Room", "Check-in", "Check-out", "Status", "Promo", "Total", "Paid", "Balance"])
            for b in q(BOOKING_SQL + " ORDER BY b.check_in"):
                w.writerow([ref(b["id"]), b["guest"], f"{b['room_no']} {b['room_type']}", b["check_in"],
                            b["check_out"], b["status"], b["promo"] or "", f"{b['total']:.2f}", f"{b['paid']:.2f}",
                            f"{b['total'] - b['paid']:.2f}"])
        messagebox.showinfo("Saved", "Report exported.")

    def backup(self):
        try:
            path = backups.make_backup(conn, BACKUP_DIR, keep=BACKUP_KEEP)
        except backups.BackupError as e:
            messagebox.showerror("Backup failed", str(e), parent=self)
            return
        name = os.path.basename(path)
        backups.log_action(LOG_PATH, self.app.username, f"Backed up database to {name}")
        messagebox.showinfo("Saved", f"Backup created: {name}\nThe {BACKUP_KEEP} newest backups are kept.", parent=self)

    def show_log(self):
        d = Dialog(self, "Activity log")
        tk.Label(d.body, text="Activity log", font=(F, 14, "bold"), bg=WHITE, fg=INK).pack(anchor="w", pady=(0, 10))
        box = tk.Frame(d.body, bg=WHITE)
        box.pack(fill="both", expand=True)
        t = tk.Text(box, font=("Consolas", 9), bd=0, bg=WHITE, fg=INK, width=80, height=22,
                    padx=10, pady=10, wrap="none")
        sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        t.insert("1.0", "\n".join(backups.read_log(LOG_PATH)) or "No activity recorded yet.")
        t.config(state="disabled")
        btn(d.body, "Close", d.destroy, TINT["ocean"], INK, height=36).pack(fill="x", pady=(12, 0))

# ------------------------------------------------------------ staff (admin)
class StaffDialog(FormDialog):
    def __init__(self, page, u=None):
        super().__init__(page, "Edit staff" if u else "Add staff", "🔑",
                         "Edit staff account" if u else "New staff account",
                         f"@{u['username']}" if u else "Create a sign-in for a team member",
                         tint=TINT["ocean"], fg=OCEAN)
        self.page, self.u = page, u
 
        card = self.panel("Account")
        g = form_grid(card)
        self.user = grid_entry(g, 0, 0, "Username *", u["username"] if u else "")
        if u:
            self.user.config(state="disabled")      # bookings/payments reference the username
        else:
            hint(self.user.master, "3-20 letters, numbers or _")
        self.full = grid_entry(g, 0, 1, "Full name *", u["fullname"] if u else "")
        cell = grid_cell(g, 1, 0, "Role", span=2)
        self.role = Segmented(cell, ["Front desk", "Admin"], "Admin" if (u and u["role"] == "admin") else "Front desk")
        self.role.pack(fill="x")
 
        card = self.panel("Password")
        g = form_grid(card)
        self.pw = grid_entry(g, 0, 0, "New password" if u else "Password *", show="•")
        self.pw2 = grid_entry(g, 0, 1, "Confirm password", show="•")
        hint(card, "Leave both blank to keep the current password" if u else "At least 6 characters")
 
        self.footer("Save account", self.save)
        self.finish()
 
    def save(self):
        full = self.full.get().strip()
        role = "admin" if self.role.get() == "Admin" else "staff"
        pw, pw2 = self.pw.get(), self.pw2.get()
        if not full:
            messagebox.showwarning("Required", "Full name is required.", parent=self)
            return
        if self.u is None:
            uname = self.user.get().strip().lower()
            if not (3 <= len(uname) <= 20) or not uname.replace("_", "").isalnum():
                messagebox.showwarning("Username", "Use 3-20 letters, numbers or underscores.", parent=self)
                return
            if len(pw) < 6:
                messagebox.showwarning("Password", "Password must be at least 6 characters.", parent=self)
                return
        elif pw and len(pw) < 6:
            messagebox.showwarning("Password", "Password must be at least 6 characters.", parent=self)
            return
        if pw != pw2:
            messagebox.showwarning("Password", "The two passwords do not match.", parent=self)
            return
        if self.u:
            if self.u["username"] == self.page.app.username and role != "admin":
                messagebox.showwarning("Role", "You cannot remove your own admin access.", parent=self)
                return
            if self.u["role"] == "admin" and role != "admin" and self.page.admin_count() <= 1:
                messagebox.showwarning("Role", "There must be at least one admin.", parent=self)
                return
            ex("UPDATE users SET fullname=?, role=? WHERE id=?", (full, role, self.u["id"]))
            if pw:
                ex("UPDATE users SET password=? WHERE id=?", (hash_pw(pw), self.u["id"]))
        else:
            try:
                ex("INSERT INTO users(username,password,role,fullname) VALUES(?,?,?,?)",
                   (uname, hash_pw(pw), role, full))
            except sqlite3.IntegrityError:
                messagebox.showerror("Duplicate", "That username is already taken.", parent=self)
                return
        who = self.u["username"] if self.u else uname
        backups.log_action(LOG_PATH, self.page.app.username,
                           f"{'Edited' if self.u else 'Created'} staff account '{who}' ({role})"
                           + (" - password reset" if (pw and self.u) else ""))
        self.destroy()
        self.page.refresh()

class StaffPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Staff", "Manage who can sign in to the system")
        btn(head, "＋  Add staff", lambda: StaffDialog(self), CORAL).pack(side="right")
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=20)
        self.k = []
        for i, (icon, label, tint) in enumerate([("👥", "Total accounts", "ocean"),
                                                 ("🛎", "Front desk staff", "teal"),
                                                 ("🔑", "Admins", "gold")]):
            row.grid_columnconfigure(i, weight=1, uniform="sk")
            self.k.append(kpi_card(row, i, icon, label, tint))
        cols = ("user", "name", "role", "made")
        f, self.tree = make_tree(self, cols, ("Username", "Full name", "Role", "Bookings made"),
                                 (160, 240, 110, 130))
        self.tree.tag_configure("admin", background="#DCE8EC")
        self.tree.tag_configure("staff", background=WHITE)
        f.pack(fill="both", expand=True, padx=26, pady=12)
        bt = tk.Frame(self, bg=BG)
        bt.pack(fill="x", padx=26, pady=(0, 16))
        btn(bt, "Edit / reset password", self.edit, OCEAN, height=36).pack(side="left", padx=(0, 8))
        btn(bt, "Delete", self.delete, CORAL, height=36).pack(side="left")

    def admin_count(self):
        return q1("SELECT COUNT(*) FROM users WHERE role='admin'")[0]

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = q("SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.staff=u.username) AS made "
                 "FROM users u ORDER BY (u.role='admin') DESC, u.username")
        for u in rows:
            self.tree.insert("", "end", iid=str(u["id"]), tags=(u["role"],),
                             values=(u["username"], u["fullname"], u["role"].capitalize(), u["made"]))
        admins = sum(1 for u in rows if u["role"] == "admin")
        self.k[0].set(str(len(rows)))
        self.k[1].set(str(len(rows) - admins))
        self.k[2].set(str(admins))

    def sel(self):
        s = self.tree.selection()
        if not s:
            messagebox.showinfo("Select", "Select an account first.")
            return None
        return q1("SELECT * FROM users WHERE id=?", (int(s[0]),))

    def edit(self):
        u = self.sel()
        if u:
            StaffDialog(self, u)

    def delete(self):
        u = self.sel()
        if not u:
            return
        if u["username"] == self.app.username:
            messagebox.showwarning("Not allowed", "You cannot delete the account you are signed in with.")
            return
        if u["role"] == "admin" and self.admin_count() <= 1:
            messagebox.showwarning("Not allowed", "There must be at least one admin.")
            return
        if confirm_delete(self, "account", f"Delete the account '{u['username']}'? "
                                   "Their past bookings and payments are kept."):
            ex("DELETE FROM users WHERE id=?", (u["id"],))
            backups.log_action(LOG_PATH, self.app.username, f"Deleted staff account '{u['username']}'")
            self.refresh()

class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = page_title(self, "Settings", "Pricing rules, defaults and the add-on price list")
        btn(head, "Save settings", self.save, CORAL).pack(side="right")
 
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
        body.grid_columnconfigure((0, 1), weight=1, uniform="set")
        body.grid_rowconfigure(0, weight=1)
        left = Card(body, pad=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right = Card(body, pad=16)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
 
        def group(parent, title, **pack):
            lf = tk.LabelFrame(parent, text=f" {title} ", bg=WHITE, fg=TEAL,
                               font=(F, 9, "bold"), padx=14, pady=10)
            lf.pack(fill=pack.get("fill", "x"), expand=pack.get("expand", False), pady=(0, 12))
            return lf
 
        # ---- left: pricing / backups / default payment method (LabelFrames)
        g = group(left.body, "Pricing")
        self.vat = lbl_entry(g, "VAT (%)")
        self.weekend = lbl_entry(g, "Weekend surcharge for Fri & Sat nights (%)")
 
        g = group(left.body, "Backups")
        self.keep = lbl_entry(g, "Number of backups to keep")
 
        g = group(left.body, "Default payment method")
        self.method_var = tk.StringVar(value=DEFAULT_METHOD)
        for m in METHODS:                       # Radiobuttons share one variable: only one can be on
            tk.Radiobutton(g, text=m, variable=self.method_var, value=m, bg=WHITE, fg=INK,
                           activebackground=WHITE, selectcolor=WHITE, font=(F, 10),
                           anchor="w", cursor="hand2").pack(fill="x")
 
        # ---- right: add-on price list (Listbox)
        g = group(right.body, "Add-ons & activities", fill="both", expand=True)
        box = tk.Frame(g, bg=WHITE)
        box.pack(fill="both", expand=True)
        self.lb = tk.Listbox(box, font=(F, 10), bd=0, highlightthickness=1,
                             highlightbackground="#D3DEE0", highlightcolor=TEAL,
                             selectbackground=TEAL, selectforeground=WHITE,
                             activestyle="none", exportselection=False)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
 
        row = tk.Frame(g, bg=WHITE)
        row.pack(fill="x", pady=(10, 0))
        row.grid_columnconfigure(0, weight=1)
        tk.Label(row, text="Name", bg=WHITE, fg=MUTED, font=(F, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(row, text="Price (₱)", bg=WHITE, fg=MUTED, font=(F, 9)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.a_name = ttk.Entry(row)
        self.a_name.grid(row=1, column=0, sticky="ew")
        self.a_price = ttk.Entry(row, width=10)
        self.a_price.grid(row=1, column=1, padx=(8, 0))
        btn(row, "Add", self.add_addon, TEAL, height=34).grid(row=1, column=2, padx=(8, 0))
        btn(g, "Remove selected", self.remove_addon, "#FCEDEA", DANGER, height=34).pack(fill="x", pady=(8, 0))
        self.items = []
 
    def refresh(self):
        for entry, val in ((self.vat, f"{VAT * 100:g}"),
                           (self.weekend, f"{(WEEKEND_MULT - 1) * 100:g}"),
                           (self.keep, str(BACKUP_KEEP))):
            entry.delete(0, "end")
            entry.insert(0, val)
        self.method_var.set(DEFAULT_METHOD)
        self.load_addons()
 
    def load_addons(self):
        self.items = q("SELECT * FROM addons ORDER BY name")
        self.lb.delete(0, "end")
        for a in self.items:
            self.lb.insert("end", f"{a['name']}   -   {money(a['price'])}")
 
    def add_addon(self):
        name = self.a_name.get().strip()
        try:
            price = float(self.a_price.get())
        except ValueError:
            messagebox.showwarning("Price", "Price must be a number.", parent=self)
            return
        if not name or price <= 0:
            messagebox.showwarning("Add-on", "Enter a name and a price above zero.", parent=self)
            return
        for a in self.items:
            if a["name"].lower() == name.lower():
                messagebox.showwarning("Duplicate", f"'{a['name']}' is already in the list.", parent=self)
                break
        else:                                   # no break happened: no duplicate, safe to add
            ex("INSERT INTO addons(name,price) VALUES(?,?)", (name, price))
            backups.log_action(LOG_PATH, self.app.username, f"Added add-on '{name}' at {money(price)}")
            self.a_name.delete(0, "end")
            self.a_price.delete(0, "end")
            self.load_addons()
 
    def remove_addon(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Select an add-on first.", parent=self)
            return
        i = sel[0]
        a = self.items[i]
        if not confirm_delete(self, "add-on", f"Remove '{a['name']}' from the price list? "
                                              "Past bookings that used it keep their charges."):
            return
        ex("DELETE FROM addons WHERE id=?", (a["id"],))
        backups.log_action(LOG_PATH, self.app.username, f"Removed add-on '{a['name']}'")
        self.lb.delete(i)
        del self.items[i]                       # keep the list in step with the Listbox
 
    def save(self):
        try:
            vat = float(self.vat.get())
            weekend = float(self.weekend.get())
            keep = int(self.keep.get())
        except ValueError:
            messagebox.showwarning("Invalid", "VAT and surcharge must be numbers, and the number "
                                              "of backups must be a whole number.", parent=self)
            return
        else:                                   # runs only when every conversion above worked
            if not (0 <= vat <= 50 and 0 <= weekend <= 100 and 1 <= keep <= 30):
                messagebox.showwarning("Out of range", "VAT must be 0-50%, the surcharge 0-100%, "
                                                       "and backups 1-30.", parent=self)
                return
        for key, val in (("vat", vat), ("weekend", weekend), ("keep", keep),
                         ("pay_method", self.method_var.get())):
            ex("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(val)))
        load_settings()
        backups.log_action(LOG_PATH, self.app.username,
                           f"Changed settings: VAT {vat:g}%, weekend {weekend:g}%, keep {keep} backups, "
                           f"default payment {self.method_var.get()}")
        messagebox.showinfo("Saved", "Settings saved. New prices use them straight away.", parent=self)

# ============================================================ main window
class App(tk.Tk):
    def __init__(self, user):
        super().__init__()
        self.username, self.role, self.fullname = user
        self.title(RESORT + " - Reservation System")
        self.minsize(1100, 680)
        self.configure(bg=BG)
        setup_style(self)
        try:
            self.state("zoomed")                 # Windows: maximized, keeps title bar + taskbar
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)     # Linux
            except tk.TclError:
                sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                self.geometry(f"{sw}x{sh}+0+0")      # macOS fallback

        side = tk.Frame(self, bg=OCEAN, width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        logo = tk.Frame(side, bg=OCEAN)
        logo.pack(fill="x", padx=20, pady=(24, 22))
        self.logo_img = logo_photo(LOGO_PATH, 56)            # keep a reference on self!
        tk.Label(logo, image=self.logo_img, bg=OCEAN, bd=0).pack(side="left")
        t = tk.Frame(logo, bg=OCEAN)
        t.pack(side="left", padx=12)
        tk.Label(t, text="The Cove", font=(F, 14, "bold"), bg=OCEAN, fg=WHITE).pack(anchor="w")
        tk.Label(t, text="RESORT SUITE", font=(F, 7, "bold"), bg=OCEAN, fg=GOLD).pack(anchor="w")
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(side="right", fill="both", expand=True)

        # (key, label, page class)  -  a page class of None means "open a pop-up instead of a page"
        nav = [("dash", "📊   Dashboard", DashboardPage), ("book", "➕   New Reservation", BookingPage),
               ("res", "📋   Reservations", BookingsPage), ("cal", "📅   Calendar", CalendarPage),
               ("rooms", "🛏   Rooms", RoomsPage), ("guests", "👥   Guests", GuestsPage),
               ("hk", "🧹   Housekeeping", HousekeepingPage)]
        if self.role == "admin":
            nav += [("promo", "🏷   Promo Codes", PromoPage), ("staff", "🔑   Staff", StaffPage),
                    ("rep", "📈   Reports", ReportsPage), ("settings", "⚙   Settings", SettingsPage)]
        self.pages, self.nav = {}, {}
        for key, label, cls in nav:
            if key in ("dash", "promo"):
                tk.Label(side, text="MENU" if key == "dash" else "ADMIN", bg=OCEAN, fg=AQUA,
                         font=(F, 8, "bold")).pack(anchor="w", padx=26, pady=(8, 2))
            cmd = (lambda: self.new_booking()) if key == "book" else (lambda k=key: self.show(k))
            b = RButton(side, label, cmd, color=OCEAN, hover=OCEAN2, fg="#CFE3E6",
                        align="w", height=42, radius=12, padx=18, font=(F, 11), bg=OCEAN, width=204)
            b.pack(fill="x", padx=16, pady=2)
            self.nav[key] = b
            self.pages[key] = cls(self)
        
        foot = Card(side, fill=OCEAN2, border=None, bw=0, fit=True, pad=12, radius=16)
        foot.pack(side="bottom", fill="x", padx=16, pady=18)
        me = tk.Frame(foot.body, bg=OCEAN2)
        me.pack(fill="x")
        avatar(me, self.fullname[0].upper(), 36, GOLD, INK, bg=OCEAN2).pack(side="left")
        info = tk.Frame(me, bg=OCEAN2)
        info.pack(side="left", padx=10)
        tk.Label(info, text=self.fullname, bg=OCEAN2, fg=WHITE, font=(F, 10, "bold")).pack(anchor="w")
        tk.Label(info, text=self.role.capitalize(), bg=OCEAN2, fg="#A9C6CB", font=(F, 8)).pack(anchor="w")
        btn(foot.body, "Sign out", self.logout, CREAM, INK, height=32).pack(fill="x", pady=(10, 0))
        self.logged_out = False
        self.current = None
        self.show("dash")

    def show(self, key):
        if self.current:
            self.pages[self.current].pack_forget()
            self.nav[self.current].set_style(OCEAN, "#CFE3E6", (F, 11), OCEAN2)
        self.current = key
        self.nav[key].set_style(AQUA, INK, (F, 11, "bold"), AQUA)
        self.pages[key].pack(fill="both", expand=True)
        self.pages[key].refresh()

    def refresh_current(self):
        if self.current:
            self.pages[self.current].refresh()

    def new_booking(self, room=None, check_in=None, check_out=None, guest=None):
        self.pages["book"].start(room, check_in, check_out, guest)
        self.show("book")

    def logout(self):
        if confirm(self, "Sign out?", "You will need to sign in again to continue.",
                   yes="Sign out", no="Stay", icon="👋"):
            self.logged_out = True
            self.destroy()

def start():
    if os.environ.get("DEV"):                       # dev shortcut: skip login
        app = App(("admin", "admin", "Resort Manager"))
        app.mainloop()
        return
    while True:
        _img_cache.clear()          # cached PhotoImages die with their Tk window
        login = Login()
        login.mainloop()
        if not login.user:          # login window closed without signing in
            break
        app = App(login.user)
        app.mainloop()
        if not app.logged_out:      # app window closed with the X button
            break


if __name__ == "__main__":
    init_db()
    load_settings()
    migrate_image_paths()      # converts your existing rows to filenames
    start()