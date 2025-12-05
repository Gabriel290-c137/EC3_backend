# agentes/airplane.py - VERSIÓN MEJORADA
from mesa import Agent
import random
import math


class Airplane(Agent):
    def __init__(self, unique_id, model, airline):
        super().__init__(unique_id, model)

        self.airline = airline
        self.flight_code = f"{self.airline.code} {unique_id:03d}"

        # Estados: arriving, holding, waiting, queued_departure, departing, diverted, gone
        self.state = "arriving"
        self.wait_time = self.model.turn_time

        self.center = (model.grid.width // 2, model.grid.height // 2)
        self.spawn_pos = self.random_edge()
        self.exit_target = self.random_edge()

        # Órbita
        self.orbit_path = []
        self.orbit_index = 0
        self.holding_time = 0
        self.holding_radius = 3
        self.angle = random.random() * 2 * math.pi

        # Prioridad y emergencia
        self.combustible_restante = random.randint(60, 120)
        self.prioridad = 0
        self.emergencia = False
        self.goaround_blink = 0
        
        # 🆕 TRACKING: registrar si este avión ya fue contabilizado como emergencia
        self.emergencia_registrada = False

    def random_edge(self):
        w, h = self.model.grid.width, self.model.grid.height
        side = random.choice(["top", "bottom", "left", "right"])

        if side == "top":
            return (random.randrange(w), h - 1)
        if side == "bottom":
            return (random.randrange(w), 0)
        if side == "left":
            return (0, random.randrange(h))
        if side == "right":
            return (w - 1, random.randrange(h))

    def build_orbit(self, radius=5):
        cx, cy = self.center
        path = []

        for x in range(cx - radius, cx + radius + 1):
            path.append((x, cy - radius))

        for y in range(cy - radius + 1, cy + radius + 1):
            path.append((cx + radius, y))

        for x in range(cx + radius - 1, cx - radius - 1, -1):
            path.append((x, cy + radius))

        for y in range(cy + radius - 1, cy - radius, -1):
            path.append((cx - radius, y))

        self.orbit_path = [
            (x, y) for (x, y) in path
            if 0 <= x < self.model.grid.width and 0 <= y < self.model.grid.height
        ]

        if not self.orbit_path:
            self.orbit_path = [self.pos]

        self.orbit_index = 0

    def move_towards(self, target):
        x, y = self.pos
        tx, ty = target

        dx = tx - x
        dy = ty - y

        if dx != 0:
            dx = 1 if dx > 0 else -1
        if dy != 0:
            dy = 1 if dy > 0 else -1

        new_pos = (x + dx, y + dy)

        w, h = self.model.grid.width, self.model.grid.height
        if 0 <= new_pos[0] < w and 0 <= new_pos[1] < h:
            self.model.grid.move_agent(self, new_pos)

    def step(self):
        # GO-AROUND: cuenta atrás
        if getattr(self, "goaround_blink", 0) > 0:
            self.goaround_blink -= 1

        # CONSUMO DE COMBUSTIBLE
        if self.state in ("arriving", "holding"):
            self.combustible_restante = max(0, self.combustible_restante - 1)

        # ACTIVACIÓN DE EMERGENCIA
        if (not self.emergencia) and self.combustible_restante <= 10:
            self.emergencia = True
            self.prioridad = 2
            
            # 🆕 Registrar en el modelo (solo la primera vez)
            if not self.emergencia_registrada:
                self.model.emergency_events += 1
                self.emergencia_registrada = True

        # ============================================
        # ESTADOS
        # ============================================
        
        if self.state == "arriving":
            if self.model.planes_on_ground() >= self.model.max_ground:
                if not self.orbit_path:
                    self.build_orbit()

                self.state = "holding"
                self.holding_time = 0

                if self not in self.model.holding_planes:
                    self.model.holding_planes.append(self)
                return

            self.move_towards(self.center)
            if self.pos == self.center:
                if self in self.model.holding_planes:
                    self.model.holding_planes.remove(self)

                self.state = "waiting"
                self.model.total_arrivals += 1
            return

        if self.state == "holding":
            self.holding_time += 1

            # GO-AROUND / caída brusca de combustible
            if (not self.emergencia) and random.random() < 0.03:
                self.combustible_restante = max(
                    0, self.combustible_restante - random.randint(20, 40)
                )
                self.emergencia = True
                self.prioridad = 2
                self.goaround_blink = 2
                
                # 🆕 Registrar evento
                self.model.goaround_events += 1
                
                if not self.emergencia_registrada:
                    self.model.emergency_events += 1
                    self.emergencia_registrada = True

            # DESVÍO
            if (
                getattr(self.model, "allow_diversion", False)
                and not self.emergencia
                and self.holding_time >= getattr(self.model, "max_holding_time", 9999)
            ):
                self.state = "diverted"
                self.model.total_diverted += 1

                if self in self.model.holding_planes:
                    self.model.holding_planes.remove(self)

                return

            # Orbitar
            cx, cy = self.model.airport_center
            self.angle += 0.25
            nx = cx + int(self.holding_radius * math.cos(self.angle))
            ny = cy + int(self.holding_radius * math.sin(self.angle))

            w, h = self.model.grid.width, self.model.grid.height
            nx = max(0, min(w - 1, nx))
            ny = max(0, min(h - 1, ny))

            self.model.grid.move_agent(self, (nx, ny))
            return

        if self.state == "waiting":
            # Al aterrizar, resolver emergencia
            if self.emergencia:
                self.emergencia = False
                if self.prioridad == 2:
                    self.prioridad = 1

            self.wait_time -= 1
            if self.wait_time <= 0:
                self.state = "queued_departure"
                self.model.departure_queue.append(self)
            return

        if self.state == "queued_departure":
            return

        if self.state == "departing":
            # Limpiar emergencia en despegue
            if self.emergencia:
                self.emergencia = False
            if self.prioridad == 2:
                self.prioridad = 1
            self.goaround_blink = 0

            self.move_towards(self.exit_target)
            if self.pos == self.exit_target:
                self.state = "gone"
                self.model.total_departures += 1
                self.model.remove_plane(self)
            return

        if self.state == "diverted":
            self.move_towards(self.exit_target)
            if self.pos == self.exit_target:
                self.model.remove_plane(self)
            return