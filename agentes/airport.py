from mesa import Agent

class Airport(Agent):
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)

    def step(self):
        # El aeropuerto no se mueve
        pass
