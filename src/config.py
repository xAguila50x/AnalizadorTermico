"""
=============================================================================
ARCHIVO: src/config.py
CONFIGURACIONES GENERALES Y RUTAS DEL PROYECTO
=============================================================================
Aquí guardamos todas las variables "fijas" (constantes) que necesita la app,
como los colores de la ventana, el tamaño de las imágenes, y un par de funciones
súper útiles para encontrar archivos como 'exiftool.exe' y el ícono de la app
sin que nos dé error si cambiamos de carpeta en la terminal.
"""

import os
import sys
from pathlib import Path
import customtkinter as ctk

# ---------------------------------------------------------------------------
# 1. Rutas importantes
# ---------------------------------------------------------------------------
# BASE_DIR es la carpeta raíz donde está guardado todo nuestro proyecto.
# __file__ es este archivo (config.py), con .parent subimos a 'src'
# y con el segundo .parent subimos a la carpeta principal 'Aplicacion Termica'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 2. Configuración de la interfaz visual (CustomTkinter)
# ---------------------------------------------------------------------------
# Ponemos el modo oscuro ("Dark") para que no canse la vista y tema azul
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Altura estándar en píxeles para mostrar las fotos térmicas en pantalla
ALTURA_IMAGEN_VISUALIZACION = 300


# ---------------------------------------------------------------------------
# 3. Funciones para buscar archivos externos
# ---------------------------------------------------------------------------
def get_exiftool_path() -> str:
    """
    ¿Para qué sirve esta función?
    'exiftool.exe' es un programa pequeñito pero potente que lee los datos
    ocultos dentro de las fotos de cámaras FLIR (temperaturas en crudo, modelo, etc.).

    Esta función busca dónde está ese ejecutable para que no nos salga el error
    típico de 'archivo no encontrado':
    - Primero revisa si el programa fue empaquetado como un .exe con PyInstaller.
    - Si no, lo busca en la carpeta raíz del proyecto.
    - Si tampoco, busca en carpetas comunes como 'bin' o 'assets/bin'.
    - Si aún no, busca en la carpeta donde estés parado en la terminal.
    - Y si no lo halla, lo busca en el PATH global de Windows.
    """
    # Si algún día empaquetamos el proyecto con PyInstaller, los archivos van a _MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_path = os.path.join(sys._MEIPASS, "exiftool.exe")
        if os.path.exists(bundle_path):
            return bundle_path

    # Buscamos en la carpeta principal del proyecto
    path_in_base = BASE_DIR / "exiftool.exe"
    if path_in_base.exists():
        return str(path_in_base)

    # Por si acaso alguien lo mueve a una subcarpeta de herramientas
    for sub in ["bin", "assets/bin", "tools"]:
        candidate = BASE_DIR / sub / "exiftool.exe"
        if candidate.exists():
            return str(candidate)

    # Si estamos en la misma carpeta desde la terminal
    if os.path.exists("exiftool.exe"):
        return os.path.abspath("exiftool.exe")

    # Como último recurso, confiamos en que esté instalado en Windows
    return "exiftool.exe"


def get_icon_path() -> str | None:
    """
    Busca la imagen del ícono 'icono1.ico' para colocarla en la barra de
    título de nuestras ventanas. Si no la encuentra, regresa None y la app
    sigue funcionando sin problema (usa el ícono por defecto).
    """
    # Si estamos en un ejecutable compilado
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_icon = os.path.join(sys._MEIPASS, "icono1.ico")
        if os.path.exists(bundle_icon):
            return bundle_icon

    # En la carpeta principal
    icon_in_base = BASE_DIR / "icono1.ico"
    if icon_in_base.exists():
        return str(icon_in_base)

    # En carpetas de recursos
    for sub in ["assets", "assets/icons"]:
        candidate = BASE_DIR / sub / "icono1.ico"
        if candidate.exists():
            return str(candidate)

    return None
