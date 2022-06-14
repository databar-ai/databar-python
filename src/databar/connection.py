from typing import Any, Dict, List, NamedTuple, Optional
from urllib.parse import urljoin

import requests

from .helpers import raise_for_status, timed_lru_cache
from .table import Table


class PaginatedResponse(NamedTuple):
    """
    Result of request where pagination is used.

    :param page: Requested page number.
    :param has_next_page: Boolean field to determine if there are more data.
    :param data: Result of request. List of sources|datasets|api-keys|tables.
    """

    page: int
    has_next_page: bool
    data: List[Dict[str, Any]]


class Connection:
    def __init__(self, api_key: str) -> None:
        """
        Init the connection.

        If api_key is incorrect, :class:`ValueError` will be raised.

        :param api_key: Api key from databar.ai
        """
        self._session = requests.Session()
        self._session.headers.update({"X-APIKey": f"{api_key}"})
        self._base_url = "https://databar.ai/api/"

        try:
            self.get_plan_info()
        except requests.HTTPError as exc:
            if exc.response.status_code in (401, 403):
                raise ValueError("Incorrect api_key, get correct one from your account")

    @timed_lru_cache
    def get_plan_info(self) -> None:
        """
        Returns info about your plan. Namely, amount of credits, used storage size,
        total storage size, count of created tables. The result of this method
        is cached for 5 minutes.
        """

        response = self._session.get(urljoin(self._base_url, "v2/users/plan-info/"))
        raise_for_status(response)
        return response.json()

    def list_of_sources(
        self, page: int = 1, search: Optional[str] = None
    ) -> PaginatedResponse:
        """
        Returns a list of available sources using pagination.
        One page stores 100 records.

        :param page: Page you want to retrieve. Default is 1.
        :param search: Search query you want to apply, for example, Coingecko. Optional.
        """

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
        self,
        page: int = 1,
        search: Optional[str] = None,
        source_id: Optional[int] = None,
    ) -> PaginatedResponse:
        """
        Returns a list of available datasets using pagination.
        One page stores 100 records.

        :param page: Page you want to retrieve. Default is 1.
        :param search: Search query you want to apply, for example, Coingecko. Optional.
        :param source_id: Id of source to filter datasets. Can be retrieved from
            :func:`~Connection.list_of_sources`. If it's passed, then will be returned
            only datasets of specific source. Optional.
        """

        params = {
            "page": page,
            "per_page": 100,
        }
        if search is not None:
            params["search"] = search
        if source_id is not None:
            params["api"] = source_id

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

    def list_of_api_keys(
        self, page: int = 1, source_id: Optional[int] = None
    ) -> PaginatedResponse:
        """
        Returns a list of api keys using pagination. One page stores 100 records.

        :param page: Page you want to retrieve. Default is 1.
        :param source_id: Id of source to filter api keys. Can be retrieved from
            :func:`~Connection.list_of_sources`. If it's passed, then will be returned
            only api keys of specific source. Optional.
        """

        params = {
            "page": page,
            "per_page": 100,
        }
        if source_id is not None:
            params["api"] = source_id
        response = self._session.get(
            urljoin(self._base_url, "v2/apikeys"),
            params=params,
        )
        raise_for_status(response)
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            data=response_json["results"],
            has_next_page=bool(response_json["next"]),
        )

    def list_of_tables(self, page: int = 1) -> PaginatedResponse:
        """
        Returns list of your tables using pagination. One page stores 100 records.

        :param page: Page you want retrieve. Default is 1.
        """
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

    def get_table(self, table_id: int) -> Table:
        """
        Returns specific table.

        :param table_id: Table id you want to get. List of tables can be retrieved
            using :func:`~Connection.list_of_tables` method.
        """
        return Table(session=self._session, tid=table_id)

    def create_table_via_dataset(self, dataset_id: int) -> Table:
        """Creates table via dataset."""

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

    def get_params_of_dataset(self, dataset_id: int) -> Dict[str, Any]:
        """
        Returns parameters of dataset. The result is info about authorization,
        pagination, query parameters of dataset.
        """

        response = self._session.get(
            urljoin(self._base_url, f"v2/datasets/{dataset_id}/params/"),
        )
        raise_for_status(response)
        return response.json()

    def calculate_price_of_request(
        self,
        dataset_id: int,
        params: Dict[str, Any],
        pagination: Optional[int] = None,
    ) -> float:
        """
        Calculates price of request in credits.

        :param dataset_id: Id of dataset you want to calculate price.
        :param params: Parameters which must be formed in according to dataset.
            Can be retrieved from :func:`~Connection.get_params_of_dataset`.
            Pass empty dictionary if there are no parameters.
        :param pagination: Count of rows|pages. Depends on what type of pagination
            dataset uses. If pagination type is `based_on_rows`, then count of rows
            must be sent, otherwise count of pages. If there is no pagination,
            nothing is required. Optional.
        """
        params = {"params": [params]}
        if pagination is not None:
            params["rows_or_pages"] = pagination

        response = self._session.post(
            urljoin(self._base_url, f"v2/datasets/{dataset_id}/pricing-calculate/"),
            json=params,
        )
        raise_for_status(response)
        return response.json()["total_cost"]
