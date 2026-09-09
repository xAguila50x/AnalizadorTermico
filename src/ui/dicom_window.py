"""
=============================================================================
ARCHIVO: src/ui/dicom_window.py
VENTANA DE FORMULARIO Y EXPORTACIÓN DICOM (.dcm)
=============================================================================
¿Qué hace esta ventana?
Es un formulario con campos de texto donde el médico o el usuario puede
revisar y rellenar los datos clínicos del paciente (Nombre, ID, Edad, Sexo,
Peso, etc.) antes de guardar el archivo final en el formato estándar médico DICOM.
"""

from datetime import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox

from src.config import get_icon_path
from src.core.dicom import generar_archivo_dicom


class VentanaExportarDicom(ctk.CTkToplevel):
    """
    Ventana flotante (CTkToplevel) con un formulario con barra de desplazamiento
    para ingresar los datos del estándar DICOM.
    """

    def __init__(
        self,
        master,
        matriz_temp,
        metadatos_originales,
        info_paciente,
        resultados_anillos=None,
    ):
        super().__init__(master)

        # Guardamos las matrices y datos que nos mandó la ventana anterior
        self.matriz_temp = matriz_temp
        self.metadatos_flir = metadatos_originales
        self.resultados_anillos = resultados_anillos

        # Configuración básica de la ventana
        self.title("Finalizar Exportación DICOM")
        self.geometry("600x850")
        self.grab_set()  # Mantiene el foco en esta ventana mientras esté abierta

        # Le ponemos el ícono a la barra de título si existe
        icon_path = get_icon_path()
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # -------------------------------------------------------------------
        # Contenedor con barra de desplazamiento (Scroll)
        # -------------------------------------------------------------------
        # Como son muchos campos (nombre, peso, altura, clínica, etc.), usamos un
        # CTkScrollableFrame para que el usuario pueda bajar y subir cómodamente.
        scroll = ctk.CTkScrollableFrame(self, width=550, height=650)
        scroll.pack(pady=10, fill="both", expand=True)

        # Diccionario donde guardaremos cada cajita de texto (Entry) para leerla luego
        self.entries = {}
        ahora = datetime.now()

        # Si ya escribieron el nombre en la pantalla anterior, lo usamos por defecto
        nombre_paciente = info_paciente.get("Nombre", "").strip() or "ANONIMO"

        # -------------------------------------------------------------------
        # Lista de campos estándar requeridos por DICOM:
        # Formato: "NombreDelTag": (ValorPorDefecto, "TextoDeGuía")
        # -------------------------------------------------------------------
        self.campos_config = {
            "PatientName": (nombre_paciente, "Nombre"),
            "PatientID": ("ID-12345", "ID"),
            "PatientBirthDate": ("19900101", "AAAAMMDD"),
            "PatientAge": (str(info_paciente.get("Edad", "")), "Auto"),
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
            "InstitutionName": ("LABORATORIO TÉRMICO", "Clínica"),
        }

        # Generamos dinámicamente cada etiqueta y campo de texto con un bucle 'for'
        for i, (tag, (valor, _placeholder)) in enumerate(self.campos_config.items()):
            # Etiqueta a la izquierda
            ctk.CTkLabel(scroll, text=f"{tag}:").grid(
                row=i, column=0, padx=10, pady=5, sticky="w"
            )

            # Caja de texto a la derecha
            entry = ctk.CTkEntry(scroll, width=300)
            entry.insert(0, valor)  # Le ponemos el texto inicial
            entry.grid(row=i, column=1, padx=10, pady=5)

            # Guardamos la referencia para poder leer lo que el usuario editó
            self.entries[tag] = entry

        # Botón verde grande para guardar el archivo
        ctk.CTkButton(
            self,
            text="GENERAR ARCHIVO .DCM",
            command=self.guardar_dicom,
            fg_color="green",
            height=45,
        ).pack(pady=20)

    def guardar_dicom(self):
        """
        Se ejecuta al presionar el botón verde:
        1. Pregunta al usuario dónde quiere guardar el archivo con una ventana de Windows.
        2. Recolecta todos los textos del formulario.
        3. Llama a 'generar_archivo_dicom()' para que arme el archivo binario.
        4. Cierra esta ventana emergente.
        """
        # Abre el diálogo de 'Guardar como...' de Windows
        ruta = filedialog.asksaveasfilename(
            defaultextension=".dcm",
            filetypes=[("Archivo DICOM", "*.dcm"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return  # El usuario canceló la ventana de guardado

        try:
            # Leemos el texto de cada una de las cajitas de entrada
            campos_paciente = {tag: entry.get().strip() for tag, entry in self.entries.items()}

            # Mandamos a crear el archivo real
            generar_archivo_dicom(
                ruta_salida=ruta,
                matriz_temp=self.matriz_temp,
                metadatos_flir=self.metadatos_flir,
                campos_paciente=campos_paciente,
                resultados_anillos=self.resultados_anillos,
            )

            # Si todo salió bien, mostramos un mensaje de felicitación y cerramos
            messagebox.showinfo("Éxito", "Dicom exportado exitosamente!")
            self.destroy()

        except Exception as e:
            # Si algo falla (por ejemplo disco lleno o permisos denegados), avisamos con un error
            messagebox.showerror("Error", f"Error en exportación: {str(e)}")
