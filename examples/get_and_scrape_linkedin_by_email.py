import json

import databar


connection = databar.Connection(
    api_key="hFfEVyk9KWJP4UCXL2g1qrDlnmi5BoeT8pvsYu76c0QaSZNG"
)

pdl_params = {
    "query": json.dumps(
        {
            # all info about what fields and what filters are applicable:
            # https://docs.peopledatalabs.com/docs/input-parameters-person-search-api#query
            # https://docs.peopledatalabs.com/docs/elasticsearch-mapping
            "query": {
                "bool": {
                    "must": [
                        {"term": {"location_country": "mexico"}},
                        {"term": {"job_title_role": "health"}},
                        {"exists": {"field": "phone_numbers"}},
                    ]
                }
            }
        }
    )
}
pdl_endpoint_id = "people-data-labs-api--search-people-data-labs-dataset"

pdl_result = connection.make_request(
    pdl_endpoint_id, pdl_params, fmt="json", rows_or_pages=10
)

with open("pdl_result.json", "w") as f:
    json.dump(pdl_result, f)

# "SP.WUS.HSS" is identifier of surgeon, all filters here:
# https://docs.healthcarelocator.com/index.htm#t=GraphQL%2Fsuggestions.htm&rhsearch=suggestion
hcl_params = {
    "query": """
    query {
  individuals(
    first: 10
    offset: 0
    country: "US"
    criterias: [
      { text: "john", scope: Name }
      { scope: Specialties, text: "Surgeon" }
    ]
    sortScope: Relevancy
  ) {
    edges {
      node {
        firstName
        lastName
        title {
          label
        }
        middleName
        maidenName
        mailingName
        firstNameInitials
        nickname
        suffixName
        professionalType {
          label
        }
        specialties {
          label
        }

        specialties {
          label
        }
        mainActivity {
          main_flag
          title {
            label
          }
          role {
            label
          }
          phone
          fax
          webAddress
          workplace {
            name
            officialName
            type {
              label
            }
            localPhone
            intlPhone
            intlFax
            webAddress
            emailAddress
            address {
              longLabel
              buildingLabel
              country
              county {
                code
                label
              }
              city {
                code
                label
              }
              postalCode
              location {
                lat
                lon
              }
            }
          }
        }
        otherActivities {
          main_flag
          title {
            label
          }
          role {
            label
          }
          phone
          fax
          webAddress
          workplace {
            name
            officialName
            type {
              label
            }
            localPhone
            intlPhone
            intlFax
            webAddress
            emailAddress
            address {
              longLabel
              buildingLabel
              country
              county {
                code
                label
              }
              city {
                code
                label
              }
              postalCode
              location {
                lat
                lon
              }
            }
          }
        }
      }
    }
  }
}

    """
}
hcl_endpoint_id = "healthcare-locator--query-data"

hcl_result = connection.make_request(
    hcl_endpoint_id,
    hcl_params,
    fmt="json",
    api_key=349,
)

with open("hcl_result.json", "w") as f:
    json.dump(hcl_result, f)
