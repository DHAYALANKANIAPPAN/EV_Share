from ..models import DocType, HubType, Role

LABELS = {
    DocType.AADHAAR: "Aadhaar card (masked: hide the first 8 digits)",
    DocType.VEHICLE_RC: "Vehicle registration certificate (RC)",
    DocType.HOUSE_DOCUMENT: "House / property documents",
    DocType.TAX_RECEIPT: "Property tax receipt",
    DocType.BUILDING_PLAN: "Sanctioned building plan",
    DocType.OCCUPANCY_CERT: "Occupancy certificate",
    DocType.SHOP_LICENSE: "Shop & establishment licence",
}


def required_docs(user) -> list[DocType]:
    if user.role == Role.DRIVER:
        return [DocType.AADHAAR, DocType.VEHICLE_RC]
    base = [DocType.HOUSE_DOCUMENT, DocType.TAX_RECEIPT]
    if user.hub_type == HubType.SHOP:
        base += [DocType.BUILDING_PLAN, DocType.OCCUPANCY_CERT, DocType.SHOP_LICENSE]
    return base
