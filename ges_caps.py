#!/usr/bin/env python3
"""Tool for importing capacitors bought from GES ELECTRONICS to InvenTree."""

import questionary
import re
import os
from dataclasses import dataclass
from inventree.api import InvenTreeAPI
from inventree.part import Parameter, ParameterTemplate, Part, PartCategory
from inventree.stock import StockItem, StockLocation
from inventree.company import Company, SupplierPart


@dataclass
class Component:
    GES_SKU: str = "GES054"
    GES_name: str = "RAD "
    description: str = ""
    dimensions: str = ""
    capacitance: str = "µF"
    rated_voltage: str = "V"
    mounting_type: str = "THT"
    package_type: str = "Ø?x?mm"
    terminal_pitch: str = ""  # unused
    high_temperature: bool = False  # only used internally


class InventreeHelper:
    def __init__(self):
        # set environment variables: INVENTREE_API_HOST, INVENTREE_API_TOKEN, INVENTREE_API_TOKEN_NAME
        self.api = InvenTreeAPI()
        self.GES_supplier = Company.list(self.api, name="GES electronics")[0]
        self.category = PartCategory(self.api, 65)
        assert self.category.pathstring == "Electronics/Passives/Capacitors/Aluminum Electrolytic"
        self.parameter_templates = self.get_parameter_templates()
        self.location = StockLocation(self.api, 16)
        assert self.location.pathstring == "Skrin chodba/Capacitors electrolytic GES"

    def get_supplier_part(self, sku):
        supplier_parts = SupplierPart.list(self.api, SKU=sku)
        if len(supplier_parts) == 1:
            return supplier_parts[0]
        if len(supplier_parts) != 0:
            raise AssertionError("more than one supplier part")
        return None

    def get_category(self, category_path):
        name = category_path.split("/")[-1]
        for category in PartCategory.list(self.api, search=name):
            if category.pathstring == category_path:
                return category
        return None

    def get_parameter_templates(self):
        return {
            parameter_template.name: parameter_template
            for parameter_template in ParameterTemplate.list(self.api)
        }

    def check_supplier_part(self, SKU: str) -> SupplierPart | None:
        return self.get_supplier_part(SKU)

    def create_GES_capacitor(self, component: Component) -> SupplierPart:
        if supplier_part := self.check_supplier_part(component.GES_SKU):
            print("warning: supplier part already exists")
            return supplier_part

        matching_parts = Part.list(self.api, search=component.GES_name)
        if len(matching_parts) == 1:
            part = matching_parts[0]
            print(f"reusing existing part {INVENTREE_URL}/part/{part.pk}/")
        else:
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
                ("Capacitance", component.capacitance),
                ("Mounting Type", component.mounting_type),
                ("Rated Voltage", component.rated_voltage),
                ("Package Type", component.package_type),
                ]:
            existing_parameter = existing_parameters[param]
            existing_parameter.save({"data": value})
            #parameter_template = self.parameter_templates[param]
            #Parameter.create(self.api, {
            #    "part": part.pk,
            #    "template": parameter_template.pk,
            #    "data": value,
            #})

        supplier_part_data = {
            "part": part.pk,
            "supplier": self.GES_supplier.pk,
            "SKU": component.GES_SKU,
        }
        supplier_part = SupplierPart.create(self.api, supplier_part_data)

        return supplier_part

    def create_stock_item(self, supplier_part: SupplierPart, quantity: int) -> None:
        StockItem.create(
            self.api,
            {
                "part": supplier_part.part,
                "supplier_part": supplier_part.pk,
                "quantity": quantity,
                "location": self.location.pk,
            }
        )


