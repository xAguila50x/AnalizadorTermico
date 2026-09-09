"""
=============================================================================
ARCHIVO: src/ui/spectrum_window.py
VENTANA DE ANÁLISIS DE ESPECTRO (FOURIER 2D)
=============================================================================
¿Qué hace esta ventana?
Es la pantalla secundaria donde vemos el resultado de aplicar la Transformada
de Fourier 2D.
Tiene dos lados:
- A la izquierda: Muestra la imagen visual del espectro (la nube de frecuencias).
- A la derecha: Muestra los porcentajes numéricos de energía (Bajas, Medias y Altas),
  un reporte técnico con una guía para que cualquier persona entienda qué significa,
  y un botón morado para exportar estos hallazgos a un archivo médico DICOM.
"""

import os
from datetime import datetime
import cv2
import numpy as np
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog, messagebox

from src.config import get_icon_path
from src.core.fourier import procesar_fourier_completo
from src.ui.dicom_window import VentanaExportarDicom


class VentanaEspectro(ctk.CTkToplevel):
    """
    Ventana flotante de análisis espectral y frecuencia espacial.
    Puede recibir las matrices directamente desde la pantalla principal (automático)
    o permitirle al usuario cargar un archivo CSV desde su disco duro (manual).
    """

    def __init__(self, master, matriz_temp=None, matriz_mascara=None):
        super().__init__(master)
        self.master_app = master  # Referencia a la ventana principal

        # Tamaño y título de la ventana
        self.title("Análisis de Espectro y Exportación DICOM")
        self.geometry("1100x850")
        self.transient(master)  # Queda vinculada a la ventana principal

        # Le ponemos el ícono a la ventana si está disponible
        icon_path = get_icon_path()
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Variables para guardar las matrices y resultados
        self.matriz_temp_local = matriz_temp
        self.imagen_espectro_cv = None
        self.resultados_energia = None

        # -------------------------------------------------------------------
        # 1. PANEL SUPERIOR: Botones para carga manual
        # -------------------------------------------------------------------
        self.frame_top = ctk.CTkFrame(self)
        self.frame_top.pack(pady=10, padx=20, fill="x")

        # Botón para cargar CSV manual
        self.btn_cargar = ctk.CTkButton(
            self.frame_top,
            text="1. CARGAR SEGMENTADA (.CSV)",
            command=self.seleccionar_archivo,
            fg_color="#1f538d",
            height=40,
        )
        self.btn_cargar.pack(pady=10, padx=10, side="left")

        # Mensaje de estado ("Esperando archivo..." o "Datos listos")
        self.lbl_status = ctk.CTkLabel(
            self.frame_top,
            text="Datos listos" if matriz_temp is not None else "Esperando archivo...",
            text_color="gray",
        )
        self.lbl_status.pack(pady=10, padx=10, side="left", expand=True)

        # Botón naranja para arrancar el cálculo
        self.btn_analizar = ctk.CTkButton(
            self.frame_top,
            text="2. REALIZAR ANÁLISIS",
            command=self.ejecutar_analisis,
            fg_color="#A85400",
            height=40,
            state="normal" if matriz_temp is not None else "disabled",
        )
        self.btn_analizar.pack(pady=10, padx=10, side="right")

        # -------------------------------------------------------------------
        # 2. CONTENEDOR PRINCIPAL: Dividido en 2 columnas
        # -------------------------------------------------------------------
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.main_container.grid_columnconfigure(0, weight=1)  # Columna 0: Imagen
        self.main_container.grid_columnconfigure(1, weight=1)  # Columna 1: Resultados
        self.main_container.grid_rowconfigure(0, weight=1)

        # --- LADO IZQUIERDO: Visualizador del Espectro ---
        self.lbl_espectro = ctk.CTkLabel(
            self.main_container, text="El espectro aparecerá aquí"
        )
        self.lbl_espectro.grid(row=0, column=0, sticky="nsew", padx=5)

        # --- LADO DERECHO: Tarjeta de Resultados ---
        right_column = ctk.CTkFrame(self.main_container)
        right_column.grid(row=0, column=1, sticky="nsew", padx=5)

        ctk.CTkLabel(
            right_column,
            text="RESULTADOS DE ENERGÍA",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=10)

        # Etiquetas de colores para cada frecuencia
        self.lbl_pct_baja = ctk.CTkLabel(
            right_column, text="Bajas: --", text_color="cyan"
        )
        self.lbl_pct_baja.pack()

        self.lbl_pct_media = ctk.CTkLabel(
            right_column, text="Medias: --", text_color="orange"
        )
        self.lbl_pct_media.pack()

        self.lbl_pct_alta = ctk.CTkLabel(
            right_column, text="Altas: --", text_color="red"
        )
        self.lbl_pct_alta.pack()

        # Cuadro de texto grande donde redactamos el informe y la guía
        self.txt_interpretacion = ctk.CTkTextbox(right_column, height=200, state="disabled")
        self.txt_interpretacion.pack(fill="both", expand=True, padx=10, pady=10)

        # Botón morado para abrir el exportador a DICOM
        self.btn_exportar_dicom_full = ctk.CTkButton(
            right_column,
            text="EXPORTAR RESULTADOS A DICOM",
            command=self._abrir_exportador_con_anillos,
            fg_color="purple",
            height=50,
            state="disabled",
            font=ctk.CTkFont(weight="bold"),
        )
        self.btn_exportar_dicom_full.pack(fill="x", padx=10, pady=20)

        # -------------------------------------------------------------------
        # 3. MODO AUTOMÁTICO: Si ya venimos con datos, procesamos de una vez
        # -------------------------------------------------------------------
        if matriz_temp is not None and matriz_mascara is not None:
            self.procesar_datos_en_memoria(matriz_temp, matriz_mascara)

    def seleccionar_archivo(self):
        """Abre un explorador para cargar un CSV de temperatura segmentada."""
        ruta = filedialog.askopenfilename(
            title="Seleccionar Matriz Segmentada",
            filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            try:
                matriz = np.genfromtxt(ruta, delimiter=",")
                # nan_to_num cambia posibles NaNs por ceros para no romper Fourier
                self.matriz_temp_local = np.nan_to_num(matriz)
                self.lbl_status.configure(
                    text=f"Listo: {os.path.basename(ruta)}", text_color="cyan"
                )
                self.btn_analizar.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar: {e}")

    def ejecutar_analisis(self):
        """Manda a llamar al algoritmo de Fourier con la matriz que tengamos cargada."""
        if self.matriz_temp_local is not None:
            try:
                # Calculamos Fourier usando nuestra función de src.core.fourier
                self.imagen_espectro_cv, self.resultados_energia = procesar_fourier_completo(
                    self.matriz_temp_local
                )
                # Mostramos la imagen a la izquierda y los textos a la derecha
                self._mostrar_espectro_en_label(self.imagen_espectro_cv)
                self._mostrar_resultados_numericos(self.resultados_energia)
                # Habilitamos el botón para exportar a DICOM
                self.btn_exportar_dicom_full.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Error", f"Error en el análisis: {e}")

    def procesar_datos_en_memoria(self, matriz_temp, matriz_mascara):
        """Multiplica la matriz original por la máscara binaria y ejecuta Fourier en automático."""
        try:
            self.matriz_temp_local = matriz_temp * matriz_mascara
            self.ejecutar_analisis()
        except Exception as e:
            messagebox.showerror("Error Automático", f"No se pudo procesar: {e}")

    def _mostrar_resultados_numericos(self, res):
        """Actualiza los números y redacta el informe en el cuadro de texto."""
        if res:
            # Ponemos los porcentajes en las etiquetas de color
            self.lbl_pct_baja.configure(text=f"Bajas Frecuencias: {res['pct_baja']:.2f}%")
            self.lbl_pct_media.configure(text=f"Medias Frecuencias: {res['pct_media']:.2f}%")
            self.lbl_pct_alta.configure(text=f"Altas Frecuencias: {res['pct_alta']:.2f}%")

            # Habilitamos temporalmente el cuadro de texto para escribir en él
            self.txt_interpretacion.configure(state="normal")
            self.txt_interpretacion.delete("1.0", "end")

            energia_total = res.get("energia_total", 0)
            p_alta = res.get("pct_alta", 0)

            # Redactamos el informe según la cantidad de altas frecuencias
            texto_base = "--- INFORME TÉCNICO ---\n"
            texto_base += f"Energía Total: {energia_total:.2e}\n"
            texto_base += "Predominio: "

            if p_alta > 15:
                texto_base += (
                    "ALTAS FRECUENCIAS\n\n"
                    "Interpretación: Se detecta una textura térmica compleja o bordes muy definidos en la segmentación. "
                    "Posible actividad térmica anómala."
                )
            elif p_alta > 5:
                texto_base += (
                    "FRECUENCIAS MEDIAS\n\n"
                    "Interpretación: Distribución térmica equilibrada. Patrón estándar."
                )
            else:
                texto_base += (
                    "BAJAS FRECUENCIAS\n\n"
                    "Interpretación: Patrón térmico suave y homogéneo. Sin variaciones bruscas de temperatura."
                )

            # Añadimos la guía pedagógica para el usuario
            texto_base += "\n" + "-" * 35 + "\n"
            texto_base += "GUÍA DE COMPRENSIÓN PARA EL USUARIO:\n\n"
            texto_base += (
                "• Energía Total: Es la intensidad de la 'información' en la imagen.\n"
                "-Valores altos indican mucha actividad o variaciones térmicas.\n"
                "-Valores bajos indican uniformidad (poca variación).\n\n"
            )
            texto_base += (
                "• Bajas Frecuencias: Representan la forma general y el volumen de calor.\n"
                "• Medias Frecuencias: Representan la estructura y el volumen térmico. Son los gradientes y transiciones suaves.\n"
                "• Altas Frecuencias: Representan los detalles finos, bordes y cambios rápidos de temperatura."
            )

            # Insertamos el texto y volvemos a deshabilitar la edición para que no lo borren sin querer
            self.txt_interpretacion.insert("1.0", texto_base)
            self.txt_interpretacion.configure(state="disabled")

    def _mostrar_espectro_en_label(self, cv2_img):
        """Convierte la imagen de OpenCV a formato compatible con CustomTkinter (CTkImage)."""
        if cv2_img is not None:
            # OpenCV usa BGR por defecto, lo convertimos a RGB para Pillow
            img_rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            # Usamos CTkImage de 500x500 para que se vea nítida en pantallas con escalado
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(500, 500))
            self.lbl_espectro.configure(image=ctk_img, text="")
            self.lbl_espectro.image = ctk_img

    def _abrir_exportador_con_anillos(self):
        """Abre la ventana de exportación DICOM pasándole los datos del paciente y de Fourier."""
        try:
            # Buscamos si la app principal tiene guardados metadatos de la cámara
            metadatos = getattr(self.master_app, "metadatos_flir", {})
            if not metadatos:
                metadatos = getattr(self.master_app, "metadatos_flir_actual", {"Model": "Unknown"})

            # Leemos el nombre del paciente desde la pantalla principal si existe
            nombre = "ANONIMO"
            if hasattr(self.master_app, "entry_nombre"):
                nombre = self.master_app.entry_nombre.get()

            edad = ""
            if hasattr(self.master_app, "entry_edad"):
                edad = self.master_app.entry_edad.get()

            fecha = datetime.now().strftime("%Y-%m-%d")
            if hasattr(self.master_app, "entry_fecha") and self.master_app.entry_fecha.get().strip():
                fecha = self.master_app.entry_fecha.get().strip()

            # Abrimos la ventana de DICOM
            VentanaExportarDicom(
                self,
                self.matriz_temp_local,
                metadatos,
                {"Nombre": nombre, "Edad": edad, "Fecha": fecha},
                self.resultados_energia,
            )
        except Exception as e:
            messagebox.showerror("Error de Exportación", f"Hubo un fallo al preparar el DICOM:\n{e}")
