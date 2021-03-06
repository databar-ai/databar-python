from databar.table import _get_nested_json_columns


def test_get_nested_json_columns():
    nested_columns = _get_nested_json_columns(
        column_name="company_officers",
        states={
            "company_officers": {
                "type": "list",
                "alias": "company_officers",
                "parent": None,
                "can_expand": True,
                "is_expanded": True,
            },
            "company_officers__expanded": {
                "type": "dict",
                "alias": "company_officers",
                "parent": "company_officers",
                "can_expand": True,
                "is_expanded": True,
            },
            "company_officers__expanded__age": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.age",
                "parent": "company_officers__expanded",
                "can_expand": False,
            },
            "company_officers__expanded__name": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.name",
                "parent": "company_officers__expanded",
                "can_expand": False,
            },
            "company_officers__expanded__title": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.title",
                "parent": "company_officers__expanded",
                "can_expand": False,
            },
            "company_officers__expanded__maxAge": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.maxAge",
                "parent": "company_officers__expanded",
                "can_expand": False,
            },
            "company_officers__expanded__yearBorn": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.yearBorn",
                "parent": "company_officers__expanded",
                "can_expand": False,
            },
            "company_officers__expanded__fiscalYear": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.fiscalYear",
                "parent": "company_officers__expanded",
                "can_expand": False,
            },
            "company_officers__expanded__exercisedValue": {
                "is_expanded": False,
                "type": "dict",
                "alias": "company_officers.exercisedValue",
                "parent": "company_officers__expanded",
                "can_expand": True,
            },
            "company_officers__expanded__unexercisedValue": {
                "is_expanded": False,
                "type": "dict",
                "alias": "company_officers.unexercisedValue",
                "parent": "company_officers__expanded",
                "can_expand": True,
            },
            "company_officers__expanded__totalPay": {
                "type": "dict",
                "alias": "company_officers.totalPay",
                "parent": "company_officers__expanded",
                "can_expand": True,
                "is_expanded": True,
            },
            "company_officers__expanded__totalPay__fmt": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.totalPay.fmt",
                "parent": "company_officers__expanded__totalPay",
                "can_expand": False,
            },
            "company_officers__expanded__totalPay__raw": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.totalPay.raw",
                "parent": "company_officers__expanded__totalPay",
                "can_expand": False,
            },
            "company_officers__expanded__totalPay__longFmt": {
                "is_expanded": False,
                "type": "str",
                "alias": "company_officers.totalPay.longFmt",
                "parent": "company_officers__expanded__totalPay",
                "can_expand": False,
            },
        },
    )
    assert nested_columns == [
        "company_officers__expanded__age",
        "company_officers__expanded__exercisedValue",
        "company_officers__expanded__fiscalYear",
        "company_officers__expanded__maxAge",
        "company_officers__expanded__name",
        "company_officers__expanded__title",
        "company_officers__expanded__totalPay__fmt",
        "company_officers__expanded__totalPay__longFmt",
        "company_officers__expanded__totalPay__raw",
        "company_officers__expanded__unexercisedValue",
        "company_officers__expanded__yearBorn",
    ]
