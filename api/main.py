from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from api.schemas import Transaction, Prediction
from src.inference import FraudScorer
from api.reviews import router as reviews_router

@asynccontextmanager
async def lifespan(app):
    # Fail startup clearly if the trained model is missing or inconsistent.
    app.state.scorer = FraudScorer()
    yield

app = FastAPI(
    title = 'Fraud Investigation MVP',
    version = '1.0.0',
    lifespan = lifespan
)
app.include_router(reviews_router)

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Do not echo input: nonfinite JSON numbers cannot be serialized in a JSON error.
    errors = [{'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]
    return JSONResponse(status_code = 422, content = {'detail': errors})

@app.get('/health')
def health():
    return {'status': 'ok', 'model_version': app.state.scorer.version,
            'feature_count': len(app.state.scorer.metadata['features'])}

@app.post('/predict', response_model = Prediction)
def predict(transaction: Transaction):
    return app.state.scorer.predict(transaction.model_dump())