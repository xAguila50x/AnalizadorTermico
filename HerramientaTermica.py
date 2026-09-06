# HerramientaTermicaGUI.py (Versión 5.0 - Análisis de Espectro Integrado)
# =================================================================================
# Esta versión integra el análisis de anillos (energía por frecuencia)
# directamente en la ventana emergente 'VentanaEspectro'.
# =================================================================================

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import subprocess
import json
import io
import cv2
import numpy as np
import pydicom
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

# --- CONFIGURACIÓN DE LA APLICACIÓN ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
ALTURA_IMAGEN_VISUALIZACION = 300

# --- LÓGICA DE FOURIER ---

def procesar_fourier_completo(datos_para_fft, r1=15, r2=50):
    """
    Realiza el análisis completo de Fourier:
    1. Calcula la DFT 2D optimizada (con padding).
    2. Genera la imagen visible del espectro de magnitud (para la GUI).
    3. Realiza el análisis de energía por anillos (para el diagnóstico).
    
    Argumentos:
    datos_para_fft (np.array): Matriz de datos de temperatura (ROI enmascarado).
    r1 (int): Radio interior del anillo (límite baja-media frecuencia en píxeles).
    r2 (int): Radio exterior del anillo (límite media-alta frecuencia en píxeles).
    
    Retorna:
    tuple: (imagen_espectro_visible, dict_resultados_energia)
           - imagen_espectro_visible: (np.array) Imagen 8-bit normalizada para mostrar.
           - dict_resultados_energia: (dict) Diccionario con los porcentajes de energía.
    """
    
    # --- 1. CÁLCULO DE LA DFT ---
    # Rellena con ceros para optimizar el cálculo de la FFT (potencias de 2)
    filas, cols = datos_para_fft.shape
    opt_filas = cv2.getOptimalDFTSize(filas)
    opt_cols = cv2.getOptimalDFTSize(cols)
    datos_padded = cv2.copyMakeBorder(datos_para_fft, 0, opt_filas - filas, 0, opt_cols - cols, cv2.BORDER_CONSTANT, value=0)

    # Calcular la FFT
    f = np.fft.fft2(datos_padded)
    fshift = np.fft.fftshift(f)
    
    # Calcular la magnitud (esta es la energía REAL)
    magnitud = np.abs(fshift)

    # --- 2. GENERAR IMAGEN VISIBLE (PARA LA GUI) ---
    
    # Aplicar escala logarítmica SÓLO para visualización
    # Se suma 1 para evitar log(0)
    magnitud_log_visible = np.log(1 + magnitud)
    
    # Normalizar para crear la imagen de 8 bits (0-255)
    imagen_espectro_visible = cv2.normalize(magnitud_log_visible, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    
    # --- 3. ANÁLISIS DE ENERGÍA POR ANILLOS (PARA EL DIAGNÓSTICO) ---
    
    # Crear un "mapa de distancias" desde el centro
    centro_fila, centro_col = opt_filas // 2, opt_cols // 2
    y, x = np.indices((opt_filas, opt_cols))
    distancia_al_centro = np.sqrt((x - centro_col)**2 + (y - centro_fila)**2)
    
    # Usamos la 'magnitud' (sin log) que representa la energía pura
    total_energia = np.sum(magnitud)
    
    if total_energia == 0:
        # Evitar división por cero si la imagen está vacía
        dict_resultados_cero = {"pct_baja": 0, "pct_media": 0, "pct_alta": 0, "radios_usados": (r1, r2), "interpretacion": "Datos de entrada vacíos."}
        return imagen_espectro_visible, dict_resultados_cero

    # Crear las máscaras para los anillos usando el mapa de distancias
    mascara_baja = (distancia_al_centro <= r1)
    mascara_media = (distancia_al_centro > r1) & (distancia_al_centro <= r2)
    mascara_alta = (distancia_al_centro > r2)
    
    # Sumar la energía (magnitud) que cae dentro de cada máscara
    energia_baja = np.sum(magnitud[mascara_baja])
    energia_media = np.sum(magnitud[mascara_media])
    energia_alta = np.sum(magnitud[mascara_alta])

    # Calcular porcentajes
    pct_baja = (energia_baja / total_energia) * 100
    pct_media = (energia_media / total_energia) * 100
    pct_alta = (energia_alta / total_energia) * 100
    
    # Generar texto de interpretación
    interpretacion_texto = (
        f"Análisis con radios: R1={r1}px, R2={r2}px.\n\n"
        "Un tejido sano tiende a concentrar >95-99% de su energía en Frec. Bajas (patrones suaves).\n\n"
        "Un porcentaje elevado en Frec. Medias y Altas sugiere una textura térmica más compleja. "
        "Esto puede ser un indicador de patrones vasculares anómalos (neovascularización), "
        "lo cual requiere mayor investigación."
    )
    
    dict_resultados_energia = {
        "pct_baja": pct_baja,
        "pct_media": pct_media,
        "pct_alta": pct_alta,
        "radios_usados": (r1, r2),
        "interpretacion": interpretacion_texto
    }
    
    # Devolver AMBAS cosas: la imagen para mostrar y los números para analizar
    return imagen_espectro_visible, dict_resultados_energia

def analizar_desde_csvs(ruta_csv_temp, ruta_csv_mascara):
    """
    Carga los dos CSV, los combina y calcula el espectro Y los resultados.
    (MODIFICADO para devolver ambos resultados)
    """
    try:
        matriz_temp = np.loadtxt(ruta_csv_temp, delimiter=",")
        matriz_mascara = np.loadtxt(ruta_csv_mascara, delimiter=",")
    except Exception as e:
        messagebox.showerror("Error de Carga", f"Error al cargar los archivos CSV: {e}")
        return None, None

    if matriz_temp.shape != matriz_mascara.shape:
        messagebox.showerror("Error de Dimensiones", 
                             f"Las matrices no tienen el mismo tamaño.\n"
                             f"Temp: {matriz_temp.shape}, Mascara: {matriz_mascara.shape}")
        return None, None
        
    # Multiplica para aislar el ROI
    datos_roi = matriz_temp * matriz_mascara
    
    # Calcula la imagen del espectro Y los resultados
    imagen_espectro, resultados_energia = procesar_fourier_completo(datos_roi)
    
    return imagen_espectro, resultados_energia

# --- LÓGICA DE PROCESAMIENTO (Segmentación, etc.) ---
# (Sin cambios en esta sección)
points_lazo = []
drawing_lazo = False

def mouse_callback_lazo(event, x, y, flags, param):
    global drawing_lazo, points_lazo; img_display = param['image_display']; img_original_copy = param['image_original_copy']
    img_display[:] = img_original_copy[:]
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing_lazo = True; points_lazo = [(x, y)]
    elif event == cv2.EVENT_MOUSEMOVE and drawing_lazo:
        points_lazo.append((x, y))
        for i in range(len(points_lazo) - 1):
            cv2.line(img_display, points_lazo[i], points_lazo[i+1], (0, 255, 0), 2)
    elif event == cv2.EVENT_LBUTTONUP:
        drawing_lazo = False
        if len(points_lazo) > 2:
            cv2.line(img_display, points_lazo[-1], points_lazo[0], (0, 255, 0), 2)

def segmentar_interactivo(ruta_imagen):
    global points_lazo; points_lazo = []
    if not show_instruction_popup(): return None
    img_original = cv2.imread(ruta_imagen)
    if img_original is None: return None
    img_display = img_original.copy(); img_original_copy = img_original.copy()
    window_name = "Ventana de Dibujo Manual (Presiona ENTER para confirmar, ESC para cancelar)"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, mouse_callback_lazo, {'image_display': img_display, 'image_original_copy': img_original_copy})
    while True:
        cv2.imshow(window_name, img_display); key = cv2.waitKey(1) & 0xFF
        if key == 27: cv2.destroyAllWindows(); return None
        if key == 13 and len(points_lazo) > 2: break
    cv2.destroyAllWindows()
    mask = np.zeros(img_original.shape[:2], dtype=np.uint8); contour = np.array(points_lazo, dtype=np.int32)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    directorio, nombre_archivo = os.path.split(ruta_imagen); nombre_base, _ = os.path.splitext(nombre_archivo)
    ruta_mascara_salida = os.path.join(directorio, f"{nombre_base}_mask.png")
    cv2.imwrite(ruta_mascara_salida, mask)
    return ruta_mascara_salida

