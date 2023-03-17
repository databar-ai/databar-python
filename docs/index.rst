Welcome to databar-python's documentation!
==========================================


:Documentation: https://databar-python.readthedocs.io/
:Source Code: https://github.com/databar-ai/databar-python
:Issue Tracker: https://github.com/databar-ai/databar-python/issues
:PyPI: https://pypi.org/project/databar/


Overview
------------

The SDK allows you to query any API from the `databar.ai catalog <https://databar.ai/explore>`__ with few lines of code.

All Databar APIs are available via the SDK - for some, you can use the Databar API key to query third party sources directly.
If we don't currently have an API in the library, you can add your own via the Add API button in your workspace or request
that we add it via our `Discord <https://discord.gg/RtV4qEdDZq>`__.

Requirements
----------

To use the SDK, you must have Python 3.8 or newer and an active account on `Databar.ai <https://databar.ai>`__.
You can sign up for an account `here <https://databar.ai/registration>`__.

Quickstart
---------
Below is a simple example of how you can get recent tweets from Twitter with the Databar SDK:

**Installation**
::

    pip install databar


**Initiate the connection**

First you need to import the package and initiate the connection:
::

    import databar

    connection = databar.Connection(api_key="<YOUR_API_KEY_HERE")

**Authentication**

Twitter requires authentication with OAuth2, so we need to get it authorized:
::

    connection.authorize("twitter")

This method will return a link where you can authorize your Twitter account. Click on the link to authorize your account.

    Note: Your authorization, credentials, and API keys are encrypted and stored privately and securely within your Databar workspace.
    Our team has no access to your credentials or API keys. You can delete credentials from your Databar workspace.

You can also check which API keys are stored in Databar via the api_keys method.
::

    connection.api_keys()


**Submit your query**
::

    result = connection.make_request(
        "twitter-api--search-recent-tweets",
        {"query": "elon"},
        api_key="<YOUR_TWITTER_API_KEY_ID_HERE>",
        fmt="json",
    )

The result for this query returns recent Tweets with the key word "elon" and should look something like this:
::
    [
        {
            "author_username": "thegingerpig",
            "text": "RT @SkyNews: BREAKING: Gary Lineker challenges Elon Musk over a threatening message sent to his son by a Twitter user in the wake of the TV…",
            "identifier": "1635734448103669763",
            "author_id": "358922958",
            "author_name": "Ginger Pig1",
        },
        {
            "author_username": "jonschmidt05",
            "text": "RT @realDonaldJNews: Raise your hand if you agree with Elon Musk saying ARREST Dr. FAUCI✋",
            "identifier": "1635734445218058244",
            "author_id": "1569239803",
            "author_name": "Jon Schmidt",
        },
        ....
    ]

Embedded documentation: searching APIs & connectors
---------------------------------------------------
**Searching API docs & parameters**

The example above demonstrates how you can make a simple connection to the Twitter API. The Databar catalogue features
over 1,200 connectors from over 200 data sources. You can search connectors & APIs directly from the SDK by calling the
following method:
::
    connection.discover_apis(search_query='twitter') # to discover apis

    connection.discover_endpoints(search_query='twitter') to discover endpoints

For example, searching "twitter" will return all connectors associated with the Twitter API:
::
    id                                             | name
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    twitter-api--twitter-users-lookup-by-username  | Twitter users lookup by username
    twitter-api--search-recent-tweets              | Search recent tweets

You can also search request parameters for each connector:
::
    connection.get_endpoint_docs('twitter-api--search-recent-tweets')

    Authorization: This api uses OAuth2 for authorization. Generate link to authorize via following code: connection.authorize(api='twitter-api'). To check existing keys call connection.api_keys(api='twitter-api')

    Pagination: this endpoint pagination is page-based, e.g. 1, 2, 3, etc. Default 1.

    Input parameters:
    +-------+------+-------------+----------------------------------------------------------------------------------------------------------+
    | name  | type | is_required |                                               description                                                |
    +-------+------+-------------+----------------------------------------------------------------------------------------------------------+
    | query | text |    True     | One query for matching Tweets. You can learn how to build this query by reading our build a query guide. |
    +-------+------+-------------+----------------------------------------------------------------------------------------------------------+

    Result columns:
    +-----------------+------+
    |      name       | type |
    +-----------------+------+
    | author_username | text |
    |      text       | text |
    |   identifier    | text |
    |    author_id    | text |
    |   author_name   | text |
    +-----------------+------+

Running direct queries
----------------------

To run a query to an API you can use the **connection.make_request** method:

* **endpoint_id** - the id of the endpoint you want to make your request to. You can search connectors and APIs using the discover_apis and discover_endpoints method.
* **params** - the query parameters, denoted as a dictionary.
* **api_key** - the id of api key, comes from `.api_keys` method, optional.
* **rows_or_pages** - count of rows or pages, depends on connector pagination. See default one in `.get_endpoint_docs`.
* **fmt** - the format you want your data in. Acceptable values are: json, df.

::

    person_info_from_email = connection.make_request(
        "people-data-labs-api--person-enrichment-by-email",
        {"email": "patrick@stripe.com"},
        fmt="json",
    )
    print(enriched_email[0]["linkedin_url"])
    print(enriched_email[0]["linkedin_username"])

Data enrichments
----------------

The Databar SDK supports data enrichments by default. You can upload a file

::

    import pandas
    import databar

    pd_df = pandas.read_csv("search_queries.csv") # a file with one column including search queries: elon, gpt4

    databar = databar.Connection(api_key='<api_key_from_databar_homepage>') #initiate the connection
    enriched_df = databar.enrich(
        pd_df,
        endpoint="twitter-api--search-recent-tweets",
        mapping={"query": "search_query"}, # mapping query parameter to search_query column from file
        api_key="<YOUR_TWITTER_API_KEY_ID_HERE>"
    )
The enriched_df dataframe will now include new columns with data from the Twitter API.

Custom connectors
-----------------
Would you like a custom connector or enrichment? We can combine multiple APIs in a single call and add APIs on a per-request basis.
New APIs can be installed on our site in under a day.

Credits
-------
Credits, access levels, and rate limits are determined by your `Databar plan catalog <https://databar.ai/pricing>`__.
Please keep in mind that your no-code workspace and SDK share the same credits.

Support
-------

To learn more about the Databar SDK, please reach out to us via email at info@databar.ai or message us in the community
`Discord <https://discord.gg/RtV4qEdDZq>`__.
