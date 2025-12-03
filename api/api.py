# api.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any

from model import AirportModel

# =========================================
#   APP + CORS
# =========================================
app = FastAPI(title="EC3 - API Simulación Aeropuerto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # para desarrollo, luego puedes restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
#   CONFIG / TIPOS
# =========================================
ScenarioType = Literal["Equilibrio", "Normal", "Sobrecarga", "Libre"]
ClimaType = Literal[
    "ninguno",
    "normal",
    "lluvia",
    "tormenta",
    "viento_fuerte",
    "niebla",
    "microburst",
]


class SimulationConfig(BaseModel):
    """
    Configuración que llega desde el frontend
    (equivalente a los UserSettableParameter del server de Mesa).
    """
    scenario: ScenarioType = "Equilibrio"
    allow_diversion: bool = False
    max_holding_time: int = 10
    clima_manual: ClimaType = "ninguno"
    usar_probabilidades: bool = True
    
    # Parámetros granulares (opcionales)
    arrival_rate: Optional[float] = None
    max_ground: Optional[int] = None
    turn_time: Optional[int] = None
    takeoff_time: Optional[int] = None
    max_release_per_step: Optional[int] = None
    
    # Sistema de tiempo
    minutes_per_step: Optional[int] = 5


# =========================================
#   ESTADO GLOBAL DEL MODELO
# =========================================
current_model: Optional[AirportModel] = None
current_step: int = 0


# =========================================
#   SERIALIZADOR → LO QUE CONSUME SVELTE
# =========================================
def serialize_model(m: AirportModel) -> Dict[str, Any]:
    # ---------- AVIONES ----------
    planes_data = []
    for p in m.planes:
        if not hasattr(p, "pos") or p.pos is None:
            continue

        x, y = p.pos
        cx, cy = m.airport_center
        dx = x - cx
        dy = y - cy
        distancia = (dx**2 + dy**2) ** 0.5

        planes_data.append(
            {
                "id": p.unique_id,
                "flight_code": p.flight_code,
                "x": x,
                "y": y,
                "state": p.state,
                "prioridad": p.prioridad,
                "combustible": p.combustible_restante,
                "emergencia": p.emergencia,
                # 👇 para GO-AROUND morado en el front
                "goaround_blink": getattr(p, "goaround_blink", 0),
                "desviado": p.state == "diverted",
                "distancia": distancia,
                "airline": {
                    "name": p.airline.name,
                    "code": p.airline.code,
                    "color": p.airline.color,
                },
            }
        )

    # ---------- AEROLÍNEAS ----------
    airlines_data = []
    for al in m.airlines:
        vuelos = len(al.fleet)
        desvios = sum(
            1
            for p in m.planes
            if p.airline is al and p.state == "diverted"
        )
        airlines_data.append(
            {
                "name": al.name,
                "code": al.code,
                "color": al.color,
                "vuelos": vuelos,
                "desvios": desvios,
                # futuros KPIs:
                "costo": 0,
                "retraso_promedio": 0,
            }
        )

    # ---------- MÉTRICAS GLOBALes (tipo InfoPanel + Chart) ----------
    emergencias = sum(1 for p in m.planes if p.emergencia)
    en_espera = sum(1 for p in m.planes if p.prioridad == 1)

    metrics = {
        # equivalentes a las series del ChartModule
        "total_arrivals": m.total_arrivals,       # Llegadas
        "total_departures": m.total_departures,   # Salidas
        "total_diverted": m.total_diverted,       # Desviados
        "emergencias": emergencias,               # Emergencias
        "en_espera": en_espera,                   # En_espera (prioridad 1)
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

    # ---------- PISTAS ----------
    runways_data = []
    for idx, rw in enumerate(m.runways):
        runways_data.append(
            {
                "id": idx,
                "busy": rw["busy"],
                "remaining": rw["remaining"],
                "plane_id": getattr(rw["plane"], "unique_id", None)
                if rw["plane"] is not None
                else None,
            }
        )

    # ---------- CONFIGURACIÓN ACTUAL ----------
    config = {
        "scenario": m.scenario,
        "allow_diversion": m.allow_diversion,
        "max_holding_time": m.max_holding_time,
        "clima_manual": m.clima_manual,
        "usar_probabilidades": m.usar_probabilidades,
        # Devolver también los valores efectivos
        "arrival_rate": m.arrival_rate,
        "max_ground": m.max_ground,
        "turn_time": m.turn_time,
        "takeoff_time": m.takeoff_time,
        "max_release_per_step": m.max_release_per_step,
    }

    # 🔹 Esto es lo que usará Svelte como SimulationSnapshot
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
    """
    Crea un modelo nuevo con la configuración dada.
    Equivalente a reiniciar el server de Mesa con parámetros.
    """
    global current_model, current_step
    current_model = AirportModel(
        scenario=config.scenario,
        allow_diversion=config.allow_diversion,
        max_holding_time=config.max_holding_time,
        clima_manual=config.clima_manual,
        usar_probabilidades=config.usar_probabilidades,
        # Nuevos parámetros
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
    """
    Avanza N ticks y devuelve el nuevo estado.
    """
    global current_model, current_step
    if current_model is None:
        raise HTTPException(
            400, "Modelo no inicializado. Llama primero a /simulacion/reset."
        )

    if steps < 1:
        steps = 1

    for _ in range(steps):
        current_model.step()
        current_step += 1

    return serialize_model(current_model)


@app.get("/simulacion/estado")
def get_estado():
    """
    Devuelve el estado actual sin avanzar.
    ESTE es el endpoint que “exporta todos tus datos”.
    """
    global current_model
    if current_model is None:
        raise HTTPException(
            400, "Modelo no inicializado. Llama primero a /simulacion/reset."
        )
    return serialize_model(current_model)