def show_instruction_popup():
    # Esta función asume que 'app' es la instancia global de App()
    popup = ctk.CTkToplevel(app) 
    popup.title("Instrucciones de Dibujo"); popup.transient(app); popup.grab_set(); popup.attributes("-topmost", True)
    app.update_idletasks()
    x = app.winfo_x() + (app.winfo_width() // 2) - 200
    y = app.winfo_y() + (app.winfo_height() // 2) - 100
    popup.geometry(f"400x200+{x}+{y}"); popup.resizable(False, False)
    ctk.CTkLabel(popup, text="Instrucciones para la Segmentación Manual:", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
    ctk.CTkLabel(popup, text="1. Haz clic y arrastra el mouse para dibujar el contorno.", justify="left").pack(anchor="w", padx=20)
    ctk.CTkLabel(popup, text="2. Al terminar, presiona la tecla ENTER para confirmar.", justify="left").pack(anchor="w", padx=20)
    ctk.CTkLabel(popup, text="3. Para cancelar, presiona la tecla ESC.", justify="left").pack(anchor="w", padx=20)
    response = tk.BooleanVar(value=False)
    def on_confirm(): response.set(True); popup.destroy()
    def on_cancel(): response.set(False); popup.destroy()
    button_frame = ctk.CTkFrame(popup, fg_color="transparent"); button_frame.pack(pady=15)
    ctk.CTkButton(button_frame, text="Entendido, Continuar", command=on_confirm).pack(side="left", padx=10)
    ctk.CTkButton(button_frame, text="Cancelar", command=on_cancel, fg_color="red").pack(side="right", padx=10)
    app.wait_window(popup)
    return response.get()

def analizar_temperaturas(ruta_imagen_original, ruta_mascara, user_info):
    try:
        if getattr(sys, 'frozen', False):
            exiftool_path = os.path.join(sys._MEIPASS, "exiftool.exe")
        else:
            exiftool_path = "exiftool.exe"
        subprocess.run([exiftool_path, "-ver"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        comando_metadata = [exiftool_path, "-json", ruta_imagen_original]
        resultado_metadata = subprocess.run(comando_metadata, capture_output=True, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        metadata = json.loads(resultado_metadata.stdout)[0]
        comando_imagen = [exiftool_path, "-b", "-RawThermalImage", ruta_imagen_original]
        resultado_imagen = subprocess.run(comando_imagen, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if not resultado_imagen.stdout: return {"error": "No se pudo extraer la imagen térmica cruda."}, None, None, None
        raw_image_data = io.BytesIO(resultado_imagen.stdout); raw_image = Image.open(raw_image_data); matriz_temperaturas_raw = np.array(raw_image)
        temperaturas_celsius_original = None; model_name = metadata.get("CameraModel", "Desconocido")
        if "E6" in model_name:
            temp_min_k, temp_max_k, raw_min, raw_max = metadata.get("ImageTemperatureMin"), metadata.get("ImageTemperatureMax"), metadata.get("RawValueRangeMin"), metadata.get("RawValueRangeMax")
            if any(v is None for v in [temp_min_k, temp_max_k, raw_min, raw_max]): return {"error": "Metadatos de calibración lineal no encontrados."}, None, None, None
            if raw_max == raw_min: temp_kelvin = np.full(matriz_temperaturas_raw.shape, temp_min_k, dtype=np.float32)
            else: m = (temp_max_k - temp_min_k) / (raw_max - raw_min); c = temp_min_k - m * raw_min; temp_kelvin = m * matriz_temperaturas_raw.astype(np.float32) + c
            temperaturas_celsius_original = temp_kelvin - 273.15
        elif "A3" in model_name:
            R1, B, F, O, R2 = metadata.get("PlanckR1"), metadata.get("PlanckB"), metadata.get("PlanckF"), metadata.get("PlanckO"), metadata.get("PlanckR2")
            if any(v is None for v in [R1, B, F, O, R2]): return {"error": "Metadatos de Planck incompletos."}, None, None, None
            raw_data_float = matriz_temperaturas_raw.astype(np.float32); term1 = R1 / (R2 * (raw_data_float + O)); termino_log = term1 + F
            if np.min(termino_log) <= 0: return {"error": "Error matemático: logaritmo de número no positivo."}, None, None, None
            temp_kelvin = B / np.log(termino_log); temperaturas_celsius_original = temp_kelvin - 273.15
        else: return {"error": f"Modelo de cámara no reconocido: '{model_name}'."}, None, None, None
        mascara_img = cv2.imread(ruta_mascara, cv2.IMREAD_GRAYSCALE)
        h_temp, w_temp = temperaturas_celsius_original.shape
        if mascara_img is None: return {"error": "No se pudo cargar la máscara."}, None, None, None
        mascara_img = cv2.resize(mascara_img, (w_temp, h_temp), interpolation=cv2.INTER_NEAREST)
        temperaturas_segmentadas_array = temperaturas_celsius_original[mascara_img > 128]
        if temperaturas_segmentadas_array.size == 0: return {"error": "El área de la máscara está vacía."}, None, None, None
        matriz_segmentada_binaria = np.where(mascara_img > 128, 1, 0)
        resultados = {"min_temp": f"{np.nanmin(temperaturas_segmentadas_array):.2f}°C", "max_temp": f"{np.nanmax(temperaturas_segmentadas_array):.2f}°C", "avg_temp": f"{np.nanmean(temperaturas_segmentadas_array):.2f}°C"}
        fig, ax = plt.subplots(figsize=(10, 6), facecolor='white')
        total_pixeles_segmentados = temperaturas_segmentadas_array.size
        counts, bins, patches = ax.hist(temperaturas_segmentadas_array[~np.isnan(temperaturas_segmentadas_array)], bins=25, color='deepskyblue', edgecolor='black', alpha=0.9)
        ax.set_xlabel('Temperatura (°C)', fontsize=12); ax.set_ylabel('Frecuencia (píxeles)', fontsize=12)
        ax.set_title('Distribución de Temperatura', fontsize=16, pad=20); ax.grid(True, linestyle='--', alpha=0.4)
        ax.tick_params(axis='x', colors='black', labelsize=8, rotation=45); ax.tick_params(axis='y', colors='black', labelsize=8)
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        info_text = (f"Nombre: {user_info.get('Nombre', 'N/A')}   |   Edad: {user_info.get('Edad', 'N/A')}   |   "
                     f"Fecha: {user_info.get('Fecha', 'N/A')}   |   Hora: {user_info.get('Hora', 'N/A')}")
        fig.suptitle(info_text, fontsize=10)
        y_max = ax.get_ylim()[1]; offset = y_max * 0.01
        for i in range(len(counts)):
            count = counts[i]
            if count > 0:
                porcentaje = (count / total_pixeles_segmentados) * 100
                x_pos = patches[i].get_x() + patches[i].get_width() / 2; y_pos = count
                temp_inicio = bins[i]; etiqueta = f"{int(count)}px ({porcentaje:.1f}%) @ {temp_inicio:.1f}°C"
                ax.text(x_pos, y_pos + offset, etiqueta, ha='center', va='bottom', fontsize=8, color='black', rotation=90)
        fig.tight_layout()
        return resultados, fig, temperaturas_celsius_original, matriz_segmentada_binaria
    except (subprocess.CalledProcessError, FileNotFoundError): return {"error": "ExifTool no encontrado."}, None, None, None
    except Exception as e: import traceback; traceback.print_exc(); return {"error": f"Error inesperado: {str(e)}"}, None, None, None

# --- CLASE: VENTANA DE ANÁLISIS DE ESPECTRO (MODIFICADA) ---

class VentanaEspectro(ctk.CTkToplevel):
    def __init__(self, master, matriz_temp=None, matriz_mascara=None):
        super().__init__(master)
        self.master_app = master
        self.title("Análisis de Espectro y Exportación DICOM")
        self.geometry("1100x850") 
        self.transient(master)

        # Variables de estado
        self.matriz_temp_local = matriz_temp
        self.imagen_espectro_cv = None
        self.resultados_energia = None
        
        # --- PANEL DE CONTROL SUPERIOR (Para carga manual) ---
        self.frame_top = ctk.CTkFrame(self)
        self.frame_top.pack(pady=10, padx=20, fill="x")

        self.btn_cargar = ctk.CTkButton(
            self.frame_top, text="1. CARGAR SEGMENTADA (.CSV)", 
            command=self.seleccionar_archivo, fg_color="#1f538d", height=40
        )
        self.btn_cargar.pack(pady=10, padx=10, side="left")

        self.lbl_status = ctk.CTkLabel(self.frame_top, text="Datos listos" if matriz_temp is not None else "Esperando archivo...", text_color="gray")
        self.lbl_status.pack(pady=10, padx=10, side="left", expand=True)

        self.btn_analizar = ctk.CTkButton(
            self.frame_top, text="2. REALIZAR ANÁLISIS", 
            command=self.ejecutar_analisis, fg_color="#A85400", height=40,
            state="normal" if matriz_temp is not None else "disabled"
        )
        self.btn_analizar.pack(pady=10, padx=10, side="right")

        # --- CONTENEDOR PRINCIPAL DE VISUALIZACIÓN ---
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.main_container.grid_columnconfigure(0, weight=1) # Espectro
        self.main_container.grid_columnconfigure(1, weight=1) # Resultados
        self.main_container.grid_rowconfigure(0, weight=1)

        # Lado Izquierdo: Visualizador del Espectro
        self.lbl_espectro = ctk.CTkLabel(self.main_container, text="El espectro aparecerá aquí")
        self.lbl_espectro.grid(row=0, column=0, sticky="nsew", padx=5)

        # Lado Derecho: Resultados y DICOM
        right_column = ctk.CTkFrame(self.main_container)
        right_column.grid(row=0, column=1, sticky="nsew", padx=5)
        
        ctk.CTkLabel(right_column, text="RESULTADOS DE ENERGÍA", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        self.lbl_pct_baja = ctk.CTkLabel(right_column, text="Bajas: --", text_color="cyan")
        self.lbl_pct_baja.pack()
        self.lbl_pct_media = ctk.CTkLabel(right_column, text="Medias: --", text_color="orange")
        self.lbl_pct_media.pack()
        self.lbl_pct_alta = ctk.CTkLabel(right_column, text="Altas: --", text_color="red")
        self.lbl_pct_alta.pack()

        self.txt_interpretacion = ctk.CTkTextbox(right_column, height=200, state="disabled")
        self.txt_interpretacion.pack(fill="both", expand=True, padx=10, pady=10)

        self.btn_exportar_dicom_full = ctk.CTkButton(
            right_column, text="EXPORTAR RESULTADOS A DICOM", 
            command=self._abrir_exportador_con_anillos,
            fg_color="purple", height=50, state="disabled", font=ctk.CTkFont(weight="bold")
        )
        self.btn_exportar_dicom_full.pack(fill="x", padx=10, pady=20)

        # --- LÓGICA AUTOMÁTICA ---
        # Si se pasaron datos directamente (Análisis automático), procesar de inmediato
        if matriz_temp is not None and matriz_mascara is not None:
            self.procesar_datos_en_memoria(matriz_temp, matriz_mascara)

    def seleccionar_archivo(self):
        """Carga manual de un CSV segmentado"""
        ruta = filedialog.askopenfilename(title="Seleccionar Matriz Segmentada", filetypes=[("CSV", "*.csv")])
        if ruta:
            try:
                matriz = np.genfromtxt(ruta, delimiter=',')
                self.matriz_temp_local = np.nan_to_num(matriz)
                self.lbl_status.configure(text=f"Listo: {os.path.basename(ruta)}", text_color="cyan")
                self.btn_analizar.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar: {e}")

    def ejecutar_analisis(self):
        """Ejecuta el análisis sobre la matriz que esté cargada (manual o automática)"""
        if self.matriz_temp_local is not None:
            try:
                # Usamos la función global procesar_fourier_completo
                self.imagen_espectro_cv, self.resultados_energia = procesar_fourier_completo(self.matriz_temp_local)
                self._mostrar_espectro_en_label(self.imagen_espectro_cv)
                self._mostrar_resultados_numericos(self.resultados_energia)
                self.btn_exportar_dicom_full.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Error", f"Error en el análisis: {e}")

    def procesar_datos_en_memoria(self, matriz_temp, matriz_mascara):
        """Lógica automática cuando vienes de la pantalla principal"""
        try:
            # Multiplicamos para obtener la segmentación real antes de Fourier
            self.matriz_temp_local = matriz_temp * matriz_mascara
            self.ejecutar_analisis() # Reutilizamos la función de análisis
        except Exception as e:
            messagebox.showerror("Error Automático", f"No se pudo procesar: {e}")

    def _mostrar_resultados_numericos(self, res):
        if res:
            # Actualizar etiquetas de porcentajes
            self.lbl_pct_baja.configure(text=f"Bajas Frecuencias: {res['pct_baja']:.2f}%")
            self.lbl_pct_media.configure(text=f"Medias Frecuencias: {res['pct_media']:.2f}%")
            self.lbl_pct_alta.configure(text=f"Altas Frecuencias: {res['pct_alta']:.2f}%")
            
            # Preparar el texto de interpretación
            self.txt_interpretacion.configure(state="normal")
            self.txt_interpretacion.delete("1.0", "end")
            
            # Generamos el texto dinámicamente si 'interpretacion' viene vacío
            energia_total = res.get('energia_total', 0)
            p_alta = res.get('pct_alta', 0)
            
            texto_base = f"--- INFORME TÉCNICO ---\n"
            texto_base += f"Energía Total: {energia_total:.2e}\n"
            texto_base += f"Predominio: "
            
            if p_alta > 15:
                texto_base += "ALTAS FRECUENCIAS\n\nInterpretación: Se detecta una textura térmica compleja o bordes muy definidos en la segmentación. Posible actividad térmica anómala."
            elif p_alta > 5:
                texto_base += "FRECUENCIAS MEDIAS\n\nInterpretación: Distribución térmica equilibrada. Patrón estándar."
            else:
                texto_base += "BAJAS FRECUENCIAS\n\nInterpretación: Patrón térmico suave y homogéneo. Sin variaciones bruscas de temperatura."

            # --- SECCIÓN DE AYUDA (Lo que me pediste) ---
            texto_base += "\n" + "-"*35 + "\n"
            texto_base += "GUÍA DE COMPRENSIÓN PARA EL USUARIO:\n\n"
            texto_base += "• Energía Total: Es la intensidad de la 'información' en la imagen. \n"
            texto_base += "-Valores altos indican mucha actividad o variaciones térmicas. \n"
            texto_base += "-Valores bajos indican uniformidad (poca variación).\n\n"
            
            texto_base += "• Bajas Frecuencias: Representan la forma general y el volumen de calor.\n"
            texto_base += "• Medias Frecuencias: Representan la estructura y el volumen térmico. Son los gradientes y las transiciones suaves de calor dentro de la zona.\n"
            texto_base += "• Altas Frecuencias: Representan los detalles finos, bordes y cambios rápidos de temperatura."
            
            # Insertar el texto generado
            self.txt_interpretacion.insert("1.0", texto_base)
            self.txt_interpretacion.configure(state="disabled")

    def _mostrar_espectro_en_label(self, cv2_img):
        if cv2_img is not None:
            # Convertir de BGR a RGB para PIL
            img_rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            # Usar CTkImage para que se vea bien en pantallas con escala
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(500, 500))
            self.lbl_espectro.configure(image=ctk_img, text="")
            self.lbl_espectro.image = ctk_img

    def _abrir_exportador_con_anillos(self):
        try:
            # Buscamos los metadatos de forma segura
            metadatos = getattr(self.master_app, 'metadatos_flir', {})
            if not metadatos:
                metadatos = getattr(self.master_app, 'metadatos_flir_actual', {"Model": "Unknown"})
            
            # Buscamos el nombre del paciente de forma segura
            nombre = "ANONIMO"
            if hasattr(self.master_app, 'entry_nombre'):
                nombre = self.master_app.entry_nombre.get()
            
            # Abrir exportador
            from HerramientaTermica import VentanaExportarDicom
            VentanaExportarDicom(
                self, 
                self.matriz_temp_local, 
                metadatos, 
                {"Nombre": nombre, "Fecha": datetime.now().strftime("%Y-%m-%d")}, 
                self.resultados_energia
            )
        except Exception as e:
            messagebox.showerror("Error de Exportación", f"Hubo un fallo al preparar el DICOM:\n{e}")
            
class VentanaExportarDicom(ctk.CTkToplevel):
    def __init__(self, master, matriz_temp, metadatos_originales, info_paciente, resultados_anillos=None):
        super().__init__(master)
        self.matriz_temp = matriz_temp
        self.metadatos_flir = metadatos_originales
        self.resultados_anillos = resultados_anillos
        
        self.title("Finalizar Exportación DICOM")
        self.geometry("600x850")
        self.grab_set()

        scroll = ctk.CTkScrollableFrame(self, width=550, height=650)
        scroll.pack(pady=10, fill="both", expand=True)

        self.entries = {}
        # ... (Mantener el mismo bucle de self.campos_config de antes)
        
        # Copiamos los campos de la respuesta anterior aquí
        ahora = datetime.now()
        self.campos_config = {
            "PatientName": (info_paciente.get("Nombre", "ANONIMO"), "Nombre"),
            "PatientID": ("ID-12345", "ID"),
            "PatientBirthDate": ("19900101", "AAAAMMDD"),
            "PatientAge": ("", "Auto"),
            "PatientSex": ("O", "M/F/O"),
            "PatientWeight": ("0", "Kg"),
            "PatientHeight": ("0", "cm"),
            "PatientAddress": ("Desconocida", "Direccion"),
            "StudyID": ("EST-001", "ID"),
            "StudyDate": (ahora.strftime("%Y%m%d"), "Fecha"),
            "StudyTime": (ahora.strftime("%H%M%S"), "Hora"),
            "StudyDescription": ("ANALISIS TERMOGRAFICO", "Desc"),
            "SeriesDate": (ahora.strftime("%Y%m%d"), "Fecha Serie"),       
            "SeriesTime": (ahora.strftime("%H%M%S"), "Hora Serie"),       
            "SeriesDescription": ("PROCESAMIENTO DE ANILLOS", "Desc Serie"), 
            "SeriesNumber": ("1", "Serie #"),
            "InstitutionName": ("LABORATORIO TÉRMICO", "Clínica")
        }
        
        for i, (tag, (valor, placeholder)) in enumerate(self.campos_config.items()):
            ctk.CTkLabel(scroll, text=f"{tag}:").grid(row=i, column=0, padx=10, pady=5, sticky="w")
            entry = ctk.CTkEntry(scroll, width=300)
            entry.insert(0, valor)
            entry.grid(row=i, column=1, padx=10, pady=5)
            self.entries[tag] = entry

        ctk.CTkButton(self, text="GENERAR ARCHIVO .DCM", command=self.guardar_dicom, 
                      fg_color="green", height=45).pack(pady=20)

    def guardar_dicom(self):
        ruta = filedialog.asksaveasfilename(defaultextension=".dcm")
        if not ruta: return

        try:
            # --- 1. PREPARACIÓN DE DATOS TÉRMICOS ---
            t_max = np.nanmax(self.matriz_temp)
            t_min = np.nanmin(self.matriz_temp)
            t_media = np.nanmean(self.matriz_temp)

            # ESTRATEGIA: Guardar la temperatura directamente con precisión de 2 decimales
            # Multiplicamos por 100 para convertir 36.54 en 3654 (entero de 16 bits)
            # Esto permite que el visor lea "temperatura" y no "píxel normalizado"
            img_celsius_scaled = (self.matriz_temp * 100).astype(np.int16)

            # --- 2. CONFIGURACIÓN DATASET ---
            file_meta = Dataset()
            file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
            file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
            file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            ds = FileDataset(ruta, {}, file_meta=file_meta, preamble=b"\0" * 128)

            # --- 3. CONFIGURACIÓN DE IMAGEN ---
            ds.Rows, ds.Columns = img_celsius_scaled.shape
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.BitsAllocated = 16
            ds.BitsStored = 16
            ds.HighBit = 15
            ds.PixelRepresentation = 1  # 1 = Signed integer (necesario para este método)
            ds.PixelData = img_celsius_scaled.tobytes()
            
            # --- CALIBRACIÓN PARA QUE EL VISOR DIVIDA ENTRE 100 ---
            # Valor_Real = (Píxel * 0.01) + 0
            ds.RescaleSlope = "0.01"
            ds.RescaleIntercept = "0.0"

            # Ajuste de ventana en valores de temperatura real
            ds.WindowCenter = f"{t_media:.2f}"
            ds.WindowWidth = f"{(t_max - t_min):.2f}"

            # --- 4. INYECCIÓN DE METADATOS TÉRMICOS ---
            info_ia = {
                "TEMP_MAX": f"{t_max:.2f} C",
                "TEMP_MIN": f"{t_min:.2f} C",
                "TEMP_AVERAGE": f"{t_media:.2f} C",
                "UNITS": "Celsius"
            }

            if self.metadatos_flir:
                mapeo_flir = {
                    'Emissivity': 'EMISSIVITY',
                    'ObjectDistance': 'DISTANCE',
                    'ReflectedApparentTemperature': 'REFLECTED_TEMP',
                    'AtmosphericTemperature': 'ATM_TEMP',
                    'RelativeHumidity': 'HUMIDITY',
                    'PlanckR1': 'PLANCK_R1',
                    'PlanckB': 'PLANCK_B',
                    'PlanckF': 'PLANCK_F',
                    'PlanckO': 'PLANCK_O',
                    'PlanckR2': 'PLANCK_R2'
                }
                for original, nuevo in mapeo_flir.items():
                    val = self.metadatos_flir.get(original, "N/A")
                    info_ia[nuevo] = val

            processing_desc = " | ".join([f"{k}={v}" for k, v in info_ia.items()])
            ds.AcquisitionDeviceProcessingDescription = processing_desc[:1024]

            # --- 5. RESULTADOS DE ANILLOS ---
            if self.resultados_anillos:
                r = self.resultados_anillos
                ds.ImageComments = (f"Analisis: BAJA:{r['pct_baja']:.4f}|"
                                    f"MEDIA:{r['pct_media']:.4f}|"
                                    f"ALTA:{r['pct_alta']:.4f}")

            # --- 6. DATOS DE PACIENTE ---
            for tag, entry in self.entries.items():
                val = entry.get().strip()
                if val:
                    if "Date" in tag: val = val.replace(":", "").replace("-", "")
                    setattr(ds, tag, val)

            ds.Modality = "TG"
            ds.ContentDate = datetime.now().strftime('%Y%m%d')
            ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
            ds.SeriesInstanceUID = pydicom.uid.generate_uid()
            ds.StudyInstanceUID = pydicom.uid.generate_uid()

            ds.save_as(ruta)
            messagebox.showinfo("Éxito", "Dicom exportado exitosamente!")
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"Error en exportación: {str(e)}")
            
            
# --- CLASE PRINCIPAL DE LA APLICACIÓN (Sin cambios) ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.ruta_imagen_original = None; self.ruta_mascara = None; self.fig_matplotlib = None
        self.matriz_temp_original = None; self.matriz_binaria_segmentada = None
        self.ventana_espectro_actual = None
        self.show_splash_screen()
    def center_window(self, width, height): self.geometry(f"{width}x{height}+{int((self.winfo_screenwidth()/2)-(width/2))}+{int((self.winfo_screenheight()/2)-(height/2))}")
    def clear_widgets(self): [widget.destroy() for widget in self.winfo_children()]
    def show_splash_screen(self):
        self.title("Herramienta Térmica - Bienvenida"); self.geometry("800x500"); self.center_window(800, 500); self.resizable(False, False)
        main_frame = ctk.CTkFrame(self, fg_color="transparent"); main_frame.pack(expand=True, fill="both", padx=50, pady=50)
        ctk.CTkLabel(main_frame, text="Asistente de Análisis de Imágenes Térmicas", font=ctk.CTkFont(size=30, weight="bold")).pack(pady=(20, 10))
        ctk.CTkLabel(main_frame, text="Herramienta profesional para la segmentación y análisis de temperatura.", font=ctk.CTkFont(size=16)).pack(pady=(0, 40))
        ctk.CTkButton(main_frame, text="INICIAR APLICACIÓN", command=self.show_main_app, font=ctk.CTkFont(size=18, weight="bold"), width=250, height=50).pack(pady=(0, 20))
    
    def show_main_app(self):
        self.clear_widgets(); self.title("Asistente de Análisis Térmico"); self.state('zoomed'); self.resizable(True, True)
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        left_column_frame = ctk.CTkFrame(self, width=280, corner_radius=0); left_column_frame.grid(row=0, column=0, sticky="nsew")
        left_column_frame.grid_rowconfigure(2, weight=1)
        control_frame = ctk.CTkFrame(left_column_frame, fg_color="transparent"); control_frame.grid(row=0, column=0, sticky="new", padx=10, pady=10)
        ctk.CTkLabel(control_frame, text="Panel de Control", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(10, 10))
        self.btn_cargar = ctk.CTkButton(control_frame, text="1. Cargar Imagen", command=self.cargar_imagen); self.btn_cargar.pack(pady=5, fill="x")
        self.btn_segmentar = ctk.CTkButton(control_frame, text="2. Segmentar Área", command=self.show_segmentation_options, state="disabled"); self.btn_segmentar.pack(pady=5, fill="x")
        self.btn_analizar = ctk.CTkButton(control_frame, text="3. Realizar Análisis", command=self.realizar_analisis, state="disabled"); self.btn_analizar.pack(pady=5, fill="x")
        
        info_frame = ctk.CTkFrame(left_column_frame); info_frame.grid(row=1, column=0, sticky="new", padx=10, pady=10)
        ctk.CTkLabel(info_frame, text="Información del Paciente e Histograma", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(10, 5))
        ctk.CTkLabel(info_frame, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_nombre = ctk.CTkEntry(info_frame); self.entry_nombre.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(info_frame, text="Edad:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_edad = ctk.CTkEntry(info_frame); self.entry_edad.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(info_frame, text="Fecha:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.entry_fecha = ctk.CTkEntry(info_frame); self.entry_fecha.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(info_frame, text="Hora:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.entry_hora = ctk.CTkEntry(info_frame); self.entry_hora.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        btn_now = ctk.CTkButton(info_frame, text="Insertar Fecha y Hora Actual", command=self._fill_current_datetime)
        btn_now.grid(row=5, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)
        
        results_text_frame = ctk.CTkFrame(left_column_frame); results_text_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(results_text_frame, text="Resultados y Descargas", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(10,5), padx=20)
        self.lbl_temp_min = ctk.CTkLabel(results_text_frame, text="Temp. Mínima: --"); self.lbl_temp_min.pack(pady=5, padx=20, anchor="w")
        self.lbl_temp_max = ctk.CTkLabel(results_text_frame, text="Temp. Máxima: --"); self.lbl_temp_max.pack(pady=5, padx=20, anchor="w")
        self.lbl_temp_avg = ctk.CTkLabel(results_text_frame, text="Temp. Promedio: --"); self.lbl_temp_avg.pack(pady=5, padx=20, anchor="w")
        self.btn_descargar_csv_orig = ctk.CTkButton(results_text_frame, text="Descargar Matriz Original (CSV)", command=self.descargar_csv_original, state="disabled"); self.btn_descargar_csv_orig.pack(pady=(10, 5), padx=20, fill="x")
        self.btn_descargar_csv_mask = ctk.CTkButton(results_text_frame, text="Descargar Matriz Mascara (CSV)", command=self.descargar_csv_mask, state="disabled"); self.btn_descargar_csv_mask.pack(pady=5, padx=20, fill="x")
        self.btn_descargar_segmentada = ctk.CTkButton(results_text_frame, text="Descargar Matriz Segmentada (CSV)", command=self.descargar_csv_segmentada, state="disabled"); self.btn_descargar_segmentada.pack(pady=5, padx=20, fill="x")
        self.btn_descargar_histo = ctk.CTkButton(results_text_frame, text="Descargar Histograma", command=self.descargar_histograma, state="disabled"); self.btn_descargar_histo.pack(pady=5, padx=20, fill="x")
        #self.btn_exportar_dicom = ctk.CTkButton(results_text_frame, text="Exportar a DICOM", command=self.abrir_exportar_dicom, state="disabled"); self.btn_exportar_dicom.pack(pady=5, padx=20, fill="x")
        
        self.btn_crear_espectro = ctk.CTkButton(results_text_frame, text="Crear Análisis de Espectro", command=self.abrir_ventana_espectro, state="disabled")
        self.btn_crear_espectro.pack(pady=(10, 5), padx=20, fill="x")

        content_frame = ctk.CTkFrame(self, fg_color="transparent"); content_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        content_frame.grid_rowconfigure(0, weight=1); content_frame.grid_rowconfigure(1, weight=2); content_frame.grid_columnconfigure(0, weight=1)
        image_frame = ctk.CTkFrame(content_frame); image_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5)); image_frame.grid_columnconfigure((0, 1), weight=1); image_frame.grid_rowconfigure(0, weight=1)
        scroll_frame_img1 = ctk.CTkScrollableFrame(image_frame, label_text="Imagen Original"); scroll_frame_img1.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.lbl_imagen_original = ctk.CTkLabel(scroll_frame_img1, text=""); self.lbl_imagen_original.pack(expand=True, padx=5, pady=5)
        scroll_frame_img2 = ctk.CTkScrollableFrame(image_frame, label_text="Máscara"); scroll_frame_img2.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.lbl_mascara = ctk.CTkLabel(scroll_frame_img2, text=""); self.lbl_mascara.pack(expand=True, padx=5, pady=5)
        histogram_container_frame = ctk.CTkFrame(content_frame, fg_color="transparent"); histogram_container_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        histogram_container_frame.grid_columnconfigure(0, weight=1); histogram_container_frame.grid_rowconfigure(0, weight=1)
        self.histogram_frame = ctk.CTkFrame(histogram_container_frame); self.histogram_frame.grid(row=0, column=0, sticky="nsew")
    
    def mostrar_imagen_en_label(self, ruta_imagen, label_widget):
        TARGET_HEIGHT = ALTURA_IMAGEN_VISUALIZACION
        try:
            img = Image.open(ruta_imagen)
            if img.height == 0: return
            ratio = img.width / img.height
            target_width = int(TARGET_HEIGHT * ratio)
            img_resized = img.resize((target_width, TARGET_HEIGHT), Image.Resampling.LANCZOS)
            ctk_img = ImageTk.PhotoImage(img_resized)
            label_widget.configure(image=ctk_img, text="")
            label_widget.image = ctk_img
        except Exception as e:
            print(f"Error al mostrar imagen {ruta_imagen}: {e}")
            label_widget.configure(text="Error al cargar imagen", image=None)


    def cargar_imagen(self):
        ruta = filedialog.askopenfilename(title="Selecciona la IMAGEN TÉRMICA ORIGINAL", filetypes=[("Imágenes FLIR", "*.jpg *.jpeg"), ("Todos", "*.*")])
        if not ruta: return
        self.ruta_imagen_original = ruta; self.ruta_mascara = None; self.btn_segmentar.configure(state="normal"); self.btn_analizar.configure(state="disabled")
        self.lbl_mascara.configure(image=None, text=""); self.limpiar_resultados()#;
        self.mostrar_imagen_en_label(self.ruta_imagen_original, self.lbl_imagen_original)

    def show_segmentation_options(self):
        menu = ctk.CTkToplevel(self); menu.title("Opciones de Segmentación"); menu.transient(self); menu.grab_set(); menu.geometry("400x250"); menu.attributes("-topmost", True)
        def center_popup(): self.update_idletasks(); x=self.winfo_x()+(self.winfo_width()//2)-200; y=self.winfo_y()+(self.winfo_height()//2)-125; menu.geometry(f"400x250+{x}+{y}")
        self.after(50, center_popup)
        ctk.CTkLabel(menu, text="¿Cómo quieres obtener la máscara?", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        ctk.CTkButton(menu, text="Segmentación Automática (por Umbral)", command=lambda: [menu.destroy(), self.iniciar_segmentacion_automatica()]).pack(pady=5, padx=20, fill="x")
        ctk.CTkButton(menu, text="Dibujar Máscara Manualmente", command=lambda: [menu.destroy(), self.iniciar_segmentacion_manual()]).pack(pady=5, padx=20, fill="x")
        ctk.CTkButton(menu, text="Cargar Máscara Existente", command=lambda: [menu.destroy(), self.cargar_mascara_existente()]).pack(pady=5, padx=20, fill="x")
        info_label = ctk.CTkLabel(menu, text="Info: Al 'Cargar Máscara', asegúrate de que sea\nuna imagen PNG en blanco y negro, donde el\nárea de interés sea de color blanco.", justify="left")
        info_label.pack(pady=10, padx=20)
        self.wait_window(menu)

    def iniciar_segmentacion_manual(self):
        self.withdraw(); ruta_mascara_generada = segmentar_interactivo(self.ruta_imagen_original); self.deiconify()
        if ruta_mascara_generada: self.ruta_mascara = ruta_mascara_generada; self.mostrar_imagen_en_label(self.ruta_mascara, self.lbl_mascara); self.btn_analizar.configure(state="normal")
        else: self.ruta_mascara = None; self.btn_analizar.configure(state="disabled"); self.lbl_mascara.configure(image=None, text="")

    def iniciar_segmentacion_automatica(self):
        dialog = ctk.CTkInputDialog(text="Ingresa la temperatura mínima (°C) para el umbral:", title="Umbral de Temperatura")
        umbral_str = dialog.get_input()
        if umbral_str:
            try:
                umbral_temp = float(umbral_str)
                ruta_mascara = self.generar_mascara_por_umbral(umbral_temp)
                if ruta_mascara:
                    self.ruta_mascara = ruta_mascara
                    self.mostrar_imagen_en_label(self.ruta_mascara, self.lbl_mascara)
                    self.btn_analizar.configure(state="normal")
                else: messagebox.showerror("Error", "No se pudo generar la máscara automática.")
            except (ValueError, TypeError): messagebox.showerror("Error", "Por favor, ingresa un número válido para la temperatura.")

    def generar_mascara_por_umbral(self, umbral):
        try:
            # Necesitamos un user_info temporal, no puede ser None
            user_info_temp = {"Nombre": "", "Edad": "", "Fecha": "", "Hora": ""}
            resultados, _, temp_matrix, _ = analizar_temperaturas(self.ruta_imagen_original, self.ruta_imagen_original, user_info=user_info_temp)
            if temp_matrix is None:
                messagebox.showerror("Error de Análisis", f"No se pudo extraer la matriz de temperatura. Error: {resultados.get('error')}")
                return None
            mascara_automatica = np.where(temp_matrix >= umbral, 255, 0).astype(np.uint8)
            directorio, nombre_archivo = os.path.split(self.ruta_imagen_original); nombre_base, _ = os.path.splitext(nombre_archivo)
            ruta_mascara_salida = os.path.join(directorio, f"{nombre_base}_mask_auto_{umbral}C.png")
            cv2.imwrite(ruta_mascara_salida, mascara_automatica)
            return ruta_mascara_salida
        except Exception as e:
            messagebox.showerror("Error de Segmentación", f"Ocurrió un error al generar la máscara: {e}")
            return None

    def cargar_mascara_existente(self):
        ruta = filedialog.askopenfilename(title="Selecciona un archivo de MÁSCARA (PNG)", filetypes=[("PNG", "*.png"), ("Todos", "*.*")])
        if not ruta: return
        try:
            if cv2.imread(ruta, cv2.IMREAD_GRAYSCALE) is None: raise ValueError("Archivo no válido")
        except Exception: messagebox.showerror("Error", "No se pudo cargar. Asegúrate de que es un PNG válido."); return
        self.ruta_mascara = ruta; self.mostrar_imagen_en_label(self.ruta_mascara, self.lbl_mascara); self.btn_analizar.configure(state="normal")
    
    def _fill_current_datetime(self):
        now = datetime.now()
        self.entry_fecha.delete(0, "end"); self.entry_fecha.insert(0, now.strftime('%d/%m/%Y'))
        self.entry_hora.delete(0, "end"); self.entry_hora.insert(0, now.strftime('%I:%M:%S %p'))

    def realizar_analisis(self):
        if not self.ruta_imagen_original or not self.ruta_mascara: return
        self.limpiar_resultados()
        user_info = {"Nombre": self.entry_nombre.get(), "Edad": self.entry_edad.get(), "Fecha": self.entry_fecha.get(), "Hora": self.entry_hora.get()}
        resultados, fig, matriz_original, matriz_segmentada = analizar_temperaturas(self.ruta_imagen_original, self.ruta_mascara, user_info)
        
        self.matriz_temp_original = matriz_original
        self.matriz_binaria_segmentada = matriz_segmentada 

        if "error" in resultados: self.lbl_temp_min.configure(text=resultados["error"], text_color="red"); return
        self.lbl_temp_min.configure(text=f"Temp. Mínima: {resultados['min_temp']}", text_color="white")
        self.lbl_temp_max.configure(text=f"Temp. Máxima: {resultados['max_temp']}", text_color="white")
        self.lbl_temp_avg.configure(text=f"Temp. Promedio: {resultados['avg_temp']}", text_color="white")
        if fig:
            self.fig_matplotlib = fig
            canvas = FigureCanvasTkAgg(self.fig_matplotlib, master=self.histogram_frame)
            canvas.draw()
            widget = canvas.get_tk_widget(); widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.btn_descargar_histo.configure(state="normal")
            self.btn_descargar_csv_orig.configure(state="normal")
            self.btn_descargar_csv_mask.configure(state="normal")
            self.btn_descargar_segmentada.configure(state="normal")
            self.btn_crear_espectro.configure(state="normal") 
            #self.btn_exportar_dicom.configure(state="normal")


    def abrir_ventana_espectro(self):
        if self.ventana_espectro_actual is None or not self.ventana_espectro_actual.winfo_exists():
            # Pasa las matrices en memoria a la nueva ventana
            self.ventana_espectro_actual = VentanaEspectro(
                master=self,
                matriz_temp=self.matriz_temp_original,
                matriz_mascara=self.matriz_binaria_segmentada
            )
        else:
            self.ventana_espectro_actual.focus()

    def limpiar_resultados(self):
        self.lbl_temp_min.configure(text="Temp. Mínima: --", text_color="white"); self.lbl_temp_max.configure(text="Temp. Máxima: --", text_color="white")
        self.lbl_temp_avg.configure(text="Temp. Promedio: --", text_color="white")
        if hasattr(self, 'histogram_frame'):
            for widget in self.histogram_frame.winfo_children(): widget.destroy()
        self.fig_matplotlib = None
        self.matriz_temp_original = None
        self.matriz_binaria_segmentada = None
        self.btn_descargar_histo.configure(state="disabled")
        self.btn_descargar_csv_orig.configure(state="disabled")
        self.btn_descargar_csv_mask.configure(state="disabled")
        self.btn_descargar_segmentada.configure(state="disabled")
        if hasattr(self, 'btn_crear_espectro'):
            self.btn_crear_espectro.configure(state="disabled")

    def descargar_histograma(self):
        if self.fig_matplotlib:
            ruta_guardado = filedialog.asksaveasfilename(title="Guardar imagen del histograma", defaultextension=".png", filetypes=[("Archivo PNG", "*.png"), ("JPG", "*.jpg")])
            if ruta_guardado:
                try:
                    self.fig_matplotlib.savefig(ruta_guardado, dpi=300, bbox_inches='tight')
                    messagebox.showinfo("Éxito", f"Histograma guardado correctamente en:\n{ruta_guardado}")
                except Exception as e: messagebox.showerror("Error al guardar", f"No se pudo guardar la imagen.\nError: {e}")

    def descargar_csv_original(self):
        if self.matriz_temp_original is not None:
            ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if ruta:
                np.savetxt(ruta, self.matriz_temp_original, delimiter=",", fmt='%.2f')
                messagebox.showinfo("Éxito", "Matriz Original guardada.")

    def descargar_csv_mask(self):
        if self.matriz_binaria_segmentada is not None:
            ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if ruta:
                np.savetxt(ruta, self.matriz_binaria_segmentada, delimiter=",", fmt='%d')
                messagebox.showinfo("Éxito", "Matriz Máscara guardada.")

    def descargar_csv_segmentada(self):
        if self.matriz_temp_original is not None and self.matriz_binaria_segmentada is not None:
            ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if ruta:
                # Multiplicamos la original por la máscara (0 y 1)
                matriz_final = self.matriz_temp_original * self.matriz_binaria_segmentada
                np.savetxt(ruta, matriz_final, delimiter=",", fmt='%.2f')
                messagebox.showinfo("Éxito", "Matriz Segmentada (Valores Reales) guardada.")
                
    def abrir_exportar_dicom(self):
        if self.matriz_temp_original is not None:
            # Intentamos obtener metadatos crudos si están disponibles
            # Para simplificar, pasamos un diccionario vacío si no se han guardado previamente
            metadatos_mock = {"CameraModel": "FLIR E6"} 
            info_paciente = {
            "Nombre": self.entry_nombre.get(),
            "Fecha": self.entry_fecha.get()
            }
            VentanaExportarDicom(self, self.matriz_temp_original, metadatos_mock, info_paciente)

# --- INICIO DEL PROGRAMA ---
if __name__ == "__main__":
    app = App()
    app.mainloop()