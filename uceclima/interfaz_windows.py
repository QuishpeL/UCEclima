# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""UCEclima: interfaz Windows para núcleo CLIMANET local, sin cálculos al abrir."""
import json,os,subprocess,sys,webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox

CORE=Path('C:/Users/agdgq/MILAGRO/climanet')
PYTHON=Path('C:/Users/agdgq/miniconda3/envs/geo_env/python.exe')

def main():
    root=tk.Tk();root.title('UCEclima · Clima, cuencas y agua');root.geometry('1120x760');root.minsize(880,660)
    root.configure(bg='#edf4fb');style=ttk.Style();style.theme_use('clam')
    style.configure('TFrame',background='#edf4fb');style.configure('TLabel',background='#edf4fb',foreground='#183b59',font=('Segoe UI',11))
    style.configure('TButton',font=('Segoe UI',10),padding=9);style.configure('TEntry',padding=6)
    header=tk.Canvas(root,height=125,highlightthickness=0);header.pack(fill='x')
    def banner(e):
        header.delete('all');w=e.width
        for x in range(w):
            a=x/max(w,1);r=int(9+14*a);g=int(44+76*a);b=int(90+86*a)
            header.create_line(x,0,x,125,fill=f'#{r:02x}{g:02x}{b:02x}')
        header.create_text(30,36,text='UCEclima',anchor='w',fill='white',font=('Segoe UI',27,'bold'))
        header.create_text(30,78,text='Laboratorio de modelamiento hidrológico e hidráulico · Ecuador',anchor='w',fill='#cdeaff',font=('Segoe UI',12))
        header.create_text(w-26,40,text='ALFA 0.2',anchor='e',fill='#a3e9ff',font=('Segoe UI',12,'bold'))
    header.bind('<Configure>',banner)
    body=ttk.Frame(root,padding=20);body.pack(fill='both',expand=True)
    nav=tk.Frame(body,bg='#123b60',width=190);nav.pack(side='left',fill='y',padx=(0,20));nav.pack_propagate(False)
    content=ttk.Frame(body);content.pack(side='left',fill='both',expand=True)
    status=tk.StringVar(value='Sin ejecución · resultados exploratorios, no calibrados')
    ttk.Label(root,textvariable=status,padding=12).pack(fill='x')
    config=tk.StringVar(value=str(CORE/'milagro.json'));proc=None;stream=None;logpath=None;logwidget=None
    def clear():
        nonlocal logwidget
        logwidget=None
        for widget in content.winfo_children():widget.destroy()
    def heading(title,description):
        clear();ttk.Label(content,text=title,font=('Segoe UI',21,'bold')).pack(anchor='w',pady=(0,10))
        ttk.Label(content,text=description,wraplength=730).pack(anchor='w',pady=(0,16))
    def load():
        path=Path(config.get());data=json.loads(path.read_text(encoding='utf-8-sig'))
        for key in ('dem','idf_csv','cn_tif','manning_tif','cobertura_tif','out_dir'):
            if data.get(key) and not Path(data[key]).is_absolute():data[key]=str((path.parent/data[key]).resolve())
        return data
    def choose():
        path=filedialog.askopenfilename(initialdir=CORE,filetypes=[('Proyecto JSON','*.json')])
        if path:config.set(path);project()
    def check():
        try:
            d=load();errors=[]
            if d.get('estado')=='preparacion_no_ejecutable':errors.append('Proyecto de preparación: faltan entradas confirmadas.')
            for k in ('dem','cn_tif','manning_tif','cobertura_tif','idf_csv'):
                if d.get(k) and not Path(d[k]).is_file():errors.append('No existe '+k+': '+d[k])
            if not d.get('dem'):errors.append('Falta el DEM.')
            if not (d.get('idf_csv') or d.get('idf_inamhi')):errors.append('Falta fuente IDF.')
            if not PYTHON.is_file() or not (CORE/'climanet/pipeline.py').is_file():errors.append('No se encontró núcleo o entorno Python local.')
            if errors:raise ValueError('\n'.join(errors))
            messagebox.showinfo('Comprobación preliminar','Rutas disponibles. El núcleo hará la validación científica al ejecutar.');return d
        except Exception as e:messagebox.showerror('Proyecto',str(e));return None
    def project():
        heading('Tu proyecto','Carga una configuración existente y revisa su procedencia antes de ejecutar.')
        ttk.Entry(content,textvariable=config,width=85).pack(fill='x',pady=8)
        row=ttk.Frame(content);row.pack(anchor='w',pady=8)
        ttk.Button(row,text='Abrir proyecto',command=choose).pack(side='left',padx=4)
        ttk.Button(row,text='Comprobar entradas',command=check).pack(side='left',padx=4)
        try:
            d=load();summary='\n'.join(f'{k}: {d.get(k,"No definido")}' for k in ('dem','res','solver','idf_inamhi','storm_min','sim_horas','out_dir'))
        except Exception:summary='Selecciona un archivo de proyecto válido.'
        text=tk.Text(content,height=14,wrap='word',bg='white',fg='#244d6b',font=('Segoe UI',10));text.pack(fill='both',expand=True,pady=12);text.insert('end',summary);text.configure(state='disabled')
    def execution():
        nonlocal logwidget
        heading('Ejecución y registro','Una tarea a la vez. La cancelación deja resultados incompletos; no inicia trabajo nocturno.')
        row=ttk.Frame(content);row.pack(anchor='w')
        ttk.Button(row,text='Ejecutar proyecto',command=start).pack(side='left',padx=4)
        ttk.Button(row,text='Cancelar corrida',command=stop).pack(side='left',padx=4)
        logwidget=tk.Text(content,bg='#092744',fg='#d5ecff',font=('Consolas',10),wrap='word');logwidget.pack(fill='both',expand=True,pady=15)
    def start():
        nonlocal proc,stream,logpath
        if proc and proc.poll() is None:messagebox.showinfo('Ejecución','Ya hay una corrida activa.');return
        d=check()
        if not d:return
        if not messagebox.askyesno('Carga de cálculo','¿Ejecutar este proyecto? Un DEM amplio puede exigir mucho tiempo y memoria.'):return
        out=Path(d.get('out_dir',str(CORE/'salida_interfaz')));out.mkdir(parents=True,exist_ok=True)
        snapshot=out/'config_interfaz.json';snapshot.write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
        logpath=out/'ejecucion_interfaz.log';stream=logpath.open('wb')
        env=os.environ.copy();env['PYTHONPATH']=str(CORE);env['PYTHONIOENCODING']='utf-8';env['NUMBA_NUM_THREADS']='2';env['OMP_NUM_THREADS']='2'
        proc=subprocess.Popen([str(PYTHON),'-u','-m','climanet',str(snapshot)],cwd=CORE,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        status.set('Calculando · 2 hilos de Numba solicitados');execution()
    def stop():
        if proc and proc.poll() is None:
            proc.terminate();status.set('Cancelación solicitada · resultados incompletos')
            if logpath:(logpath.parent/'CORRIDA_INTERRUMPIDA.txt').write_text('Cancelada desde interfaz; revisar resultados parciales.',encoding='utf-8')
    def poll():
        nonlocal stream
        if logwidget and logpath and logpath.exists():
            with logpath.open('rb') as f:f.seek(max(0,logpath.stat().st_size-18000));text=f.read().decode('utf-8','replace')
            logwidget.delete('1.0','end');logwidget.insert('end',text);logwidget.see('end')
        if proc and proc.poll() is not None and stream:
            stream.close();stream=None;status.set(f'Proceso terminado · código {proc.returncode} · revisar mensajes y validación')
        root.after(1500,poll)
    def results():
        heading('Resultados','Abre la carpeta de salida para mapas, balance y evaluación. No confundir cálculo completo con validación.')
        def openout():
            try:
                p=Path(load()['out_dir'])
                if not p.exists():raise ValueError('Aún no existe carpeta de resultados.')
                os.startfile(str(p))
            except Exception as e:messagebox.showerror('Resultados',str(e))
        ttk.Button(content,text='Abrir carpeta de resultados',command=openout).pack(anchor='w',pady=10)
        ttk.Button(content,text='Abrir visor demostrativo',command=lambda:webbrowser.open((CORE/'visual/index.html').as_uri())).pack(anchor='w',pady=10)
        ttk.Label(content,text='Visor actual: datos sintéticos. Los rásteres reales se abren en QGIS; visor temporal real pendiente.',wraplength=700).pack(anchor='w')
    def pending():
        heading('Módulos en preparación','Estas funciones no están conectadas en esta alfa.')
        for line in ['GEE / CHIRPS: autenticación y descarga automática pendientes.','Caiza / pluviógrafo: auditoría Excel y digitalización pendientes.','Canales: secciones, entradas y capacidad reales por confirmar.','CMIP6: bloqueado hasta calibración y validación de condiciones existentes.','VOTEX 4D: estados georreferenciados y biblioteca pendientes.']:
            ttk.Label(content,text=line,wraplength=700).pack(anchor='w',pady=12)
    for name,fn in [('01  Proyecto',project),('02  Ejecutar',execution),('03  Resultados',results),('04  Módulos',pending)]:
        tk.Button(nav,text=name,command=fn,bg='#123b60',fg='white',activebackground='#206194',activeforeground='white',relief='flat',font=('Segoe UI',12),anchor='w',padx=14,pady=18).pack(fill='x')
    def close():
        if proc and proc.poll() is None:
            messagebox.showinfo('Corrida activa','Cancela o espera antes de cerrar.');return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);project();poll();root.mainloop()

if __name__=='__main__':
    if '--self-test' in sys.argv:
        assert CORE.is_dir() and PYTHON.is_file();json.loads((CORE/'milagro.json').read_text());print('OK núcleo y configuración')
    else:main()
