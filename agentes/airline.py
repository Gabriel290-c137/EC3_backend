# agentes/airline.py
from mesa import Agent

class Airline(Agent):
    """
    Agente Aerolínea con sistema de costos y métricas económicas.
    """
    def __init__(self, unique_id, model, name, code, color):
        super().__init__(unique_id, model)
        self.name = name
        self.code = code
        self.color = color
        self.fleet = []
        
        # ====================================
        # SISTEMA DE COSTOS Y MÉTRICAS
        # ====================================
        
        # Costos acumulados
        self.total_fuel_cost = 0.0           # Costo por combustible desperdiciado
        self.delay_penalties = 0.0           # Penalizaciones por retrasos
        self.diversion_cost = 0.0            # Costo de desvíos
        self.emergency_cost = 0.0            # Costo de emergencias
        
        # Métricas operacionales
        self.total_holding_time = 0          # Tiempo total en holding
        self.completed_flights = 0           # Vuelos completados
        self.active_emergencies = 0          # Emergencias activas
        
        # Historial para análisis
        self.flight_times = []               # Tiempos de vuelo completados
        self.holding_times = []              # Tiempos en holding por vuelo

    def register_plane(self, plane):
        """Asociar un avión a esta aerolínea."""
        self.fleet.append(plane)

    def calculate_costs(self):
        """
        Calcula costos operacionales en tiempo real.
        Retorna un diccionario con el desglose de costos.
        """
        # Resetear costos del tick actual
        fuel_tick = 0
        delay_tick = 0
        emergency_tick = 0
        
        for plane in self.fleet:
            # 1) COSTO DE COMBUSTIBLE EN HOLDING
            if plane.state == "holding":
                # $50 por tick en órbita (combustible desperdiciado)
                fuel_tick += 50
                self.total_holding_time += 1
            
            # 2) PENALIZACIÓN POR RETRASOS
            if plane.prioridad == 1:  # Retrasado
                # $100 por tick retrasado
                delay_tick += 100
            
            # 3) COSTO DE EMERGENCIAS
            if plane.emergencia:
                # $200 por tick en emergencia (recursos adicionales)
                emergency_tick += 200
        
        # Actualizar totales acumulados
        self.total_fuel_cost += fuel_tick
        self.delay_penalties += delay_tick
        self.emergency_cost += emergency_tick
        
        return {
            "fuel": self.total_fuel_cost,
            "delays": self.delay_penalties,
            "diversions": self.diversion_cost,
            "emergencies": self.emergency_cost,
            "total": (self.total_fuel_cost + self.delay_penalties + 
                     self.diversion_cost + self.emergency_cost)
        }
    
    def register_diversion(self):
        """Registra un desvío (costo fijo de $5000)."""
        self.diversion_cost += 5000
    
    def register_completed_flight(self, plane):
        """
        Registra un vuelo completado y sus métricas.
        """
        self.completed_flights += 1
        
        # Registrar tiempo en holding si aplica
        if hasattr(plane, 'holding_time') and plane.holding_time > 0:
            self.holding_times.append(plane.holding_time)
    
    def get_performance_metrics(self):
        """
        Retorna métricas de rendimiento de la aerolínea.
        """
        # Calcular promedios
        avg_holding = (sum(self.holding_times) / len(self.holding_times) 
                      if self.holding_times else 0)
        
        # Tasa de desvío
        total_flights = self.completed_flights + len([p for p in self.fleet if p.state == "diverted"])
        diversion_rate = (len([p for p in self.fleet if p.state == "diverted"]) / 
                         total_flights if total_flights > 0 else 0)
        
        # Eficiencia operacional (vuelos completados vs costos)
        cost_per_flight = (self.calculate_costs()["total"] / 
                          self.completed_flights if self.completed_flights > 0 else 0)
        
        return {
            "avg_holding_time": avg_holding,
            "diversion_rate": diversion_rate * 100,  # En porcentaje
            "cost_per_flight": cost_per_flight,
            "completed_flights": self.completed_flights,
            "efficiency_score": self._calculate_efficiency_score(),
        }
    
    def _calculate_efficiency_score(self):
        """
        Calcula un score de eficiencia (0-100).
        Mayor score = mejor performance.
        """
        if self.completed_flights == 0:
            return 0
        
        # Factores que reducen el score
        diversions = len([p for p in self.fleet if p.state == "diverted"])
        avg_holding = (sum(self.holding_times) / len(self.holding_times) 
                      if self.holding_times else 0)
        
        # Base de 100 puntos
        score = 100
        
        # Penalizaciones
        score -= diversions * 10                    # -10 por cada desvío
        score -= min(avg_holding * 2, 30)           # -2 por cada tick de holding (max -30)
        score -= (self.active_emergencies * 5)      # -5 por emergencia activa
        
        return max(0, min(100, score))  # Mantener entre 0-100
    
    def step(self):
        """
        Ejecuta en cada tick:
        - Calcula costos actuales
        - Actualiza métricas
        - Toma decisiones estratégicas (futuro)
        """
        # Calcular costos del tick
        self.calculate_costs()
        
        # Contar emergencias activas
        self.active_emergencies = sum(1 for p in self.fleet if p.emergencia)
        
        # FUTURO: Aquí podrías agregar lógica de decisión
        # Por ejemplo: solicitar prioridad a la torre, renegociar slots, etc.