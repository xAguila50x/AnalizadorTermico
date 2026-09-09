"""
=============================================================================
ARCHIVO: src/core/segmentation.py
SEGMENTACIÓN DE LA REGIÓN DE INTERÉS (ROI)
=============================================================================
¿Para qué sirve este archivo?
En una foto térmica se ve todo: el fondo, la ropa, la cara, etc. Pero a nosotros
solo nos interesa estudiar una parte específica del cuerpo (el área tumoral,
la tiroides, etc.), a la que en visión por computadora llamamos "ROI" (Region Of Interest).

Aquí damos dos opciones para aislar esa zona:
1. MODO MANUAL: Abre una ventana de OpenCV para que el usuario dibuje a mano alzada
   un lazo con el mouse (como en Paint o Photoshop).
2. MODO AUTOMÁTICO: El usuario ingresa una temperatura mínima (umbral), y la computadora
   pinta automáticamente de blanco todo lo que esté caliente y de negro lo que esté frío.
"""

import os
import cv2
import numpy as np
from tkinter import messagebox

from src.core.thermal import analizar_temperaturas

# Variables globales que recuerdan las coordenadas por donde pasa el mouse
_points_lazo = []
_drawing_lazo = False


def _mouse_callback_lazo(event, x, y, flags, param):
    """
    Función 'callback' de OpenCV:
    OpenCV la llama automáticamente cada vez que el mouse hace algo sobre la ventana
    (si se mueve, si haces clic, o si sueltas el botón).
    """
    global _drawing_lazo, _points_lazo
    img_display = param["image_display"]
    img_original_copy = param["image_original_copy"]

    # Restauramos la imagen limpia antes de redibujar
    img_display[:] = img_original_copy[:]

    # CASO 1: El usuario hizo clic izquierdo -> Empezamos a dibujar
    if event == cv2.EVENT_LBUTTONDOWN:
        _drawing_lazo = True
        _points_lazo = [(x, y)]

    # CASO 2: El usuario se está moviendo con el clic apretado -> Guardamos puntos y dibujamos líneas verdes
    elif event == cv2.EVENT_MOUSEMOVE and _drawing_lazo:
        _points_lazo.append((x, y))
        for i in range(len(_points_lazo) - 1):
            # Línea verde de grosor 2 píxeles
            cv2.line(img_display, _points_lazo[i], _points_lazo[i + 1], (0, 255, 0), 2)

    # CASO 3: El usuario soltó el clic -> Terminamos el contorno uniendo el final con el inicio
    elif event == cv2.EVENT_LBUTTONUP:
        _drawing_lazo = False
        if len(_points_lazo) > 2:
            cv2.line(img_display, _points_lazo[-1], _points_lazo[0], (0, 255, 0), 2)


def segmentar_interactivo(ruta_imagen: str, parent=None) -> str | None:
    """
    Abre la ventana interactiva para dibujar la máscara con el mouse:
    - Tecla ENTER: confirma el dibujo y guarda el archivo PNG.
    - Tecla ESC: cancela la operación sin guardar nada.
    """
    global _points_lazo
    _points_lazo = []

    # Importamos aquí la ventana de instrucciones para no crear importaciones circulares
    from src.ui.dialogs import show_instruction_popup

    # Mostramos el mensajito de cómo usar el mouse antes de abrir OpenCV
    if not show_instruction_popup(parent):
        return None

    # Cargamos la imagen con OpenCV
    img_original = cv2.imread(ruta_imagen)
    if img_original is None:
        return None

    # Hacemos copias: una para dibujar encima y otra para tenerla limpia de respaldo
    img_display = img_original.copy()
    img_original_copy = img_original.copy()
    window_name = "Ventana de Dibujo Manual (Presiona ENTER para confirmar, ESC para cancelar)"

    # Creamos la ventana y le conectamos nuestra función que escucha al mouse
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(
        window_name,
        _mouse_callback_lazo,
        {"image_display": img_display, "image_original_copy": img_original_copy},
    )

    # Bucle infinito para refrescar la ventana hasta que presionen ENTER o ESC
    while True:
        cv2.imshow(window_name, img_display)
        key = cv2.waitKey(1) & 0xFF

        # 27 es el código ASCII de la tecla ESC (Escape)
        if key == 27:
            cv2.destroyAllWindows()
            return None

        # 13 es el código ASCII de la tecla ENTER
        if key == 13 and len(_points_lazo) > 2:
            break

    # Cerramos la ventana de dibujo de OpenCV
    cv2.destroyAllWindows()

    # -----------------------------------------------------------------------
    # Crear la máscara binaria (negro = 0, blanco = 255)
    # -----------------------------------------------------------------------
    # Creamos un lienzo completamente negro del mismo tamaño que la foto
    mask = np.zeros(img_original.shape[:2], dtype=np.uint8)

    # Convertimos los puntos que dibujó el usuario en un polígono relleno de blanco
    contour = np.array(_points_lazo, dtype=np.int32)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

    # Guardamos la máscara en disco con el nombre de la foto original + '_mask.png'
    directorio, nombre_archivo = os.path.split(ruta_imagen)
    nombre_base, _ = os.path.splitext(nombre_archivo)
    ruta_mascara_salida = os.path.join(directorio, f"{nombre_base}_mask.png")
    cv2.imwrite(ruta_mascara_salida, mask)

    return ruta_mascara_salida


def generar_mascara_por_umbral(
    ruta_imagen_original: str, umbral: float, user_info_temp: dict = None
) -> str | None:
    """
    Crea una máscara automáticamente usando un umbral térmico:
    Ejemplo: Si el umbral es 36.0 °C, todos los píxeles con 36°C o más
    se pintan de blanco (255), y los que estén por debajo se quedan negros (0).
    """
    try:
        # Datos temporales por si no se han rellenado en la interfaz
        if user_info_temp is None:
            user_info_temp = {"Nombre": "", "Edad": "", "Fecha": "", "Hora": ""}

        # Obtenemos la matriz de temperaturas en grados Celsius reales
        resultados, _, temp_matrix, _ = analizar_temperaturas(
            ruta_imagen_original, ruta_imagen_original, user_info=user_info_temp
        )

        if temp_matrix is None:
            messagebox.showerror(
                "Error de Análisis",
                f"No se pudo extraer la matriz de temperatura. Error: {resultados.get('error')}",
            )
            return None

        # np.where es como un 'if' condicional gigante sobre toda la matriz:
        # Si temp >= umbral -> píntalo blanco (255), sino -> negro (0)
        mascara_automatica = np.where(temp_matrix >= umbral, 255, 0).astype(np.uint8)

        # Guardamos la máscara en la misma carpeta que la foto
        directorio, nombre_archivo = os.path.split(ruta_imagen_original)
        nombre_base, _ = os.path.splitext(nombre_archivo)
        ruta_mascara_salida = os.path.join(directorio, f"{nombre_base}_mask_auto_{umbral}C.png")
        cv2.imwrite(ruta_mascara_salida, mascara_automatica)

        return ruta_mascara_salida

    except Exception as e:
        messagebox.showerror("Error de Segmentación", f"Ocurrió un error al generar la máscara: {e}")
        return None
