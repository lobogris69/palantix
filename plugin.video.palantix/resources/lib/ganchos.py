"""Módulos opcionales que el servicio avisa durante la reproducción (Trakt, saltar intro...).

Cada gancho es un objeto con cualquiera de estos métodos:
    al_empezar(meta, reproductor)
    al_avanzar(meta, reproductor, segundo_actual, duracion_total)   # cada segundo
    al_parar(meta, reproductor, terminado)
`meta` = {"tipo": "pelicula"|"episodio", "tmdb": id (de la peli o de la SERIE), "s": temporada, "e": capítulo, "titulo"}
"""

REGISTRO = []  # clases de gancho; se rellena al importar cada módulo opcional


def registrar(clase):
    REGISTRO.append(clase)
    return clase


def cargar(log=print):
    for modulo in ("seguimiento", "progreso", "trakt", "intro"):  # si un módulo no existe o falla, se sigue sin él
        try:
            __import__("resources.lib." + modulo)
        except Exception as e:
            log("Gancho %s no cargado: %s" % (modulo, e))
    activos = []
    for clase in REGISTRO:
        try:
            g = clase()
            if getattr(g, "activo", lambda: True)():
                activos.append(g)
        except Exception as e:
            log("Gancho %s no arrancó: %s" % (clase.__name__, e))
    return activos
