"""Поиск книг в Hardcover: /search?query=God of Fury"""
from fastapi import APIRouter, Query

from hardcover import gql

router = APIRouter()

SEARCH = """
query Search($q: String!) {
  search(query: $q, query_type: "Book", per_page: 10, page: 1) {
    results
  }
}
"""


@router.get("/search")
async def search_books(query: str = Query(min_length=1), debug: bool = False):
    data = await gql(SEARCH, {"q": query})
    if debug:  # «сырой» ответ, чтобы проверить названия полей
        return data

    hits = data["data"]["search"]["results"]["hits"]
    books = []
    for hit in hits:
        doc = hit["document"]
        books.append({
            "title": doc.get("title"),
            "authors": doc.get("author_names"),
            "year": doc.get("release_year"),
            "pages": doc.get("pages"),
            "cover": (doc.get("image") or {}).get("url"),
            "series_names": doc.get("series_names"),
            "series_position": doc.get("featured_series_position"),
            "moods": doc.get("moods"),
            "tags": doc.get("tags"),
            "content_warnings": doc.get("content_warnings"),
            "slug": doc.get("slug"),
        })
    return books
