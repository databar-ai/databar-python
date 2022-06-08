from typing import Any, Dict, List, NamedTuple, Optional
from urllib.parse import urljoin

import requests

from .helpers import raise_for_status, timed_lru_cache
from .table import Table


class PaginatedResponse(NamedTuple):
    page: int
    has_next_page: bool
    data: List[Dict[str, Any]]


class Connection:
    def __init__(self, api_key: str):
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Token {api_key}"})
        self._base_url = "https://databar.ai/api/"

        try:
            self.get_plan_info()
        except requests.HTTPError as exc:
            if exc.response.status_code in (401, 403):
                raise ValueError("Incorrect api_key, get correct one from your account")

    @timed_lru_cache
    def get_plan_info(self):
        response = self._session.get(urljoin(self._base_url, "v2/users/plan-info/"))
        raise_for_status(response)
        return response.json()

    def list_of_api_keys(self, page=1, api_id: Optional[int] = None):
        params = {
            "page": page,
            "per_page": 100,
        }
        if api_id is not None:
            params["api"] = api_id
        response = self._session.get(
            urljoin(self._base_url, "v1/apikey"),
            params=params,
        )
        raise_for_status(response)
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            data=response_json["results"],
            has_next_page=bool(response_json["next"]),
        )

    def list_of_sources(
        self, page=1, search: Optional[str] = None
    ) -> PaginatedResponse:
        params = {
            "page": page,
            "per_page": 100,
        }
        if search is not None:
            params["search"] = search

        response = self._session.get(
            urljoin(self._base_url, "v2/sources/lite-list/"),
            params=params,
        )
        raise_for_status(response)
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            data=response_json["results"],
            has_next_page=bool(response_json["next"]),
        )

    def list_of_datasets(
        self, page=1, search: Optional[str] = None, api_id: Optional[int] = None
    ) -> PaginatedResponse:
        params = {
            "page": page,
            "per_page": 100,
        }
        if search is not None:
            params["search"] = search
        if api_id is not None:
            params["api"] = api_id

        response = self._session.get(
            urljoin(self._base_url, "v2/datasets/lite-list/"),
            params=params,
        )
        raise_for_status(response)
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            data=response_json["results"],
            has_next_page=bool(response_json["next"]),
        )

    def list_of_tables(self, page=1):
        params = {
            "page": page,
            "per_page": 100,
        }
        response = self._session.get(
            urljoin(self._base_url, "v2/tables"),
            params=params,
        )
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            has_next_page=bool(response_json["next"]),
            data=response_json["results"],
        )

    def create_table_via_dataset(self, dataset_id: int):
        raise_for_status(
            self._session.get(urljoin(self._base_url, f"v1/dataset/{dataset_id}/"))
        )

        response = self._session.post(
            urljoin(self._base_url, "v2/tables/create-using-dataset/"),
            json={
                "dataset": dataset_id,
            },
        )
        raise_for_status(response)
        response_as_json = response.json()

        table = Table(tid=response_as_json["id"], session=self._session)
        return table

    def get_table(self, table_id: int):
        return Table(session=self._session, tid=table_id)

    def calculate_price_of_request(
        self,
        dataset_id: int,
        params: Dict[str, Any],
        pagination: Optional[int] = None,
    ) -> float:
        params = {"params": [params]}
        if pagination is not None:
            params["rows_or_pages"] = pagination

        response = self._session.post(
            urljoin(self._base_url, f"v2/datasets/{dataset_id}/pricing-calculate/"),
            json=params,
        )
        raise_for_status(response)
        return response.json()["total_cost"]
