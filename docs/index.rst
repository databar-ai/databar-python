Welcome to databar-python's documentation!
==========================================


:Documentation: https://databar-python.readthedocs.io/
:Source Code: https://github.com/databar-ai/databar-python
:Issue Tracker: https://github.com/databar-ai/databar-python/issues
:PyPI: https://pypi.org/project/databar-python/


Introduction
------------

This is a official databar.ai python library. Using this package you
can access databar.ai functionality from python.


Quickstart
----------

`databar-python` requires Python 3.6 or newer.

Installation:

::

    pip install databar-python


To get started with databar-python, you need to have api-key.

Usage example:

::

    import databar

    connection = databar.Connection(api_key="<some_api_key>")
    my_tables = connection.get_tables()
    print(my_tables.data)

    coingecko_data_table = connection.get_table(table_id=<coingecko_table_id>)
    table_as_pandas_df = coingecko_data_table.as_pandas_df()


Classes
--------------------------
.. autoclass:: databar.connection.PaginatedResponse

.. autoclass:: databar.connection.Connection
   :members:

   .. automethod:: __init__

.. autoclass:: databar.table.Table
   :show-inheritance:
   :members:
