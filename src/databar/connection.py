from urllib.parse import urljoin

import requests

from .helpers import PaginatedResponse, raise_for_status, timed_lru_cache
from .table import Table


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

    def list_of_api_keys(self, page: int = 1) -> PaginatedResponse:
        """
        Returns a list of api keys using pagination. One page stores 100 records.

        :param page: Page you want to retrieve. Default is 1.
        """

        params = {
            "page": page,
            "per_page": 100,
        }
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
            urljoin(self._base_url, "v3/tables"),
            params=params,
        )
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            has_next_page=bool(response_json["next"]),
            data=response_json["results"],
        )

    def get_table(self, table_id: str) -> Table:
        """
        Returns specific table.

        :param table_id: Table id you want to get. List of tables can be retrieved
            using :func:`~Connection.list_of_tables` method.
        """
        return Table(session=self._session, tid=table_id)
