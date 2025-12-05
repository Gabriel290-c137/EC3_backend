# api/api.py - VERSIÓN MEJORADA
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any, List

from model import AirportModel

app = FastAPI(title="EC3 - API Simulación Aeropuerto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ScenarioType = Literal["Equilibrio", "Normal", "Sobrecarga", "Libre"]
ClimaType = Literal[
    "ninguno", "normal", "lluvia", "tormenta", "viento_fuerte", "niebla", "microburst"
]

class SimulationConfig(BaseModel):
    scenario: ScenarioType = "Equilibrio"
    allow_diversion: bool = False
    max_holding_time: int = 10
    clima_manual: ClimaType = "ninguno"
    usar_probabilidades: bool = True
    arrival_rate: Optional[float] = None
    max_ground: Optional[int] = None
    turn_time: Optional[int] = None
    takeoff_time: Optional[int] = None
    max_release_per_step: Optional[int] = None
    minutes_per_step: Optional[int] = 5

current_model: Optional[AirportModel] = None
current_step: int = 0

# =========================================
#   SERIALIZADOR MEJORADO
# =========================================
def serialize_model(m: AirportModel) -> Dict[str, Any]:
    # Aviones
    planes_data = []
    for p in m.planes:
        if not hasattr(p, "pos") or p.pos is None:
            continue

        x, y = p.pos
        cx, cy = m.airport_center
        dx = x - cx
        dy = y - cy
        distancia = (dx**2 + dy**2) ** 0.5

        planes_data.append({
            "id": p.unique_id,
            "flight_code": p.flight_code,
            "x": x,
            "y": y,
            "state": p.state,
            "prioridad": p.prioridad,
            "combustible": p.combustible_restante,
            "emergencia": p.emergencia,
            "goaround_blink": getattr(p, "goaround_blink", 0),
            "desviado": p.state == "diverted",
            "distancia": distancia,
            "holding_time": getattr(p, "holding_time", 0),
            "airline": {
                "name": p.airline.name,
                "code": p.airline.code,
                "color": p.airline.color,
            },
        })

    # Aerolíneas CON MÉTRICAS DE PERFORMANCE
    airlines_data = []
    for al in m.airlines:
        costs = al.calculate_costs()
        perf = al.get_performance_metrics()
        
        vuelos = len(al.fleet)
        desvios = sum(1 for p in m.planes if p.airline is al and p.state == "diverted")
        
        airlines_data.append({
            "name": al.name,
            "code": al.code,
            "color": al.color,
            "vuelos": vuelos,
            "desvios": desvios,
            # NUEVAS MÉTRICAS
            "costos": costs,
            "performance": perf,
        })

    # Métricas globales
    emergencias = sum(1 for p in m.planes if p.emergencia)
    en_espera = sum(1 for p in m.planes if p.prioridad == 1)

    # MÉTRICAS AVANZADAS
    advanced_metrics = {
        "throughput": m.get_throughput(),
        "runway_utilization": m.get_runway_utilization(),
        "avg_holding_time": m.get_avg_holding_time(),
        "fuel_efficiency": m.get_fuel_efficiency(),
        "emergency_rate": m.get_emergency_rate(),
    }

    # Torre de control
    tower_stats = m.control_tower.get_statistics()

    metrics = {
        # Básicas
        "total_arrivals": m.total_arrivals,
        "total_departures": m.total_departures,
        "total_diverted": m.total_diverted,
        "emergencias": emergencias,
        "en_espera": en_espera,
        
        # Avanzadas
        "advanced": advanced_metrics,
        
        # Torre
        "tower": tower_stats,
        
        # Clima y tiempo
        "clima": {
            "tipo": m.clima_actual,
            "factor": m.factor_clima,
        },
        "time": {
            "hour": m.current_hour,
            "minute": m.current_minute,
            "period": m.get_time_period(),
        },
    }

    # Pistas
    runways_data = []
    for idx, rw in enumerate(m.runways):
        runways_data.append({
            "id": idx,
            "busy": rw["busy"],
            "remaining": rw["remaining"],
            "plane_id": getattr(rw["plane"], "unique_id", None) if rw["plane"] else None,
        })

    # Config actual
    config = {
        "scenario": m.scenario,
        "allow_diversion": m.allow_diversion,
        "max_holding_time": m.max_holding_time,
        "clima_manual": m.clima_manual,
        "usar_probabilidades": m.usar_probabilidades,
        "arrival_rate": m.arrival_rate,
        "max_ground": m.max_ground,
        "turn_time": m.turn_time,
        "takeoff_time": m.takeoff_time,
        "max_release_per_step": m.max_release_per_step,
    }

    return {
        "step": m.schedule.steps,
        "config": config,
        "planes": planes_data,
        "airlines": airlines_data,
        "metrics": metrics,
        "runways": runways_data,
    }

# =========================================
#   ENDPOINTS
# =========================================

@app.post("/simulacion/reset")
def reset_simulacion(config: SimulationConfig):
    global current_model, current_step
    current_model = AirportModel(
        scenario=config.scenario,
        allow_diversion=config.allow_diversion,
        max_holding_time=config.max_holding_time,
        clima_manual=config.clima_manual,
        usar_probabilidades=config.usar_probabilidades,
        arrival_rate=config.arrival_rate,
        max_ground=config.max_ground,
        turn_time=config.turn_time,
        takeoff_time=config.takeoff_time,
        max_release_per_step=config.max_release_per_step,
        minutes_per_step=config.minutes_per_step or 5,
    )
    current_step = 0
    return serialize_model(current_model)

@app.post("/simulacion/step")
def step_simulacion(steps: int = 1):
    global current_model, current_step
    if current_model is None:
        raise HTTPException(400, "Modelo no inicializado")

    if steps < 1:
        steps = 1

    for _ in range(steps):
        current_model.step()
        current_step += 1

    return serialize_model(current_model)

@app.get("/simulacion/estado")
def get_estado():
    global current_model
    if current_model is None:
        raise HTTPException(400, "Modelo no inicializado")
    return serialize_model(current_model)

# =========================================
#   NUEVO: ENDPOINT DE EXPORTACIÓN
# =========================================

@app.get("/simulacion/export")
def export_data():
    """
    Exporta datos históricos de la simulación para análisis.
    Ideal para generar gráficas en Excel/Python.
    """
    if current_model is None:
        raise HTTPException(400, "No hay simulación activa")
    
    try:
        df_data = current_model.datacollector.get_model_vars_dataframe()
        
        # Convertir a listas para JSON
        export = {
            "steps": df_data.index.tolist(),
            "llegadas": df_data["Llegadas"].tolist(),
            "salidas": df_data["Salidas"].tolist(),
            "emergencias": df_data["Emergencias"].tolist(),
            "desviados": df_data["Desviados"].tolist(),
            "en_espera": df_data["En_espera"].tolist(),
            
            # NUEVAS MÉTRICAS
            "aviones_en_holding": df_data["Aviones_en_holding"].tolist(),
            "tiempo_holding_promedio": df_data["Tiempo_holding_promedio"].tolist(),
            "utilizacion_pistas": df_data["Utilizacion_pistas"].tolist(),
            "throughput": df_data["Throughput"].tolist(),
            "eficiencia_combustible": df_data["Eficiencia_combustible"].tolist(),
            "tasa_emergencias": df_data["Tasa_emergencias"].tolist(),
        }
        
        return export
    except Exception as e:
        raise HTTPException(500, f"Error al exportar datos: {str(e)}")

# =========================================
#   NUEVO: ANÁLISIS COMPARATIVO
# =========================================

@app.get("/simulacion/summary")
def get_summary():
    """
    Retorna un resumen ejecutivo de la simulación actual.
    Útil para el informe final.
    """
    if current_model is None:
        raise HTTPException(400, "No hay simulación activa")
    
    m = current_model
    
    # Calcular KPIs principales
    total_flights = m.total_arrivals + m.total_departures
    success_rate = (m.total_departures / total_flights * 100) if total_flights > 0 else 0
    diversion_rate = (m.total_diverted / total_flights * 100) if total_flights > 0 else 0
    
    # Performance de aerolíneas
    best_airline = None
    best_score = 0
    
    for al in m.airlines:
        perf = al.get_performance_metrics()
        if perf["efficiency_score"] > best_score:
            best_score = perf["efficiency_score"]
            best_airline = al.name
    
    return {
        "scenario": m.scenario,
        "total_steps": m.schedule.steps,
        "horas_simuladas": (m.schedule.steps * m.minutes_per_step) / 60,
        
        "kpis": {
            "total_flights": total_flights,
            "success_rate": round(success_rate, 2),
            "diversion_rate": round(diversion_rate, 2),
            "throughput": round(m.get_throughput(), 2),
            "runway_utilization": round(m.get_runway_utilization(), 2),
            "avg_holding_time": round(m.get_avg_holding_time(), 2),
        },
        
        "best_airline": {
            "name": best_airline,
            "score": round(best_score, 2),
        },
        
        "tower_performance": m.control_tower.get_statistics(),
    }