import asyncio
import copy
import itertools
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urljoin

import aiohttp
import pandas
import requests

from .helpers import PaginatedResponse, raise_for_status


def _get_nested_json_columns(
    column_name: str, states: Dict[str, Dict[str, Any]]
) -> List[str]:
    nested_columns = []
    column_state = states.get(column_name)
    if column_state is None or not (
        column_state["can_expand"] and column_state["is_expanded"]
    ):
        nested_columns.append(column_name)
    else:
        for nested_column_name, state in states.items():
            if (
                nested_column_name.startswith(column_name)
                and state["parent"] == column_name
            ):
                nested_columns.extend(
                    _get_nested_json_columns(nested_column_name, states)
                )

    return list(sorted(nested_columns))


async def _get_chunk_of_data(*, session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        return (await response.json())["result"]


async def _get_data(
    *, headers: Mapping[str, str], base_url: str, count_of_pages: int, per_page: int
):
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = []
        for number in range(count_of_pages):
            url = f"{base_url}rows/?per_page={per_page}&page={number + 2}"
            tasks.append(
                asyncio.ensure_future(_get_chunk_of_data(session=session, url=url))
            )
        return await asyncio.gather(*tasks)


class Table:
    def __init__(self, session: requests.Session, tid: str):
        self._session = session
        self._base_url = f"https://databar.ai/api/v3/tables/{tid}/"
        response = self._session.get(self._base_url)
        raise_for_status(response)
        self._table_detail: dict = response.json()

    def __str__(self) -> str:
        return self._table_detail["name"]

    def __repr__(self) -> str:
        return self._table_detail["name"]

    @property
    def uid(self):
        return self._table_detail["identifier"]

    @property
    def dataset_id(self):
        """Returns dataset id of table."""
        return self._table_detail["dataset_id_based_on"]

    def get_total_cost(self) -> float:
        """Returns total cost of all requests"""
        response = self._session.get(self._base_url)
        raise_for_status(response)
        return response.json()["total_cost"]

    def get_meta(self, page=1) -> PaginatedResponse:
        """"""
        params = {
            "page": page,
            "per_page": 100,
        }
        response = self._session.get(
            urljoin(self._base_url, "request-meta"), params=params
        )
        raise_for_status(response)
        response_json = response.json()
        return PaginatedResponse(
            page=page,
            data=response_json["results"],
            has_next_page=bool(response_json["next"]),
        )

    def get_status(self) -> str:
        """Returns status of requests.

        Status types:
            - **none** - there are no requests.
            - **failed** - all requests are failed.
            - **partially_completed** - part of requests are failed|canceled,
              part of requests are successful.
            - **completed** - all requests are successful.
            - **processing** - requests are processing.
        """
        response = self._session.get(urljoin(self._base_url, "request-status"))
        raise_for_status(response)
        return response.json()["status"]

    def cancel_request(self):
        """Cancels processing request."""
        raise_for_status(self._session.post(urljoin(self._base_url, "request-cancel/")))

    def append_data(
        self,
        parameters: Optional[Dict[str, Any]] = None,
        pagination: Optional[int] = None,
        authorization_id: Optional[int] = None,
    ):
        """
        Appends data to table.

        :param parameters: Parameters which must be formed in according to dataset.
            Can be retrieved from :func:`~Table.get_params_of_dataset`.
            Nothing is required if there are no parameters.
        :param pagination: Count of rows|pages. Depends on what type of pagination
            dataset uses. If pagination type is `based_on_rows`, then count of rows
            must be sent, otherwise count of pages. If there is no pagination,
            nothing is required. Optional.
        :param authorization_id: Id of api key. Can be retrieved from
            :func:`~databar.connection.Connection.list_of_api_keys`. Pass only if it's
            required by dataset. Optional.
        """
        if self.dataset_id is None:
            raise ValueError(
                "Cannot get parameters for table which was "
                "created from blank table or based on csv file."
            )

        params: Dict[str, Any] = {"params": parameters or {}}
        if pagination is not None:
            params["rows_or_pages"] = pagination
        if authorization_id is not None:
            params["authorization"] = authorization_id

        raise_for_status(
            self._session.post(
                urljoin(self._base_url, "append-data/"),
                json=params,
            )
        )

    def get_params_of_dataset(self) -> Dict[str, Any]:
        """
        Returns parameters of dataset. The result is info about authorization,
        pagination, query parameters of dataset.
        """
        if self.dataset_id is None:
            raise ValueError(
                "Cannot get parameters for table which was "
                "created from blank table or based on csv file."
            )

        response = self._session.get(
            f"https://databar.ai/api/v2/datasets/{self.dataset_id}/params/",
        )
        raise_for_status(response)
        return response.json()

    def calculate_price_of_request(
        self,
        parameters: Dict[str, Any] = None,
        pagination: Optional[int] = None,
    ) -> float:
        """
        Calculates price of request in credits.

        :param parameters: Parameters which must be formed in according to dataset.
            Can be retrieved from :func:`~Table.get_params_of_dataset`.
            Nothing is required if there are no parameters.
        :param pagination: Count of rows|pages. Depends on what type of pagination
            dataset uses. If pagination type is `based_on_rows`, then count of rows
            must be sent, otherwise count of pages. If there is no pagination,
            nothing is required. Optional.
        """
        if self.dataset_id is None:
            raise ValueError(
                "Cannot get parameters for table which was "
                "created from blank table or based on csv file."
            )

        params: Dict[str, Any] = {"params": parameters or {}}
        if pagination is not None:
            params["rows_or_pages"] = pagination

        response = self._session.post(
            f"https://databar.ai/api/v2/datasets/{self.dataset_id}/pricing-calculate/",
            json=params,
        )
        raise_for_status(response)
        return response.json()["total_cost"]

    def _get_columns(self):
        json_columns_states = self._session.get(
            urljoin(self._base_url, "json-fields-details")
        ).json()
        columns = []
        for column in self._session.get(urljoin(self._base_url, "columns")).json():
            internal_name = column["internal_name"]
            if column["type_of_value"] == "json":
                columns.extend(
                    _get_nested_json_columns(internal_name, json_columns_states)
                )
            else:
                columns.append(internal_name)
        return columns

    def _get_rows(self):
        per_page = 1000
        rows_url = urljoin(self._base_url, "rows")

        first_rows_response = self._session.get(rows_url, params={"per_page": per_page})
        rows_response_json = first_rows_response.json()
        rows_total_count = rows_response_json["total_count"]

        remaining_data = []
        if not (0 <= rows_total_count <= per_page):
            remaining_rows_count = rows_total_count - per_page
            if remaining_rows_count <= per_page:
                remaining_data.append(
                    self._session.get(
                        rows_url, params={"per_page": per_page, "page": 2}
                    ).json()["result"]
                )
            else:
                loop = asyncio.events.new_event_loop()
                try:
                    asyncio.events.set_event_loop(loop)
                    result = loop.run_until_complete(
                        _get_data(
                            headers=copy.copy(self._session.headers),
                            base_url=self._base_url,
                            count_of_pages=(remaining_rows_count // per_page) + 1,
                            per_page=per_page,
                        )
                    )
                    remaining_data.extend(result)
                finally:
                    asyncio.events.set_event_loop(None)
                    loop.close()

        return (
            row["data"]
            for row in itertools.chain(rows_response_json["result"], *remaining_data)
        )

    def as_pandas_df(self) -> pandas.DataFrame:
        """Returns table as a pandas dataframe."""
        rows = self._get_rows()
        columns = self._get_columns()
        return pandas.DataFrame(data=rows, columns=columns)
