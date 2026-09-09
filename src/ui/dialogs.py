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


def show_segmentation_options_dialog(parent, on_auto, on_manual, on_load):
    """
    Abre el menú con 3 botones grandes para elegir cómo segmentar la foto:
    - Botón 1: Automática (por umbral térmico).
    - Botón 2: Manual (dibujando con el mouse).
    - Botón 3: Cargar máscara existente (.png).
    """
    menu = ctk.CTkToplevel(parent)
    menu.title("Opciones de Segmentación")
    menu.transient(parent)
    menu.grab_set()
    menu.geometry("400x250")
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
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 125
        menu.geometry(f"400x250+{x}+{y}")

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
