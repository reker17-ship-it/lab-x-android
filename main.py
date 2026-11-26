import math, time, csv, os
from collections import deque
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp

SENSORS = {1:('Beschleunigung','m/s²',3),2:('Magnetfeld','µT',3),4:('Gyroskop','rad/s',3),5:('Licht','lx',1),6:('Luftdruck','hPa',1),8:('Näherung','cm',1),9:('Schwerkraft','m/s²',3),10:('Lineare Beschleunigung','m/s²',3),12:('Luftfeuchtigkeit','%',1),13:('Raumtemperatur','°C',1),19:('Schrittzähler','Schritte',1)}
EXTRA={'Akkutemperatur':'°C','Akkuspannung':'V','Akkustand':'%','Ladestrom':'mA','WLAN-Signal':'dBm','Kompass (magnetisch)':'°','Neigung X':'°','Neigung Y':'°','Relative Druckhöhe':'m'}
class Graph(Widget):
    def draw(self, data):
        self.canvas.clear()
        with self.canvas:
            Color(.035,.09,.13); Rectangle(pos=self.pos,size=self.size)
            Color(.12,.24,.29)
            for i in range(6):
                y=self.y+self.height*i/5; Line(points=[self.x,y,self.right,y])
            if len(data)>1:
                lo,hi=min(data),max(data); span=max(hi-lo,1e-8)
                pts=[]
                for i,v in enumerate(data): pts.extend([self.x+i*self.width/(len(data)-1),self.y+self.height*(.05+.9*(v-lo)/span)])
                Color(.2,1,.65); Line(points=pts,width=1.5)
