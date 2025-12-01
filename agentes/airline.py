# agentes/airline.py
from mesa import Agent

class Airline(Agent):
    """
    Agente Aerolínea.
    No se mueve en el grid; representa una compañía que tiene varios aviones.
    Más adelante puede tener:
    - nombre, código IATA/ICAO
    - color asociado
    - lista de aviones (flota)
    - lógica de costos / decisiones
    """
    def __init__(self, unique_id, model, name, code, color):
        super().__init__(unique_id, model)
        self.name = name      # ej. "Aerolínea 1"
        self.code = code      # ej. "AL1"
        self.color = color    # ej. "#00BFFF" (celeste)
        self.fleet = []       # lista de aviones que pertenecen a esta aerolínea

    def register_plane(self, plane):
        """Asociar un avión a esta aerolínea."""
        self.fleet.append(plane)

    def step(self):
        """
        Por ahora no hace nada en cada tick.
        Más adelante puede:
        - decidir prioridades
        - negociar slots
        - registrar métricas, etc.
        """
        pass
