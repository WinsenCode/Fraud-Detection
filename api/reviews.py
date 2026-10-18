from contextlib import contextmanager
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from src.data import connect

router = APIRouter(prefix ='/reviews', tags = ['Reviews'])

class ReviewInput(BaseModel):
    model_config = ConfigDict(extra = 'forbid', strict = True)
    transaction_id: int = Field(ge = 0, le = 9223372036854775807)
    model_version: str = Field(min_length = 1, max_length = 100)
    action: Literal['Review', 'Escalate', 'Close']

class ReviewRecord(ReviewInput):
    review_id: int

@contextmanager
def review_cursor():
    try:
        with connect() as connection:
            if connection.info.dbname != 'fraud_detection_database':
                raise HTTPException(
                    status_code = 503,
                    detail = 'Review storage requires fraud_detection_database.'
                )
            with connection.cursor(row_factory = dict_row) as cursor:
                yield cursor
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable) as exc:
        raise HTTPException(
            status_code = 503,
            detail = (
                'Review storage is unavailable. Check PostgreSQL, '
                'connection settings, and the fraud.review_events table.'
            )
        ) from exc

@router.post('', response_model = ReviewRecord, status_code = 201)
def save_review(payload: ReviewInput, request: Request):
    current_version = request.app.state.scorer.version

    if payload.model_version != current_version:
        raise HTTPException(
            status_code = 409,
            detail = 'Model version does not match the loaded model.'
        )
    with review_cursor() as cursor:
        transaction = cursor.execute(
            '''
            SELECT transaction_id
            FROM fraud.transactions
            WHERE transaction_id = %s
            ''',
            (payload.transaction_id,)
        ).fetchone()
        if transaction is None:
            raise HTTPException(
                status_code = 404,
                detail = 'Transaction was not found in the fraud database.'
            )
        saved = cursor.execute(
            '''
            INSERT INTO fraud.review_events (
                transaction_id,
                model_version,
                action
            )
            VALUES (%s, %s, %s)
            RETURNING
                review_id,
                transaction_id,
                model_version,
                action
            ''',
            (
                payload.transaction_id,
                payload.model_version,
                payload.action
            )
        ).fetchone()
    return saved

@router.get('/{transaction_id}', response_model = list[ReviewRecord])
def get_reviews(
    request: Request,
    transaction_id: int = Path(ge = 0, le = 9223372036854775807),
    model_version: str | None = Query(default = None, min_length = 1),
    limit: int = Query(default = 100, ge = 1, le = 100)
):
    version = (
        model_version
        if model_version is not None
        else request.app.state.scorer.version
    )
    with review_cursor() as cursor:
        reviews = cursor.execute(
            '''
            SELECT
                review_id,
                transaction_id,
                model_version,
                action
            FROM fraud.review_events
            WHERE transaction_id = %s
              AND model_version = %s
            ORDER BY review_id DESC
            LIMIT %s
            ''',
            (transaction_id, version, limit)
        ).fetchall()
    return reviews

@router.get("", response_model=list[ReviewRecord])
def get_latest_reviews(
    request: Request,
    model_version: str | None = Query(default=None, min_length=1)
):
    version = (
        model_version
        if model_version is not None
        else request.app.state.scorer.version
    )

    with review_cursor() as cursor:
        reviews = cursor.execute(
            """
            SELECT DISTINCT ON (transaction_id)
                review_id,
                transaction_id,
                model_version,
                action
            FROM fraud.review_events
            WHERE model_version = %s
            ORDER BY transaction_id, review_id DESC
            """,
            (version,)
        ).fetchall()

    return reviews