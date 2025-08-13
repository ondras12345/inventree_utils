#!/usr/bin/env python3
"""Import products from prusa3d.com e-shop to inventree."""

import argparse
import requests
import json
import re
import os
import tempfile
import pathlib
import mimetypes
import urllib
from urllib.parse import urlparse
from bs4 import BeautifulSoup  # pip3 install beautifulsoup4
from inventree.api import InvenTreeAPI
from inventree.part import Part, PartCategory
from inventree.company import Company, SupplierPart, SupplierPriceBreak

# environment variables needed:
# INVENTREE_API_HOST, INVENTREE_API_TOKEN, INVENTREE_API_TOKEN_NAME
INVENTREE_URL = os.getenv("INVENTREE_API_HOST")

COOKIES = {
    "CURRENCY_CODE": "CZK",
}

CATEGORY_MAP = {
    ("Accessories", "Nozzles"): "3D Printer Accessories/Nozzles",
    ("Accessories", "Print Sheets"): "3D Printer Accessories/Print Sheets",
    ("Accessories", "Tools & Crafting"): "3D Printer Accessories",
    # ("Accessories", ): "3D Printer Accessories",
    ("Filament", ): "3D Printing Filament",
    ("Spare parts", ): "3D Printer Accessories/Spare Parts",
}


def get_inventree_category(prusa_category: tuple) -> str:
    cat = prusa_category
    while cat:
        if cat in CATEGORY_MAP:
            return CATEGORY_MAP[cat]
        cat = cat[:-1]  # drop the rightmost element
    raise KeyError(f"No category mapping for {prusa_category}")


class InventreeHelper:
    def __init__(self):
        self.api = InvenTreeAPI()
        self.prusa_company = Company.list(self.api, name="Prusa Research")[0]

    def get_category(self, category_path):
        name = category_path.split("/")[-1]
        for category in PartCategory.list(self.api, search=name):
            if category.pathstring == category_path:
                return category
        return None

    def get_supplier_part(self, sku):
        supplier_parts = SupplierPart.list(self.api, SKU=sku, supplier=self.prusa_company.pk)
        if len(supplier_parts) == 1:
            return supplier_parts[0]
        if len(supplier_parts) != 0:
            raise AssertionError("more than one supplier part")
        return None

    def check_supplier_part(self, sku: str) -> SupplierPart | None:
        return self.get_supplier_part(sku)

    def upload_image(self, part: Part, image_url: str, filename_prefix: str):
        r = requests.get(image_url)
        r.raise_for_status()
        image_content = r.content
        if not image_content:
            raise Exception(f"failed to download image {image_url}")

        extension = mimetypes.guess_extension(r.headers['content-type']) or ""
        filename = f"{filename_prefix}{extension}"

        with tempfile.TemporaryDirectory() as td:
            img_file = pathlib.Path(td) / filename
            with open(img_file, "wb") as f:
                f.write(image_content)
            part.uploadImage(str(img_file))

    def create_prusa_part(self, part_data: dict) -> SupplierPart:
        matching_parts = Part.list(self.api, search=part_data["name"])
        if len(matching_parts) == 1:
            part = matching_parts[0]
            print(f"reusing existing part {INVENTREE_URL}/part/{part.pk}/")
        else:
            category_path = get_inventree_category(part_data["category"])

            category = self.get_category(category_path)
            if category is None:
                raise Exception(f"category does not exist: {category_path}")

            inventree_part_data = {
                "category": category.pk,
                "name": part_data["name"],
                "description": part_data["description"],
                "active": True,
                "component": True,
                "purchaseable": True,
            }
            part = Part.create(self.api, inventree_part_data)
            self.upload_image(part, part_data["image"], part_data["sku"])

        supplier_part_data = {
            "part": part.pk,
            "supplier": self.prusa_company.pk,
            "SKU": part_data["sku"],
            "link": part_data["url"],
            "available": part_data["stock_quantity"],
        }

        if not (supplier_part := self.check_supplier_part(part_data["sku"])):
            supplier_part = SupplierPart.create(self.api, supplier_part_data)

        # update existing supplier part
        supplier_part.save(supplier_part_data)
        price_data = {
            "quantity": 1,
            "price": part_data["price_czk_without_vat"],
            "price_currency": "CZK",
        }
        price_breaks = SupplierPriceBreak.list(self.api, part=supplier_part.pk)
        if price_breaks:
            price_break = price_breaks[0]
            price_break.save(price_data)
        else:
            price_break = SupplierPriceBreak.create(self.api, {
                "part": supplier_part.pk,
                **price_data,
            })

        return supplier_part


