# Asistente de Análisis de Imágenes Térmicas (Herramienta Térmica)

Aplicación médica y científica de escritorio desarrollada en Python para el procesamiento, segmentación, análisis espectral de Fourier 2D y exportación estandarizada a formato DICOM (.dcm) de imágenes térmicas radiométricas (FLIR).

---

## Estructura del Proyecto

El código está organizado siguiendo las mejores prácticas de arquitectura por capas (separación de responsabilidades entre lógica de cálculo, presentación y configuración):

```text
Aplicacion Termica/
│
├── main.py                     # Punto de entrada estándar de la aplicación
├── requirements.txt            # Dependencias del proyecto
├── .gitignore                  # Reglas de exclusión de Git
├── README.md                   # Documentación técnica
│
├── exiftool.exe                # Ejecutable de ExifTool para extracción de metadatos térmicos
├── exiftool_files/             # Archivos auxiliares de ExifTool
├── icono1.ico                  # Ícono de la aplicación
│
└── src/                        # Código fuente modular
    ├── __init__.py
    ├── config.py               # Configuración global, temas visuales y resolución de rutas
    │
    ├── core/                   # Núcleo de cálculo científico y radiométrico
    │   ├── __init__.py
    │   ├── thermal.py          # Extracción ExifTool, calibración FLIR (E6/A3) e histogramas
    │   ├── fourier.py          # Transformada de Fourier 2D y análisis de energía por anillos
    │   ├── segmentation.py     # Lazo interactivo OpenCV y segmentación por umbral
    │   └── dicom.py            # Ensamblado, calibración int16 y exportación DICOM
    │
    └── ui/                     # Capa gráfica (CustomTkinter)
        ├── __init__.py
        ├── main_window.py      # Ventana principal (App) y flujo de trabajo
        ├── spectrum_window.py  # Ventana de Análisis de Espectro (VentanaEspectro)
        ├── dicom_window.py     # Ventana de Exportación DICOM (VentanaExportarDicom)
        └── dialogs.py          # Diálogos emergentes e instrucciones de dibujo
```

---

## Requisitos de Instalación

Instala las dependencias requeridas mediante `pip`:

```bash
pip install -r requirements.txt
```

### Librerías Principales:
- `customtkinter`: Interfaz moderna con soporte para modo oscuro.
- `opencv-python`: Procesamiento de imágenes y dibujo de contornos interactivo.
- `Pillow`: Manejo y redimensionado de imágenes.
- `matplotlib`: Generación y renderizado de histogramas térmicos.
- `numpy`: Cálculo matricial y operaciones sobre tensores de temperatura.
- `pydicom`: Creación de archivos médicos bajo el estándar DICOM.

---

## Ejecución

Puedes iniciar la aplicación usando cualquiera de los dos comandos:

```bash
python main.py
```
---

## Funcionalidades Principales

1. **Carga y Extracción Radiométrica:**
   - Lectura directa de imágenes térmicas FLIR (.jpg).
   - Extracción de datos brutos (`-RawThermalImage`) vía ExifTool.
   - Calibración automática según el modelo de cámara (Lineal para FLIR E6, ecuaciones de Planck para FLIR A3).
2. **Segmentación de Región de Interés (ROI):**
   - Segmentación automática basada en umbral térmico (°C).
   - Segmentación manual interactiva con lazo continuo (OpenCV).
   - Carga de máscaras binarias existentes (.png).
3. **Análisis Estadístico:**
   - Cálculo de temperaturas mínimas, máximas y promedio del área aislada.
   - Generación de histograma de frecuencias térmicas con porcentajes por intervalo.
   - Descarga de matrices crudas y segmentadas en formato CSV.
4. **Análisis de Espectro de Fourier 2D:**
   - DFT 2D con zero-padding óptimo.
   - Visualización del espectro de magnitud en escala logarítmica.
   - Descomposición energética por anillos concéntricos: bajas (forma/volumen térmico general), medias (gradientes) y altas frecuencias (texturas complejas/patrones vasculares anómalos).
5. **Exportación Médica DICOM (.dcm):**
   - Codificación con factor de escala `0.01` en enteros de 16 bits para lectura directa de grados Celsius en visores médicos (Horos, RadiAnt, Weasis, etc.).
   - Inyección de metadatos radiométricos (emisividad, distancia, temperaturas reflejadas) y resultados del análisis por anillos.
