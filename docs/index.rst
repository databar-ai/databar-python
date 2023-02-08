Welcome to databar-python's documentation!
==========================================


:Documentation: https://databar-python.readthedocs.io/
:Source Code: https://github.com/databar-ai/databar-python
:Issue Tracker: https://github.com/databar-ai/databar-python/issues
:PyPI: https://pypi.org/project/databar/


Overview
------------

The SDK allows you to query any API from `databar.ai catalog <https://databar.ai/explore>`__ with few lines of code.

    Please note, if you'd like us to add new api, let us know via our `Discord <https://discord.gg/RtV4qEdDZq>`__.
    Usually it takes ~1 day.

Quickstart
----------

`databar` package requires Python 3.8 or newer. Below we demonstrate how to get recent tweets from twitter.

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

Result of this method is a link to authenticate, click it and it will take you to twitter auth page.

Once you've authenticated successfully, please check your api keys out via following code:
::

    connection.api_keys()


**Request and get result**
::

    result = connection.make_request(
        "twitter--search-recent-tweets",
        {"query": "elon"},
        api_key="<YOUR_TWITTER_API_KEY_ID_HERE>",
        fmt="json",
    )

If you want to get more information about all functions
and understand exchange formats of api, please reach out to us using `Discord <https://discord.gg/RtV4qEdDZq>`__.
