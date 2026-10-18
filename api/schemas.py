from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[float, Field(allow_inf_nan = False)]
Text = Annotated[str, Field(min_length = 1, max_length = 200)]

class Transaction(BaseModel):
    model_config = ConfigDict(extra = 'forbid', strict = True)
    transaction_id: Annotated[int, Field(ge = 0)]
    transaction_dt: Annotated[int, Field(ge = 0)]  # Metadata only; never a feature.
    transaction_amt: Annotated[Number, Field(ge = 0)]
    dist1: Number | None
    c1: Number | None
    c2: Number | None
    c6: Number | None
    c11: Number | None
    c13: Number | None
    c14: Number | None
    d1: Number | None
    d2: Number | None
    d3: Number | None
    d10: Number | None
    d15: Number | None
    id_02: Number | None
    product_cd: Literal['W', 'C', 'R', 'H', 'S']
    card1: Text | None
    card2: Text | None
    card4: Text | None
    card6: Text | None
    addr1: Text | None
    p_emaildomain: Text | None
    r_emaildomain: Text | None
    device_type: Text | None
    id_12: Text | None
    id_15: Text | None

class Factor(BaseModel):
    feature: str
    value: str | float | None
    contribution: float

class Prediction(BaseModel):
    transaction_id: int
    risk_score: Annotated[float, Field(ge = 0, le = 1)]
    is_alert: bool
    threshold: float
    threshold_operator: Literal['>']
    model_version: str
    contribution_unit: Literal['raw_log_odds']
    expected_log_odds: float
    top_factors: list[Factor]