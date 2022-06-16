Welcome to databar-python's documentation!
==========================================


:Documentation: https://databar-python.readthedocs.io/
:Source Code: https://github.com/databar-ai/databar-python
:Issue Tracker: https://github.com/databar-ai/databar-python/issues
:PyPI: https://pypi.org/project/databar-python/


Overview
------------

The SDK allows you to query tables that you've already created via the `databar.ai <https://discord.gg/RtV4qEdDZq>`__ UI.
You can also create new rows in existing tables and get meta-data about your tables.
All enrichments and automations that you set up will show up when you query your table via this SDK.

    Please note, you cannot yet create new tables with the SDK.
    If you'd like us to add this feature, please let us know via our `Discord <https://discord.gg/RtV4qEdDZq>`__.


Quickstart
----------

`databar` package requires Python 3.8 or newer.

**Installation**
::

    pip install databar


**Initiate the connection**

First you need to import the package and initiate the connection:
::

    import databar

    connection = databar.Connection(api_key="<YOUR_API_KEY_HERE")

**Get a list of all tables in your account**
::

    my_tables = connection.list_of_tables()

the .list_of_tables() method returns 100 tables. If you have more than 100 tables, you can paginate through them:
::

    my_tables = connection.list_of_tables(page=2)


**Connect to a specific table**
::

    table = connection.get_table(table_id=<your_table_id_here>)


**Get your table as a dataframe**
::

    df = table.as_pandas_df()


**Retrieve meta data about your table**

The total cost of your table (in databar credits):
::

    table.get_total_cost()


**Adding rows to your table**

*Adding rows does not work when you create a blank/csv table.
Adding rows only works when you create a table from a dataset/API.*

If a dataset doesn't require parameters, pagination and authorization, you can query them directly via:
::

    table.append_data()

If a table's dataset requires parameters, you can retrieve them(otherwise if table was created from csv/blank, exception would be raised):
::

    table.get_params_of_dataset()

And pass them along with the append_data() class:
::

    table.append_data(
        parameters={"param1":"param1", "param2":"param2"},
        pagination=<count of rows|pages if there is pagination>,
        authorization_id=<your own api key id, if authorization is required>,
    )

Once you submit a request, your table will update and append data to the existing table.
You can then retrieve the updated table again with `table.as_pandas_df()`.


**Meta data about requests and user**

Once you make your request to a dataset, you can also check the request status:
::

    table.get_status()

Or cancel the request:
::

    table.cancel_request()

Information about requests(details of api calls: result status code, error message, execution time):
::

    table.get_meta()

Get info about your plan(storage size, credits, count of tables):
::

    connection.get_plan_info()

|

If you want to get more information about all functions
and understand exchange formats of api, please discover interfaces below.

Interface
--------------------------
.. autoclass:: databar.connection.PaginatedResponse

.. autoclass:: databar.connection.Connection
    :members:

    .. automethod:: __init__

.. autoclass:: databar.table.Table
   :show-inheritance:
   :members:

