"""
=============================================================================
ARCHIVO: src/core/thermal.py
EXTRACCIÓN DE TEMPERATURAS Y CALIBRACIÓN RADIOMÉTRICA
=============================================================================
¿Qué hace este archivo?
Las fotos que toman las cámaras térmicas FLIR son especiales: por fuera parecen
fotos normales (.jpg), pero por dentro guardan los datos invisibles de radiación
infrarroja que captó el sensor.

En este archivo hacemos la "física térmica":
1. Usamos ExifTool para sacarle las entrañas a la foto (la matriz de calor cruda).
2. Averiguamos qué modelo de cámara tomó la foto (FLIR E6 o FLIR A3).
3. Aplicamos la fórmula matemática de calibración correspondiente para convertir
   esos números raros en grados Celsius reales (°C).
4. Recortamos el área que seleccionó el usuario (con la máscara).
5. Dibujamos un histograma con Matplotlib para ver cuántos píxeles hay en cada rango de temperatura.
"""

import io
import json
import os
import subprocess
import sys
import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from src.config import get_exiftool_path

# Esta bandera sirve para que en Windows no se abra una molesta ventanita negra
# de CMD cada vez que mandamos llamar a ExifTool en segundo plano.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def analizar_temperaturas(
    ruta_imagen_original: str,
    ruta_mascara: str,
    user_info: dict,
    exiftool_path: str = None,
):
    """
    Función que realiza todo el proceso de calibración y análisis térmico:

    Parámetros:
        ruta_imagen_original: La ruta donde está la foto FLIR (.jpg).
        ruta_mascara: La ruta donde está la máscara dibujada o generada (.png).
        user_info: Diccionario con los datos del paciente (Nombre, Edad, Fecha, Hora).
        exiftool_path: (Opcional) La ruta a 'exiftool.exe'. Si no se pasa, la busca solo.

    Retorna:
        - resultados: Diccionario con min_temp, max_temp, avg_temp y posibles errores.
        - fig: La gráfica del histograma lista para incrustar en la ventana.
        - temperaturas_celsius_original: Matriz 2D completa con las temperaturas de toda la foto.
        - matriz_segmentada_binaria: Matriz 2D de 0s y 1s de la máscara.
    """
    try:
        # Si no nos pasaron la ruta de ExifTool, la buscamos con nuestra función de config.py
        if exiftool_path is None:
            exiftool_path = get_exiftool_path()

        # Probamos que ExifTool responda bien preguntándole su versión (-ver)
        subprocess.run(
            [exiftool_path, "-ver"],
            capture_output=True,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )

        # -------------------------------------------------------------------
        # PASO 1: Leer los metadatos de la foto en formato JSON
        # -------------------------------------------------------------------
        # Le pedimos a ExifTool los datos de la cámara (modelo, constantes de Planck, etc.)
        comando_metadata = [exiftool_path, "-json", ruta_imagen_original]
        resultado_metadata = subprocess.run(
            comando_metadata,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=CREATE_NO_WINDOW,
        )
        metadata = json.loads(resultado_metadata.stdout)[0]

        # -------------------------------------------------------------------
        # PASO 2: Extraer la matriz térmica cruda (-RawThermalImage)
        # -------------------------------------------------------------------
        # El parámetro '-b' le dice a ExifTool que devuelva los bytes crudos (binario)
        comando_imagen = [exiftool_path, "-b", "-RawThermalImage", ruta_imagen_original]
        resultado_imagen = subprocess.run(
            comando_imagen,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        if not resultado_imagen.stdout:
            return {"error": "No se pudo extraer la imagen térmica cruda."}, None, None, None

        # Convertimos esos bytes en una imagen en memoria usando Pillow y luego en matriz numpy
        raw_image_data = io.BytesIO(resultado_imagen.stdout)
        raw_image = Image.open(raw_image_data)
        matriz_temperaturas_raw = np.array(raw_image)

        # -------------------------------------------------------------------
        # PASO 3: Calibración matemática a grados Celsius (°C)
        # -------------------------------------------------------------------
        # Dependiendo del modelo de cámara, el fabricante usa una fórmula diferente:
        model_name = metadata.get("CameraModel", "Desconocido")
        temperaturas_celsius_original = None

        if "E6" in model_name:
            # CASO A: Modelo FLIR E6 (Calibración Lineal)
            # La relación entre el valor del sensor y la temperatura en Kelvin es una recta:
            # y = m * x + c (donde m es la pendiente y c es el cruce con el eje Y).
            temp_min_k = metadata.get("ImageTemperatureMin")
            temp_max_k = metadata.get("ImageTemperatureMax")
            raw_min = metadata.get("RawValueRangeMin")
            raw_max = metadata.get("RawValueRangeMax")

            if any(v is None for v in [temp_min_k, temp_max_k, raw_min, raw_max]):
                return {"error": "Metadatos de calibración lineal no encontrados."}, None, None, None

            if raw_max == raw_min:
                temp_kelvin = np.full(matriz_temperaturas_raw.shape, temp_min_k, dtype=np.float32)
            else:
                m = (temp_max_k - temp_min_k) / (raw_max - raw_min)
                c = temp_min_k - m * raw_min
                temp_kelvin = m * matriz_temperaturas_raw.astype(np.float32) + c

            # De Kelvin a Celsius: restamos 273.15
            temperaturas_celsius_original = temp_kelvin - 273.15

        elif "A3" in model_name:
            # CASO B: Modelo FLIR A3 (Ecuación física de Planck)
            # Es un modelo científico más avanzado. Usa la Ley de Radiación de Planck
            # con 5 constantes de calibración de fábrica (R1, B, F, O, R2).
            # Fórmula: T = B / ln( (R1 / (R2 * (RAW + O))) + F )
            R1 = metadata.get("PlanckR1")
            B = metadata.get("PlanckB")
            F = metadata.get("PlanckF")
            O = metadata.get("PlanckO")
            R2 = metadata.get("PlanckR2")

            if any(v is None for v in [R1, B, F, O, R2]):
                return {"error": "Metadatos de Planck incompletos."}, None, None, None

            raw_data_float = matriz_temperaturas_raw.astype(np.float32)
            term1 = R1 / (R2 * (raw_data_float + O))
            termino_log = term1 + F

            # Cuidado: el logaritmo de números negativos o cero no existe en matemáticas reales
            if np.min(termino_log) <= 0:
                return {"error": "Error matemático: logaritmo de número no positivo."}, None, None, None

            temp_kelvin = B / np.log(termino_log)
            temperaturas_celsius_original = temp_kelvin - 273.15

        else:
            return {"error": f"Modelo de cámara no reconocido: '{model_name}'."}, None, None, None

        # -------------------------------------------------------------------
        # PASO 4: Aplicar la máscara para aislar el área de interés (ROI)
        # -------------------------------------------------------------------
        # Leemos la máscara en blanco y negro (escala de grises)
        mascara_img = cv2.imread(ruta_mascara, cv2.IMREAD_GRAYSCALE)
        if mascara_img is None:
            return {"error": "No se pudo cargar la máscara."}, None, None, None

        # Nos aseguramos de que la máscara mida exactamente lo mismo que la matriz térmica
        h_temp, w_temp = temperaturas_celsius_original.shape
        mascara_img = cv2.resize(mascara_img, (w_temp, h_temp), interpolation=cv2.INTER_NEAREST)

        # Filtramos: tomamos solo los píxeles donde la máscara es blanca (> 128)
        temperaturas_segmentadas_array = temperaturas_celsius_original[mascara_img > 128]
        if temperaturas_segmentadas_array.size == 0:
            return {"error": "El área de la máscara está vacía."}, None, None, None

        # Matriz binaria de 1s (área elegida) y 0s (fondo ignorado)
        matriz_segmentada_binaria = np.where(mascara_img > 128, 1, 0)

        # -------------------------------------------------------------------
        # PASO 5: Estadísticas básicas de temperatura
        # -------------------------------------------------------------------
        # Usamos nanmin, nanmax y nanmean para evitar errores si hay píxeles nulos (NaN)
        resultados = {
            "min_temp": f"{np.nanmin(temperaturas_segmentadas_array):.2f}°C",
            "max_temp": f"{np.nanmax(temperaturas_segmentadas_array):.2f}°C",
            "avg_temp": f"{np.nanmean(temperaturas_segmentadas_array):.2f}°C",
            "_metadata_raw": metadata,
        }

        # -------------------------------------------------------------------
        # PASO 6: Generar la gráfica del Histograma con Matplotlib
        # -------------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")
        total_pixeles_segmentados = temperaturas_segmentadas_array.size

        # Filtramos datos que sean números válidos
        datos_validos = temperaturas_segmentadas_array[~np.isnan(temperaturas_segmentadas_array)]

        # Creamos el histograma dividiendo el rango en 25 barras ("bins")
        counts, bins, patches = ax.hist(
            datos_validos,
            bins=25,
            color="deepskyblue",
            edgecolor="black",
            alpha=0.9,
        )

        # Personalizamos los títulos y ejes
        ax.set_xlabel("Temperatura (°C)", fontsize=12)
        ax.set_ylabel("Frecuencia (píxeles)", fontsize=12)
        ax.set_title("Distribución de Temperatura", fontsize=16, pad=20)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.tick_params(axis="x", colors="black", labelsize=8, rotation=45)
        ax.tick_params(axis="y", colors="black", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Escribimos los datos del paciente en la parte superior de la gráfica
        info_text = (
            f"Nombre: {user_info.get('Nombre', 'N/A')}   |   "
            f"Edad: {user_info.get('Edad', 'N/A')}   |   "
            f"Fecha: {user_info.get('Fecha', 'N/A')}   |   "
            f"Hora: {user_info.get('Hora', 'N/A')}"
        )
        fig.suptitle(info_text, fontsize=10)

        # Ponemos una etiqueta de texto sobre cada barrita del histograma con
        # el número de píxeles y el porcentaje que representa
        y_max = ax.get_ylim()[1]
        offset = y_max * 0.01

        for i in range(len(counts)):
            count = counts[i]
            if count > 0:
                porcentaje = (count / total_pixeles_segmentados) * 100
                x_pos = patches[i].get_x() + patches[i].get_width() / 2
                y_pos = count
                temp_inicio = bins[i]
                etiqueta = f"{int(count)}px ({porcentaje:.1f}%) @ {temp_inicio:.1f}°C"
                ax.text(
                    x_pos,
                    y_pos + offset,
                    etiqueta,
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="black",
                    rotation=90,
                )

        fig.tight_layout()

        # Devolvemos todo listo para que la pantalla principal lo muestre
        return resultados, fig, temperaturas_celsius_original, matriz_segmentada_binaria

    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"error": "ExifTool no encontrado."}, None, None, None
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Error inesperado: {str(e)}"}, None, None, None
