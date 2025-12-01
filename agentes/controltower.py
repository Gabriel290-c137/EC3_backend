from mesa import Agent

class ControlTower(Agent):
    """
    Torre de Control:
    - Ordena la cola de aviones en holding usando criterios multicriterio
        (prioridad, combustible, tiempo de espera, orden de llegada).
    - Autoriza quién baja de la órbita (holding -> arriving).
    - Asigna pistas a la cola de despegue (departure_queue).

    Convención de prioridad en los aviones:
        prioridad = 0 -> normal
        prioridad = 1 -> retrasado (porque fue desplazado por una emergencia)
        prioridad = 2 -> emergencia
    """

    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)

    # --------------------------
    #  AYUDA: marcar retrasados
    # --------------------------
    def _marcar_retrasados_por_emergencia(self):
        """
        Si hay al menos una emergencia en holding,
        todos los demás aviones que están esperando en holding
        pasan a ser 'retrasados' (prioridad = 1) si no son emergencia.
        """
        m = self.model
        if not m.holding_planes:
            return

        hay_emergencia = any(
            getattr(p, "emergencia", False) for p in m.holding_planes
        )
        if not hay_emergencia:
            return

        for p in m.holding_planes:
            if not getattr(p, "emergencia", False):
                # si no es emergencia, lo marcamos al menos como retrasado
                if getattr(p, "prioridad", 0) < 2:
                    p.prioridad = 1

    # --------------------------
    #  PRIORIDAD DE ATERRIZAJE
    # --------------------------
    def programar_aterrizaje(self, aviones_en_espera):
        """
        Ordena los aviones en holding según:
        1) Mayor prioridad (2 emergencia, 1 retrasado, 0 normal)
        2) Menos combustible restante
        3) Mayor tiempo en holding
        4) Aproximación al orden de llegada (unique_id)
        """
        def clave(p):
            prioridad = getattr(p, "prioridad", 0)
            combustible = getattr(p, "combustible_restante", 999)
            holding_time = getattr(p, "holding_time", 0)

            return (
                -prioridad,      # 2 > 1 > 0
                combustible,     # menos combustible primero
                -holding_time,   # más tiempo esperando primero
                p.unique_id,     # desempate estable
            )

        return sorted(aviones_en_espera, key=clave)

    # --------------------------
    #  GESTIÓN DE LLEGADAS
    # --------------------------
    def gestionar_llegadas(self):
        m = self.model

        capacidad_libre = m.max_ground - m.planes_on_ground()
        if capacidad_libre <= 0 or not m.holding_planes:
            return

        # Primero marcamos retrasados si hay alguna emergencia
        self._marcar_retrasados_por_emergencia()

        # Ordenar por prioridad y criterios secundarios
        m.holding_planes = self.programar_aterrizaje(m.holding_planes)

        n_a_liberar = min(
            capacidad_libre,
            m.max_release_per_step,
            len(m.holding_planes),
        )

        for _ in range(n_a_liberar):
            plane = m.holding_planes.pop(0)
            if plane.state == "holding":
                plane.state = "arriving"
                plane.holding_time = 0  # reiniciar su temporizador de holding

    # --------------------------
    #  GESTIÓN DE SALIDAS
    # --------------------------
    def gestionar_salidas(self):
        m = self.model

        for rw in m.runways:
            if not rw["busy"] and m.departure_queue:
                plane = m.departure_queue.pop(0)
                rw["busy"] = True
                rw["remaining"] = m.takeoff_time
                rw["plane"] = plane
                plane.state = "departing"

    # --------------------------
    #  STEP DE LA TORRE
    # --------------------------
    def step(self):
        # La torre cada tick:
        # 1) Ordena y libera de holding (aterrizajes)
        # 2) Asigna pistas a despegues
        self.gestionar_llegadas()
        self.gestionar_salidas()
