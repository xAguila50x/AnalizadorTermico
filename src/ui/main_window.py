"""
=============================================================================
ARCHIVO: src/ui/main_window.py
VENTANA PRINCIPAL DE LA APLICACIÓN TÉRMICA (CLASE APP)
=============================================================================
¿Qué encontramos aquí?
Este archivo es el corazón de la interfaz gráfica. Aquí se define la clase 'App',
la cual hereda de 'ctk.CTk' (la ventana principal de CustomTkinter).

El flujo de uso de la aplicación está pensado en 3 pasos súper claros para el usuario:
1. Cargar Imagen FLIR (.jpg)
2. Segmentar el Área (manual con mouse, por umbral de temperatura o cargando un PNG)
3. Realizar Análisis (calcula temperaturas, dibuja el histograma y habilita Fourier y exportaciones)
"""

import os
from datetime import datetime
import cv2
import numpy as np
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.config import ALTURA_IMAGEN_VISUALIZACION, get_icon_path
from src.core.thermal import analizar_temperaturas
from src.core.segmentation import segmentar_interactivo, generar_mascara_por_umbral
from src.ui.dialogs import show_segmentation_options_dialog
from src.ui.spectrum_window import VentanaEspectro
from src.ui.dicom_window import VentanaExportarDicom


class App(ctk.CTk):
    """
    Clase principal de la aplicación.
    Controla todo el flujo: desde la pantalla de bienvenida (Splash Screen)
    hasta el panel completo de análisis con histogramas y visualizadores.
    """

    def __init__(self):
        super().__init__()

        # Variables donde guardamos los datos mientras la app esté abierta:
        self.ruta_imagen_original = None       # Ruta del archivo de foto térmica
        self.ruta_mascara = None               # Ruta del archivo de máscara PNG
        self.fig_matplotlib = None             # Objeto de la gráfica del histograma
        self.matriz_temp_original = None       # Matriz completa con temperaturas en °C
        self.matriz_binaria_segmentada = None  # Matriz de 0s y 1s de la máscara
        self.metadatos_flir = {}               # Datos técnicos que traía la cámara
        self.ventana_espectro_actual = None    # Referencia a la ventana de Fourier

        # Le ponemos el ícono a la aplicación y mostramos la pantalla de bienvenida
        self._set_app_icon()
        self.show_splash_screen()

    def _set_app_icon(self):
        """Asigna el archivo 'icono1.ico' a la barra de título si existe."""
        icon_path = get_icon_path()
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    def center_window(self, width: int, height: int):
        """Calcula la mitad de la resolución de tu monitor para centrar la ventana."""
        pos_x = int((self.winfo_screenwidth() / 2) - (width / 2))
        pos_y = int((self.winfo_screenheight() / 2) - (height / 2))
        self.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    def clear_widgets(self):
        """Borra todos los botones y etiquetas que estén en la ventana para dibujar una nueva vista."""
        for widget in self.winfo_children():
            widget.destroy()

    # =======================================================================
    # VISTA 1: PANTALLA DE BIENVENIDA (SPLASH SCREEN)
    # =======================================================================
    def show_splash_screen(self):
        """Muestra una pantalla limpia de bienvenida con el botón 'INICIAR APLICACIÓN'."""
        self.title("Herramienta Térmica - Bienvenida")
        self.geometry("800x500")
        self.center_window(800, 500)
        self.resizable(False, False)

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=50, pady=50)

        ctk.CTkLabel(
            main_frame,
            text="Asistente de Análisis de Imágenes Térmicas",
            font=ctk.CTkFont(size=30, weight="bold"),
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            main_frame,
            text="Herramienta profesional para la segmentación y análisis de temperatura.",
            font=ctk.CTkFont(size=16),
        ).pack(pady=(0, 40))

        # Al dar clic aquí, pasamos a la pantalla principal de trabajo
        ctk.CTkButton(
            main_frame,
            text="INICIAR APLICACIÓN",
            command=self.show_main_app,
            font=ctk.CTkFont(size=18, weight="bold"),
            width=250,
            height=50,
        ).pack(pady=(0, 20))

    # =======================================================================
    # VISTA 2: PANTALLA PRINCIPAL DE TRABAJO
    # =======================================================================
    def show_main_app(self):
        """Construye el panel completo de trabajo con sus dos grandes columnas."""
        self.clear_widgets()
        self.title("Asistente de Análisis Térmico")
        self._set_app_icon()

        # Intentamos maximizar la ventana en Windows
        try:
            self.state("zoomed")
        except Exception:
            self.geometry("1200x800")

        self.resizable(True, True)

        # Configuramos la cuadrícula (Grid):
        # Columna 0: Barra lateral fija a la izquierda (botones y formularios)
        # Columna 1: Área grande a la derecha con peso 1 para expandirse (imágenes y gráfica)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # -------------------------------------------------------------------
        # COLUMNA IZQUIERDA: PANEL DE CONTROL LATERAL
        # -------------------------------------------------------------------
        left_column_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        left_column_frame.grid(row=0, column=0, sticky="nsew")
        left_column_frame.grid_rowconfigure(2, weight=1)

        # SECCIÓN A: Los 3 botones principales de flujo
        control_frame = ctk.CTkFrame(left_column_frame, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="new", padx=10, pady=10)

        ctk.CTkLabel(
            control_frame, text="Panel de Control", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(10, 10))

        # Paso 1: Cargar foto
        self.btn_cargar = ctk.CTkButton(
            control_frame, text="1. Cargar Imagen", command=self.cargar_imagen
        )
        self.btn_cargar.pack(pady=5, fill="x")

        # Paso 2: Segmentar (se habilita solo cuando ya cargaste una imagen)
        self.btn_segmentar = ctk.CTkButton(
            control_frame,
            text="2. Segmentar Área",
            command=self.show_segmentation_options,
            state="disabled",
        )
        self.btn_segmentar.pack(pady=5, fill="x")

        # Paso 3: Calcular (se habilita solo cuando ya tienes imagen y máscara)
        self.btn_analizar = ctk.CTkButton(
            control_frame,
            text="3. Realizar Análisis",
            command=self.realizar_analisis,
            state="disabled",
        )
        self.btn_analizar.pack(pady=5, fill="x")

        # SECCIÓN B: Formulario de datos del paciente
        info_frame = ctk.CTkFrame(left_column_frame)
        info_frame.grid(row=1, column=0, sticky="new", padx=10, pady=10)

        ctk.CTkLabel(
            info_frame,
            text="Información del Paciente e Histograma",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(10, 5))

        ctk.CTkLabel(info_frame, text="Nombre:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_nombre = ctk.CTkEntry(info_frame)
        self.entry_nombre.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(info_frame, text="Edad:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_edad = ctk.CTkEntry(info_frame)
        self.entry_edad.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(info_frame, text="Fecha:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.entry_fecha = ctk.CTkEntry(info_frame)
        self.entry_fecha.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(info_frame, text="Hora:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.entry_hora = ctk.CTkEntry(info_frame)
        self.entry_hora.grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        # Botón para no tener que escribir la fecha y hora a mano
        btn_now = ctk.CTkButton(
            info_frame,
            text="Insertar Fecha y Hora Actual",
            command=self._fill_current_datetime,
        )
        btn_now.grid(row=5, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        # SECCIÓN C: Resultados numéricos y botones de descarga
        results_text_frame = ctk.CTkFrame(left_column_frame)
        results_text_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(
            results_text_frame,
            text="Resultados y Descargas",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(10, 5), padx=20)

        self.lbl_temp_min = ctk.CTkLabel(results_text_frame, text="Temp. Mínima: --")
        self.lbl_temp_min.pack(pady=5, padx=20, anchor="w")

        self.lbl_temp_max = ctk.CTkLabel(results_text_frame, text="Temp. Máxima: --")
        self.lbl_temp_max.pack(pady=5, padx=20, anchor="w")

        self.lbl_temp_avg = ctk.CTkLabel(results_text_frame, text="Temp. Promedio: --")
        self.lbl_temp_avg.pack(pady=5, padx=20, anchor="w")

        # Botones para exportar las matrices numéricas a Excel/CSV
        self.btn_descargar_csv_orig = ctk.CTkButton(
            results_text_frame,
            text="Descargar Matriz Original (CSV)",
            command=self.descargar_csv_original,
            state="disabled",
        )
        self.btn_descargar_csv_orig.pack(pady=(10, 5), padx=20, fill="x")

        self.btn_descargar_csv_mask = ctk.CTkButton(
            results_text_frame,
            text="Descargar Matriz Mascara (CSV)",
            command=self.descargar_csv_mask,
            state="disabled",
        )
        self.btn_descargar_csv_mask.pack(pady=5, padx=20, fill="x")

        self.btn_descargar_segmentada = ctk.CTkButton(
            results_text_frame,
            text="Descargar Matriz Segmentada (CSV)",
            command=self.descargar_csv_segmentada,
            state="disabled",
        )
        self.btn_descargar_segmentada.pack(pady=5, padx=20, fill="x")

        # Botón para guardar la foto de la gráfica del histograma
        self.btn_descargar_histo = ctk.CTkButton(
            results_text_frame,
            text="Descargar Histograma",
            command=self.descargar_histograma,
            state="disabled",
        )
        self.btn_descargar_histo.pack(pady=5, padx=20, fill="x")

        # Botón para abrir la ventana de Fourier 2D
        self.btn_crear_espectro = ctk.CTkButton(
            results_text_frame,
            text="Crear Análisis de Espectro",
            command=self.abrir_ventana_espectro,
            state="disabled",
        )
        self.btn_crear_espectro.pack(pady=(10, 5), padx=20, fill="x")

        # -------------------------------------------------------------------
        # COLUMNA DERECHA: VISUALIZADORES DE IMÁGENES Y GRÁFICA
        # -------------------------------------------------------------------
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        content_frame.grid_rowconfigure(0, weight=1)  # Fila superior (imágenes)
        content_frame.grid_rowconfigure(1, weight=2)  # Fila inferior (histograma)
        content_frame.grid_columnconfigure(0, weight=1)

        # Fila Superior: Imagen Original (izq) y Máscara (der)
        image_frame = ctk.CTkFrame(content_frame)
        image_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        image_frame.grid_columnconfigure((0, 1), weight=1)
        image_frame.grid_rowconfigure(0, weight=1)

        scroll_frame_img1 = ctk.CTkScrollableFrame(image_frame, label_text="Imagen Original")
        scroll_frame_img1.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.lbl_imagen_original = ctk.CTkLabel(scroll_frame_img1, text="")
        self.lbl_imagen_original.pack(expand=True, padx=5, pady=5)

        scroll_frame_img2 = ctk.CTkScrollableFrame(image_frame, label_text="Máscara")
        scroll_frame_img2.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.lbl_mascara = ctk.CTkLabel(scroll_frame_img2, text="")
        self.lbl_mascara.pack(expand=True, padx=5, pady=5)

        # Fila Inferior: Contenedor donde incrustamos la gráfica de Matplotlib
        histogram_container_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        histogram_container_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        histogram_container_frame.grid_columnconfigure(0, weight=1)
        histogram_container_frame.grid_rowconfigure(0, weight=1)

        self.histogram_frame = ctk.CTkFrame(histogram_container_frame)
        self.histogram_frame.grid(row=0, column=0, sticky="nsew")

    # =======================================================================
    # FUNCIONES DE CARGA Y VISUALIZACIÓN DE IMÁGENES
    # =======================================================================
    def mostrar_imagen_en_label(self, ruta_imagen: str, label_widget: ctk.CTkLabel):
        """
        Lee una imagen con Pillow, calcula su proporción de aspecto (aspect ratio)
        para no deformarla o aplastarla, la escala a la altura definida en config.py
        y la asigna a un CTkLabel usando CTkImage (ideal para pantallas High-DPI).
        """
        TARGET_HEIGHT = ALTURA_IMAGEN_VISUALIZACION
        try:
            img = Image.open(ruta_imagen)
            if img.height == 0:
                return

            # Calculamos el ancho proporcional: ancho = alto_objetivo * (ancho_original / alto_original)
            ratio = img.width / img.height
            target_width = int(TARGET_HEIGHT * ratio)

            # Redimensionamos con el filtro Lanczos (máxima calidad visual)
            img_resized = img.resize((target_width, TARGET_HEIGHT), Image.Resampling.LANCZOS)

            # Envolvemos en CTkImage para que se vea nítida en Windows con escala del 125% o 150%
            ctk_img = ctk.CTkImage(
                light_image=img_resized,
                dark_image=img_resized,
                size=(target_width, TARGET_HEIGHT),
            )
            label_widget.configure(image=ctk_img, text="")
            label_widget.image = ctk_img
        except Exception as e:
            print(f"Error al mostrar imagen {ruta_imagen}: {e}")
            label_widget.configure(text="Error al cargar imagen", image=None)

    def cargar_imagen(self):
        """Paso 1: Abre el explorador para elegir la foto térmica FLIR (.jpg)."""
        ruta = filedialog.askopenfilename(
            title="Selecciona la IMAGEN TÉRMICA ORIGINAL",
            filetypes=[("Imágenes FLIR", "*.jpg *.jpeg"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return

        self.ruta_imagen_original = ruta
        self.ruta_mascara = None

        # Actualizamos botones: habilitamos 'Segmentar' y deshabilitamos 'Analizar' hasta tener máscara
        self.btn_segmentar.configure(state="normal")
        self.btn_analizar.configure(state="disabled")
        self.lbl_mascara.configure(image=None, text="")
        self.limpiar_resultados()

        # Mostramos la foto en el visualizador izquierdo
        self.mostrar_imagen_en_label(self.ruta_imagen_original, self.lbl_imagen_original)

    # =======================================================================
    # FUNCIONES DE SEGMENTACIÓN (PASO 2)
    # =======================================================================
    def show_segmentation_options(self):
        """Abre el diálogo modal para que el usuario elija cómo segmentar."""
        show_segmentation_options_dialog(
            self,
            on_auto=self.iniciar_segmentacion_automatica,
            on_manual=self.iniciar_segmentacion_manual,
            on_load=self.cargar_mascara_existente,
        )

    def iniciar_segmentacion_manual(self):
        """
        Oculta temporalmente la ventana principal (withdraw), abre OpenCV para
        que dibujes con el mouse sin distracciones, y al terminar vuelve a mostrar la app (deiconify).
        """
        self.withdraw()
        ruta_mascara_generada = segmentar_interactivo(self.ruta_imagen_original, parent=self)
        self.deiconify()

        if ruta_mascara_generada:
            self.ruta_mascara = ruta_mascara_generada
            self.mostrar_imagen_en_label(self.ruta_mascara, self.lbl_mascara)
            self.btn_analizar.configure(state="normal")
        else:
            self.ruta_mascara = None
            self.btn_analizar.configure(state="disabled")
            self.lbl_mascara.configure(image=None, text="")

    def iniciar_segmentacion_automatica(self):
        """Pide una temperatura con un cuadrito de texto y genera la máscara por umbral."""
        dialog = ctk.CTkInputDialog(
            text="Ingresa la temperatura mínima (°C) para el umbral:",
            title="Umbral de Temperatura",
        )
        umbral_str = dialog.get_input()
        if umbral_str:
            try:
                umbral_temp = float(umbral_str)
                ruta_mascara = self.generar_mascara_por_umbral(umbral_temp)
                if ruta_mascara:
                    self.ruta_mascara = ruta_mascara
                    self.mostrar_imagen_en_label(self.ruta_mascara, self.lbl_mascara)
                    self.btn_analizar.configure(state="normal")
                else:
                    messagebox.showerror("Error", "No se pudo generar la máscara automática.")
            except (ValueError, TypeError):
                messagebox.showerror(
                    "Error", "Por favor, ingresa un número válido para la temperatura."
                )

    def generar_mascara_por_umbral(self, umbral: float):
        """Llama a la función de segmentación automática ubicada en src.core.segmentation."""
        user_info_temp = {"Nombre": "", "Edad": "", "Fecha": "", "Hora": ""}
        return generar_mascara_por_umbral(self.ruta_imagen_original, umbral, user_info_temp)

    def cargar_mascara_existente(self):
        """Permite seleccionar un archivo PNG en blanco y negro ya guardado en la computadora."""
        ruta = filedialog.askopenfilename(
            title="Selecciona un archivo de MÁSCARA (PNG)",
            filetypes=[("PNG", "*.png"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return
        try:
            if cv2.imread(ruta, cv2.IMREAD_GRAYSCALE) is None:
                raise ValueError("Archivo no válido")
        except Exception:
            messagebox.showerror(
                "Error", "No se pudo cargar. Asegúrate de que es un PNG válido."
            )
            return

        self.ruta_mascara = ruta
        self.mostrar_imagen_en_label(self.ruta_mascara, self.lbl_mascara)
        self.btn_analizar.configure(state="normal")

    def _fill_current_datetime(self):
        """Llena automáticamente los campos con la fecha y hora de la computadora."""
        now = datetime.now()
        self.entry_fecha.delete(0, "end")
        self.entry_fecha.insert(0, now.strftime("%d/%m/%Y"))
        self.entry_hora.delete(0, "end")
        self.entry_hora.insert(0, now.strftime("%I:%M:%S %p"))

    # =======================================================================
    # FUNCIONES DE ANÁLISIS TÉRMICO (PASO 3)
    # =======================================================================
    def realizar_analisis(self):
        """
        Paso 3: Procesa la foto térmica con la máscara:
        1. Llama a 'analizar_temperaturas()' de src.core.thermal.
        2. Muestra las temperaturas mínima, máxima y promedio calculadas.
        3. Incrusta la gráfica del histograma en la pantalla usando FigureCanvasTkAgg.
        4. Habilita los botones de descarga de matrices y de análisis de Fourier.
        """
        if not self.ruta_imagen_original or not self.ruta_mascara:
            return

        self.limpiar_resultados()

        # Tomamos los datos del paciente desde los campos de texto
        user_info = {
            "Nombre": self.entry_nombre.get(),
            "Edad": self.entry_edad.get(),
            "Fecha": self.entry_fecha.get(),
            "Hora": self.entry_hora.get(),
        }

        # Ejecutamos el motor térmico (ExifTool + Calibración + Matplotlib)
        resultados, fig, matriz_original, matriz_segmentada = analizar_temperaturas(
            self.ruta_imagen_original, self.ruta_mascara, user_info
        )

        # Guardamos las matrices en memoria para usarlas luego en Fourier o DICOM
        self.matriz_temp_original = matriz_original
        self.matriz_binaria_segmentada = matriz_segmentada
        self.metadatos_flir = resultados.get("_metadata_raw", {})

        # Si hubo algún error (ej. cámara no compatible), lo mostramos en color rojo
        if "error" in resultados:
            self.lbl_temp_min.configure(text=resultados["error"], text_color="red")
            return

        # Mostramos los valores térmicos calculados
        self.lbl_temp_min.configure(
            text=f"Temp. Mínima: {resultados['min_temp']}", text_color="white"
        )
        self.lbl_temp_max.configure(
            text=f"Temp. Máxima: {resultados['max_temp']}", text_color="white"
        )
        self.lbl_temp_avg.configure(
            text=f"Temp. Promedio: {resultados['avg_temp']}", text_color="white"
        )

        # Dibujamos la gráfica de Matplotlib dentro de nuestra ventana de CustomTkinter
        if fig:
            self.fig_matplotlib = fig
            canvas = FigureCanvasTkAgg(self.fig_matplotlib, master=self.histogram_frame)
            canvas.draw()
            widget = canvas.get_tk_widget()
            widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

            # Ya tenemos resultados, así que habilitamos todos los botones de descarga
            self.btn_descargar_histo.configure(state="normal")
            self.btn_descargar_csv_orig.configure(state="normal")
            self.btn_descargar_csv_mask.configure(state="normal")
            self.btn_descargar_segmentada.configure(state="normal")
            self.btn_crear_espectro.configure(state="normal")

    def abrir_ventana_espectro(self):
        """
        Abre la ventana de Análisis de Espectro (Fourier).
        Si ya estaba abierta, solo le da el foco para que no abras 10 ventanas iguales.
        """
        if self.ventana_espectro_actual is None or not self.ventana_espectro_actual.winfo_exists():
            self.ventana_espectro_actual = VentanaEspectro(
                master=self,
                matriz_temp=self.matriz_temp_original,
                matriz_mascara=self.matriz_binaria_segmentada,
            )
        else:
            self.ventana_espectro_actual.focus()

    def limpiar_resultados(self):
        """Borra la gráfica anterior y reinicia los textos de temperatura a '--'."""
        self.lbl_temp_min.configure(text="Temp. Mínima: --", text_color="white")
        self.lbl_temp_max.configure(text="Temp. Máxima: --", text_color="white")
        self.lbl_temp_avg.configure(text="Temp. Promedio: --", text_color="white")

        # Destruye el canvas viejo de Matplotlib si existía
        if hasattr(self, "histogram_frame"):
            for widget in self.histogram_frame.winfo_children():
                widget.destroy()

        self.fig_matplotlib = None
        self.matriz_temp_original = None
        self.matriz_binaria_segmentada = None
        self.metadatos_flir = {}

        # Apagamos los botones de descarga hasta que vuelvan a analizar
        self.btn_descargar_histo.configure(state="disabled")
        self.btn_descargar_csv_orig.configure(state="disabled")
        self.btn_descargar_csv_mask.configure(state="disabled")
        self.btn_descargar_segmentada.configure(state="disabled")
        if hasattr(self, "btn_crear_espectro"):
            self.btn_crear_espectro.configure(state="disabled")

    # =======================================================================
    # FUNCIONES DE DESCARGA (EXPORTAR A ARCHIVOS)
    # =======================================================================
    def descargar_histograma(self):
        """Guarda la figura actual de Matplotlib como imagen PNG o JPG."""
        if self.fig_matplotlib:
            ruta_guardado = filedialog.asksaveasfilename(
                title="Guardar imagen del histograma",
                defaultextension=".png",
                filetypes=[("Archivo PNG", "*.png"), ("JPG", "*.jpg"), ("Todos los archivos", "*.*")],
            )
            if ruta_guardado:
                try:
                    self.fig_matplotlib.savefig(ruta_guardado, dpi=300, bbox_inches="tight")
                    messagebox.showinfo(
                        "Éxito", f"Histograma guardado correctamente en:\n{ruta_guardado}"
                    )
                except Exception as e:
                    messagebox.showerror(
                        "Error al guardar", f"No se pudo guardar la imagen.\nError: {e}"
                    )

    def descargar_csv_original(self):
        """Guarda toda la matriz térmica cruda en un archivo de texto separado por comas (.csv)."""
        if self.matriz_temp_original is not None:
            ruta = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
            )
            if ruta:
                np.savetxt(ruta, self.matriz_temp_original, delimiter=",", fmt="%.2f")
                messagebox.showinfo("Éxito", "Matriz Original guardada.")

    def descargar_csv_mask(self):
        """Guarda la matriz de ceros y unos de la máscara en un archivo .csv."""
        if self.matriz_binaria_segmentada is not None:
            ruta = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
            )
            if ruta:
                np.savetxt(ruta, self.matriz_binaria_segmentada, delimiter=",", fmt="%d")
                messagebox.showinfo("Éxito", "Matriz Máscara guardada.")

    def descargar_csv_segmentada(self):
        """
        Multiplica la matriz original por la máscara (dejando en 0 el fondo
        y conservando la temperatura en el área de interés) y la guarda en CSV.
        """
        if self.matriz_temp_original is not None and self.matriz_binaria_segmentada is not None:
            ruta = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
            )
            if ruta:
                matriz_final = self.matriz_temp_original * self.matriz_binaria_segmentada
                np.savetxt(ruta, matriz_final, delimiter=",", fmt="%.2f")
                messagebox.showinfo("Éxito", "Matriz Segmentada (Valores Reales) guardada.")

    def abrir_exportar_dicom(self):
        """Abre directamente la ventana de exportación DICOM."""
        if self.matriz_temp_original is not None:
            metadatos_mock = self.metadatos_flir or {"CameraModel": "FLIR E6"}
            info_paciente = {
                "Nombre": self.entry_nombre.get(),
                "Fecha": self.entry_fecha.get(),
            }
            VentanaExportarDicom(self, self.matriz_temp_original, metadatos_mock, info_paciente)
