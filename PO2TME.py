#!/usr/bin/env python3
"""Convert InvenTree purchase order CSV export to a CSV compatible with TME import.

Personally, I usually use it like this:
./PO2TME.py -t -i ~/Downloads/PO-0033\ -\ TME\ -\ TME.csv
and copy the output from the terminal directly to TME QuickBuy.
"""

import argparse
import logging
import pandas as pd

_LOGGER = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-file", "-i",
        type=argparse.FileType("r"),
        default="-",
        help="csv file from InvenTree"
    )
    parser.add_argument(
        "--out-file", "-o",
        type=argparse.FileType("w"),
        default="-",
        help="csv file for TME import"
    )
    parser.add_argument(
        "--tab", "-t",
        help="create a tab separated file instead of CSV",
        action="store_const",
        dest="out_sep",
        const="\t", default=",",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    _LOGGER.debug("args: %s", args)

    with args.in_file as fr:
        df_in = pd.read_csv(fr)

        _LOGGER.debug("read csv:\n%s", df_in)

        df_out = df_in[["SKU", "quantity"]].copy()
        # InvenTree exports quantity as float for some reason
        df_out["quantity"] = df_out["quantity"].astype(int)

        with args.out_file as fw:
            df_out.to_csv(
                fw,
                index=False,
                sep=args.out_sep,
                header=False
            )


if __name__ == "__main__":
    main()
