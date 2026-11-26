# Pydroid run kivy
"""Tagesplan. In Pydroid 3 öffnen und starten. Die Daten liegen neben dem Skript."""
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from functools import partial
from pathlib import Path
from uuid import uuid4
import base64
import io
import sqlite3
import subprocess

DATABASE = Path(__file__).resolve().with_name("alltagsplaner.sqlite3")


class InputError(ValueError):
    pass


def connect():
    db = sqlite3.connect(DATABASE, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize():
    with closing(connect()) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS eintraege (
                id INTEGER PRIMARY KEY,
                titel TEXT NOT NULL,
                bereich TEXT NOT NULL DEFAULT 'aufgabe',
                faellig TEXT,
                intervall INTEGER,
                erledigt INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS abschluesse (
                id INTEGER PRIMARY KEY,
                eintrag_id INTEGER NOT NULL REFERENCES eintraege(id),
                faellig_vorher TEXT,
                faellig_nachher TEXT,
                tag TEXT NOT NULL,
                zurueckgenommen INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS planer_einstellungen (
                schluessel TEXT PRIMARY KEY,
                wert TEXT NOT NULL
            );
        """)
        db.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(eintraege)")}
        if "ziel" not in columns:
            db.execute("ALTER TABLE eintraege ADD COLUMN ziel TEXT NOT NULL DEFAULT 'plan'")
        if "uhrzeit" not in columns:
            db.execute("ALTER TABLE eintraege ADD COLUMN uhrzeit TEXT")
        if "notiz" not in columns:
            db.execute("ALTER TABLE eintraege ADD COLUMN notiz TEXT NOT NULL DEFAULT ''")


def snapshot(db):
    entries = db.execute("""
        SELECT * FROM eintraege
        WHERE erledigt = 0
        ORDER BY faellig IS NULL, faellig, uhrzeit IS NULL, uhrzeit, id DESC
    """).fetchall()
    history = db.execute("""
        SELECT a.*, e.titel, e.intervall, e.faellig, e.erledigt
        FROM abschluesse a JOIN eintraege e ON e.id = a.eintrag_id
        WHERE a.zurueckgenommen = 0
        ORDER BY a.id DESC LIMIT 15
    """).fetchall()
    preferences = dict(db.execute("SELECT schluessel, wert FROM planer_einstellungen"))
    return {
        "entries": [dict(row) for row in entries],
        "history": [dict(row) for row in history],
        "preferences": preferences,
    }


def text_value(data, key, size):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > size:
        raise InputError("Die Eingabe ist zu lang oder ungültig.")
    return value.strip()


def entry_values(data):
    title = text_value(data, "titel", 240)
    if not title:
        raise InputError("Gib deinem Eintrag einen Titel.")
    category = data.get("bereich")
    interval = data.get("intervall")
    if category not in ("aufgabe", "einkauf", "notiz") or interval not in (None, 1, 7):
        raise InputError("Wähle eine passende Kategorie oder Wiederholung.")
    due = text_value(data, "faellig", 10)
    clock = text_value(data, "uhrzeit", 5)
    try:
        if due and date.fromisoformat(due).isoformat() != due:
            raise ValueError
        if clock and time.fromisoformat(clock).isoformat(timespec="minutes") != clock:
            raise ValueError
    except ValueError as error:
        raise InputError("Datum oder Uhrzeit ist ungültig.") from error
    if category != "aufgabe":
        due = clock = ""
        interval = None
    if not due and (clock or interval):
        raise InputError("Wähle ein Datum für die Uhrzeit oder Wiederholung.")
    return title, category, due or None, interval, clock or None, text_value(data, "notiz", 3000)


def complete(db, entry_id):
    row = db.execute("SELECT * FROM eintraege WHERE id = ? AND erledigt = 0", (entry_id,)).fetchone()
    if row is None:
        raise InputError("Dieser Eintrag ist bereits erledigt oder wurde entfernt.")
    today = date.today()
    next_due = None
    if row["intervall"]:
        previous = date.fromisoformat(row["faellig"])
        interval = row["intervall"]
        steps = max(1, (today - previous).days // interval + 1)
        try:
            next_due = (previous + timedelta(days=steps * interval)).isoformat()
        except OverflowError as error:
            raise InputError("Der Folgetermin liegt außerhalb des Datumsbereichs.") from error
    db.execute("UPDATE eintraege SET faellig = ?, erledigt = ? WHERE id = ?",
               (next_due or row["faellig"], int(next_due is None), entry_id))
    db.execute("""
        INSERT INTO abschluesse (eintrag_id, faellig_vorher, faellig_nachher, tag)
        VALUES (?, ?, ?, ?)
    """, (entry_id, row["faellig"], next_due, today.isoformat()))


def undo(db, history_id):
    row = db.execute("""
        SELECT a.*, e.intervall, e.faellig, e.erledigt
        FROM abschluesse a JOIN eintraege e ON e.id = a.eintrag_id
        WHERE a.id = ? AND a.zurueckgenommen = 0
    """, (history_id,)).fetchone()
    if row is None:
        raise InputError("Dieser Abschluss wurde bereits zurückgenommen.")
    after = row["faellig_nachher"]
    if after is None:
        available = bool(row["erledigt"])
    else:
        available = bool(row["intervall"]) and row["faellig"] == after and not row["erledigt"]
    if not available:
        raise InputError("Der Eintrag wurde inzwischen geändert oder erneut abgehakt.")
    db.execute("UPDATE eintraege SET faellig = ?, erledigt = 0 WHERE id = ?",
               (row["faellig_vorher"], row["eintrag_id"]))
    db.execute("UPDATE abschluesse SET zurueckgenommen = 1 WHERE id = ?", (history_id,))


def change(db, data):
    action = data.get("action")
    entry_id = data.get("id")
    if action in ("edit", "complete", "archive", "undo") and (
        type(entry_id) is not int or not 1 <= entry_id <= 2**63 - 1
    ):
        raise InputError("Ungültige Eintragsnummer.")
    if action == "add":
        items = data.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 30:
            raise InputError("Füge höchstens 30 Einträge auf einmal hinzu.")
        for item in items:
            if not isinstance(item, dict):
                raise InputError("Ungültiger Eintrag.")
            db.execute("""
                INSERT INTO eintraege (titel, bereich, faellig, intervall, uhrzeit, notiz)
                VALUES (?, ?, ?, ?, ?, ?)
            """, entry_values(item))
    elif action == "edit":
        result = db.execute("""
            UPDATE eintraege SET titel=?, bereich=?, faellig=?, intervall=?, uhrzeit=?, notiz=?
            WHERE id=? AND erledigt=0
        """, (*entry_values(data), entry_id))
        if not result.rowcount:
            raise InputError("Dieser Eintrag ist nicht mehr offen.")
    elif action == "complete":
        complete(db, entry_id)
    elif action == "archive":
        result = db.execute("UPDATE eintraege SET erledigt=1 WHERE id=? AND erledigt=0", (entry_id,))
        if not result.rowcount:
            raise InputError("Dieser Eintrag ist nicht mehr offen.")
        db.execute("""
            INSERT INTO abschluesse (eintrag_id, faellig_vorher, tag)
            SELECT id, faellig, ? FROM eintraege WHERE id=?
        """, (date.today().isoformat(), entry_id))
    elif action == "undo":
        undo(db, entry_id)
    elif action == "settings":
        name = text_value(data, "name", 26)
        accent = data.get("accent")
        if accent not in ("berry", "sage", "blue"):
            raise InputError("Wähle eine der drei Farben.")
        db.executemany("""
            INSERT OR REPLACE INTO planer_einstellungen (schluessel, wert) VALUES (?, ?)
        """, (("name", name), ("accent", accent)))
    else:
        raise InputError("Unbekannte Aktion.")

# Android-Standardaktionen. Die lokale Datenbank wird vor jeder Übergabe gespeichert.
DAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember")
TYPES = {"plan":"Aufgabe", "clock":"Wecker", "calendar":"Termin", "shopping":"Einkauf", "note":"Notiz"}


def kind_of(entry):
    if entry["bereich"] == "einkauf":
        return "shopping"
    if entry["bereich"] == "notiz":
        return "note"
    return entry.get("ziel", "plan")


def start_of(data):
    try:
        return datetime.combine(date.fromisoformat(data["faellig"]), time.fromisoformat(data["uhrzeit"]))
    except (ValueError, TypeError, KeyError) as error:
        raise InputError("Bitte Datum und Uhrzeit eintragen.") from error


def android_request(kind, data, now=None):
    if kind == "note":
        text = "\n".join(x for x in (data["titel"], data.get("notiz")) if x)
        return "android.intent.action.SEND", "", "text/plain", [
            ("str", "android.intent.extra.TEXT", text)]
    now = now or datetime.now()
    start = start_of(data)
    if start <= now:
        raise InputError("Für die Übergabe bitte eine zukünftige Uhrzeit wählen.")
    repeat = data.get("intervall")
    if kind == "calendar":
        extras = [("str","title",data["titel"]), ("str","description",data.get("notiz") or ""),
                  ("long","beginTime",int(start.timestamp()*1000)),
                  ("long","endTime",int((start+timedelta(minutes=30)).timestamp()*1000))]
        if repeat:
            extras.append(("str","rrule","FREQ="+("DAILY" if repeat==1 else "WEEKLY")))
        return "android.intent.action.INSERT", "content://com.android.calendar/events", "", extras
    if kind != "clock":
        raise InputError("Unbekanntes Ziel.")
    first = datetime.combine(now.date(), start.time())
    if first <= now:
        first += timedelta(days=1)
    if repeat == 7:
        first += timedelta(days=(start.weekday()-first.weekday()) % 7)
    if start.date() != first.date():
        raise InputError("Ein Android-Wecker beginnt beim nächsten passenden Wochentag oder der nächsten passenden Uhrzeit. Wähle dieses Datum oder lege einen Termin an.")
    prefix = "android.intent.extra.alarm."
    extras = [("str", prefix+"MESSAGE", data["titel"]), ("int",prefix+"HOUR",start.hour),
              ("int",prefix+"MINUTES",start.minute), ("bool",prefix+"SKIP_UI",True)]
    if repeat:
        weekdays = list(range(1,8)) if repeat==1 else [(start.weekday()+1)%7+1]
        extras.append(("days",prefix+"DAYS",weekdays))
    return "android.intent.action.SET_ALARM", "", "", extras


PICK_CALENDAR = "In Kalender-App auswählen"


def android_context(autoclass):
    context = None
    for name, attribute in (("org.kivy.android.PythonActivity","mActivity"),
                            ("org.libsdl.app.SDLActivity","getContext")):
        try:
            getter = getattr(autoclass(name),attribute)
            context = getter() if attribute=="getContext" else getter
            if context is not None:
                break
        except Exception:
            continue
    if context is None:
        context = autoclass("android.app.ActivityThread").currentApplication()
    if context is None:
        raise RuntimeError("Kein Android-Kontext.")
    return context


def writable_calendars():
    """Liest ausschließlich Namen und IDs beschreibbarer Zielkalender."""
    cursor = None
    try:
        from jnius import autoclass
        context = android_context(autoclass)
        if any(context.checkSelfPermission("android.permission."+permission)!=0
               for permission in ("READ_CALENDAR","WRITE_CALENDAR")):
            return {}
        uri = autoclass("android.net.Uri").parse("content://com.android.calendar/calendars")
        cursor = context.getContentResolver().query(
            uri, ["_id","calendar_displayName","allowedReminders"],
            "calendar_access_level >= 500 AND visible = 1",None,"calendar_displayName ASC")
        items = {}
        while cursor is not None and cursor.moveToNext():
            number = cursor.getLong(0)
            name = cursor.getString(1) or "Kalender"
            methods = (cursor.getString(2) or "0").split(",")
            method = 1 if "1" in methods else 0 if "0" in methods else None
            if method is not None:
                key = f"{name} · {number}" if name in items or name==PICK_CALENDAR else name
                items[key] = (number,method)
        return items
    except Exception:
        return {}
    finally:
        if cursor is not None:
            cursor.close()


def insert_calendar_event(target,data):
    """Termin und Benachrichtigung werden gemeinsam durch den Kalenderanbieter gespeichert."""
    from jnius import autoclass, cast
    context = android_context(autoclass)
    number,method = target
    Op = autoclass("android.content.ContentProviderOperation")
    Uri = autoclass("android.net.Uri")
    Long = autoclass("java.lang.Long")
    Integer = autoclass("java.lang.Integer")
    String = autoclass("java.lang.String")
    operations = autoclass("java.util.ArrayList")()
    def value(builder,key,obj):
        builder.withValue(key,cast("java.lang.Object",obj))
    start = start_of(data)
    event = Op.newInsert(Uri.parse("content://com.android.calendar/events"))
    value(event,"calendar_id",Long(number))
    value(event,"title",String(data["titel"]))
    value(event,"description",String(data.get("notiz") or ""))
    value(event,"dtstart",Long(int(start.timestamp()*1000)))
    value(event,"eventTimezone",String(autoclass("java.util.TimeZone").getDefault().getID()))
    value(event,"hasAlarm",Integer(1))
    if data.get("intervall"):
        value(event,"rrule",String("FREQ="+("DAILY" if data["intervall"]==1 else "WEEKLY")))
        value(event,"duration",String("PT30M"))
    else:
        value(event,"dtend",Long(int((start+timedelta(minutes=30)).timestamp()*1000)))
    operations.add(cast("java.lang.Object",event.build()))
    remind = Op.newInsert(Uri.parse("content://com.android.calendar/reminders"))
    remind.withValueBackReference("event_id",0)
    value(remind,"minutes",Integer(0))
    value(remind,"method",Integer(method))
    operations.add(cast("java.lang.Object",remind.build()))
    results = context.getContentResolver().applyBatch("com.android.calendar",operations)
    return len(results)==2 and results[0].uri is not None


def jni_send(request):
    from jnius import autoclass, cast
    Intent = autoclass("android.content.Intent")
    Bundle = autoclass("android.os.Bundle")
    context = android_context(autoclass)
    action, uri, mime, values = request
    intent = Intent(action)
    if uri:
        intent.setData(autoclass("android.net.Uri").parse(uri))
    if mime:
        intent.setType(mime)
    bundle = Bundle()
    for datatype, key, value in values:
        if datatype=="days":
            result = autoclass("java.util.ArrayList")()
            Integer = autoclass("java.lang.Integer")
            for day in value:
                result.add(cast("java.lang.Object", Integer(day)))
            bundle.putIntegerArrayList(key,result)
        else:
            method = {"str":"putString","int":"putInt","long":"putLong","bool":"putBoolean"}[datatype]
            getattr(bundle, method)(key,value)
    intent.putExtras(bundle)
    if action.endswith(".SEND"):
        intent = Intent.createChooser(intent, "Notiz teilen")
    intent.addFlags(0x10000000)
    context.startActivity(intent)


def deliver(request):
    try:
        jni_send(request)
        return True
    except Exception:
        pass
    manager = Path("/system/bin/am")
    if not manager.is_file():
        return False
    action, uri, mime, values = request
    args = [str(manager), "start", "-a", action]
    if uri:
        args += ["-d",uri]
    if mime:
        args += ["-t",mime]
    for datatype, key, value in values:
        flag = {"str":"--es","int":"--ei","long":"--el","bool":"--ez","days":"--eial"}[datatype]
        if datatype=="days":
            value = ",".join(str(day) for day in value)
        elif datatype=="bool":
            value = str(value).lower()
        args += [flag,key,str(value)]
    try:
        result = subprocess.run(args,capture_output=True,text=True,timeout=4)
    except (OSError, subprocess.SubprocessError):
        return False
    output = (result.stdout+result.stderr).lower()
    return result.returncode==0 and "starting: intent" in output and not any(
        x in output for x in ("error","denial","exception","unable","not allowed","aborted"))


def store_entry(data, kind, entry_id=None):
    values = entry_values(data)
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if entry_id is None:
            result = db.execute("""
                INSERT INTO eintraege(titel,bereich,faellig,intervall,uhrzeit,notiz,ziel)
                VALUES(?,?,?,?,?,?,?)
            """, (*values,kind))
            return result.lastrowid
        updated = db.execute("""
            UPDATE eintraege SET titel=?,bereich=?,faellig=?,intervall=?,uhrzeit=?,notiz=?,ziel=?
            WHERE id=? AND erledigt=0
        """, (*values,kind,entry_id))
        if not updated.rowcount:
            raise InputError("Dieser Eintrag ist bereits abgeschlossen.")
        return entry_id


def read_local_day(value):
    if not value.strip():
        return ""
    try:
        return datetime.strptime(value.strip(),"%d.%m.%Y").date().isoformat()
    except ValueError as error:
        raise InputError("Datum bitte als TT.MM.JJJJ eingeben.") from error


def export_event(data):
    start = start_of(data)
    def escape(text):
        return text.replace("\\","\\\\").replace("\r","").replace("\n","\\n").replace(",","\\,").replace(";","\\;")
    def fold(text):
        parts, line, width = [], "", 0
        for char in text:
            size=len(char.encode())
            if width+size > 75:
                parts.append(line)
                line,width=" ",1
            line+=char
            width+=size
        return "\r\n".join([*parts,line])
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Tagesplan//DE","BEGIN:VEVENT",
           f"UID:{uuid4()}@tagesplan.local",f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
           f"DTSTART:{start:%Y%m%dT%H%M%S}",f"DTEND:{start+timedelta(minutes=30):%Y%m%dT%H%M%S}",
           "SUMMARY:"+escape(data["titel"]),"DESCRIPTION:"+escape(data.get("notiz") or "")]
    if data.get("intervall"):
        lines.append("RRULE:FREQ="+("DAILY" if data["intervall"]==1 else "WEEKLY"))
    lines.extend(["BEGIN:VALARM","ACTION:DISPLAY","TRIGGER:PT0M","DESCRIPTION:"+escape(data["titel"]),
                  "END:VALARM","END:VEVENT","END:VCALENDAR"])
    file=DATABASE.with_name("termin_"+uuid4().hex[:8]+".ics")
    file.write_bytes(("\r\n".join(map(fold,lines))+"\r\n").encode())
    return file


CLOCK_IMAGE = (
    "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"
)

try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.clipboard import Clipboard
    from kivy.core.image import Image as CoreImage
    from kivy.core.window import Window
    from kivy.graphics import Color, RoundedRectangle
    from kivy.metrics import dp, sp
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.image import Image
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner, SpinnerOption
    from kivy.uix.textinput import TextInput
    from kivy.utils import get_color_from_hex
except ImportError as error:
    raise SystemExit("Diese Oberfläche braucht Kivy. Öffne in Pydroid 3 das Menü → Pip, "
                     "installiere kivy und starte die Datei erneut.\n" + str(error))


PAPER="#F6F5EF"
WHITE="#FFFFFF"
INK="#182B28"
GREEN="#11483D"
DIM="#536660"
PALE="#E4ECE4"
CORAL="#FD7752"
BLUSH="#FCE3D8"
WARN="#8D381F"
THEMES={"sage":GREEN,"berry":"#69405C","blue":"#364F76"}
WEEK={"Einmalig":None,"Täglich":1,"Wöchentlich":7}


def color(value):
    return get_color_from_hex(value)


def paint(widget, shade, radius=0):
    with widget.canvas.before:
        brush=Color(*color(shade))
        box=RoundedRectangle(pos=widget.pos,size=widget.size,radius=[dp(radius)])
    def fit(*_):
        box.pos,box.size=widget.pos,widget.size
    widget.bind(pos=fit,size=fit)
    return brush


def stack(gap=8, pads=0):
    result=BoxLayout(orientation="vertical",spacing=dp(gap),padding=dp(pads),size_hint_y=None)
    result.bind(minimum_height=result.setter("height"))
    return result


def row(height, gap=8):
    return BoxLayout(size_hint_y=None,height=dp(height),spacing=dp(gap))


def label(value,size=16,shade=INK,bold=False,height=28,align="left"):
    obj=Label(text=value,font_size=sp(size),color=color(shade),bold=bold,halign=align,valign="middle",
              size_hint_y=None,height=dp(height),shorten=True,shorten_from="right")
    obj.bind(size=lambda w,v:setattr(w,"text_size",v))
    return obj


def paragraph(value,shade=DIM,size=14):
    obj=Label(text=value,color=color(shade),font_size=sp(size),halign="left",valign="middle",size_hint_y=None)
    obj.bind(width=lambda w,v:setattr(w,"text_size",(v,None)))
    obj.bind(texture_size=lambda w,v:setattr(w,"height",v[1]+dp(6)))
    return obj


def tap(value,callback,shade=PALE,ink=INK,height=48,radius=14,size=15):
    obj=Button(text=value,font_size=sp(size),bold=True,color=color(ink),
               size_hint_y=None,height=dp(height),background_normal="",background_down="",
               background_color=(0,0,0,0),halign="center",valign="middle",shorten=True)
    brush=paint(obj,shade,radius)
    obj.bind(state=lambda w,v:setattr(brush,"a",.70 if v=="down" else 1))
    obj.bind(size=lambda w,v:setattr(w,"text_size",(max(1,v[0]-dp(6)),v[1])))
    obj.bind(on_release=lambda *_:callback())
    return obj


class EntryLink(ButtonBehavior, BoxLayout):
    pass


class Choice(SpinnerOption):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.height=dp(48)
        self.color=color(INK)
        self.font_size=sp(16)
        self.background_normal=""
        self.background_color=color(PALE)


def select(options,current):
    obj=Spinner(text=current,values=tuple(options),option_cls=Choice,size_hint_y=None,height=dp(50),
                background_normal="",background_down="",background_color=(0,0,0,0),
                color=color(INK),bold=True,font_size=sp(16))
    paint(obj,PALE,12)
    return obj


def field(value="",hint="",multi=False):
    obj=TextInput(text=value or "",hint_text=hint,multiline=multi,write_tab=False,
                  size_hint_y=None,height=dp(88 if multi else 50),font_size=sp(17),
                  background_normal="",background_active="",background_color=(0,0,0,0),
                  foreground_color=color(INK),hint_text_color=color(DIM),cursor_color=color(GREEN),
                  padding=[dp(14),dp(12),dp(12),dp(8)])
    # Hintergrund vor den Kivy-Textfarben zeichnen, nicht danach.
    from kivy.graphics import InstructionGroup
    background=InstructionGroup()
    background.add(Color(*color(WHITE)))
    box=RoundedRectangle(pos=obj.pos,size=obj.size,radius=[dp(13)])
    background.add(box)
    obj.canvas.before.insert(0,background)
    def fit(*_):
        box.pos,box.size=obj.pos,obj.size
    obj.bind(pos=fit,size=fit)
    return obj


class Tagesplan(App):
    title="Tagesplan"

    def build(self):
        global DATABASE
        DATABASE = Path(self.user_data_dir) / "alltagsplaner.sqlite3"
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        initialize()
        Window.clearcolor=color(PAPER)
        Window.softinput_mode="resize"
        Window.bind(on_keyboard=self.back_key)
        self.base=BoxLayout(orientation="vertical")
        self.tab="Heute"
        self.screen=""
        self.last_scroll={}
        self.cover=CoreImage(io.BytesIO(base64.b64decode(CLOCK_IMAGE)),ext="jpg")
        self.home()
        return self.base

    def on_pause(self):
        return True

    def back_key(self,_win,key,*_):
        if key==27 and self.screen!="home":
            self.home()
            return True
        return False

    def read(self):
        with closing(connect()) as db:
            return snapshot(db)

    def page(self,name,heading):
        if self.screen=="home" and hasattr(self,"scroll"):
            self.last_scroll[self.visible_tab]=self.scroll.scroll_y
        self.screen=name
        self.base.clear_widgets()
        state=self.read()
        self.theme=THEMES.get(state["preferences"].get("accent"),GREEN)
        self.outer=BoxLayout(orientation="vertical",padding=[dp(16),dp(9),dp(16),dp(8)],spacing=dp(8))
        self.base.add_widget(self.outer)
        header=row(46)
        self.outer.add_widget(header)
        if name=="home":
            header.add_widget(label("Tagesplan",24,INK,True,46))
            header.add_widget(tap("Stil",self.settings,height=44,size=14))
            header.children[0].size_hint_x=None
            header.children[0].width=dp(56)
        else:
            back=tap("‹ Zurück",self.home,height=44,size=14)
            back.size_hint_x=None
            back.width=dp(82)
            header.add_widget(back)
            header.add_widget(label(heading,18,INK,True,46,"right"))
        self.scroll=ScrollView(do_scroll_x=False,bar_width=dp(3),bar_color=color(DIM))
        self.outer.add_widget(self.scroll)
        self.body=stack(10)
        self.scroll.add_widget(self.body)
        self.footer=stack(6)
        self.outer.add_widget(self.footer)
        return state

    def home(self,message=""):
        state=self.page("home","")
        self.visible_tab=self.tab
        items=state["entries"]
        today=date.today()
        iso=today.isoformat()
        tabs=row(44,3)
        for name in ("Heute","Plan","Einkauf","Notizen"):
            active=name==self.tab
            tabs.add_widget(tap(name,partial(self.switch,name),self.theme if active else PALE,
                                WHITE if active else INK,height=44,size=14))
        self.outer.add_widget(tabs,index=2)
        if self.tab=="Heute":
            tasks=[e for e in items if e["bereich"]=="aufgabe"]
            due=[e for e in tasks if e["faellig"] and e["faellig"]<=iso]
            self.hero(today,len(due),state["preferences"].get("name",""))
            shortcuts=row(48)
            shortcuts.add_widget(tap("Wecker stellen",partial(self.editor,"clock"),BLUSH,WARN))
            shortcuts.add_widget(tap("Termin anlegen",partial(self.editor,"calendar"),PALE,self.theme))
            self.body.add_widget(shortcuts)
            self.group("Heute und überfällig",due,"Heute ist nichts fällig.")
            loose=[e for e in tasks if not e["faellig"]]
            if loose:
                self.group("Ohne Termin",loose)
            self.body.add_widget(tap("Täglichen Erinnerungswecker anlegen",self.daily_clock))
        elif self.tab=="Plan":
            tasks=[e for e in items if e["bereich"]=="aufgabe"]
            self.group("Mit Termin",[e for e in tasks if e["faellig"]],"Dein Terminplan ist frei.")
            self.group("Ohne Termin",[e for e in tasks if not e["faellig"]],"Keine offenen Aufgaben ohne Datum.")
            if state["history"]:
                self.body.add_widget(tap("Verlauf öffnen",self.history))
        else:
            shopping=self.tab=="Einkauf"
            self.group("Einkaufsliste" if shopping else "Meine Notizen",
                       [e for e in items if e["bereich"]==("einkauf" if shopping else "notiz")],
                       "Die Einkaufsliste ist leer." if shopping else "Hier erscheinen deine Notizen.")
        if message:
            self.footer.add_widget(paragraph(message,self.theme))
        default={"Einkauf":"shopping","Notizen":"note"}.get(self.tab,"plan")
        self.footer.add_widget(tap("+   Neuer Eintrag",partial(self.editor,default),self.theme,WHITE,52))
        scroll=self.scroll
        Clock.schedule_once(lambda _:setattr(scroll,"scroll_y",self.last_scroll.get(self.tab,1)),0)

    def hero(self,today,count,name):
        panel=row(130,0)
        paint(panel,"#123D35",18)
        panel.padding=[dp(15),dp(7),dp(6),dp(7)]
        words=BoxLayout(orientation="vertical",size_hint_x=.64,padding=[0,dp(5),0,dp(5)])
        stamp=DAYS[today.weekday()][:2]+f" · {today.day}. "+MONTHS[today.month-1]
        words.add_widget(label(stamp,13,"#BED4C7",True,24))
        words.add_widget(label("Hallo, "+name if name else "Mein Tag",27,WHITE,True,45))
        words.add_widget(label("Heute ist frei." if not count else ("1 Aufgabe fällig" if count==1 else f"{count} Aufgaben fällig"),
                               14,"#E3EFE6",False,27))
        panel.add_widget(words)
        art=Image(texture=self.cover.texture,size_hint_x=.36,allow_stretch=True,keep_ratio=True)
        panel.add_widget(art)
        self.body.add_widget(panel)

    def switch(self,tab):
        self.tab=tab
        self.home()

    def group(self,title,entries,empty=""):
        self.body.add_widget(label(title,18,INK,True,32))
        if not entries:
            msg=stack(0,12)
            paint(msg,WHITE,14)
            msg.add_widget(paragraph(empty))
            self.body.add_widget(msg)
        for e in entries:
            kind=kind_of(e)
            box=row(74,6)
            box.padding=[dp(8),dp(5),dp(8),dp(5)]
            paint(box,WHITE,14)
            if kind!="note":
                btn=tap("✓",partial(self.mutate,"complete",e["id"]),PALE,GREEN,48,size=19)
                btn.size_hint_x=None
                btn.width=dp(44)
                box.add_widget(btn)
            details=TYPES.get(kind,"Aufgabe")
            if e["faellig"]:
                due=date.fromisoformat(e["faellig"])
                details+="  ·  "+("Heute" if due==date.today() else due.strftime("%d.%m.%y"))
            if e["uhrzeit"]:
                details+="  ·  "+e["uhrzeit"]
            if e["intervall"]:
                details+="  ·  "+("täglich" if e["intervall"]==1 else "wöch.")
            content=EntryLink(orientation="vertical")
            content.bind(on_release=lambda _,k=kind,entry=e:self.editor(k,entry))
            content.add_widget(label(e["titel"],17,INK,True,33))
            content.add_widget(label(details,12,DIM,False,24))
            box.add_widget(content)
            edit=tap("›",partial(self.editor,kind,e),WHITE,self.theme,54,size=25)
            edit.size_hint_x=None
            edit.width=dp(44)
            box.add_widget(edit)
            self.body.add_widget(box)

    def history(self):
        state=self.page("history","Verlauf")
        for e in state["history"]:
            self.body.add_widget(paragraph(e["titel"],INK,16))
            self.body.add_widget(tap("Rückgängig",partial(self.mutate,"undo",e["id"])))

    def mutate(self,action,number):
        try:
            with closing(connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                change(db,{"action":action,"id":number})
        except (ValueError,sqlite3.Error) as error:
            self.home(str(error))
            return
        self.home({"undo":"Wieder offen.","archive":"Archiviert.","complete":"Abgehakt."}[action])

    def settings(self):
        state=self.page("settings","Dein Stil")
        self.caption("Dein Name")
        name=field(state["preferences"].get("name"),"Vorname")
        self.body.add_widget(name)
        self.caption("Akzentfarbe")
        colors={"Waldgrün":"sage","Beere":"berry","Nachtblau":"blue"}
        accent=state["preferences"].get("accent","sage")
        choice=select(colors,next((k for k,v in colors.items() if v==accent),"Waldgrün"))
        self.body.add_widget(choice)
        def save():
            try:
                with closing(connect()) as db,db:
                    change(db,{"action":"settings","name":name.text,"accent":colors[choice.text]})
            except (ValueError,sqlite3.Error) as error:
                self.notify(str(error))
                return
            self.home()
        self.footer.add_widget(tap("Übernehmen",save,self.theme,WHITE,52))

    def caption(self,text,where=None):
        (where or self.body).add_widget(label(text,14,DIM,True,23))

    def notify(self,message):
        if hasattr(self,"notice") and self.notice.parent is self.footer:
            self.notice.text=message
        else:
            self.notice=paragraph(message,WARN)
            self.footer.add_widget(self.notice,index=len(self.footer.children))

    def daily_clock(self):
        when=datetime.now().replace(hour=19,minute=0,second=0,microsecond=0)
        if when<=datetime.now():
            when+=timedelta(days=1)
        self.editor("clock",preset={"titel":"Tagesplan öffnen","faellig":when.date().isoformat(),
                                    "uhrzeit":"19:00","intervall":1})

    def editor(self,kind="plan",existing=None,preset=None):
        self.page("editor","Eintrag bearbeiten" if existing else "Neuer Eintrag")
        self.entry_id=existing["id"] if existing else None
        self.busy=False
        self.calendars=None
        data=existing or preset or {}
        self.caption("Eintragstyp")
        self.type_choice=select(TYPES.values(),TYPES[kind])
        self.body.add_widget(self.type_choice)
        self.caption("Titel")
        self.title_field=field(data.get("titel"),"Was möchtest du dir merken?")
        self.body.add_widget(self.title_field)
        self.details_form=stack(7)
        self.body.add_widget(self.details_form)
        due=data.get("faellig")
        self.date_field=field(date.fromisoformat(due).strftime("%d.%m.%Y") if due else "","TT.MM.JJJJ")
        self.time_field=field(data.get("uhrzeit"),"HH:MM")
        self.repeat_choice=select(WEEK,next((k for k,v in WEEK.items() if v==data.get("intervall")),"Einmalig"))
        selected_day=date.fromisoformat(due) if due else date.today()
        self.weekday_choice=select(DAYS,DAYS[selected_day.weekday()])
        self.repeat_choice.bind(text=lambda *_:self.form_kind() if self.kind=="clock" else None)
        self.note_field=field(data.get("notiz"),"Optional",True)
        self.type_choice.bind(text=lambda *_:self.form_kind())
        self.form_kind()

    def form_kind(self):
        kind=next(k for k,v in TYPES.items() if v==self.type_choice.text)
        self.kind=kind
        form=self.details_form
        form.clear_widgets()
        self.footer.clear_widgets()
        if kind in ("clock","calendar") and not self.date_field.text and not self.time_field.text:
            start=(datetime.now()+timedelta(hours=1)).replace(second=0,microsecond=0)
            self.date_field.text=start.strftime("%d.%m.%Y")
            self.time_field.text=start.strftime("%H:%M")
        if kind in ("plan","calendar"):
            self.caption("Datum",form)
            form.add_widget(self.date_field)
            dates=row(44)
            dates.add_widget(tap("Heute",lambda:setattr(self.date_field,"text",date.today().strftime("%d.%m.%Y")),height=44))
            dates.add_widget(tap("Morgen",lambda:setattr(self.date_field,"text",(date.today()+timedelta(days=1)).strftime("%d.%m.%Y")),height=44))
            form.add_widget(dates)
        if kind in ("plan","calendar","clock"):
            self.caption("Uhrzeit",form)
            form.add_widget(self.time_field)
            self.caption("Wiederholung",form)
            form.add_widget(self.repeat_choice)
            if kind=="clock" and WEEK[self.repeat_choice.text]==7:
                self.caption("Wochentag",form)
                form.add_widget(self.weekday_choice)
        self.calendar_choice=None
        if kind=="calendar":
            if not getattr(self, "calendar_permission_requested", False):
                self.calendar_permission_requested = True
                try:
                    from android.permissions import Permission, check_permission, request_permissions
                    needed = [p for p in (Permission.READ_CALENDAR, Permission.WRITE_CALENDAR)
                              if not check_permission(p)]
                    if needed:
                        def permission_result(*_):
                            def refresh(_dt):
                                if self.screen == "editor" and self.kind == "calendar":
                                    self.calendars = None
                                    self.form_kind()
                            Clock.schedule_once(refresh, 0)
                        request_permissions(needed, permission_result)
                except (ImportError, RuntimeError):
                    pass
            if self.calendars is None:
                self.calendars=writable_calendars()
            if self.calendars:
                self.caption("Zielkalender",form)
                initial=next(iter(self.calendars)) if len(self.calendars)==1 else PICK_CALENDAR
                self.calendar_choice=select([PICK_CALENDAR,*self.calendars],initial)
                form.add_widget(self.calendar_choice)
                form.add_widget(paragraph("Direkt im gewählten Kalender: 30 Minuten, Erinnerung bei Beginn."))
            else:
                form.add_widget(paragraph("Die Kalender-App erhält Titel, Datum und Uhrzeit. Speichere den Termin dort."))
        if kind!="clock" or self.note_field.text:
            self.caption("Notiz",form)
            form.add_widget(self.note_field)
        external=kind in ("clock","calendar","note")
        if self.entry_id:
            form.add_widget(tap("Archivieren",partial(self.mutate,"archive",self.entry_id)))
        labels={"clock":"Speichern & Wecker stellen","calendar":"Speichern & Kalender öffnen",
                "note":"Speichern & Notiz teilen"}
        if external and self.entry_id:
            labels={"clock":"Als neuen Wecker übergeben","calendar":"Als neuen Termin übergeben",
                    "note":"Notiz teilen"}
        if external:
            form.add_widget(tap("Im Planer speichern",partial(self.save,False)))
        action=tap(labels.get(kind,"Speichern"),partial(self.save,external),self.theme,WHITE,52)
        self.footer.add_widget(action)
        if self.calendar_choice is not None:
            def change_label(_choice,value):
                action.text=labels["calendar"] if value==PICK_CALENDAR else (
                    "Neuen Kalendereintrag speichern" if self.entry_id else "Im Kalender speichern")
            self.calendar_choice.bind(text=change_label)
            change_label(None,self.calendar_choice.text)
        if self.entry_id and kind in ("clock","calendar"):
            form.add_widget(paragraph("Die erneute Übergabe bereitet einen neuen Eintrag in der Handy-App vor."))

    def save(self,handoff):
        if self.busy:
            return
        self.busy=True
        try:
            scheduled=self.kind in ("clock","calendar","plan")
            data={"titel":self.title_field.text.strip(),"notiz":self.note_field.text.strip(),
                  "bereich":{"shopping":"einkauf","note":"notiz"}.get(self.kind,"aufgabe"),
                  "faellig":read_local_day(self.date_field.text) if self.kind in ("plan","calendar") else "",
                  "uhrzeit":self.time_field.text.strip() if scheduled else "",
                  "intervall":WEEK[self.repeat_choice.text] if scheduled else None}
            if self.kind=="clock":
                try:
                    now=datetime.now()
                    when=datetime.combine(now.date(),time.fromisoformat(data["uhrzeit"]))
                except ValueError as error:
                    raise InputError("Bitte die Weckzeit als HH:MM eingeben, z. B. 07:30.") from error
                if when<=now:
                    when+=timedelta(days=1)
                if data["intervall"]==7:
                    when+=timedelta(days=(DAYS.index(self.weekday_choice.text)-when.weekday())%7)
                data["faellig"]=when.date().isoformat()
            entry_values(data)
            request=android_request(self.kind,data) if handoff else None
            self.entry_id=store_entry(data,self.kind,self.entry_id)
        except (ValueError,sqlite3.Error) as error:
            self.busy=False
            self.notify(str(error))
            return
        if not handoff:
            self.home("Gespeichert.")
            return
        target=(self.calendars or {}).get(self.calendar_choice.text) if self.calendar_choice is not None else None
        if self.kind=="calendar" and target is not None:
            try:
                verified=insert_calendar_event(target,data)
            except Exception:
                verified=False
            if verified:
                self.home("Termin mit Erinnerung im gewählten Kalender gespeichert.")
            else:
                self.outcome("calendar",data,False,
                             "Der direkte Eintrag wurde nicht bestätigt. Prüfe deinen Kalender vor einer erneuten Übergabe.")
            return
        self.outcome(self.kind,data,deliver(request))

    def outcome(self,kind,data,opened,reason=""):
        self.page("result","App-Übergabe")
        self.body.add_widget(label("Im Planer gespeichert",21,INK,True,48))
        text={"calendar":"Die Kalender-App wurde aufgerufen. Prüfe die Benachrichtigung und speichere den Termin dort.",
              "clock":"Der Wecker wurde angefordert. Prüfe in der Uhr-App, ob er aktiv ist, und bestätige ihn bei Bedarf.",
              "note":"Android hat die Notiz zum Teilen erhalten. Wähle deine Notiz-App und speichere sie dort."}
        self.body.add_widget(paragraph(text[kind] if opened else reason or
            "Android konnte die Ziel-App nicht öffnen. Dein Eintrag ist lokal gespeichert."))
        if not opened:
            if kind=="calendar":
                def export():
                    try:
                        saved=export_event(data)
                        self.notify("Kalenderdatei gespeichert neben dem Skript: "+saved.name)
                    except (ValueError,OSError) as error:
                        self.notify(str(error))
                self.body.add_widget(tap("Kalenderdatei speichern",export))
            def copy():
                text="\n".join(x for x in (data["titel"],data.get("faellig"),data.get("uhrzeit"),data.get("notiz")) if x)
                Clipboard.copy(text)
                self.notify("In die Zwischenablage kopiert.")
            self.body.add_widget(tap("Daten kopieren",copy))
        self.footer.add_widget(tap("Fertig",self.home,self.theme,WHITE,52))


if __name__=="__main__":
    Tagesplan().run()