def main():
    inv = InventreeHelper()

    params_1 = [
        ("GES_SKU", re.compile(r"^GES[0-9]{8}$")),
        ("GES_name", re.compile(r"")),
        ("dimensions", re.compile(r"[0-9.]+x[0-9.]+")),
    ]

    params_2 = [
        ("capacitance", re.compile(r"^[0-9.]+µF")),
        ("rated_voltage", re.compile(r"^\d+V")),
        ("package_type", re.compile(r"^Ø[0-9.,]+x[0-9.,]+mm$")),
        ("mounting_type", re.compile(r"")),
    ]

    while True:
        print("Creating new component")
        component = Component()
        # Keep asking about this component until all info is correct
        while True:
            for key, validate_regex in params_1:
                setattr(component, key,
                        questionary.text(
                            key,
                            default=getattr(component, key),
                            validate=lambda x: bool(validate_regex.match(x))
                        ).unsafe_ask()
                        )
                if key == "GES_SKU":
                    if supplier_part := inv.check_supplier_part(component.GES_SKU):
                        print("found existing supplier part")
                        break

            if supplier_part is not None:
                break

            def match_GES_name(component):
                m = re.match(
                    # not forcing $ to allow trailing "GF", etc.
                    r"^RAD (?P<capacitance>[0-9,]+)/(?P<voltage>[0-9,]+)(?P<HT> HT)? RM(?P<RM>[0-9,]+)",
                    component.GES_name
                )
                if m:
                    component.terminal_pitch = f"{float(m.group('RM').replace(',', '.'))}mm"
                    description_base = "Elektrolytický kondenzátor, radiální vývody"
                    return m, description_base

                m = re.match(
                    r"^BSN (?P<capacitance>[0-9,]+)/(?P<voltage>\d+)(?P<HT>-HT)?$",
                    component.GES_name
                )
                if m:
                    description_base = "Elektrolytický kondenzátor s vývody SNAP-IN"
                    component.mounting_type = "SNAP-IN"
                    return m, description_base

                m = re.match(
                    r"^RAD BIP (?P<capacitance>[0-9,]+)/(?P<voltage>[0-9,]+)(?P<HT> HT)? RM(?P<RM>[0-9,]+)",
                    component.GES_name
                )
                if m:
                    description_base = "Bipolární kondenzátor, radiální vývody"
                    return m, description_base

                m = re.match(
                    r"^AXI (?P<capacitance>[0-9,]+)/(?P<voltage>[0-9,]+)",
                    component.GES_name
                )
                if m:
                    description_base = "Elektrolytický kondenzátor, axiální vývody"
                    return m, description_base

                return None, ""

            m, description_base = match_GES_name(component)

            # common for all regexes:
            if m:
                try:
                    capacitance = int(m.group('capacitance'))
                except ValueError:
                    capacitance = float(m.group('capacitance').replace(',', '.'))
                try:
                    voltage = int(m.group('voltage'))
                except ValueError:
                    voltage = float(m.group('voltage').replace(',', '.'))
                component.capacitance = f"{capacitance}µF"
                component.rated_voltage = f"{voltage}V"
                try:
                    component.high_temperature = m.group("HT") is not None
                except IndexError:
                    component.high_temperature = False
                component.package_type = f"Ø{component.dimensions}mm"
                component.description = (
                    f"{description_base}, "
                    f"prům. {component.dimensions}mm"
                    f"{', 105°C' if component.high_temperature else ''}"
                )
            else:
                print("warning: regex did not match")

                for key, validate_regex in params_2:
                    setattr(component, key,
                            questionary.text(
                                key,
                                default=getattr(component, key),
                                validate=lambda x: bool(validate_regex.match(x))
                            ).unsafe_ask()
                            )
            component.description = questionary.text(
                    "Description", default=component.description
                ).unsafe_ask()

            print(component)
            correct = questionary.confirm(
                    "Is the above information correct?", default=True
                ).unsafe_ask()
            if correct:
                break

        if supplier_part is None:
            print("creating component")
            supplier_part = inv.create_GES_capacitor(component)
        print(INVENTREE_URL + supplier_part.url)
        quantity = int(questionary.text(
                "quantity",
                validate=lambda x: x.isdigit() and int(x) >= 0
            ).unsafe_ask())
        # TODO allow +x to add to existing stock item
        if quantity > 0:
            inv.create_stock_item(supplier_part, quantity)


if __name__ == "__main__":
    main()
