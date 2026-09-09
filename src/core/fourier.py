"""
=============================================================================
ARCHIVO: src/core/fourier.py
ANÁLISIS DE FRECUENCIAS ESPACIALES (FOURIER 2D)
=============================================================================
¿Qué hacemos en este archivo?
Aquí aplicamos la famosa Transformada Rápida de Fourier en 2 Dimensiones (FFT 2D)
sobre la matriz de temperaturas del paciente.

¿Por qué hacemos esto en medicina térmica?
- En una imagen normal vemos "espacio" (píxel X, píxel Y).
- Con Fourier cambiamos al dominio de las "frecuencias espaciales":
  * Bajas frecuencias (centro): cambios suaves de temperatura (la forma general del cuerpo).
    En una persona sana, casi toda la energía (>95%) está aquí.
  * Medias y Altas frecuencias (hacia afuera): cambios bruscos, bordes o texturas
    térmicas raras (como venas nuevas formándose por un tumor, conocido como neovascularización).
"""

import cv2
import numpy as np
from tkinter import messagebox


def procesar_fourier_completo(datos_para_fft: np.ndarray, r1: int = 15, r2: int = 50):
    """
    Función principal de análisis de Fourier:
    1. Ajusta el tamaño de la matriz para que la computadora calcule la FFT súper rápido.
    2. Calcula la Transformada de Fourier 2D y centra las frecuencias.
    3. Crea una imagen bonita en escala de grises (8 bits) para mostrar en la interfaz.
    4. Mide la energía en 3 "anillos" concéntricos (Bajas, Medias y Altas frecuencias).

    Parámetros:
        datos_para_fft: Matriz 2D de numpy con los números de temperatura del área seleccionada.
        r1: Radio interior en píxeles (límite entre bajas y medias frecuencias). Por defecto 15.
        r2: Radio exterior en píxeles (límite entre medias y altas frecuencias). Por defecto 50.

    Retorna:
        - imagen_espectro_visible: Imagen de 0 a 255 lista para dibujar en la pantalla.
        - dict_resultados_energia: Diccionario con los porcentajes de energía de cada anillo.
    """

    # -----------------------------------------------------------------------
    # PASO 1: Optimizar el tamaño de la matriz (Zero-Padding)
    # -----------------------------------------------------------------------
    # El algoritmo matemático de la FFT funciona a máxima velocidad cuando las
    # filas y columnas son potencias de 2 (o múltiplos de 2, 3 o 5).
    # 'getOptimalDFTSize' nos da ese tamaño ideal y 'copyMakeBorder' rellena con
    # ceros los bordes que sobren para no alterar los datos reales.
    filas, cols = datos_para_fft.shape
    opt_filas = cv2.getOptimalDFTSize(filas)
    opt_cols = cv2.getOptimalDFTSize(cols)
    datos_padded = cv2.copyMakeBorder(
        datos_para_fft, 0, opt_filas - filas, 0, opt_cols - cols, cv2.BORDER_CONSTANT, value=0
    )

    # -----------------------------------------------------------------------
    # PASO 2: Calcular la FFT 2D y centrarla
    # -----------------------------------------------------------------------
    # fft2 convierte la matriz espacial en números complejos (frecuencia + fase)
    f = np.fft.fft2(datos_padded)

    # fftshift mueve el punto de frecuencia cero (la componente DC) al centro exacto
    # de la matriz. Así las frecuencias bajas quedan en medio y las altas hacia afuera.
    fshift = np.fft.fftshift(f)

    # La 'magnitud' (valor absoluto del número complejo) representa la ENERGÍA real
    magnitud = np.abs(fshift)

    # -----------------------------------------------------------------------
    # PASO 3: Crear la imagen visible para el ojo humano (Escala Logarítmica)
    # -----------------------------------------------------------------------
    # En el centro la energía es millones de veces más fuerte que en las orillas.
    # Si mostráramos la magnitud tal cual, veríamos un solo píxel blanco y todo lo demás negro.
    # Por eso aplicamos logaritmo np.log(1 + magnitud): comprime los valores gigantescos
    # para que podamos ver los patrones y texturas en la pantalla.
    magnitud_log_visible = np.log(1 + magnitud)

    # Normalizamos para que los números queden entre 0 y 255 (formato de imagen uint8)
    imagen_espectro_visible = cv2.normalize(
        magnitud_log_visible, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U
    )

    # -----------------------------------------------------------------------
    # PASO 4: Medir la energía por anillos concéntricos
    # -----------------------------------------------------------------------
    # Calculamos las coordenadas del centro de la matriz
    centro_fila, centro_col = opt_filas // 2, opt_cols // 2

    # Creamos una malla de coordenadas y calculamos la distancia de cada píxel al centro
    # usando el teorema de Pitágoras: d = sqrt((x - x0)^2 + (y - y0)^2)
    y, x = np.indices((opt_filas, opt_cols))
    distancia_al_centro = np.sqrt((x - centro_col) ** 2 + (y - centro_fila) ** 2)

    # Sumamos la energía total de toda la imagen
    total_energia = np.sum(magnitud)

    # Si por alguna razón la imagen está vacía (todo ceros), evitamos dividir entre 0
    if total_energia == 0:
        dict_resultados_cero = {
            "pct_baja": 0.0,
            "pct_media": 0.0,
            "pct_alta": 0.0,
            "radios_usados": (r1, r2),
            "interpretacion": "Datos de entrada vacíos.",
            "energia_total": 0.0,
        }
        return imagen_espectro_visible, dict_resultados_cero

    # Creamos tres máscaras booleanas (filtros tipo dona o anillo):
    # 1. Bajas frecuencias: todo lo que esté dentro del círculo interior (distancia <= r1)
    mascara_baja = distancia_al_centro <= r1

    # 2. Medias frecuencias: la zona entre el círculo interior y el exterior (r1 < distancia <= r2)
    mascara_media = (distancia_al_centro > r1) & (distancia_al_centro <= r2)

    # 3. Altas frecuencias: todo lo que quede fuera del círculo exterior (distancia > r2)
    mascara_alta = distancia_al_centro > r2

    # Sumamos la energía de los píxeles que caen dentro de cada anillo
    energia_baja = np.sum(magnitud[mascara_baja])
    energia_media = np.sum(magnitud[mascara_media])
    energia_alta = np.sum(magnitud[mascara_alta])

    # Convertimos a porcentajes respecto a la energía total (la suma dará 100%)
    pct_baja = float((energia_baja / total_energia) * 100)
    pct_media = float((energia_media / total_energia) * 100)
    pct_alta = float((energia_alta / total_energia) * 100)

    # Redactamos el texto de interpretación médica preliminar
    interpretacion_texto = (
        f"Análisis con radios: R1={r1}px, R2={r2}px.\n\n"
        "Un tejido sano tiende a concentrar >95-99% de su energía en Frec. Bajas (patrones suaves).\n\n"
        "Un porcentaje elevado en Frec. Medias y Altas sugiere una textura térmica más compleja. "
        "Esto puede ser un indicador de patrones vasculares anómalos (neovascularización), "
        "lo cual requiere mayor investigación."
    )

    # Guardamos todo en un diccionario fácil de leer
    dict_resultados_energia = {
        "pct_baja": pct_baja,
        "pct_media": pct_media,
        "pct_alta": pct_alta,
        "radios_usados": (r1, r2),
        "interpretacion": interpretacion_texto,
        "energia_total": float(total_energia),
    }

    return imagen_espectro_visible, dict_resultados_energia


