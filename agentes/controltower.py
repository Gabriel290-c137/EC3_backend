# agentes/controltower.py
from mesa import Agent

class ControlTower(Agent):
    """
    Torre de Control con 3 políticas de secuenciación:
    1. FCFS (First Come First Served) - Asignación fija
    2. FUEL_PRIORITY - Asignación basada solo en combustible
    3. DYNAMIC - Algoritmo multicriterio adaptativo
    """

    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        
        # Estadísticas de la torre
        self.reordenamientos_realizados = 0
        self.emergencias_atendidas = 0
        self.desviaciones_autorizadas = 0

    # ================================================================
    #  ALGORITMO MULTICRITERIO MEJORADO
    # ================================================================
    
    def programar_aterrizaje(self, aviones_en_espera):
        """
        Ordena aviones según la política de control activa.
        
        Políticas disponibles:
        - "fixed" (FCFS): First Come First Served
        - "fuel_priority": Solo por combustible restante
        - "dynamic": Multicriterio adaptativo (RECOMENDADO)
        """
        if not aviones_en_espera:
            return []
        
        policy = getattr(self.model, "control_policy", "dynamic")
        
        # ==========================================
        # POLÍTICA 1: FCFS (Asignación Fija)
        # ==========================================
        if policy == "fixed":
            # Orden de llegada (por ID)
            return sorted(aviones_en_espera, key=lambda p: p.unique_id)
        
        # ==========================================
        # POLÍTICA 2: Prioridad de Combustible
        # ==========================================
        elif policy == "fuel_priority":
            # Menos combustible = mayor prioridad
            def fuel_score(p):
                # Emergencias SIEMPRE primero
                if p.emergencia:
                    return 0  # Máxima prioridad
                return p.combustible_restante  # Menor combustible = menor score
            
            return sorted(aviones_en_espera, key=fuel_score)
        
        # ==========================================
        # POLÍTICA 3: DINÁMICA (Multicriterio)
        # ==========================================
        else:  # "dynamic"
            pesos = self._calcular_pesos_adaptativos()
            
            def calcular_score(p):
                # 1. PRIORIDAD BASE
                prioridad_norm = p.prioridad / 2.0
                
                # 2. COMBUSTIBLE
                combustible_norm = 1.0 - (p.combustible_restante / 120.0)
                combustible_norm = max(0, min(1, combustible_norm))
                
                # 3. TIEMPO EN HOLDING
                holding_norm = min(p.holding_time / 30.0, 1.0)
                
                # 4. ID (FIFO como desempate)
                max_id = max(plane.unique_id for plane in aviones_en_espera)
                id_norm = p.unique_id / max_id if max_id > 0 else 0
                
                # 🆕 5. TIPO DE AERONAVE
                type_weight = p.get_type_priority_weight()  # Heavy = 1.2, Medium = 1.0, Small = 0.8
                
                # 🆕 6. PUNTUALIDAD
                punctuality_bonus = 0
                if p.punctuality_status == "delayed":
                    punctuality_bonus = 0.1  # Bonus para retrasados
                elif p.punctuality_status == "early":
                    punctuality_bonus = -0.05  # Penalización para adelantados
                
                # Score combinado
                base_score = (
                    prioridad_norm * pesos["prioridad"] +
                    combustible_norm * pesos["combustible"] +
                    holding_norm * pesos["holding"] +
                    id_norm * pesos["fifo"]
                )
                
                # Aplicar modificadores
                final_score = base_score * type_weight + punctuality_bonus
                
                return final_score
            
            # ==========================================
            # PASO 4: Ordenar de mayor a menor score
            # ==========================================
            
            ordenado = sorted(aviones_en_espera, key=calcular_score, reverse=True)
            
            if ordenado != aviones_en_espera:
                self.reordenamientos_realizados += 1
            
            return ordenado
        
    
    def _calcular_pesos_adaptativos(self):
        """
        Calcula pesos dinámicos basados en el estado actual del sistema.
        
        Retorna: dict con pesos para cada criterio (suman 1.0)
        """
        m = self.model
        
        # Contar emergencias activas
        emergencias_activas = sum(1 for p in m.holding_planes if p.emergencia)
        
        # Nivel de congestión (0.0 = vacío, 1.0 = saturado)
        congestion = len(m.holding_planes) / max(m.max_ground * 2, 1)
        
        # ==========================================
        # ESCENARIO 1: Clima extremo (tormenta/microburst)
        # ==========================================
        if m.clima_actual in ["tormenta", "microburst"]:
            return {
                "prioridad": 0.45,      # Enfoque en emergencias
                "combustible": 0.35,    # Combustible crítico
                "holding": 0.15,        # Menos peso a tiempo
                "fifo": 0.05,
            }
        
        # ==========================================
        # ESCENARIO 2: Hay emergencias activas
        # ==========================================
        elif emergencias_activas > 0:
            return {
                "prioridad": 0.40,
                "combustible": 0.35,
                "holding": 0.20,
                "fifo": 0.05,
            }
        
        # ==========================================
        # ESCENARIO 3: Alta congestión
        # ==========================================
        elif congestion > 0.7:
            return {
                "prioridad": 0.25,
                "combustible": 0.25,
                "holding": 0.40,        # Priorizar quien más tiempo lleva
                "fifo": 0.10,
            }
        
        # ==========================================
        # ESCENARIO 4: Operación normal
        # ==========================================
        else:
            return {
                "prioridad": 0.30,
                "combustible": 0.30,
                "holding": 0.30,
                "fifo": 0.10,
            }

    # ================================================================
    #  GESTIÓN DE LLEGADAS (con marcado de retrasados)
    # ================================================================
    
    def _marcar_retrasados_por_emergencia(self):
        """
        Si hay emergencia(s) en holding, marca a los demás como retrasados.
        """
        m = self.model
        if not m.holding_planes:
            return

        hay_emergencia = any(p.emergencia for p in m.holding_planes)
        if not hay_emergencia:
            return

        for p in m.holding_planes:
            if not p.emergencia and p.prioridad < 1:
                p.prioridad = 1  # Marcar como retrasado

    def gestionar_llegadas(self):
        """
        Libera aviones de holding hacia aterrizaje según capacidad disponible.
        """
        m = self.model

        capacidad_libre = m.max_ground - m.planes_on_ground()
        if capacidad_libre <= 0 or not m.holding_planes:
            return

        # Marcar retrasados si hay emergencias
        self._marcar_retrasados_por_emergencia()

        # Ordenar con algoritmo mejorado
        m.holding_planes = self.programar_aterrizaje(m.holding_planes)

        # Liberar los N primeros según capacidad
        n_a_liberar = min(
            capacidad_libre,
            m.max_release_per_step,
            len(m.holding_planes),
        )

        for _ in range(n_a_liberar):
            plane = m.holding_planes.pop(0)
            if plane.state == "holding":
                plane.state = "arriving"
                plane.holding_time = 0
                
                # Registrar si era emergencia
                if plane.emergencia:
                    self.emergencias_atendidas += 1

    # ================================================================
    #  GESTIÓN DE SALIDAS
    # ================================================================
    
    def gestionar_salidas(self):
        """
        Asigna pistas disponibles a aviones en cola de despegue.
        """
        m = self.model

        for rw in m.runways:
            if not rw["busy"] and m.departure_queue:
                plane = m.departure_queue.pop(0)
                rw["busy"] = True
                rw["remaining"] = m.takeoff_time
                rw["plane"] = plane
                plane.state = "departing"

    # ================================================================
    #  STEP DE LA TORRE
    # ================================================================
    
    def step(self):
        """
        Ejecuta cada tick:
        1. Gestiona llegadas (ordena y libera de holding)
        2. Gestiona salidas (asigna pistas)
        """
        self.gestionar_llegadas()
        self.gestionar_salidas()
    
    # ================================================================
    #  MÉTRICAS DE LA TORRE
    # ================================================================
    
    def get_statistics(self):
        """
        Retorna estadísticas de performance de la torre.
        """
        return {
            "reordenamientos": self.reordenamientos_realizados,
            "emergencias_atendidas": self.emergencias_atendidas,
            "desviaciones": self.desviaciones_autorizadas,
            "eficiencia": self._calcular_eficiencia_torre(),
            "policy": getattr(self.model, "control_policy", "dynamic"),  # 🆕
        }
    
    def _calcular_eficiencia_torre(self):
        """
        Calcula eficiencia de la torre (0-100).
        Considera: throughput, emergencias manejadas, retrasos evitados.
        """
        m = self.model
        
        if m.schedule.steps == 0:
            return 100
        
        # Base de 100 puntos
        score = 100
        
        # Penalizaciones
        tasa_desvio = (m.total_diverted / max(m.total_arrivals, 1)) * 100
        score -= tasa_desvio * 2  # -2 por cada % de desvíos
        
        # Bonus por emergencias bien manejadas
        if self.emergencias_atendidas > 0:
            score += min(self.emergencias_atendidas * 5, 20)
        
        return max(0, min(100, score))