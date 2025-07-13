#!/usr/bin/env python3
import re
from inventree.api import InvenTreeAPI
from inventree.part import Parameter, ParameterTemplate, Part, PartCategory


class InventreeHelper:
    def __init__(self):
        # set environment variables: INVENTREE_API_HOST, INVENTREE_API_TOKEN, INVENTREE_API_TOKEN_NAME
        self.api = InvenTreeAPI()
        self.parameter_templates = self.get_parameter_templates()

    def get_parameter_templates(self):
        return {
            parameter_template.name: parameter_template
            for parameter_template in ParameterTemplate.list(self.api)
        }

    def set_kicad_NS25(self):
        category = PartCategory(self.api, 20)
        assert category.pathstring == "Electronics/Connectors/Rectangular"

        matching_parts = Part.list(self.api, category=category, search="NS25-W")

        for part in matching_parts:
            print("part:", part)
            existing_parameters = {
                parameter.template_detail["name"]: parameter
                for parameter in Parameter.list(self.api, part=part.pk)
            }

            m = re.match(
                r'^NS25-W(?P<pin_count>[0-9]+)(?P<variant>[PK])$',
                part.name
            )

            pin_count = int(m.group("pin_count"))
            VARIANTS = {
                "P": "Vertical",
                "K": "Horizontal",
            }
            variant = VARIANTS[m.group("variant")]

            for param, value in [
                    ("KiCad Symbol", f"Connector:Conn_01x{pin_count:02}_Pin"),
                    ("KiCad Footprint", f"Connector_Molex:Molex_KK-254_AE-6410-{pin_count:02}A_1x{pin_count:02}_P2.54mm_{variant}"),
                    ]:
                parameter = existing_parameters.get(param, None)
                if parameter is not None:
                    parameter.save({"data": value})
                else:
                    parameter = Parameter.create(
                        self.api,
                        data={
                            "part": part.pk,
                            "template": self.parameter_templates[param].pk,
                            "data": value
                        }
                    )


ih = InventreeHelper()
ih.set_kicad_NS25()
