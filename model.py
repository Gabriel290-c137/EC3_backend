# model.py - VERSIÓN MEJORADA CON MÉTRICAS AVANZADAS
from mesa import Model
from mesa.time import RandomActivation
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector
import random

from agentes.airport import Airport
from agentes.airplane import Airplane
from agentes.airline import Airline
from agentes.controltower import ControlTower

# Constantes de clima (sin cambios)
CLIMAS = ["normal", "lluvia", "tormenta", "viento_fuerte", "niebla", "microburst"]

PROBABILIDADES_CLIMA = {
    "normal": 0.54,
    "lluvia": 0.20,
    "tormenta": 0.10,
    "viento_fuerte": 0.10,
    "niebla": 0.05,
    "microburst": 0.01,
}

FACTOR_CLIMA = {
    "normal": 1.0,
    "lluvia": 1.4,
    "niebla": 1.6,
    "viento_fuerte": 1.7,
    "tormenta": 2.0,
    "microburst": 999,
}

class AirportModel(Model):
    def __init__(
        self,
        scenario="Equilibrio",
        allow_diversion=False,
        max_holding_time=25,
        clima_manual="ninguno",
        usar_probabilidades=True,
        arrival_rate=None,
        max_ground=None,
        turn_time=None,
        takeoff_time=None,
        max_release_per_step=None,
        minutes_per_step=5,
        control_policy="dynamic", 
    ):
        super().__init__()
        self.schedule = RandomActivation(self)
        self.grid = MultiGrid(20, 20, torus=False)

        self.scenario = scenario
        self.clima_manual = clima_manual
        self.usar_probabilidades = usar_probabilidades
        self.clima_actual = "normal"
        self.factor_clima = 1.0

        # 🆕 POLÍTICA DE CONTROL
        self.control_policy = control_policy  # "fixed", "fuel_priority", "dynamic"

        # Sistema de tiempo
        self.minutes_per_step = minutes_per_step
        self.current_hour = 6
        self.current_minute = 0
        self.last_clima_change_hour = 0
        self.hours_until_next_clima_change = random.randint(4, 8)

        # Configuración por escenario
        if scenario == "Equilibrio":
            base_arrival = 0.2
            base_max_ground = 6
            base_turn_time = 3
            base_takeoff_time = 3
            base_max_release = 3
        elif scenario == "Normal":
            base_arrival = 0.5
            base_max_ground = 4
            base_turn_time = 3
            base_takeoff_time = 5
            base_max_release = 2
        elif scenario == "Sobrecarga":
            base_arrival = 1.0
            base_max_ground = 3
            base_turn_time = 2
            base_takeoff_time = 8
            base_max_release = 1
        elif scenario == "Libre":
            base_arrival = 0.5
            base_max_ground = 4
            base_turn_time = 3
            base_takeoff_time = 5
            base_max_release = 2
        else:
            base_arrival = 0.5
            base_max_ground = 4
            base_turn_time = 3
            base_takeoff_time = 5
            base_max_release = 2

        self.arrival_rate = arrival_rate if arrival_rate is not None else base_arrival
        self.max_ground = max_ground if max_ground is not None else base_max_ground
        self.turn_time = turn_time if turn_time is not None else base_turn_time
        self.takeoff_time = takeoff_time if takeoff_time is not None else base_takeoff_time
        self.max_release_per_step = max_release_per_step if max_release_per_step is not None else base_max_release

        self.allow_diversion = allow_diversion
        self.max_holding_time = max_holding_time

        self.next_id = 0
        self.planes = []

        # Contadores básicos
        self.total_arrivals = 0
        self.total_departures = 0
        self.total_diverted = 0

        # ====================================
        # NUEVAS MÉTRICAS AVANZADAS
        # ====================================
        self.total_holding_time_accumulated = 0  # Tiempo total en holding (todos los aviones)
        self.runway_busy_time = 0                 # Ticks totales que las pistas estuvieron ocupadas
        self.total_fuel_consumed = 0              # Combustible total consumido
        self.emergency_events = 0                 # Total de emergencias que ocurrieron
        self.goaround_events = 0                  # Total de go-arounds

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

        # Pistas
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
        self.grid.place_agent(
            self.control_tower,
            (self.airport_center[0], self.airport_center[1] - 1)
        )

        # ====================================
        # DATA COLLECTOR MEJORADO
        # ====================================
        self.datacollector = DataCollector(
            model_reporters={
                # Métricas básicas
                "Llegadas": lambda m: m.total_arrivals,
                "Salidas": lambda m: m.total_departures,
                "En_espera": lambda m: sum(1 for p in m.planes if getattr(p, "prioridad", 0) == 1),
                "Emergencias": lambda m: sum(1 for p in m.planes if getattr(p, "emergencia", False)),
                "Desviados": lambda m: m.total_diverted,
                
                # MÉTRICAS AVANZADAS
                "Aviones_en_holding": lambda m: len(m.holding_planes),
                "Tiempo_holding_promedio": lambda m: m.get_avg_holding_time(),
                "Utilizacion_pistas": lambda m: m.get_runway_utilization(),
                "Throughput": lambda m: m.get_throughput(),
                "Eficiencia_combustible": lambda m: m.get_fuel_efficiency(),
                "Tasa_emergencias": lambda m: m.get_emergency_rate(),

                 # 🆕 NUEVAS MÉTRICAS
                "Tipos_aeronaves": lambda m: self._count_aircraft_types(m),
                "Vuelos_puntuales": lambda m: sum(1 for p in m.planes if getattr(p, "punctuality_status", "") == "on_time"),
                "Vuelos_retrasados": lambda m: sum(1 for p in m.planes if getattr(p, "punctuality_status", "") == "delayed"),
                "Vuelos_adelantados": lambda m: sum(1 for p in m.planes if getattr(p, "punctuality_status", "") == "early"),
            }
        )

    # ====================================
    # NUEVOS MÉTODOS PARA MÉTRICAS
    # ====================================
    
    def get_avg_holding_time(self):
        """Retorna el tiempo promedio en holding de los aviones actualmente en espera."""
        if not self.holding_planes:
            return 0
        return sum(p.holding_time for p in self.holding_planes) / len(self.holding_planes)
    
    def get_runway_utilization(self):
        """
        Calcula el % de utilización de pistas.
        100% = todas las pistas ocupadas todo el tiempo
        """
        if self.schedule.steps == 0:
            return 0
        
        total_capacity = len(self.runways) * self.schedule.steps
        return (self.runway_busy_time / total_capacity) * 100 if total_capacity > 0 else 0
    
    def get_throughput(self):
        """
        Retorna aviones procesados por hora simulada.
        (Arrivals + Departures) / horas transcurridas
        """
        horas_transcurridas = (self.schedule.steps * self.minutes_per_step) / 60
        if horas_transcurridas == 0:
            return 0
        
        total_procesados = self.total_arrivals + self.total_departures
        return total_procesados / horas_transcurridas
    
    def get_fuel_efficiency(self):
        """
        Calcula eficiencia de combustible.
        Menor tiempo en holding = mayor eficiencia
        """
        if self.total_arrivals == 0:
            return 100
        
        # Eficiencia inversa al tiempo en holding
        avg_holding = self.total_holding_time_accumulated / max(self.total_arrivals, 1)
        eficiencia = max(0, 100 - (avg_holding * 2))  # -2 puntos por cada tick de holding
        return eficiencia
    
    def get_emergency_rate(self):
        """Retorna el % de vuelos que tuvieron emergencias."""
        total_flights = self.total_arrivals + len(self.planes)
        if total_flights == 0:
            return 0
        return (self.emergency_events / total_flights) * 100

    # ====================================
    # MÉTODOS EXISTENTES (SIN CAMBIOS)
    # ====================================
    
    def planes_on_ground(self):
        return sum(
            1 for p in self.planes
            if p.state in ("waiting", "queued_departure", "departing")
        )

    def advance_time(self):
        self.current_minute += self.minutes_per_step
        if self.current_minute >= 60:
            self.current_minute = 0
            self.current_hour += 1
            if self.current_hour >= 24:
                self.current_hour = 0

    def get_time_period(self):
        if 5 <= self.current_hour < 7:
            return "morning"
        elif 7 <= self.current_hour < 18:
            return "day"
        elif 18 <= self.current_hour < 20:
            return "evening"
        else:
            return "night"

    def get_time_multiplier(self):
        if 6 <= self.current_hour < 9:
            return 1.5
        elif 17 <= self.current_hour < 20:
            return 1.5
        elif self.current_hour >= 23 or self.current_hour < 5:
            return 0.3
        else:
            return 1.0
        
    def _count_aircraft_types(self, m):
        """Cuenta aviones por tipo."""
        types = {}
        for p in m.planes:
            t = getattr(p, "aircraft_type", "Unknown")
            types[t] = types.get(t, 0) + 1
        return types

    # ====================================
    # STEP MEJORADO
    # ====================================
    
    def step(self):
        # Avanzar tiempo
        self.advance_time()

        # Actualizar clima
        self.actualizar_clima()

        # Microburst: evento crítico
        if self.clima_actual == "microburst":
            self.aplicar_microburst()
            self.datacollector.collect(self)
            return

        # Calcular tasa de llegadas ajustada
        time_multiplier = self.get_time_multiplier()
        if self.factor_clima > 0:
            arrival_rate_efectiva = (self.arrival_rate * time_multiplier) / self.factor_clima
        else:
            arrival_rate_efectiva = self.arrival_rate * time_multiplier

        # Crear avión según probabilidad
        if random.random() < arrival_rate_efectiva:
            self.create_plane()

        # Actualizar pistas Y contabilizar utilización
        self.update_runways()

        # Torre + Aeropuerto + Aerolíneas + Aviones
        self.schedule.step()

        # Acumular tiempo en holding
        self.total_holding_time_accumulated += len(self.holding_planes)

        # Registrar datos
        self.datacollector.collect(self)

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
        # Registrar vuelo completado en la aerolínea
        if plane.state == "gone":
            plane.airline.register_completed_flight(plane)
        elif plane.state == "diverted":
            plane.airline.register_diversion()
        
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

    def update_runways(self):
        """Actualiza pistas Y contabiliza tiempo ocupado."""
        for rw in self.runways:
            if rw["busy"]:
                self.runway_busy_time += 1  # Contabilizar utilización
                rw["remaining"] -= 1
                if rw["remaining"] <= 0:
                    rw["busy"] = False
                    rw["plane"] = None

    def actualizar_clima(self):
        if self.clima_manual != "ninguno":
            self.clima_actual = self.clima_manual
        elif self.usar_probabilidades:
            hours_since_change = self.current_hour - self.last_clima_change_hour
            if hours_since_change < 0:
                hours_since_change += 24
            
            if hours_since_change >= self.hours_until_next_clima_change:
                self.clima_actual = random.choices(
                    list(PROBABILIDADES_CLIMA.keys()),
                    weights=list(PROBABILIDADES_CLIMA.values())
                )[0]
                self.last_clima_change_hour = self.current_hour
                self.hours_until_next_clima_change = random.randint(4, 8)
        else:
            pass

        self.factor_clima = FACTOR_CLIMA.get(self.clima_actual, 1.0)

    def aplicar_microburst(self):
        for plane in list(self.planes):
            if plane.state in ("arriving", "holding"):
                plane.state = "diverted"
                self.total_diverted += 1

        for rw in self.runways:
            rw["busy"] = True
            rw["remaining"] = 999999

    def serialize(self):
        # (Tu método serialize existente sin cambios)
        positions = []
        for p in self.planes:
            if not hasattr(p, "pos") or p.pos is None:
                continue

            x, y = p.pos
            cx, cy = self.airport_center
            dx = x - cx
            dy = y - cy
            distancia = (dx**2 + dy**2) ** 0.5

            positions.append({
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
            })

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
            "time": {
                "hour": self.current_hour,
                "minute": self.current_minute,
                "period": self.get_time_period(),
            },
            "aerolineas": [],
        }

        for al in self.airlines:
            vuelos = len(al.fleet)
            desvios = sum(
                1 for p in self.planes
                if getattr(p, "airline", None) is al
                and getattr(p, "state", "") == "diverted"
            )
            metrics["aerolineas"].append({
                "nombre": al.name,
                "vuelos": vuelos,
                "costo": 0,
                "retraso_promedio": 0,
                "desvios": desvios,
            })

        return {
            "step": self.schedule.steps,
            "positions": positions,
            "metrics": metrics,
        }