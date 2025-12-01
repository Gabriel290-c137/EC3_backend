# server.py
from mesa.visualization.ModularVisualization import ModularServer
from mesa.visualization.modules import CanvasGrid, TextElement, ChartModule
from mesa.visualization.UserParam import UserSettableParameter

from model import AirportModel
from agentes.airport import Airport
from agentes.airplane import Airplane

# ================================================================
#   EMOJIS DE CLIMA (solo para el panel)
# ================================================================
CLIMA_EMOJI = {
    "normal": "☀️",
    "lluvia": "🌧️",
    "tormenta": "⛈️",
    "viento_fuerte": "💨",
    "niebla": "🌫️",
    "microburst": "🌀",
}


# ================================================================
#   PORTRAYAL
# ================================================================
def portrayal(agent):

    # Aeropuerto (cuadrado negro)
    if isinstance(agent, Airport):
        return {
            "Shape": "rect",
            "Color": "black",
            "Filled": True,
            "w": 0.9,
            "h": 0.9,
            "Layer": 0,
        }

    # Aviones
    if isinstance(agent, Airplane):
        # Color base según aerolínea
        base_color = agent.airline.color

        # 1️⃣ GO-AROUND → morado (parpadeo unos ticks)
        if getattr(agent, "goaround_blink", 0) > 0:
            agent.goaround_blink -= 1
            color = "purple"

        # 2️⃣ Emergencias → ROJO (domina sobre todo)
        elif getattr(agent, "emergencia", False):
            color = "red"

        # 3️⃣ Holding (si no está en emergencia)
        elif agent.state == "holding":
            color = "orange"

        # 4️⃣ Despegando
        elif agent.state == "departing":
            color = "black"

        # 5️⃣ Desviado
        elif agent.state == "diverted":
            color = "gray"

        # 6️⃣ Normal (color según aerolínea)
        else:
            color = base_color

        return {
            "Shape": "circle",
            "Color": color,
            "Filled": True,
            "r": 0.6,
            "Layer": 1,
        }

    return {}


# ================================================================
#   PANEL DE INFORMACIÓN
# ================================================================
class InfoPanel(TextElement):
    def render(self, model):
        en_sistema = len(model.planes)
        llegadas = model.total_arrivals
        salidas = model.total_departures
        desviados = model.total_diverted
        emergencias = sum(1 for p in model.planes if getattr(p, "emergencia", False))

        desvio_on = "ON" if getattr(model, "allow_diversion", False) else "OFF"
        escenario = getattr(model, "scenario", "N/A")

        # 🔹 Clima actual
        clima_actual = getattr(model, "clima_actual", "normal")
        emoji_clima = CLIMA_EMOJI.get(clima_actual, "❓")

        return (
            f"Escenario: {escenario} | "
            f"Aviones en sistema: {en_sistema} | "
            f"Llegadas: {llegadas} | Salidas: {salidas} | "
            f"Emergencias: {emergencias} | "
            f"Desviados: {desviados} | "
            f"Desvíos: {desvio_on} | "
            f"Clima: {emoji_clima} {clima_actual}"
        )


# ================================================================
#   GRID Y GRÁFICAS
# ================================================================
grid = CanvasGrid(portrayal, 20, 20, 500, 500)
info_panel = InfoPanel()

chart = ChartModule(
    [
        {"Label": "Llegadas", "Color": "blue"},
        {"Label": "Salidas", "Color": "green"},
        {"Label": "En_espera", "Color": "orange"},
        {"Label": "Emergencias", "Color": "red"},
        {"Label": "Desviados", "Color": "gray"},
    ],
    data_collector_name="datacollector",
)


# ================================================================
#   PARÁMETROS DEL MODELO
# ================================================================
model_params = {
    "scenario": UserSettableParameter(
        "choice",
        "Escenario",
        value="Equilibrio",
        choices=["Equilibrio", "Normal", "Sobrecarga"],
    ),
    "allow_diversion": UserSettableParameter(
        "checkbox",
        "Permitir desvíos",
        False,
    ),
    "max_holding_time": 10,

    # Clima fijo (override manual)
    "clima_manual": UserSettableParameter(
        "choice",
        "Clima fijo (override)",
        value="ninguno",
        choices=[
            "ninguno",      # = no forzar clima
            "normal",
            "lluvia",
            "tormenta",
            "viento_fuerte",
            "niebla",
            "microburst",
        ],
    ),

    # Modo aleatorio por probabilidades
    "usar_probabilidades": UserSettableParameter(
        "checkbox",
        "Clima aleatorio (probabilidades)",
        True,
    ),
}


# ================================================================
#   SERVER
# ================================================================
server = ModularServer(
    AirportModel,
    [grid, info_panel, chart],
    "Airport - Llegadas, Emergencias, Órbita, Salidas y Desvíos",
    model_params,
)

server.launch()
