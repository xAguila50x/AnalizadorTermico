"""
 =============================================================================
ARCHIVO: src/core/SegmentacionPechoBeta.py
SEGMENTACIÓN BETA DEL Pecho (ROI adaptativa)
 =============================================================================
¿Para qué sirve este archivo?
Aislar automáticamente el área del PECHO en una termografía anterior/oblicua,
sin depender de un umbral de temperatura ni de una banda fija de la imagen,
porque los encuadres de las fotos cambian de paciente en paciente.

Cómo funciona (MODO BETA):
1. Se estima la silueta del cuerpo a partir de la imagen visible (Otsu y/o
   fondo de los bordes), quedándose con el mayor componente conexo.
2. Sobre el bounding box de esa silueta se propone una ELIPSE central con
   proporciones anatómicas (centro y semiejes relativos al cuerpo), que es
   donde habitualmente queda el tórax/busto.
3. La propuesta se muestra en una vista previa donde el usuario puede
   moverla/redimensionarla o redibujarla a mano antes de guardarla.

Además está el MODO MANUAL: una ventana de OpenCV para dibujar el lazo con el
mouse (ENTER confirma, ESC cancela).
"""

import os
import cv2
import numpy as np


# Proporciones anatómicas del tórax respecto al bounding box del cuerpo.
# Calibradas contra la única máscara de referencia del dataset
# (Breast Thermography/Malignant/IIR0019/IIR0019_anterior_mask.png).
_CX_PECHO = 0.537   # centro horizontal del pecho (0 = izquierda del bbox)
_CY_PECHO = 0.532   # centro vertical del pecho (0 = arriba del bbox)
_RX_PECHO = 0.425   # semieje horizontal (fracción del ancho del bbox)
_RY_PECHO = 0.275   # semieje vertical (fracción de la altura del bbox)


def _rellenar_huecos(mascara):
    """Rellena los agujeros internos de una máscara binaria."""
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    salida = np.zeros_like(mascara)
    cv2.drawContours(salida, contornos, -1, 255, cv2.FILLED)
    return salida


def _silueta_cuerpo(gris):
    """
    Estima la silueta del cuerpo (sin fondo) a partir de la imagen en escala
    de grises. Prueba dos estrategias y se queda con la que dé un cuerpo más
    grande pero plausible. Devuelve la máscara (0/255) o None si no hay.
    """
    h, w = gris.shape
    total = float(h * w)
    franja = max(2, int(min(h, w) * 0.04))

    # Estrategia A: umbral de Otsu (separa lo más brillante/cálido del resto)
    _, otsu = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidatas = [(otsu > 0).astype(np.uint8)]

    # Estrategia B: fondo estimado con la mediana de las franjas del borde
    bordes = np.concatenate(
        [
            gris[:franja].ravel(),
            gris[-franja:].ravel(),
            gris[:, :franja].ravel(),
            gris[:, -franja:].ravel(),
        ]
    )
    fondo = float(np.median(bordes))
    candidatas.append((gris > fondo + 5).astype(np.uint8))

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mejor, mejor_area = None, 0.0
    for m in candidatas:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        if n <= 1:
            continue
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        area = float(stats[idx, cv2.CC_STAT_AREA])
        if area / total < 0.15 or area / total > 0.98:
            continue
        comp = (etiquetas == idx).astype(np.uint8) * 255
        comp = _rellenar_huecos(comp)
        if area > mejor_area:
            mejor, mejor_area = comp, area
    return mejor


def proponer_region_pecho(ruta_imagen: str) -> np.ndarray | None:
    """
    Propone (sin interacción) una máscara del área del pecho para la foto dada.

    - Detecta la silueta del cuerpo para conocer su bounding box.
    - Recorta una elipse central con proporciones anatómicas del tórax.
    - Si la silueta no es confiable, usa toda la imagen como referencia.

    Retorna la máscara binaria (0/255) del mismo tamaño que la imagen, o None
    si la imagen no se puede leer.
    """
    gris = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
    if gris is None:
        return None

    h, w = gris.shape
    silueta = _silueta_cuerpo(gris)
    if silueta is None:
        y0, y1, x0, x1 = 0, h - 1, 0, w - 1
    else:
        ys, xs = np.where(silueta > 0)
        if ys.size == 0:
            y0, y1, x0, x1 = 0, h - 1, 0, w - 1
        else:
            y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())

    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    cx = int(round(x0 + _CX_PECHO * bw))
    cy = int(round(y0 + _CY_PECHO * bh))
    rx = max(4, int(round(_RX_PECHO * bw)))
    ry = max(4, int(round(_RY_PECHO * bh)))

    mascara = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(mascara, (cx, cy), (rx, ry), 0, 0, 360, 255, cv2.FILLED)
    return mascara


def guardar_mascara_pecho(ruta_imagen: str, mascara: np.ndarray) -> str | None:
    """Guarda la máscara del pecho junto a la foto original y devuelve la ruta."""
    try:
        directorio, nombre_archivo = os.path.split(ruta_imagen)
        nombre_base, _ = os.path.splitext(nombre_archivo)
        ruta_salida = os.path.join(directorio, f"{nombre_base}_mask_pecho_beta.png")
        if not cv2.imwrite(ruta_salida, mascara):
            return None
        return ruta_salida
    except Exception:
        return None



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

