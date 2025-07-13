#!/usr/bin/env python3
import os
from dataclasses import dataclass
from inventree.api import InvenTreeAPI
from inventree.part import Parameter, ParameterTemplate, Part, PartCategory
from inventree.company import Company, SupplierPart, ManufacturerPart

INVENTREE_URL = os.getenv("INVENTREE_API_HOST", "")


@dataclass
class Component:
    GES_SKU: str = ""
    GES_name: str = ""
    description: str = ""
    MPN: str = ""
    number_of_contacts: int = None
    number_of_rows: int = None


class InventreeHelper:
    def __init__(self):
        # set environment variables: INVENTREE_API_HOST, INVENTREE_API_TOKEN, INVENTREE_API_TOKEN_NAME
        self.api = InvenTreeAPI()
        self.GES_supplier = Company.list(self.api, name="GES electronics")[0]
        self.econ_connect_manufacturer = Company.list(self.api, name="econ connect")[0]
        self.category = PartCategory(self.api, 17)
        assert self.category.pathstring == "Electronics/Connectors/Connector Housings"
        self.parameter_templates = self.get_parameter_templates()

    def get_supplier_part(self, sku):
        supplier_parts = SupplierPart.list(self.api, SKU=sku)
        if len(supplier_parts) == 1:
            return supplier_parts[0]
        if len(supplier_parts) != 0:
            raise AssertionError("more than one supplier part")
        return None

    def check_supplier_part(self, SKU: str) -> SupplierPart | None:
        return self.get_supplier_part(SKU)

    def get_parameter_templates(self):
        return {
            parameter_template.name: parameter_template
            for parameter_template in ParameterTemplate.list(self.api)
        }

    def create_component(self, component: Component) -> SupplierPart:
        if supplier_part := self.check_supplier_part(component.GES_SKU):
            print("warning: supplier part already exists")

        matching_parts = Part.list(self.api, search=component.GES_name)
        if len(matching_parts) >= 0:
            for p in matching_parts:
                if p.name == component.GES_name:
                    part = p
            assert part
            print(f"reusing existing part {INVENTREE_URL}/part/{part.pk}/")
        else:
            assert len(matching_parts) == 0
            part_data = {
                "category": self.category.pk,
                "name": component.GES_name,
                "description": component.description,
                "active": True,
                "component": True,
                "purchaseable": True,
            }
            part = Part.create(self.api, part_data)

        existing_parameters = {
            parameter.template_detail["name"]: parameter
            for parameter in Parameter.list(self.api, part=part.pk)
        }

        for param, value in [
                ("Number of Contacts", component.number_of_contacts),
                ("Number of Rows", component.number_of_rows),
                ]:
            existing_parameter = existing_parameters[param]
            existing_parameter.save({"data": value})

        if supplier_part:
            return supplier_part

        manufacturer_part_data = {
            "part": part.pk,
            "manufacturer": self.econ_connect_manufacturer.pk,
            "MPN": component.MPN,
        }
        manufacturer_part = ManufacturerPart.create(self.api, manufacturer_part_data)

        supplier_part_data = {
            "part": part.pk,
            "manufacturer_part": manufacturer_part.pk,
            "supplier": self.GES_supplier.pk,
            "SKU": component.GES_SKU,
        }
        supplier_part = SupplierPart.create(self.api, supplier_part_data)

        return supplier_part


def main():
    inv = InventreeHelper()

    for c, i in enumerate([*range(1, 9), 10, 14, 16]):
        component = Component()
        component.GES_name = f"BLS {i:02}"
        if i == 1:
            component.GES_SKU = "GES06614525"
        else:
            component.GES_SKU = f"GES066140{36+c}"
        component.description = f"Prázdné pouzdro bez kontaktů typ BLS {i}PIN"
        component.MPN = f"CG{i}"
        component.number_of_rows = 1
        component.number_of_contacts = i
        print(component)
        supplier_part = inv.create_component(component)
        print(INVENTREE_URL + supplier_part.url)

    for c in [("BLD 14", "GES06615682", "CGD14", 14), ("BLD 16", "GES06615683", "CGD16", 16)]:
        component = Component()
        component.GES_name = c[0]
        component.GES_SKU = c[1]
        component.MPN = c[2]
        component.description = ""
        component.number_of_rows = 2
        component.number_of_contacts = c[3]
        print(component)
        supplier_part = inv.create_component(component)
        print(INVENTREE_URL + supplier_part.url)


if __name__ == "__main__":
    main()
