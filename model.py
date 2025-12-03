# model.py
from mesa import Model
from mesa.time import RandomActivation
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector
import random

from agentes.airport import Airport
from agentes.airplane import Airplane
from agentes.airline import Airline
from agentes.controltower import ControlTower   # 👈 IMPORTANTE


# ==========================
#   CLIMA (CONSTANTES)
# ==========================
CLIMAS = [
    "normal",
    "lluvia",
    "tormenta",
    "viento_fuerte",
    "niebla",
    "microburst",   # evento extremo
]

PROBABILIDADES_CLIMA = {
    "normal":        0.54,
    "lluvia":        0.20,
    "tormenta":      0.10,
    "viento_fuerte": 0.10,
    "niebla":        0.05,
    "microburst":    0.01,   # microburst raro pero posible
}

FACTOR_CLIMA = {
    "normal":        1.0,   # día perfecto
    "lluvia":        1.4,   # algo más complicado
    "niebla":        1.6,   # visibilidad mala
    "viento_fuerte": 1.7,   # turbulencia fuerte
    "tormenta":      2.0,   # casi colapsado
    "microburst":    999,   # evento crítico: cierre total
}

class AirportModel(Model):
    def __init__(
        self,
        scenario="Equilibrio",
        allow_diversion=False,
        max_holding_time=25,
        clima_manual="ninguno",      # override desde el panel
        usar_probabilidades=True,    # modo aleatorio
    ):
        super().__init__()
        self.schedule = RandomActivation(self)
        self.grid = MultiGrid(20, 20, torus=False)

        # Guardamos el escenario
        self.scenario = scenario

        # ---------------------------
        #   ESTADO DE CLIMA
        # ---------------------------
        self.clima_manual = clima_manual          # "ninguno" = no forzar
        self.usar_probabilidades = usar_probabilidades
        self.clima_actual = "normal"
        self.factor_clima = 1.0

        # ===============================
        #   CONFIGURACIÓN POR ESCENARIO
        # ===============================
        if scenario == "Equilibrio":
            self.arrival_rate = 0.2
            self.max_ground = 6
            self.turn_time = 3
            self.takeoff_time = 3
            self.max_release_per_step = 3

        elif scenario == "Normal":
            self.arrival_rate = 0.5
            self.max_ground = 4
            self.turn_time = 3
            self.takeoff_time = 5
            self.max_release_per_step = 2

        elif scenario == "Sobrecarga":
            self.arrival_rate = 1.0
            self.max_ground = 3
            self.turn_time = 2
            self.takeoff_time = 8
            self.max_release_per_step = 1

        else:
            # Fallback
            self.arrival_rate = 0.5
            self.max_ground = 4
            self.turn_time = 3
            self.takeoff_time = 5
            self.max_release_per_step = 2

        # Parámetros desde el servidor
        self.allow_diversion = allow_diversion
        self.max_holding_time = max_holding_time

        # Identificadores
        self.next_id = 0
        self.planes = []

        # Contadores para métricas
        self.total_arrivals = 0
        self.total_departures = 0
        self.total_diverted = 0

        # Aerolíneas
        self.airlines = []
        configs = [
            ("AL1", "Aerolínea 1", "#00BFFF"),
            ("AL2", "Aerolínea 2", "#32CD32"),
            ("AL3", "Aerolínea 3", "#8B4513"),
        ]
        for i, (code, name, color) in enumerate(configs):
            al = Airline(f"airline_{i}", self, name, code, color)
            self.airlines.append(al)
            self.schedule.add(al)

        # Pistas simples (NO agentes)
        self.runways = [
            {"busy": False, "remaining": 0, "plane": None},
            {"busy": False, "remaining": 0, "plane": None},
        ]

        self.departure_queue = []
        self.holding_planes = []

        # Aeropuerto
        self.airport_center = (self.grid.width // 2, self.grid.height // 2)
        self.airport = Airport("airport", self)
        self.schedule.add(self.airport)
        self.grid.place_agent(self.airport, self.airport_center)

        # Torre de control
        self.control_tower = ControlTower("tower", self)
        self.schedule.add(self.control_tower)

        # La torre justo encima del aeropuerto
        self.grid.place_agent(
            self.control_tower,
            (self.airport_center[0], self.airport_center[1] - 1)
        )

        # ===============================
        #   DATA COLLECTOR NUEVO
        # ===============================
        self.datacollector = DataCollector(
            model_reporters={
                "Llegadas": lambda m: m.total_arrivals,
                "Salidas": lambda m: m.total_departures,
                # Retrasados = prioridad 1
                "En_espera": lambda m: sum(
                    1 for p in m.planes if getattr(p, "prioridad", 0) == 1
                ),
                # Emergencias rojas
                "Emergencias": lambda m: sum(
                    1 for p in m.planes if getattr(p, "emergencia", False)
                ),
                # Desviados
                "Desviados": lambda m: m.total_diverted,
            }
        )

    # ====================================
    # Helpers
    # ====================================
    def planes_on_ground(self):
        """Cuenta aviones en tierra (waiting, queued_dep, departing)."""
        return sum(
            1 for p in self.planes
            if p.state in ("waiting", "queued_departure", "departing")
        )

    # ====================================
    # Step Principal del Modelo
    # ====================================
    def step(self):
        # 0) Actualizar clima (manual o probabilístico)
        self.actualizar_clima()

        # 0.1) Si es microburst → evento crítico
        if self.clima_actual == "microburst":
            # Aplica el evento: desviar aviones y cerrar pistas
            self.aplicar_microburst()
            # Igualmente registramos métricas del tick
            self.datacollector.collect(self)
            return

        # 1) Ajustar tasa de llegadas según el clima
        #    Clima peor => factor_clima más alto => llegan menos aviones
        if self.factor_clima > 0:
            arrival_rate_efectiva = self.arrival_rate / self.factor_clima
        else:
            arrival_rate_efectiva = self.arrival_rate

        # 2) Crear avión según probabilidad AJUSTADA por clima
        if random.random() < arrival_rate_efectiva:
            self.create_plane()

        # 3) Actualizar pistas
        self.update_runways()

        # 4) Torre + Aeropuerto + Aerolíneas + Aviones
        self.schedule.step()

        # 5) Registrar datos
        self.datacollector.collect(self)

    # ====================================
    # Crear / eliminar aviones
    # ====================================
    def create_plane(self):
        airline = random.choice(self.airlines)
        plane = Airplane(self.next_id, self, airline)
        self.next_id += 1

        self.planes.append(plane)
        self.schedule.add(plane)

        airline.register_plane(plane)

        x, y = plane.spawn_pos
        self.grid.place_agent(plane, (x, y))

    def remove_plane(self, plane):
        if plane in self.planes:
            self.planes.remove(plane)
        try:
            self.schedule.remove(plane)
        except:
            pass
        try:
            self.grid.remove_agent(plane)
        except:
            pass

        if plane in self.holding_planes:
            self.holding_planes.remove(plane)
        if plane in self.departure_queue:
            self.departure_queue.remove(plane)

    # ====================================
    # Lógica de pistas
    # ====================================
    def update_runways(self):
        """Cuenta regresiva de ocupación de pistas."""
        for rw in self.runways:
            if rw["busy"]:
                rw["remaining"] -= 1
                if rw["remaining"] <= 0:
                    rw["busy"] = False
                    rw["plane"] = None

    # ====================================
    # Clima: actualización y efectos
    # ====================================
    def actualizar_clima(self):
        """
        Decide el clima_actual en este tick:
        - Si clima_manual != 'ninguno' → se usa ese
        - Si usar_probabilidades → sorteo según PROBABILIDADES_CLIMA
        """
        if self.clima_manual != "ninguno":
            self.clima_actual = self.clima_manual
        elif self.usar_probabilidades:
            self.clima_actual = random.choices(
                list(PROBABILIDADES_CLIMA.keys()),
                weights=list(PROBABILIDADES_CLIMA.values())
            )[0]
        else:
            # Si no hay nada configurado, se queda el último
            pass

        # Actualizar factor_clima
        self.factor_clima = FACTOR_CLIMA.get(self.clima_actual, 1.0)

    def aplicar_microburst(self):
        """
        Evento extremo:
        - Cierra el aeropuerto (no más aterrizajes/despegues)
        - Todos los aviones en llegada / holding se desvían
        """
        # Desviar aviones que aún no tocaron tierra
        for plane in list(self.planes):
            if plane.state in ("arriving", "holding"):
                plane.state = "diverted"
                self.total_diverted += 1

        # Marcar las pistas como 'cerradas' poniéndolas siempre ocupadas
        for rw in self.runways:
            rw["busy"] = True
            rw["remaining"] = 999999  # efecto: nunca se liberan mientras dure el evento

    # ====================================
    #  SERIALIZACIÓN PARA EL FRONTEND
    # ====================================
    def serialize(self):
        positions = []
        for p in self.planes:
            if not hasattr(p, "pos") or p.pos is None:
                continue

            x, y = p.pos
            cx, cy = self.airport_center
            dx = x - cx
            dy = y - cy
            distancia = (dx**2 + dy**2) ** 0.5

            positions.append(
                {
                    "id": p.unique_id,
                    "x": x,
                    "y": y,
                    "airline": getattr(p.airline, "name", "N/A"),
                    "state": getattr(p, "state", "unknown"),
                    "prioridad": getattr(p, "prioridad", 0),
                    "combustible": getattr(p, "combustible_restante", 0),
                    "emergencia": getattr(p, "emergencia", False),
                    "goaround_blink": getattr(p, "goaround_blink", 0),
                    "distancia": distancia,
                    "desviado": getattr(p, "state", "") == "diverted",
                }
            )

        clima_actual = getattr(self, "clima_actual", "normal")
        factor = getattr(self, "factor_clima", 1.0)

        metrics = {
            "costos_totales": 0,
            "reordenamientos": 0,
            "clima": {
                "tipo": clima_actual,
                "viento_intensidad": factor,
                "visibilidad": 1.0 / factor if factor > 0 else 0.0,
            },
            "aerolineas": [],
        }

        for al in self.airlines:
            vuelos = len(al.fleet)
            desvios = sum(
                1
                for p in self.planes
                if getattr(p, "airline", None) is al
                and getattr(p, "state", "") == "diverted"
            )
            metrics["aerolineas"].append(
                {
                    "nombre": al.name,
                    "vuelos": vuelos,
                    "costo": 0,
                    "retraso_promedio": 0,
                    "desvios": desvios,
                }
            )

        return {
            "step": self.schedule.steps,
            "positions": positions,
            "metrics": metrics,
        }
