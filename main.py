"""
=============================================================================
ARCHIVO: main.py
PUNTO DE ENTRADA PRINCIPAL DEL PROGRAMA
=============================================================================
Hola! Este archivo es el que debes ejecutar para abrir la aplicación térmica.
Básicamente lo que hace es importar la ventana principal desde nuestra carpeta 'src'
y ponerla a correr en un bucle infinito para que podamos interactuar con ella.
"""

# Traemos la clase 'App' desde nuestro módulo de interfaz gráfica
from src.ui.main_window import App


def main():
    """
    Función principal:
    1. Crea la instancia de la aplicación (la ventana).
    2. Ejecuta 'mainloop()', que se encarga de escuchar los clics del mouse,
       las teclas que presionemos y de redibujar la pantalla.
    """
    # Creamos el objeto de la aplicación
    app = App()

    # Arrancamos el bucle de eventos de la ventana (para que no se cierre sola)
    app.mainloop()


# Este bloque sirve para que la función main() solo se ejecute cuando abrimos
# este archivo directamente desde la terminal (ej: python main.py)
if __name__ == "__main__":
    main()
