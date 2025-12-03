from mesa import Agent
import random
import math


class Airplane(Agent):
    def __init__(self, unique_id, model, airline):
        super().__init__(unique_id, model)

        # Aerolínea propietaria
        self.airline = airline
        
        # Código de vuelo único (formato: CÓDIGO_AEROLÍNEA + NÚMERO)
        self.flight_code = f"{self.airline.code} {unique_id:03d}"

        # Estados posibles:
        # arriving, holding, waiting, queued_departure,
        # departing, diverted, gone
        self.state = "arriving"
        self.wait_time = self.model.turn_time  # tiempo en tierra antes de querer salir

        # Centro del aeropuerto
        self.center = (model.grid.width // 2, model.grid.height // 2)

        # Donde nace (borde aleatorio) y por dónde se irá
        self.spawn_pos = self.random_edge()
        self.exit_target = self.random_edge()

        # Datos para órbita
        self.orbit_path = []
        self.orbit_index = 0
        self.holding_time = 0

        # Órbita circular
        self.holding_radius = 3
        self.angle = random.random() * 2 * math.pi

        # ============================
        #   CAMPOS PRIORIDAD / EMERGENCIA
        # ============================

        # Combustible inicial (modelo simple)
        self.combustible_restante = random.randint(60, 120)

        # prioridad: 0 = normal, 1 = retrasado, 2 = emergencia
        self.prioridad = 0
        self.emergencia = False

        # Go-around: parpadeo morado cuando ocurre el evento
        self.goaround_blink = 0   # ticks que estará en color morado

    # =========================================================
    #  Helpers de movimiento
    # =========================================================
    def random_edge(self):
        """Devuelve una coordenada en el borde del grid."""
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
        """Órbita cuadrada (legacy)."""
        cx, cy = self.center
        path = []

        # Borde superior
        for x in range(cx - radius, cx + radius + 1):
            path.append((x, cy - radius))

        # Borde derecho
        for y in range(cy - radius + 1, cy + radius + 1):
            path.append((cx + radius, y))

        # Borde inferior
        for x in range(cx + radius - 1, cx - radius - 1, -1):
            path.append((x, cy + radius))

        # Borde izquierdo
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
        """Mueve un paso hacia un objetivo."""
        x, y = self.pos
        tx, ty = target

        dx = tx - x
        dy = ty - y

        if dx != 0:
            dx = 1 if dx > 0 else -1
        if dy != 0:
            dy = 1 if dy > 0 else -1

        new_pos = (x + dx, y + dy)

        # seguridad
        w, h = self.model.grid.width, self.model.grid.height
        if 0 <= new_pos[0] < w and 0 <= new_pos[1] < h:
            self.model.grid.move_agent(self, new_pos)

    # =========================================================
    #  Dinámica por estado
    # =========================================================
    def step(self):

        # -------------------------------------------------------
        # 0) GO-AROUND: cuenta atrás del parpadeo morado
        # -------------------------------------------------------
        if getattr(self, "goaround_blink", 0) > 0:
            self.goaround_blink -= 1

        # -------------------------------------------------------
        # 0.bis) CONSUMO DE COMBUSTIBLE + ACTIVACIÓN EMERGENCIA
        # -------------------------------------------------------
        if self.state in ("arriving", "holding"):
            self.combustible_restante = max(0, self.combustible_restante - 1)

        # Si el combustible llega muy bajo → emergencia general
        if (not self.emergencia) and self.combustible_restante <= 10:
            self.emergencia = True
            self.prioridad = 2   # prioridad máxima

        # -------------------------------------------------------
        # 1) LLEGANDO
        # -------------------------------------------------------
        if self.state == "arriving":

            # si no puede entrar → holding
            if self.model.planes_on_ground() >= self.model.max_ground:

                if not self.orbit_path:
                    self.build_orbit()

                self.state = "holding"
                self.holding_time = 0

                if self not in self.model.holding_planes:
                    self.model.holding_planes.append(self)
                return

            # si sí puede → sigue hacia el centro
            self.move_towards(self.center)
            if self.pos == self.center:
                if self in self.model.holding_planes:
                    self.model.holding_planes.remove(self)

                self.state = "waiting"
                self.model.total_arrivals += 1
            return

        # -------------------------------------------------------
        # 2) HOLDING (órbita)
        # -------------------------------------------------------
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

            # DESVÍO (solo si NO es emergencia)
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

            # orbitar alrededor del aeropuerto
            cx, cy = self.model.airport_center
            self.angle += 0.25
            nx = cx + int(self.holding_radius * math.cos(self.angle))
            ny = cy + int(self.holding_radius * math.sin(self.angle))

            # seguridad grid
            w, h = self.model.grid.width, self.model.grid.height
            nx = max(0, min(w - 1, nx))
            ny = max(0, min(h - 1, ny))

            self.model.grid.move_agent(self, (nx, ny))
            return

        # -------------------------------------------------------
        # 3) EN TIERRA
        # -------------------------------------------------------
        if self.state == "waiting":
            # 🆕 al estar en tierra, consideramos resuelta la emergencia
            if self.emergencia:
                self.emergencia = False
                # si quieres, baja la prioridad a "retrasado" o normal
                if self.prioridad == 2:
                    self.prioridad = 1

            self.wait_time -= 1
            if self.wait_time <= 0:
                self.state = "queued_departure"
                self.model.departure_queue.append(self)
            return

        # -------------------------------------------------------
        # 4) COLA DESPEGUE
        # -------------------------------------------------------
        if self.state == "queued_departure":
            return

        # -------------------------------------------------------
        # 5) DESPEGANDO
        # -------------------------------------------------------
        if self.state == "departing":
            # 🆕 AL DESPEGAR: limpiar emergencia para que el front lo pinte blanco
            if self.emergencia:
                self.emergencia = False
            # opcional: limpiar prioridad máxima
            if self.prioridad == 2:
                self.prioridad = 1
            # opcional: ya no tiene sentido el blink en salida
            self.goaround_blink = 0

            self.move_towards(self.exit_target)
            if self.pos == self.exit_target:
                self.state = "gone"
                self.model.total_departures += 1
                self.model.remove_plane(self)
            return

        # -------------------------------------------------------
        # 6) DESVIADO
        # -------------------------------------------------------
        if self.state == "diverted":
            self.move_towards(self.exit_target)
            if self.pos == self.exit_target:
                self.model.remove_plane(self)
            return