class Lab(App):
    def build(self):
        Window.clearcolor=(.025,.05,.08,1)
        self.values={}; self.units={v[0]:v[1] for v in SENSORS.values()}; self.units.update(EXTRA)
        self.history=deque(maxlen=300); self.ref=0; self.low=None; self.high=None; self.paused=False; self.file=None; self.lastlog=0; self.pressure0=None; self.manager=None; self.listener=None; self.error=''; self.available=[]
        root=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(6))
        def label(s,h):
            w=Label(text=s,color=(.3,1,.75,1),size_hint_y=None,height=dp(h)); root.add_widget(w); return w
        label('LAB X  /  GLOBAL 4.1',38)
        self.setup()
        self.available=list(dict.fromkeys(self.available+list(self.units)))
        self.selector=Spinner(text=self.available[0] if self.available else 'Keine Sensoren',values=self.available,size_hint_y=None,height=dp(48)); root.add_widget(self.selector); self.selector.bind(text=self.change)
        self.readout=label('Warte auf Messdaten ...',65); self.readout.font_size='30sp'
        self.stats=label('',44); self.graph=Graph(); root.add_widget(self.graph)
        self.detail=label('',42); self.status=label(self.error or 'LIVE',44); self.status.font_size='12sp'; self.status.bind(size=lambda w,s:setattr(w,'text_size',s)); self.status.halign='center'
        def row(items):
            r=BoxLayout(size_hint_y=None,height=dp(45),spacing=dp(5)); root.add_widget(r)
            for title,fn in items:
                b=Button(text=title,background_normal='',background_color=(.08,.23,.28,1)); b.bind(on_release=fn); r.add_widget(b)
        row([('Pause / Live',self.pause),('Referenz',self.reference),('Reset',self.reset)])
        row([('CSV Start / Stopp',self.record),('Sensorliste',self.inventory),('Vollbild',self.full)])
        self.alarm=TextInput(hint_text='Oberer Alarmgrenzwert (optional)',multiline=False,size_hint_y=None,height=dp(42),input_type='number'); root.add_widget(self.alarm)
        Clock.schedule_interval(self.update,.15); Clock.schedule_interval(self.system,2); self.system(0)
        return root
    def setup(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            try: activity=autoclass('org.kivy.android.PythonActivity').mActivity
            except Exception: activity=autoclass('org.renpy.android.PythonActivity').mActivity
            self.ctx=activity; self.ac=autoclass; self.manager=activity.getSystemService('sensor'); owner=self
            class Listener(PythonJavaClass):
                __javainterfaces__=['android/hardware/SensorEventListener']; __javacontext__='app'
                @java_method('(Landroid/hardware/SensorEvent;)V')
                def onSensorChanged(self,event):
                    try:
                        k=event.sensor.getType(); name,unit,n=SENSORS[k]; owner.values[name]=tuple(float(event.values[i]) for i in range(n))
                    except Exception: pass
                @java_method('(Landroid/hardware/Sensor;I)V')
                def onAccuracyChanged(self,sensor,accuracy): pass
            self.listener=Listener()
            for k,(name,unit,n) in SENSORS.items():
                try:
                    s=self.manager.getDefaultSensor(k)
                    if s and self.manager.registerListener(self.listener,s,3): self.available.append(name)
                except Exception: pass
            self.available.extend(n for n in self.units if n not in self.available)
        except Exception as e: self.error='Android-Zugriff fehlgeschlagen: '+str(e)[:100]
    def system(self,dt):
        if not hasattr(self,'ctx'): return
        try:
            intent=self.ctx.registerReceiver(None,self.ac('android.content.IntentFilter')('android.intent.action.BATTERY_CHANGED'))
            for name,key,div in [('Akkutemperatur','temperature',10),('Akkuspannung','voltage',1000),('Akkustand','level',1)]:
                v=intent.getIntExtra(key,-99999)
                if v!=-99999:
                    if key=='level': div=max(1,intent.getIntExtra('scale',100))/100
                    self.values[name]=(v/div,)
            v=self.ctx.getSystemService('batterymanager').getIntProperty(2)
            if v!=-2147483648: self.values['Ladestrom']=(v/1000,)
            else: self.values.pop('Ladestrom',None)
        except Exception: pass
        try:
            info=self.ctx.getSystemService('wifi').getConnectionInfo(); v=info.getRssi()
            if -126<v<0: self.values['WLAN-Signal']=(float(v),)
            else: self.values.pop('WLAN-Signal',None)
        except Exception: self.values.pop('WLAN-Signal',None)
    def derived(self):
        a=self.values.get('Beschleunigung'); m=self.values.get('Magnetfeld')
        if a:
            x,y,z=a; self.values['Neigung X']=(math.degrees(math.atan2(x,math.hypot(y,z))),); self.values['Neigung Y']=(math.degrees(math.atan2(y,math.hypot(x,z))),)
        if a and m:
            try:
                from jnius import autoclass
                # East = magnetic field cross gravity; north = gravity cross east
                x,y,z=a; u,v,w=m; e=(v*z-w*y,w*x-u*z,u*y-v*x); en=math.sqrt(sum(i*i for i in e)); an=math.sqrt(sum(i*i for i in a))
                if en>0 and an>0:
                    ex,ey,ez=(i/en for i in e); x,y,z=(i/an for i in a); ny=z*ex-x*ez
                    self.values['Kompass (magnetisch)']=((math.degrees(math.atan2(ey,ny))+360)%360,)
            except Exception: pass
        p=self.values.get('Luftdruck')
        if p and p[0]>0:
            if self.pressure0 is None: self.pressure0=p[0]
            self.values['Relative Druckhöhe']=(44330*(1-(p[0]/self.pressure0)**.1903),)
    def change(self,*args): self.reset(); setattr(self.alarm,'text','') if hasattr(self,'alarm') else None
    def reset(self,*args): self.history.clear(); self.ref=0; self.low=self.high=None
    def pause(self,*args): self.paused=not self.paused
    def reference(self,*args):
        v=self.values.get(self.selector.text)
        if v: self.reset(); self.ref=self.scalar(v)
    def scalar(self,v): return math.sqrt(sum(x*x for x in v)) if len(v)>1 else v[0]
    def update(self,dt):
        if self.paused: self.status.text='PAUSE'; return
        self.derived(); name=self.selector.text; v=self.values.get(name)
        if not v: self.status.text='Keine aktuellen Daten'; self.readout.text='Nicht verfügbar'; self.stats.text=''; self.detail.text=''; self.graph.draw([]); return
        raw=self.scalar(v); val=raw-self.ref; unit=self.units[name]; self.history.append(val); self.low=val if self.low is None else min(val,self.low); self.high=val if self.high is None else max(val,self.high)
        self.readout.text=f'{val:.3f} {unit}'; self.stats.text=f'MIN {self.low:.3f}    MAX {self.high:.3f}'; self.detail.text='  '.join(f'{k}: {x:.3f}' for k,x in zip('XYZ',v)) if len(v)>1 else f'Rohwert: {raw:.3f} {unit}'
        self.graph.draw(self.history); self.status.text='LIVE'+(' | CSV aktiv' if self.file else '')
        try:
            if val>float(self.alarm.text.replace(',','.')): self.status.text='ALARM: Grenzwert überschritten'; self.readout.color=(1,.25,.25,1)
            else: self.readout.color=(.3,1,.75,1)
        except ValueError: self.readout.color=(.3,1,.75,1)
        if self.file and time.monotonic()-self.lastlog>=1:
            self.writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'),name,unit,val,*v,*(['']*(3-len(v)))]); self.file.flush(); self.lastlog=time.monotonic()
    def record(self,*args):
        if self.file: self.file.close(); self.file=None; self.message('CSV gespeichert',self.path); return
        try:
            self.path=os.path.join(self.user_data_dir,time.strftime('lab_%Y%m%d_%H%M%S.csv')); os.makedirs(self.user_data_dir,exist_ok=True); self.file=open(self.path,'w',newline='',encoding='utf-8'); self.writer=csv.writer(self.file); self.writer.writerow(['Zeit','Sensor','Einheit','Messwert','Rohwert_X','Rohwert_Y','Rohwert_Z'])
        except Exception as e: self.message('CSV Fehler',str(e))
    def message(self,title,msg):
        from kivy.uix.popup import Popup
        w=Label(text=msg); w.bind(size=lambda obj,s:setattr(obj,'text_size',s)); Popup(title=title,content=w,size_hint=(.95,.8)).open()
    def inventory(self,*args): self.message('Sensorstatus','\n'.join(n+': '+('Messwert vorhanden' if n in self.values else 'Keine Daten') for n in self.units))
    def full(self,*args):
        from kivy.uix.popup import Popup
        g=Graph(); p=Popup(title=self.selector.text,content=g,size_hint=(1,1)); ev=Clock.schedule_interval(lambda dt:g.draw(self.history),.15); p.bind(on_dismiss=lambda *a:ev.cancel()); p.open()
    def on_stop(self):
        if self.manager and self.listener: self.manager.unregisterListener(self.listener)
        if self.file: self.file.close()


# Additional Android sensor types (scalar or three-axis measurements).
SENSORS.update({14:('Magnetfeld unkalibriert','µT',3),16:('Gyroskop unkalibriert','rad/s',3),18:('Schritterkennung','Ereignis',1),
  21:('Herzfrequenz','bpm',1),28:('Pose-Bewegung','Ereignis',1),31:('Herzschlag-Konfidenz','Wert',1),35:('Beschleunigung unkalibriert','m/s²',3),
  29:('Stationär','Ereignis',1),30:('Bewegung erkannt','Ereignis',1)})
# Trigger-only and pose sensors require other APIs; do not register them here.
for k in (28,29,30): SENSORS.pop(k,None)
SENSOR_PERMISSIONS = {
    SENSORS[k][0]: (k, 'android.permission.ACTIVITY_RECOGNITION', 29) for k in (18, 19)
}
SENSOR_PERMISSIONS.update({
    SENSORS[k][0]: (k, 'android.permission.BODY_SENSORS', 24) for k in (21, 31)
})
EXTRA.update({'Akku-Leistung':'W','Akku-Ladungszähler':'mAh','Akku-Energie':'Wh','Akku-Strom Mittel':'mA',
 'WLAN-Frequenz':'MHz','WLAN-Linkrate':'Mbit/s','WLAN-Kanal':'Kanal','RAM frei':'MiB','RAM gesamt':'MiB',
 'Speicher frei':'GiB','Speicher gesamt':'GiB','CPU-Kerne':'Anzahl','Systemlaufzeit':'h','Bildschirmhelligkeit':'% (Einstellung)',
 'Bildwiederholrate':'Hz','GPS Breite':'°','GPS Länge':'°','GPS Höhe':'m','GPS Tempo':'km/h','GPS Genauigkeit':'m','GPS Kurs':'°',
 'Mikrofon RMS':'dBFS','Mikrofon Peak':'dBFS','Tonfrequenz':'Hz','Thermalstatus':'Stufe','Akku-Ladestatus':'Code',
 'Neigung gesamt':'°','Dynamische Beschleunigung':'m/s²'})

import threading, struct, shutil
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup

class Omega(Lab):
    def build(self):
        self.audio_running=False; self.audio_thread=None; self.audio_error=''; self.gps=None; self.gps_active=False; self.gps_time=0
        root=super().build()
        r=BoxLayout(size_hint_y=None,height=dp(44),spacing=dp(5)); root.add_widget(r)
        for text,fn in [('GPS Start/Stopp',self.toggle_gps),('MIC Start/Stopp',self.toggle_audio),('Dashboard',self.dashboard)]:
            b=Button(text=text,font_size='12sp',background_normal='',background_color=(.08,.23,.28,1)); b.bind(on_release=fn); r.add_widget(b)
        self.selector.option_cls = __import__('kivy.uix.spinner',fromlist=['SpinnerOption']).SpinnerOption
        return root
    def system(self,dt):
        super().system(dt)
        if not hasattr(self,'ctx'): return
        def put(n,fn):
            try:
                v=fn()
                if v is None or not math.isfinite(float(v)): raise ValueError()
                self.values[n]=(float(v),)
            except Exception: self.values.pop(n,None)
        bm=self.ctx.getSystemService('batterymanager')
        def prop(k,div,long=False):
            v=bm.getLongProperty(k) if long else bm.getIntProperty(k)
            return None if v in (-2147483648,-9223372036854775808) else v/div
        put('Akku-Ladungszähler',lambda:prop(1,1000)); put('Akku-Strom Mittel',lambda:prop(3,1000)); put('Akku-Energie',lambda:prop(5,1e9,True))
        put('Akku-Leistung',lambda:self.values['Akkuspannung'][0]*self.values['Ladestrom'][0]/1000)
        put('Akku-Ladestatus',lambda:self.ctx.registerReceiver(None,self.ac('android.content.IntentFilter')('android.intent.action.BATTERY_CHANGED')).getIntExtra('status',1))
        def wifi(method):
            i=self.ctx.getSystemService('wifi').getConnectionInfo()
            if i.getNetworkId()<0: return None
            v=getattr(i,method)(); return v if v>0 else None
        put('WLAN-Frequenz',lambda:wifi('getFrequency')); put('WLAN-Linkrate',lambda:wifi('getLinkSpeed'))
        def channel():
            f=self.values['WLAN-Frequenz'][0]
            if f==2484:return 14
            if 2412<=f<=2472:return (f-2407)/5
            if 5000<f<5900:return (f-5000)/5
            if f==5935:return 2
            if 5955<=f<=7115:return (f-5950)/5
        put('WLAN-Kanal',channel)
        def ram(attr):
            info=self.ac('android.app.ActivityManager$MemoryInfo')(); self.ctx.getSystemService('activity').getMemoryInfo(info); return getattr(info,attr)/1048576
        put('RAM frei',lambda:ram('availMem')); put('RAM gesamt',lambda:ram('totalMem'))
        put('Speicher frei',lambda:shutil.disk_usage(self.user_data_dir if os.path.exists(self.user_data_dir) else os.path.expanduser('~')).free/2**30)
        put('Speicher gesamt',lambda:shutil.disk_usage(self.user_data_dir if os.path.exists(self.user_data_dir) else os.path.expanduser('~')).total/2**30)
        put('CPU-Kerne',os.cpu_count); put('Systemlaufzeit',lambda:self.ac('android.os.SystemClock').elapsedRealtime()/3600000)
        put('Bildschirmhelligkeit',lambda:self.ac('android.provider.Settings$System').getInt(self.ctx.getContentResolver(),'screen_brightness')*100/255)
        put('Bildwiederholrate',lambda:self.ctx.getWindowManager().getDefaultDisplay().getRefreshRate())
        put('Thermalstatus',lambda:self.ctx.getSystemService('power').getCurrentThermalStatus())
        if time.monotonic()-self.gps_time>20:
            for n in EXTRA:
                if n.startswith('GPS '): self.values.pop(n,None)
    def derived(self):
        super().derived()
        a=self.values.get('Schwerkraft') or self.values.get('Beschleunigung')
        if a: self.values['Neigung gesamt']=(math.degrees(math.atan2(math.hypot(a[0],a[1]),a[2])),)
        a=self.values.get('Lineare Beschleunigung')
        if a: self.values['Dynamische Beschleunigung']=(self.scalar(a),)
    def change(self, *args):
        super().change(*args)
        protected = SENSOR_PERMISSIONS.get(self.selector.text)
        if not protected or not self.manager or not self.listener:
            return
        sensor_type, permission, min_api = protected
        if self.ac('android.os.Build$VERSION').SDK_INT >= min_api:
            sensor = self.manager.getDefaultSensor(sensor_type)
            if sensor:
                self.permissions([permission], lambda: self.manager.registerListener(self.listener, sensor, 3))

    def permissions(self,names,fn):
        message = 'Erlaube den Zugriff in den Android-Einstellungen unter Apps > LAB X > Berechtigungen.'
        def granted():
            results = [self.ctx.checkSelfPermission(name) == 0 for name in names]
            if 'android.permission.ACCESS_COARSE_LOCATION' in names:
                return any(results)
            return all(results)

        def finish(dt):
            if granted():
                fn()
            else:
                self.message('Berechtigung fehlt', message)

        try:
            if granted():
                fn()
            elif self.ctx.getPackageName() == 'org.reker17.labx':
                from android.permissions import request_permissions
                request_permissions(names, lambda *_: Clock.schedule_once(finish))
            else:
                self.message('Berechtigung fehlt', 'Erlaube den Zugriff in den Android-Einstellungen für die App, in der LAB X läuft.')
        except Exception as e:
            self.message('Berechtigung nicht prüfbar',str(e))
    def toggle_gps(self,*args):
        if self.gps_active: self.stop_gps(); return
        self.permissions(['android.permission.ACCESS_FINE_LOCATION','android.permission.ACCESS_COARSE_LOCATION'],self.start_gps)
    def start_gps(self):
        try:
            from plyer import gps
            self.gps=gps; gps.configure(on_location=self.location,on_status=lambda *a,**kw:None); gps.start(minTime=1000,minDistance=0); self.gps_active=True
            self.message('GPS aktiv','Warte auf Standortfix. Im Freien meist besser. Standortdaten werden nur bei aktivem CSV-Logger für den ausgewählten GPS-Wert gespeichert.')
        except Exception as e:self.message('GPS nicht verfügbar',str(e))
    def location(self,**kw):
        if not self.gps_active:return
        self.gps_time=time.monotonic()
        for n,k,f in [('Breite','lat',1),('Länge','lon',1),('Höhe','altitude',1),('Tempo','speed',3.6),('Genauigkeit','accuracy',1),('Kurs','bearing',1)]:
            try:self.values['GPS '+n]=(float(kw[k])*f,)
            except (KeyError,ValueError,TypeError):self.values.pop('GPS '+n,None)
    def stop_gps(self):
        self.gps_active=False
        if self.gps:
            try:self.gps.stop()
            except Exception:pass
        for n in EXTRA:
            if n.startswith('GPS '):self.values.pop(n,None)
    def toggle_audio(self,*args):
        if self.audio_running:self.audio_running=False;return
        if self.audio_thread and self.audio_thread.is_alive():return
        self.permissions(['android.permission.RECORD_AUDIO'],self.start_audio)
    def start_audio(self):
        if self.audio_running:return
        self.audio_running=True; self.audio_thread=threading.Thread(target=self.capture,daemon=True); self.audio_thread.start()
    def capture(self):
        rec=None
        try:
            AR=self.ac('android.media.AudioRecord'); rate=16000; n=2048; size=AR.getMinBufferSize(rate,16,2)
            if size<=0:raise RuntimeError('Audioformat nicht unterstützt')
            rec=AR(1,rate,16,2,max(size,n*4))
            if rec.getState()!=1:raise RuntimeError('Mikrofon nicht verfügbar')
            rec.startRecording(); buf=bytearray(n*2)
            while self.audio_running:
                got=rec.read(buf,0,len(buf))
                if got<0:raise RuntimeError('Audio-Lesefehler')
                if got<4:continue
                a=struct.unpack_from('<'+'h'*(got//2),buf); self.monitor_samples(a,rate) if hasattr(self,'monitor_samples') else None; rms=math.sqrt(sum(x*x for x in a)/len(a))/32768; peak=max(map(abs,a))/32768
                self.values['Mikrofon RMS']=(20*math.log10(max(rms,1e-6)),); self.values['Mikrofon Peak']=(20*math.log10(max(peak,1e-6)),)
                try:
                    import numpy as np
                    if rms>.001 and len(a)>=6:
                        x=np.array(a,dtype=float); x-=x.mean(); spec=np.abs(np.fft.rfft(x*np.hanning(len(x)))); k=int(np.argmax(spec[3:])+3)
                        self.values['Tonfrequenz']=(k*rate/len(x),)
                    else:self.values.pop('Tonfrequenz',None)
                except ImportError:self.values.pop('Tonfrequenz',None)
        except Exception as e:
            msg=str(e); Clock.schedule_once(lambda dt:self.message('Mikrofon',msg),0)
        finally:
            if rec:
                try:rec.stop()
                except Exception:pass
                try:rec.release()
                except Exception:pass
            self.audio_running=False
            if hasattr(self,"close_monitor"): self.close_monitor()
            for n in ('Mikrofon RMS','Mikrofon Peak','Tonfrequenz'):self.values.pop(n,None)
    def dashboard(self,*args):
        scroll=ScrollView(); grid=BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(3)); grid.bind(minimum_height=grid.setter('height')); scroll.add_widget(grid)
        labels={}
        for n,u in self.units.items():
            b=Button(text=n,size_hint_y=None,height=dp(44),background_normal='',background_color=(.08,.23,.28,1)); grid.add_widget(b); labels[n]=b
        p=Popup(title='OMEGA / Messinstrumente',content=scroll,size_hint=(.97,.95))
        def select(n):self.selector.text=n;p.dismiss()
        for n,b in labels.items():b.bind(on_release=lambda w,n=n:select(n))
        def refresh(dt):
            for n,b in labels.items():
                v=self.values.get(n); b.text=n+'  |  '+(f'{self.scalar(v):.3f} {self.units[n]}' if v else 'Keine Daten')
        refresh(0); ev=Clock.schedule_interval(refresh,.5);p.bind(on_dismiss=lambda *a:ev.cancel());p.open()
    def inventory(self,*args):self.dashboard()
    def on_pause(self):
        self.audio_running=False;self.stop_gps();return True
    def on_stop(self):
        self.audio_running=False;self.stop_gps();super().on_stop()



import json, ssl, urllib.request, urllib.parse
from kivy.uix.slider import Slider
WEATHER = {'temperature_2m':('Außentemperatur','°C'),'relative_humidity_2m':('Außen-Luftfeuchtigkeit','%'),'apparent_temperature':('Gefühlte Temperatur','°C'),'surface_pressure':('Außen-Luftdruck','hPa'),'pressure_msl':('Meeresspiegel-Luftdruck','hPa'),'wind_speed_10m':('Wind','km/h'),'wind_direction_10m':('Windrichtung','°'),'wind_gusts_10m':('Windböen','km/h'),'precipitation':('Niederschlag','mm'),'cloud_cover':('Bewölkung','%'),'weather_code':('Wettercode','WMO'),'is_day':('Tageslicht','0/1')}
HOURLY={'dew_point_2m':('Taupunkt außen','°C'),'visibility':('Sichtweite','m'),'uv_index':('UV-Index','Index')}
AIR={'pm2_5':('Feinstaub PM2.5','µg/m³'),'pm10':('Feinstaub PM10','µg/m³'),'ozone':('Ozon','µg/m³'),'nitrogen_dioxide':('Stickstoffdioxid','µg/m³'),'carbon_monoxide':('Kohlenmonoxid','µg/m³'),'sulphur_dioxide':('Schwefeldioxid','µg/m³'),'european_aqi':('EU Luftqualitätsindex','Index')}
ONLINE={n:u for n,u in list(WEATHER.values())+list(HOURLY.values())+list(AIR.values())}; ONLINE['Absolute Feuchte außen']='g/m³'
EXTRA.update(ONLINE)
class GlobalLab(Omega):
    def build(self):
        self.online_place=''; self.online_coords=None; self.online_busy=False; self.online_stamp=''; self.monitor=False; self.gain=1.; self.highpass=True; self.track=None; self.prev_x=0.; self.prev_y=0.
        root=super().build(); row=BoxLayout(size_hint_y=None,height=dp(44),spacing=dp(5)); root.add_widget(row)
        for text,fn in [('ONLINE / Wetter',self.weather_menu),('AUDIO / Verstärker',self.audio_menu)]:
            b=Button(text=text,background_normal='',background_color=(.08,.23,.28,1)); b.bind(on_release=fn); row.add_widget(b)
        Clock.schedule_interval(lambda dt:self.fetch_weather() if self.online_coords else None,900)
        return root
    def update(self,dt):
        super().update(dt)
        if not self.paused and self.selector.text in ONLINE:
            self.status.text='ONLINE | '+self.online_place+' | '+(self.online_stamp or 'Keine Daten')+(' | CSV aktiv' if self.file else '')+(' | ALARM' if self.readout.color[0]>.9 else '')
    def weather_menu(self,*args):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8)); box.add_widget(Label(text='Open-Meteo: Außenwerte aus Wettermodellen.\nOrt oder GPS-Koordinaten werden an den Dienst gesendet.'))
        field=TextInput(text=self.online_place or '',hint_text='Stadt eingeben',multiline=False,size_hint_y=None,height=dp(45)); box.add_widget(field)
        p=Popup(title='Online-Daten',content=box,size_hint=(.96,.65))
        def city(*a):
            if field.text.strip(): self.online_coords=None; self.online_place=field.text.strip(); p.dismiss(); self.fetch_weather()
        def gps(*a):
            try:self.online_coords=(self.values['GPS Breite'][0],self.values['GPS Länge'][0]); self.online_place='GPS'; p.dismiss(); self.fetch_weather()
            except KeyError:self.message('GPS','Zuerst GPS starten und auf Standort warten.')
        for t,f in [('Stadt laden',city),('GPS freiwillig verwenden',gps)]:
            b=Button(text=t,size_hint_y=None,height=dp(45)); b.bind(on_release=f); box.add_widget(b)
        p.open()
    def fetch_weather(self):
        if self.online_busy:return
        self.online_busy=True; place=self.online_place; coords=self.online_coords
        def get(url,params):
            try:
                import certifi
            except ImportError:
                context = None
            else:
                context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(url+'?'+urllib.parse.urlencode(params),timeout=15,context=context) as r:return json.load(r)
        def worker():
            data={}; stamp=''; errors=[]; pos=coords; name=place
            try:
                if not pos:
                    g=get('https://geocoding-api.open-meteo.com/v1/search',{'name':place,'count':1,'language':'de'})['results'][0]; pos=(g['latitude'],g['longitude']); name=g['name']+', '+g.get('country','')
                base={'latitude':pos[0],'longitude':pos[1],'timezone':'auto'}
                w=get('https://api.open-meteo.com/v1/forecast',dict(base,current=','.join(WEATHER),hourly=','.join(HOURLY),forecast_days=1)); cur=w['current']; stamp=cur['time']; h=w['hourly']; i=min(range(len(h['time'])),key=lambda i:abs(__import__('datetime').datetime.fromisoformat(h['time'][i])-__import__('datetime').datetime.fromisoformat(stamp)))
                for k,(n,u) in WEATHER.items():
                    if cur.get(k) is not None:data[n]=(float(cur[k]),)
                for k,(n,u) in HOURLY.items():
                    if h[k][i] is not None:data[n]=(float(h[k][i]),)
                t=cur['temperature_2m']; rh=cur['relative_humidity_2m']; data['Absolute Feuchte außen']=(216.7*(rh/100*6.112*math.exp(17.62*t/(243.12+t)))/(273.15+t),)
            except Exception as e:errors.append('Wetter: '+str(e))
            if pos:
                try:
                    a=get('https://air-quality-api.open-meteo.com/v1/air-quality',dict(base,current=','.join(AIR)))['current']
                    for k,(n,u) in AIR.items():
                        if a.get(k) is not None:data[n]=(float(a[k]),)
                except Exception as e:errors.append('Luftqualität: '+str(e))
            def done(dt):
                self.online_busy=False; self.online_coords=pos; self.online_place=name; self.online_stamp=stamp or 'Zeit unbekannt'
                for n in ONLINE:self.values.pop(n,None)
                self.values.update(data)
                if data:self.selector.text=next(iter(data))
                if errors:self.message('Online-Daten', '\n'.join(errors))
            Clock.schedule_once(done,0)
        threading.Thread(target=worker,daemon=True).start()
    def audio_menu(self,*args):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8)); box.add_widget(Label(text='Nur mit Kopfhörern verwenden.\nLeise beginnen! Keine Lautsprecher-Rückkopplung.\nDigitaler Gain, kein zusätzlicher Sensor.'))
        l=Label(text=f'Verstärkung: {self.gain:.1f}x',size_hint_y=None,height=dp(35)); box.add_widget(l)
        slider=Slider(min=1,max=8,step=.5,value=self.gain,size_hint_y=None,height=dp(45)); box.add_widget(slider)
        def gain(w,v):self.gain=v;l.text=f'Verstärkung: {v:.1f}x'
        slider.bind(value=gain)
        f=Button(text='Hochpass: '+('AN' if self.highpass else 'AUS'),size_hint_y=None,height=dp(45)); box.add_widget(f)
        def filt(*a):self.highpass=not self.highpass;f.text='Hochpass: '+('AN' if self.highpass else 'AUS')
        f.bind(on_release=filt)
        b=Button(text='Monitor START / STOPP',size_hint_y=None,height=dp(48));box.add_widget(b)
        def start_monitor():
            if not self.headphones():self.message('Audio','Kabel- oder USB-Kopfhörer anschließen.');return
            if self.audio_thread and self.audio_thread.is_alive() and not self.audio_running:return
            self.monitor=True
            self.start_audio()
        def toggle(*a):
            if self.monitor:self.monitor=False;return
            if not self.headphones():self.message('Audio','Kabel- oder USB-Kopfhörer anschließen.');return
            self.permissions(['android.permission.RECORD_AUDIO'],start_monitor)
        b.bind(on_release=toggle);Popup(title='Audio-Labor',content=box,size_hint=(.96,.7)).open()
    def headphones(self):
        try:return any(d.getType() in (3,4,22) for d in self.ctx.getSystemService('audio').getDevices(2))
        except Exception:return False
    def close_monitor(self):
        if self.track:
            try:self.track.stop();self.track.release()
            except Exception:pass
            self.track=None
    def monitor_samples(self,a,rate):
        if not self.monitor or not self.headphones():self.monitor=False;self.close_monitor();return
        try:
            if self.track is None:
                T=self.ac('android.media.AudioTrack'); size=T.getMinBufferSize(rate,4,2);self.track=T(3,rate,4,2,max(size,8192),1);self.track.setVolume(.15);self.track.play()
            out=[]
            for x in a:
                y=.96*(self.prev_y+x-self.prev_x);self.prev_x=x;self.prev_y=y
                out.append(int(12000*math.tanh((y if self.highpass else x)*self.gain/12000)))
            buf=bytearray(struct.pack('<'+'h'*len(out),*out));self.track.write(buf,0,len(buf))
        except Exception as e:
            self.monitor=False;self.close_monitor();msg=str(e);Clock.schedule_once(lambda dt:self.message('Audio-Ausgabe',msg),0)
    def on_pause(self):self.monitor=False;return super().on_pause()
    def on_stop(self):self.monitor=False;super().on_stop()

if __name__=='__main__': GlobalLab().run()
