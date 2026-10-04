"""Общий клиент Hardcover: токен и запрос к API. Все остальные файлы используют gql()."""
import os

import httpx
from fastapi import HTTPException

URL = "https://api.hardcover.app/v1/graphql"


async def gql(query: str, variables: dict | None = None) -> dict:
    token = os.getenv("HARDCOVER_TOKEN")
    if not token:
        raise HTTPException(500, "Не задана переменная HARDCOVER_TOKEN")
    if not token.lower().startswith("bearer "):
        token = "Bearer " + token

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            URL,
            json=payload,
            headers={"Authorization": token, "User-Agent": "BookApp/0.1 (personal)"},
        )
    response.raise_for_status()
    return response.json()
