from pydantic import BaseModel


class DFTResult(BaseModel):
    """
    A Pydantic model to represent the results of a DFT calculation.
    """

    total_energy_ev: float
    forces: list[list[float]]
    stress: list[list[float]]
    was_successful: bool
    error_message: str | None = None


class TrainingConfig(BaseModel):
    """
    A Pydantic model for configuring the MLIP training process.
    """

    model_type: str
    learning_rate: float
    num_epochs: int
    r_cut: float
    delta_learn: bool
    baseline_potential: str
