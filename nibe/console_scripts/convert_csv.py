import json
import logging
import re

import pandas
from slugify import slugify

from nibe.heatpump import Model

logger = logging.getLogger("nibe").getChild(__name__)


class CSVConverter:
    def __init__(self, in_file, out_file):
        self.in_file = in_file
        self.out_file = out_file

        self.data = None

    def convert(self):
        self._read_csv()

        self._lowercase_column_names()

        self._update_index()

        self._make_name_using_slugify()

        self._fix_data_unit_column()

        self._fix_data_types()

        self._replace_mode_with_boolean_write_parameter()

        self._unset_equal_min_max_default_values()

        self._make_mapping_parameter()

        self._export_to_file()

    def _make_dict(self):
        return {index: row.dropna().to_dict() for index, row in self.data.iterrows()}

    def _make_mapping_parameter(self):
        re_mapping = re.compile(
            r"(?P<value>\d+|I)\s*=\s*(?P<key>(?:[\w +.-]+[\w]\b[+]?(?! *=)))",
            re.IGNORECASE,
        )
        mappings = (
            self.data["info"]
            .where(~self.data["info"].str.contains("encoded"))
            .str.extractall(re_mapping)
        )
        mappings["value"] = mappings["value"].str.replace("I", "1").astype("int")
        mappings = mappings.reset_index("match", drop=True)
        mappings = mappings.drop_duplicates()
        self.data["mappings"] = pandas.Series(
            {k: dict(g.values) for k, g in mappings.groupby("value", level=0)}
        )

    def _unset_equal_min_max_default_values(self):
        valid_min_max = self.data["min"] != self.data["max"]
        self.data["min"] = self.data["min"].where(valid_min_max)
        self.data["max"] = self.data["max"].where(valid_min_max)
        self.data["default"] = self.data["default"].where(valid_min_max)

    def _fix_data_types(self):
        self.data["unit"] = self.data["unit"].astype("string")
        self.data["title"] = self.data["title"].astype("string")
        self.data["info"] = self.data["info"].astype("string")
        self.data["size"] = self.data["size"].astype("string")
        self.data["name"] = self.data["name"].astype("string")

    def _fix_data_unit_column(self):
        self.data["unit"] = (
            self.data["unit"].replace(r"^\s*$", pandas.NA, regex=True).str.strip()
        )

    def _make_name_using_slugify(self):
        ids = pandas.Series(self.data.index, index=self.data.index)
        self.data["name"] = self.data["title"].combine(
            ids, lambda title, id_: slugify(f"{title}-{id_}")
        )

    def _replace_mode_with_boolean_write_parameter(self):
        self.data["mode"] = self.data["mode"].str.strip().astype("string")

        self.data["write"] = self.data["mode"].map(
            lambda x: True if x == "R/W" else pandas.NA
        )
        del self.data["mode"]

    def _lowercase_column_names(self):
        self.data.columns = map(str.lower, self.data.columns)

    def _read_csv(self):
        self.data = pandas.read_csv(
            self.in_file,
            sep=";",
            skiprows=4,
            encoding="latin1",
            index_col=False,
            skipinitialspace=True,
        )

    def _update_index(self):
        self.data = self.data.set_index("id")

    def _export_to_file(self):
        o = self._make_dict()
        with open(self.out_file, "w") as fh:
            json.dump(o, fh, indent=2)


def run():
    for in_file in Model.get_data_path().glob("*.csv"):
        out_file = in_file.with_suffix(".json")
        logger.info(f"Converting {in_file} to {out_file}")
        CSVConverter(in_file, out_file).convert()
        logger.info(f"Converted {in_file} to {out_file}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
