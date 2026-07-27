from typing import Any


DEFAULT_FIELD_MAPPING = {
    "customer_name": "customer_name",
    "customer_phone": "mobile_no",
    "request_type": "request_type",
}


def map_request_to_erpnext(request_data: dict, field_mapping: dict) -> dict[str, Any]:
    result = {}
    for local_field, erpnext_field in field_mapping.items():
        value = request_data.get(local_field)
        if value is not None:
            result[erpnext_field] = value
    return result


def get_config_value(configuration: dict, key: str, default: Any = None) -> Any:
    return configuration.get(key, default) if configuration else default
