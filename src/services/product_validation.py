class AttributeValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Invalid product attributes")


def normalize_attributes(definitions: list, values: dict[str, object]) -> dict[str, object]:
    by_key = {item.key: item for item in definitions}
    errors = {key: "Unknown attribute" for key in values.keys() - by_key.keys()}
    normalized = {}

    for key, definition in by_key.items():
        value = values.get(key)
        empty = value is None or value == "" or value == []
        if empty:
            if definition.required:
                errors[key] = "Required attribute"
            continue

        if definition.type == "text":
            if type(value) is not str:
                errors[key] = "Must be text"
                continue
            normalized[key] = value
        elif definition.type == "number":
            if type(value) not in (int, float):
                errors[key] = "Must be a number"
                continue
            normalized[key] = value
        elif definition.type == "single_select":
            if type(value) is not str:
                errors[key] = "Must be a single option"
                continue
            if value not in definition.options:
                errors[key] = "Invalid option"
                continue
            normalized[key] = value
        elif definition.type == "multi_select":
            if type(value) is not list or any(type(item) is not str for item in value):
                errors[key] = "Must be a list of options"
                continue
            invalid = [item for item in value if item not in definition.options]
            if invalid:
                errors[key] = "Invalid option"
                continue
            normalized[key] = list(dict.fromkeys(value))
        elif definition.type == "boolean":
            if type(value) is not bool:
                errors[key] = "Must be a boolean"
                continue
            normalized[key] = value
        else:
            errors[key] = "Unsupported attribute type"

    if errors:
        raise AttributeValidationError(errors)
    return normalized
