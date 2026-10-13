"""
=============================================================================
ARCHIVO: src/ui/dialogs.py
VENTANAS EMERGENTES Y CUADROS DE DIÁLOGO (POPUPS)
=============================================================================
¿Qué hay aquí?
Aquí programamos las pequeñas ventanitas secundarias (diálogos modales)
que le piden información o le dan instrucciones al usuario antes de hacer
algo importante (como dibujar el lazo o elegir cómo segmentar).
"""

import tkinter as tk

import cv2
import numpy as np
from PIL import Image
import customtkinter as ctk

from src.config import get_icon_path


def show_instruction_popup(parent=None) -> bool:
    """
    Muestra la ventanita con los 3 pasos para dibujar con el mouse:
    1. Arrastrar el mouse.
    2. Presionar ENTER al terminar.
    3. Presionar ESC si te equivocaste y quieres cancelar.

    Retorna True si el usuario hace clic en 'Entendido, Continuar',
    o False si hace clic en 'Cancelar'.
    """
    # Si no nos pasaron la ventana padre, tomamos la raíz principal de Tkinter
    if parent is None:
        parent = tk._default_root

    # CTkToplevel es una ventana secundaria flotante
    popup = ctk.CTkToplevel(parent)
    popup.title("Instrucciones de Dibujo")

    if parent:
        popup.transient(parent)  # La anclamos a la ventana principal

    # grab_set() hace que sea "modal": bloquea el resto de la app hasta responder
    popup.grab_set()
    popup.attributes("-topmost", True)  # Se queda siempre al frente de la pantalla

    # Le ponemos el ícono si existe
    icon_path = get_icon_path()
    if icon_path:
        try:
            popup.iconbitmap(icon_path)
        except Exception:
            pass

    # Centramos la ventanita en medio de la pantalla respecto a su ventana padre
    if parent and hasattr(parent, "winfo_x"):
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 100
        popup.geometry(f"400x200+{x}+{y}")
    else:
        popup.geometry("400x200")

    popup.resizable(False, False)

    # Textos de instrucciones
    ctk.CTkLabel(
        popup,
        text="Instrucciones para la Segmentación Manual:",
        font=ctk.CTkFont(size=16, weight="bold"),
    ).pack(pady=10)
    ctk.CTkLabel(
        popup, text="1. Haz clic y arrastra el mouse para dibujar el contorno.", justify="left"
    ).pack(anchor="w", padx=20)
    ctk.CTkLabel(
        popup,
        text="2. Al terminar, presiona la tecla ENTER para confirmar.",
        justify="left",
    ).pack(anchor="w", padx=20)
    ctk.CTkLabel(
        popup, text="3. Para cancelar, presiona la tecla ESC.", justify="left"
    ).pack(anchor="w", padx=20)

    # Variable booleana de Tkinter para saber qué botón apretó el usuario
    response = tk.BooleanVar(value=False)

    def on_confirm():
        response.set(True)
        popup.destroy()

    def on_cancel():
        response.set(False)
        popup.destroy()

    # Contenedor de botones (Continuar en azul, Cancelar en rojo)
    button_frame = ctk.CTkFrame(popup, fg_color="transparent")
    button_frame.pack(pady=15)

    ctk.CTkButton(button_frame, text="Entendido, Continuar", command=on_confirm).pack(
        side="left", padx=10
    )
    ctk.CTkButton(
        button_frame, text="Cancelar", command=on_cancel, fg_color="red"
    ).pack(side="right", padx=10)

    # Pausamos el código aquí hasta que el usuario cierre o conteste el popup
    if parent:
        parent.wait_window(popup)
    else:
        popup.wait_window()

    return response.get()


