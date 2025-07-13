#!/usr/bin/env python3
import re
from inventree.api import InvenTreeAPI
from inventree.part import Parameter, Part, PartCategory


class InventreeHelper:
    def __init__(self):
        # set environment variables: INVENTREE_API_HOST, INVENTREE_API_TOKEN, INVENTREE_API_TOKEN_NAME
        self.api = InvenTreeAPI()
        self.category = PartCategory(self.api, 105)
        assert self.category.pathstring == "CNC/Tools/Drills"

    def set_drill_bit_parameters(self):
        matching_parts = Part.list(self.api, search="Carbide Drill Bit 1/8")
        for part in matching_parts:
            print("part:", part)
            existing_parameters = {
                parameter.template_detail["name"]: parameter
                for parameter in Parameter.list(self.api, part=part.pk)
            }

            m = re.match(
                r'^Carbide Drill Bit (?P<shank_diameter>1/8") (?P<tip_diameter>[0-9.]+mm) (?P<overall_length>[0-9.]+mm)$',
                part.name
            )

            for param, value in [
                    ("Shank Diameter", m.group("shank_diameter")),
                    ("Overall Length", m.group("overall_length")),
                    ("Tip Diameter", m.group("tip_diameter")),
                    ]:
                existing_parameter = existing_parameters[param]
                existing_parameter.save({"data": value})

ih = InventreeHelper()
ih.set_drill_bit_parameters()
