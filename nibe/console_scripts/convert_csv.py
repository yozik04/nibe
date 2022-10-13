import asyncio
from collections.abc import Mapping, MutableMapping
from importlib.resources import files, open_text
import json
import logging
import re

import pandas
from slugify import slugify

from nibe.heatpump import HeatPump, Model

logger = logging.getLogger("nibe").getChild(__name__)


def update_dict(d: MutableMapping, u: Mapping) -> Mapping:
    for k, v in u.items():
        if isinstance(v, Mapping):
            update_dict(d.setdefault(k, {}), v)
        else:
            d[k] = v


class CSVConverter:
    def __init__(self, in_file, out_file, extensions):
        self.in_file = in_file
        self.out_file = out_file
        self.extensions = extensions

        self.data = None

    def convert(self):
        self._read_csv()

        self._lowercase_column_names()

        self._update_index()

        self._fix_data_soft_hyphens()

        self._make_name_using_slugify()

        self._fix_data_unit_column()

        self._fix_data_types()

        self._fix_data_size_column()

        self._replace_mode_with_boolean_write_parameter()

        self._unset_equal_min_max_default_values()

        self._make_mapping_parameter()

        self._export_to_file()

    def _make_dict(self):
        return {index: row.dropna().to_dict() for index, row in self.data.iterrows()}

    def _make_mapping_parameter(self):
        if "info" not in self.data:
            return

        re_mapping = re.compile(
            r"(?P<value>\d+|I)\s*=\s*(?P<key>(?:[\w +.-]+[\w]\b[+]?(?! *=)))",
            re.IGNORECASE,
        )
        mappings = (
            self.data["info"]
            .where(~self.data["info"].str.contains("encoded"))
            .str.extractall(re_mapping)
        )
        mappings["value"] = mappings["value"].str.replace("I", "1").astype("str")
        mappings = mappings.reset_index("match", drop=True)
        self.data["mappings"] = pandas.Series(
            {
                str(k): self._make_mapping_series(g)
                for k, g in mappings.groupby("value", level=0)
            }
        )

    def _make_mapping_series(self, g):
        return g.set_index("value", drop=True)["key"].drop_duplicates()

    def _unset_equal_min_max_default_values(self):
        valid_min_max = self.data["min"] != self.data["max"]
        self.data["min"] = self.data["min"].where(valid_min_max)
        self.data["max"] = self.data["max"].where(valid_min_max)
        self.data["default"] = self.data["default"].where(valid_min_max)

    def _fix_data_types(self):
        self.data["unit"] = self.data["unit"].astype("string")
        self.data["title"] = self.data["title"].astype("string")
        if "info" in self.data:
            self.data["info"] = self.data["info"].astype("string")
        self.data["size"] = self.data["size"].astype("string")
        self.data["name"] = self.data["name"].astype("string")

    def _fix_data_size_column(self):
        mapping = {
            "1.0": "s8",
            "2.0": "s16",
            "3.0": "s32",
            "4.0": "u8",
            "5.0": "u16",
            "6.0": "u32",
            "s8": "s8",
            "s16": "s16",
            "s32": "s32",
            "u8": "u8",
            "u16": "u16",
            "u32": "u32",
        }

        self.data["size"] = self.data["size"].map(mapping)

    def _fix_data_unit_column(self):
        self.data["unit"] = (
            self.data["unit"].replace(r"^\s*$", pandas.NA, regex=True).str.strip()
        )

    def _fix_data_soft_hyphens(self):
        self.data["title"] = self.data["title"].str.replace("\xad", "")

    def _make_name_using_slugify(self):
        ids = pandas.Series(self.data.index, index=self.data.index)
        self.data["name"] = self.data["title"].combine(
            ids, lambda title, id_: slugify(f"{title}-{id_}")
        )

    def _replace_mode_with_boolean_write_parameter(self):
        if "mode" in self.data:
            self.data["mode"] = self.data["mode"].str.strip().astype("string")

            self.data["write"] = self.data["mode"].map(
                lambda x: True if x == "R/W" else pandas.NA
            )
            del self.data["mode"]

    def _lowercase_column_names(self):
        self.data.columns = map(str.lower, self.data.columns)

    def _read_csv(self):
        with open(self.in_file, encoding="latin1") as f:
            modbus_manager = f.readline().startswith("ModbusManager")

        if modbus_manager:
            self.data = pandas.read_csv(
                self.in_file,
                sep=";",
                skiprows=4,
                encoding="latin1",
                index_col=False,
                skipinitialspace=True,
            )
        else:
            self.data = pandas.read_csv(
                self.in_file,
                sep="\t",
                skiprows=0,
                encoding="utf8",
                index_col=False,
                skipinitialspace=True,
                na_values="-",
            )

    def _update_index(self):
        def calculate_number(register_type: str, register: str):
            if register_type == "MODBUS_COIL":
                return str(10000 + int(register))
            if register_type == "MODBUS_DISCRETE_INPUT":
                return str(20000 + int(register))
            if register_type == "MODBUS_INPUT_REGISTER":
                return str(30000 + int(register))
            if register_type == "MODBUS_HOLDING_REGISTER":
                return str(40000 + int(register))
            return None

        if "id" in self.data:
            self.data["id"] = self.data["id"].astype("string")
        else:
            self.data["id"] = self.data["registertype"].combine(
                self.data["register"], calculate_number
            )
            del self.data["registertype"]
            del self.data["register"]
        self.data = self.data.set_index("id")

    def _convert_series_to_dict(self, o):
        if isinstance(o, pandas.Series):
            return o.sort_index(key=lambda i: i.astype(int)).to_dict()

        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    def _export_to_file(self):
        o = self._make_dict()
        update_dict(o, self.extensions)
        with open(self.out_file, "w") as fh:
            json.dump(o, fh, indent=2, default=self._convert_series_to_dict)
            fh.write("\n")


async def run():
    with open_text("nibe.data", "extensions.json") as fp:
        all_extensions = json.load(fp)

    for in_file in files("nibe.data").glob("*.csv"):
        out_file = in_file.with_suffix(".json")

        extensions = {}
        for extra in all_extensions:
            if out_file.name not in extra["files"]:
                continue
            update_dict(extensions, extra["data"])

        logger.info(f"Converting {in_file} to {out_file}")
        try:
            CSVConverter(in_file, out_file, extensions).convert()

            await _validate(out_file)

            logger.info(f"Converted {in_file} to {out_file}")
        except Exception as e:
            logger.exception(f"Failed to convert {in_file}: {e}", e)


async def _validate(out_file):
    model = Model.CUSTOM
    model.data_file = out_file
    hp = HeatPump(model)
    await hp.initialize()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