def show_segmentation_options_dialog(parent, on_auto, on_manual, on_load, on_auto_beta=None):
    """
    Abre el menú con los botones grandes para elegir cómo segmentar la foto:
    - Botón 1: Automática (por umbral térmico).
    - Botón 2: Automática Beta (región del pecho adaptativa + vista previa).
    - Botón 3: Manual (dibujando con el mouse).
    - Botón 4: Cargar máscara existente (.png).
    """
    menu = ctk.CTkToplevel(parent)
    menu.title("Opciones de Segmentación")
    menu.transient(parent)
    menu.grab_set()
    menu.geometry("400x350")
    menu.attributes("-topmost", True)

    icon_path = get_icon_path()
    if icon_path:
        try:
            menu.iconbitmap(icon_path)
        except Exception:
            pass

    # Función para centrar la ventana después de que se dibuje
    def center_popup():
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 175
        menu.geometry(f"400x350+{x}+{y}")

    parent.after(50, center_popup)

    # Título del menú
    ctk.CTkLabel(
        menu,
        text="¿Cómo quieres obtener la máscara?",
        font=ctk.CTkFont(size=16, weight="bold"),
    ).pack(pady=10)

    # Botón de umbral automático
    ctk.CTkButton(
        menu,
        text="Segmentación Automática (por Umbral)",
        command=lambda: [menu.destroy(), on_auto()],
    ).pack(pady=5, padx=20, fill="x")

    # Botón de umbral automático (versión beta, refina el área del pecho)
    if on_auto_beta:
        ctk.CTkButton(
            menu,
            text="Segmentación Automática Beta (Pecho)",
            command=lambda: [menu.destroy(), on_auto_beta()],
        ).pack(pady=5, padx=20, fill="x")

    # Botón de dibujo a mano alzada
    ctk.CTkButton(
        menu,
        text="Dibujar Máscara Manualmente",
        command=lambda: [menu.destroy(), on_manual()],
    ).pack(pady=5, padx=20, fill="x")

    # Botón de cargar imagen PNG
    ctk.CTkButton(
        menu,
        text="Cargar Máscara Existente",
        command=lambda: [menu.destroy(), on_load()],
    ).pack(pady=5, padx=20, fill="x")

    # Texto de ayuda al pie
    info_label = ctk.CTkLabel(
        menu,
        text=(
            "Info: Al 'Cargar Máscara', asegúrate de que sea\n"
            "una imagen PNG en blanco y negro, donde el\n"
            "área de interés sea de color blanco."
        ),
        justify="left",
    )
    info_label.pack(pady=10, padx=20)

    # Esperamos a que el usuario elija una opción
    parent.wait_window(menu)


