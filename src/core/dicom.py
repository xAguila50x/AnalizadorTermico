"""
=============================================================================
ARCHIVO: src/core/dicom.py
CREACIÓN Y EXPORTACIÓN DE ARCHIVOS MÉDICOS DICOM (.dcm)
=============================================================================
¿Qué es DICOM?
DICOM (Digital Imaging and Communication in Medicine) es el formato estándar
que usan todos los hospitales, clínicas y visores médicos del mundo (como RadiAnt,
Horos o Weasis) para guardar estudios como tomografías, rayos X y termografías.

¿Cuál es el truco genial que hacemos aquí?
Los archivos DICOM normalmente guardan números enteros (sin decimales), pero la
temperatura humana tiene decimales importantes (ejemplo: 36.54 °C).
Para no perder esa precisión:
1. Multiplicamos la temperatura por 100: 36.54 se convierte en 3654 (entero de 16 bits).
2. Le configuramos a DICOM la etiqueta 'RescaleSlope' en 0.01.
Así, cuando el médico abre el archivo en su programa del hospital, el software
automáticamente hace 3654 * 0.01 = 36.54 °C. ¡Magia pura!
"""

from datetime import datetime
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

# Identificador estándar de DICOM para "Captura Secundaria de Imagen" (Secondary Capture)
SOP_CLASS_SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"


def generar_archivo_dicom(
    ruta_salida: str,
    matriz_temp: np.ndarray,
    metadatos_flir: dict | None,
    campos_paciente: dict[str, str],
    resultados_anillos: dict | None = None,
) -> None:
    """
    Construye desde cero un archivo .dcm con los datos térmicos del paciente.

    Parámetros:
        ruta_salida: Dónde guardar el archivo final (ejemplo: 'C:/estudios/paciente1.dcm').
        matriz_temp: La matriz 2D con los números de temperatura en grados Celsius.
        metadatos_flir: Diccionario con los datos que tenía la cámara FLIR (emisividad, distancia, etc.).
        campos_paciente: Diccionario con lo que escribió el usuario en el formulario (Nombre, ID, etc.).
        resultados_anillos: (Opcional) Los porcentajes de Fourier calculados previamente.
    """
    # -----------------------------------------------------------------------
    # PASO 1: Calcular valores clave y escalar la temperatura
    # -----------------------------------------------------------------------
    t_max = np.nanmax(matriz_temp)
    t_min = np.nanmin(matriz_temp)
    t_media = np.nanmean(matriz_temp)

    # Multiplicamos por 100 y convertimos a enteros con signo de 16 bits (int16)
    img_celsius_scaled = (matriz_temp * 100).astype(np.int16)

    # -----------------------------------------------------------------------
    # PASO 2: Crear la estructura básica del archivo DICOM (FileDataset)
    # -----------------------------------------------------------------------
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = SOP_CLASS_SECONDARY_CAPTURE
    # generate_uid() crea un código único mundial para este archivo específico
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    # Creamos el dataset con el encabezado estándar de 128 bytes en ceros
    ds = FileDataset(ruta_salida, {}, file_meta=file_meta, preamble=b"\0" * 128)

    # -----------------------------------------------------------------------
    # PASO 3: Configurar la imagen (tamaño, tipo de píxel y escala)
    # -----------------------------------------------------------------------
    ds.Rows, ds.Columns = img_celsius_scaled.shape
    ds.SamplesPerPixel = 1  # 1 canal (escala de grises)
    ds.PhotometricInterpretation = "MONOCHROME2"  # 0 es negro, valores altos son blanco
    ds.BitsAllocated = 16  # 16 bits por píxel
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1  # 1 significa entero con signo (permite números negativos si hiciera falta)
    ds.PixelData = img_celsius_scaled.tobytes()

    # Aquí le decimos al visor médico cómo recuperar los decimales:
    # Valor_Real = (Píxel_Almacenado * RescaleSlope) + RescaleIntercept
    ds.RescaleSlope = "0.01"
    ds.RescaleIntercept = "0.0"

    # Configuramos la ventana de contraste (Window Center y Window Width)
    # para que al abrir el archivo se vea con buen contraste de inmediato
    ds.WindowCenter = f"{t_media:.2f}"
    ds.WindowWidth = f"{(t_max - t_min):.2f}"

    # -----------------------------------------------------------------------
    # PASO 4: Guardar metadatos térmicos de la cámara FLIR
    # -----------------------------------------------------------------------
    info_ia = {
        "TEMP_MAX": f"{t_max:.2f} C",
        "TEMP_MIN": f"{t_min:.2f} C",
        "TEMP_AVERAGE": f"{t_media:.2f} C",
        "UNITS": "Celsius",
    }

    if metadatos_flir:
        # Mapeamos los nombres técnicos de FLIR a etiquetas legibles
        mapeo_flir = {
            "Emissivity": "EMISSIVITY",
            "ObjectDistance": "DISTANCE",
            "ReflectedApparentTemperature": "REFLECTED_TEMP",
            "AtmosphericTemperature": "ATM_TEMP",
            "RelativeHumidity": "HUMIDITY",
            "PlanckR1": "PLANCK_R1",
            "PlanckB": "PLANCK_B",
            "PlanckF": "PLANCK_F",
            "PlanckO": "PLANCK_O",
            "PlanckR2": "PLANCK_R2",
        }
        for original, nuevo in mapeo_flir.items():
            val = metadatos_flir.get(original, "N/A")
            info_ia[nuevo] = val

    # Guardamos todo esto en la descripción del dispositivo
    processing_desc = " | ".join([f"{k}={v}" for k, v in info_ia.items()])
    ds.AcquisitionDeviceProcessingDescription = processing_desc[:1024]

    # -----------------------------------------------------------------------
    # PASO 5: Guardar los porcentajes de Fourier en los comentarios
    # -----------------------------------------------------------------------
    if resultados_anillos:
        r = resultados_anillos
        ds.ImageComments = (
            f"Analisis: BAJA:{r.get('pct_baja', 0):.4f}|"
            f"MEDIA:{r.get('pct_media', 0):.4f}|"
            f"ALTA:{r.get('pct_alta', 0):.4f}"
        )

    # -----------------------------------------------------------------------
    # PASO 6: Llenar los datos del paciente (Nombre, Edad, ID, Fecha)
    # -----------------------------------------------------------------------
    for tag, val in campos_paciente.items():
        val = str(val).strip()
        if val:
            # En DICOM las fechas no llevan guiones ni dos puntos (formato YYYYMMDD)
            if "Date" in tag:
                val = val.replace(":", "").replace("-", "")
            setattr(ds, tag, val)

    # Modalidad médica: "TG" significa Thermography (Termografía)
    ds.Modality = "TG"
    ds.ContentDate = datetime.now().strftime("%Y%m%d")
    ds.SOPClassUID = SOP_CLASS_SECONDARY_CAPTURE
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()

    # Guardamos físicamente el archivo en el disco duro
    ds.save_as(ruta_salida)