def url_type(arg):
    url = urlparse(arg)
    if all((url.scheme, url.netloc)):
        return arg
    raise argparse.ArgumentTypeError("Invalid URL")


def get_product_json(json_data: dict) -> dict:
    tmp1 = json_data["props"]["pageProps"]["urqlState"]
    if len(tmp1.keys()) != 1:
        raise ValueError(f"expected one product key: {tmp1.keys()}")
    tmp2 = next(iter(tmp1.values()))
    assert not tmp2["hasNext"]
    product = json.loads(tmp2["data"])["product"]
    return product


def get_description(product: dict) -> str:
    soup = BeautifulSoup(product["shortDescription"], "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return text.split("\n")[0].strip()


def parse_prusa_json(json_data: dict) -> dict:
    product = get_product_json(json_data)

    categories = [
        b["name"] for b in product["breadcrumbs"]
        if b["__typename"] == "Category"
    ]
    categories.reverse()

    en_urls = [
        u["url"] for u in product["urlList"]
        if u["locale"] == "en"
    ]
    assert len(en_urls) == 1
    english_url = en_urls[0]

    base_url = re.match(r"^(https?://[^/]+)/", english_url)[1]

    # Are they mixing images with videos? Let's check the typename just to be
    # sure.
    image_urls = [
        i["url"] for i in product["images"]
        if i["__typename"] == "Image"
    ]
    image_url = image_urls[0] if len(image_urls) > 0 else None

    part_data = {
        "name": product["nameWithReplacedPlaceholders"],
        "sku": product["slug"].removeprefix("product/").removesuffix("/"),
        "description": get_description(product),
        "prusa_uuid": product["uuid"],
        "url": english_url,
        "stock_quantity": product["stockQuantity"],
        "category": tuple(categories),
        "price_czk_without_vat": product["price"]["priceWithoutVat"],
        "manufacturer": product["brand"]["name"] if product["brand"] else None,
        "image": f"{base_url}{image_url}",
    }
    return part_data


def get_part_json(listing_url: str) -> dict:
    r = requests.get(listing_url, cookies=COOKIES)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__", type="application/json")
    assert script_tag
    script_data = script_tag.string.strip()
    del soup
    json_data = json.loads(script_data)
    return json_data


def get_part_data(listing_url: str) -> dict:
    json_data = get_part_json(listing_url)
    return parse_prusa_json(json_data)


def get_english_url(listing_url: str) -> str:
    # the slug is different in each language...
    # listing_url = re.sub(r"^(https?://[^/]+)/../prod[^/]*/", r"\1/product/", listing_url)

    if re.match(r"^https?://[^/]+/product/", listing_url):
        return listing_url

    json_data = get_part_json(listing_url)
    product = get_product_json(json_data)
    url_list = product["urlList"]
    en_urls = [
        u["url"] for u in url_list
        if u["locale"] == "en"
    ]
    assert len(en_urls) == 1
    english_url = en_urls[0]
    print(f"english URL: {english_url}")
    return english_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("listing_url", type=url_type)
    args = parser.parse_args()

    listing_url = get_english_url(args.listing_url)
    from pprint import pprint
    part_data: dict = get_part_data(listing_url)
    pprint(part_data)

    inv = InventreeHelper()
    sp = inv.create_prusa_part(part_data)
    print(f"\nimported supplier part: {INVENTREE_URL}{sp.url}")


if __name__ == "__main__":
    main()