def analizar_desde_csvs(ruta_csv_temp: str, ruta_csv_mascara: str):
    """
    Función auxiliar por si el usuario quiere cargar dos archivos CSV directamente
    desde el disco duro: uno con las temperaturas y otro con la máscara de ceros y unos.
    """
    try:
        # Cargamos los números separados por coma
        matriz_temp = np.loadtxt(ruta_csv_temp, delimiter=",")
        matriz_mascara = np.loadtxt(ruta_csv_mascara, delimiter=",")
    except Exception as e:
        messagebox.showerror("Error de Carga", f"Error al cargar los archivos CSV: {e}")
        return None, None

    # Validamos que las dos matrices tengan exactamente el mismo alto y ancho
    if matriz_temp.shape != matriz_mascara.shape:
        messagebox.showerror(
            "Error de Dimensiones",
            f"Las matrices no tienen el mismo tamaño.\n"
            f"Temp: {matriz_temp.shape}, Mascara: {matriz_mascara.shape}",
        )
        return None, None

    # Multiplicación elemento a elemento: los píxeles con máscara 0 se vuelven 0,
    # y los píxeles con máscara 1 conservan su temperatura real
    datos_roi = matriz_temp * matriz_mascara

    # Le pasamos esta matriz resultante a nuestra función de Fourier
    return procesar_fourier_completo(datos_roi)
