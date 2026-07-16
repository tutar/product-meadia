def build_product_snapshot(product, category) -> dict:
    attributes = []
    definitions = sorted(category.attributes, key=lambda item: item.sort_order)
    for definition in definitions:
        if definition.key in product.attributes:
            attributes.append({
                "key": definition.key,
                "label": definition.label,
                "type": definition.type,
                "value": product.attributes[definition.key],
            })
    return {
        "version": 1,
        "id": str(product.id),
        "name": product.name,
        "description": product.description,
        "selling_points": list(product.selling_points or []),
        "scenarios": list(product.scenarios or []),
        "main_image_url": product.main_image_url,
        "main_image_source": product.main_image_source,
        "category": {"id": str(category.id), "name": category.name, "template_version": category.template_version},
        "attributes": attributes,
    }


def format_product_context(snapshot: dict) -> str:
    if snapshot.get("version") != 1 or not isinstance(snapshot.get("category"), dict):
        raise ValueError("Invalid product snapshot")
    lines = [f"Product: {snapshot['name']}", f"Category: {snapshot['category']['name']}"]
    for item in snapshot.get("attributes", []):
        value = item["value"]
        if isinstance(value, list):
            value = ", ".join(str(part) for part in value)
        elif isinstance(value, bool):
            value = "Yes" if value else "No"
        lines.append(f"{item['label']}: {value}")
    return "\n".join(lines)