def show_mask_preview_dialog(parent, ruta_imagen, mascara_inicial):
    """
    Vista previa de la máscara propuesta para el Pecho.

    Muestra la foto con la región superpuesta en verde y 4 sliders para
    ajustarla en vivo (centro X/Y y semiejes) antes de guardarla.

    Retorna una tupla (accion, mascara):
    - ("aceptar", mascara_uint8)  -> el usuario confirmó la región.
    - ("redibujar", None)         -> el usuario quiere dibujarla a mano.
    - (None, None)                -> el usuario canceló o hubo un error.
    """
    base = cv2.imread(ruta_imagen)
    if base is None:
        return None, None
    h, w = base.shape[:2]

    ys, xs = np.where(mascara_inicial > 0)
    if ys.size == 0:
        return None, None

    # Parámetros de la elipse en porcentaje de la imagen (para los sliders)
    params = {
        "cx": 100.0 * float(xs.min() + xs.max()) / (2.0 * w),
        "cy": 100.0 * float(ys.min() + ys.max()) / (2.0 * h),
        "rx": 100.0 * float(max(1, xs.max() - xs.min())) / (2.0 * w),
        "ry": 100.0 * float(max(1, ys.max() - ys.min())) / (2.0 * h),
    }

    win = ctk.CTkToplevel(parent)
    win.title("Vista Previa - Región del Pecho")
    win.transient(parent)
    win.grab_set()
    win.attributes("-topmost", True)
    win.resizable(False, False)

    icon_path = get_icon_path()
    if icon_path:
        try:
            win.iconbitmap(icon_path)
        except Exception:
            pass

    # Centramos la ventana sobre la ventana padre
    if parent and hasattr(parent, "winfo_x"):
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 440
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 300
        win.geometry(f"880x600+{x}+{y}")
    else:
        win.geometry("880x600")

    # -------------------- zona de la imagen --------------------
    max_lado = 540
    escala = min(1.0, max_lado / float(max(h, w)))
    dw, dh = max(1, int(w * escala)), max(1, int(h * escala))

    lbl_preview = ctk.CTkLabel(win, text="")
    lbl_preview.pack(side="left", padx=15, pady=15)

    ctk_img = {"ref": None}  # referencia viva para que Tk no recoja la imagen

    def _mascara_actual():
        m = np.zeros((h, w), dtype=np.uint8)
        centro = (
            int(round(params["cx"] * w / 100.0)),
            int(round(params["cy"] * h / 100.0)),
        )
        ejes = (
            max(3, int(round(params["rx"] * w / 100.0))),
            max(3, int(round(params["ry"] * h / 100.0))),
        )
        cv2.ellipse(m, centro, ejes, 0, 0, 360, 255, cv2.FILLED)
        return m

    def _refrescar():
        mascara = _mascara_actual()
        vis = base.copy()
        verde = np.zeros_like(vis)
        verde[..., 1] = 255
        mezcla = cv2.addWeighted(base, 0.5, verde, 0.5, 0)
        seleccion = mascara > 0
        vis[seleccion] = mezcla[seleccion]
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contornos, -1, (0, 255, 0), 2)
        if escala != 1.0:
            vis = cv2.resize(vis, (dw, dh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        ctk_img["ref"] = ctk.CTkImage(light_image=Image.fromarray(rgb), size=(dw, dh))
        lbl_preview.configure(image=ctk_img["ref"], text="")

    # -------------------- panel de control --------------------
    panel = ctk.CTkFrame(win, width=280)
    panel.pack(side="right", fill="y", padx=10, pady=15)
    panel.pack_propagate(False)

    ctk.CTkLabel(
        panel,
        text="Ajusta la región del pecho",
        font=ctk.CTkFont(size=15, weight="bold"),
    ).pack(pady=(15, 5))
    ctk.CTkLabel(
        panel,
        text="Mueve los sliders hasta que\nel óvalo cubra el busto.",
        justify="left",
    ).pack(padx=10)

    etiquetas = {}

    def _crear_slider(texto, clave, minimo, maximo):
        marco = ctk.CTkFrame(panel, fg_color="transparent")
        marco.pack(fill="x", padx=15, pady=(12, 0))
        etiqueta = ctk.CTkLabel(marco, text=f"{texto}: {params[clave]:.0f}%")
        etiqueta.pack(anchor="w")
        etiquetas[clave] = etiqueta

        def _al_mover(valor, c=clave, e=etiqueta, t=texto):
            params[c] = float(valor)
            e.configure(text=f"{t}: {valor:.0f}%")
            _refrescar()

        slider = ctk.CTkSlider(
            marco, from_=minimo, to=maximo, number_of_steps=100, command=_al_mover
        )
        slider.set(params[clave])
        slider.pack(fill="x", pady=(2, 0))

    _crear_slider("Centro X", "cx", 0, 100)
    _crear_slider("Centro Y", "cy", 0, 100)
    _crear_slider("Ancho (radio X)", "rx", 5, 60)
    _crear_slider("Alto (radio Y)", "ry", 5, 60)

    resultado = {"accion": None, "mascara": None}

    def _aceptar():
        resultado["accion"] = "aceptar"
        resultado["mascara"] = _mascara_actual()
        win.destroy()

    def _redibujar():
        resultado["accion"] = "redibujar"
        win.destroy()

    marco_botones = ctk.CTkFrame(panel, fg_color="transparent")
    marco_botones.pack(side="bottom", pady=15, fill="x", padx=15)

    ctk.CTkButton(
        marco_botones, text="Aceptar región", fg_color="#2E7D32", command=_aceptar
    ).pack(fill="x", pady=4)
    ctk.CTkButton(
        marco_botones,
        text="Redibujar manualmente",
        fg_color="#6D4C41",
        command=_redibujar,
    ).pack(fill="x", pady=4)
    ctk.CTkButton(
        marco_botones, text="Cancelar", fg_color="red", command=win.destroy
    ).pack(fill="x", pady=4)

    _refrescar()
    parent.wait_window(win)

    return resultado["accion"], resultado["mascara"]
