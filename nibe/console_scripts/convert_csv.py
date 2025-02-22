import argparse
import asyncio
from collections.abc import Mapping, MutableMapping
import difflib
from importlib.resources import files, open_text
import json
import logging
import re
from typing import Optional

import pandas as pd
from slugify import slugify

from nibe.heatpump import HeatPump, Model

logger = logging.getLogger("nibe")

re_mapping = re.compile(
    r"(?P<key>(?<!\w)\d+|I)\s*=\s*(?P<value>(?:[\w +.-]+[\w]\b[+]?(?! *=)))",
    re.IGNORECASE,
)


def _extract_mappings(info: str) -> Optional[Mapping]:
    if pd.isna(info):
        return None

    if "Binary encoded" in info:
        return None

    mappings = {}
    matches = re_mapping.finditer(info)

    for match in matches:
        key = match.group("key")
        value = match.group("value")

        if key == "I":
            key = "1"

        mappings[key] = value

    if not mappings:
        return None

    return _sort_mappings(mappings)


def _sort_mappings(mappings) -> Mapping:
    return {str(k): mappings[str(k)] for k in sorted(map(int, mappings.keys()))}


def _sort_mappings_in_output(dict_):
    for key, value in dict_.items():
        if "mappings" in value:
            dict_[key]["mappings"] = _sort_mappings(value["mappings"])


def _update_dict(d: MutableMapping, u: Mapping, removeExplicitNulls: bool) -> Mapping:
    for k, v in u.items():
        if v is None and removeExplicitNulls:
            try:
                d.pop(k)
            except (IndexError, KeyError):
                pass
        elif isinstance(v, Mapping):
            _update_dict(d.setdefault(k, {}), v, removeExplicitNulls)
        else:
            d[k] = v

    return d


class ValidationFailed(Exception):
    """Raised when validation fails."""

    pass


class CSVConverter:
    """Converts CSV file to JSON file."""

    data: pd.DataFrame

    def __init__(self, in_file, out_file, extensions):
        self.in_file = in_file
        self.out_file = out_file
        self.extensions = extensions

    def convert(self):
        """Converts CSV file to JSON file."""
        self._process()

        self._export_to_file()

    def verify(self):
        """Verifies that the JSON file matches the CSV file after conversion."""
        self._process()

        self._verify_export()

    def _process(self):
        self._read_csv()

        self._unifi_column_names()

        self._update_index()

        self._fix_data_soft_hyphens()

        self._make_name_using_slugify()

        self._fix_data_unit_column()

        self._fix_data_types()

        self._fix_data_size_column()

        self._replace_mode_with_boolean_write_parameter()

        self._unset_equal_min_max_default_values()

        self._make_mapping_parameter()

        self._ensure_no_duplicate_ids()

    def _make_mapping_parameter(self):
        if "info" not in self.data:
            return

        # Create a mask to identify rows where mapping is allowed
        allowed_mask = self.data["factor"] == 1

        # Apply the function to each cell in self.data["info"] column where mapping is allowed
        self.data.loc[allowed_mask, "mappings"] = self.data.loc[
            allowed_mask, "info"
        ].apply(_extract_mappings)

    def _unset_equal_min_max_default_values(self):
        valid_min_max = self.data["min"] != self.data["max"]
        for column in ["min", "max", "default"]:
            self.data[column] = self.data[column].where(valid_min_max)

    def _fix_data_types(self):
        string_columns = ["unit", "title", "size", "name"]
        for column in string_columns:
            self.data[column] = self.data[column].astype("string")

        if "info" in self.data:
            self.data["info"] = self.data["info"].astype("string")

        self.data["factor"] = self.data["factor"].astype("int")

        float_columns = ["min", "max", "default"]
        for column in float_columns:
            self.data[column] = self.data[column].astype("float")

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

        size = self.data["size"].map(mapping)

        invalid_size = size.isna()
        if any(invalid_size):
            logger.warning(
                "Invalid size data replaced with u16:\n%s", self.data[invalid_size]
            )
            size[invalid_size] = "u16"

        self.data["size"] = size

    def _fix_data_unit_column(self):
        self.data["unit"] = (
            self.data["unit"].replace(r"^\s*$", pd.NA, regex=True).str.strip()
        )

    def _fix_data_soft_hyphens(self):
        self.data["title"] = self.data["title"].str.replace("\xad", "")

    def _make_name_using_slugify(self):
        ids = pd.Series(self.data.index, index=self.data.index)
        self.data["name"] = self.data["title"].combine(
            ids, lambda title, id_: slugify(f"{title}-{id_}")
        )

    def _replace_mode_with_boolean_write_parameter(self):
        if "mode" in self.data:
            self.data["mode"] = self.data["mode"].str.strip().astype("string")

            self.data["write"] = self.data["mode"].map(
                lambda x: True if x == "R/W" else pd.NA
            )
            del self.data["mode"]

    def _unifi_column_names(self):
        self.data.columns = map(str.lower, self.data.columns)
        self.data.rename(
            columns={
                "division factor": "factor",
                "size of variable": "size",
                "min value": "min",
                "max value": "max",
                "default value": "default",
            },
            inplace=True,
        )

    def _read_csv(self):
        with open(self.in_file, encoding="latin1") as f:
            modbus_manager = f.readline().startswith("ModbusManager")

        if modbus_manager:
            self.data = pd.read_csv(
                self.in_file,
                sep=";",
                skiprows=4,
                encoding="latin1",
                index_col=False,
                skipinitialspace=True,
            )
        else:
            self.data = pd.read_csv(
                self.in_file,
                sep="\t",
                skiprows=0,
                encoding="utf-8",
                index_col=False,
                skipinitialspace=True,
                na_values="-",
            )

    def _update_index(self):
        def calculate_number(row):
            register_type: str = row["register type"]
            location = 1 + int(row["register"])
            if register_type == "MODBUS_COIL":
                return str(int(location))
            if register_type == "MODBUS_DISCRETE_INPUT":
                return str(10000 + int(location))
            if register_type == "MODBUS_INPUT_REGISTER":
                return str(30000 + int(location))
            if register_type == "MODBUS_HOLDING_REGISTER":
                return str(40000 + int(location))
            return None

        if "register type" in self.data:
            id_prefixed = self.data.loc[
                self.data["title"].str.startswith("id:", na=True)
            ]
            if len(id_prefixed) > 0:
                logger.warning(
                    "Ignoring unnamed and often duplicated rows:\n%s",
                    id_prefixed,
                )
                self.data.drop(id_prefixed.index, inplace=True)

            self.data["id"] = self.data.apply(calculate_number, axis=1)

            self.data["mode"] = self.data["register type"].map(
                lambda x: "R/W"
                if x in ("MODBUS_HOLDING_REGISTER", "MODBUS_COIL")
                else "R"
            )

            del self.data["register type"]
            del self.data["register"]

        self.data["id"] = self.data["id"].astype("string")

        self.data = self.data.set_index("id")

    def _ensure_no_duplicate_ids(self):
        if self.data.index.has_duplicates:
            logger.error(
                f"Duplicate IDs found in {self.in_file}:\n{self.data[self.data.index.duplicated()]}"
            )
            raise ValueError("Duplicate IDs found")

    def _make_dict(self) -> dict:
        out = {index: row.dropna().to_dict() for index, row in self.data.iterrows()}

        _update_dict(out, self.extensions, True)
        _sort_mappings_in_output(out)

        return out

    def _export_to_file(self):
        out = self._make_dict()

        with open(self.out_file, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
            fh.write("\n")

    def _verify_export(self):
        o = self._make_dict()

        try:
            with open(self.out_file, encoding="utf-8") as fh:
                file_contents = json.load(fh)
        except json.JSONDecodeError:
            raise ValidationFailed(f"Failed to decode JSON file {self.out_file}")
        except FileNotFoundError:
            raise ValidationFailed(f"File {self.out_file} not found")

        if o != file_contents:
            expected = json.dumps(o, indent=2, sort_keys=True)
            actual = json.dumps(file_contents, indent=2, sort_keys=True)
            diff = difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile="expected",
                tofile="actual",
                lineterm="",
            )
            diff_text = "\n".join(diff)
            raise ValidationFailed(f"File {self.out_file} does not match:\n{diff_text}")


async def _verify_heat_pump_initialization(out_file):
    model = Model.CUSTOM
    model.data_file = out_file
    hp = HeatPump(model)
    await hp.initialize()


async def run(mode):
    with open_text("nibe.data", "extensions.json") as fp:
        all_extensions = json.load(fp)

    processed_files = []
    processing_failed = []

    for in_file in files("nibe.data").glob("*.csv"):
        out_file = in_file.with_suffix(".json")

        extensions = {}
        for extra in all_extensions:
            if out_file.name not in extra["files"]:
                continue
            _update_dict(extensions, extra["data"], False)

        logger.info(f"Processing {in_file} to {out_file}")
        try:
            converter = CSVConverter(in_file, out_file, extensions)
            if mode == "verify":
                converter.verify()
            elif mode == "export":
                converter.convert()
            else:
                raise ValueError(f"Invalid mode: {mode}")

            await _verify_heat_pump_initialization(out_file)

            if mode == "verify":
                logger.info(f"Verified {out_file}")
            else:
                logger.info(f"Converted {in_file} to {out_file}")
        except ValidationFailed as ex:
            processing_failed.append(in_file)
            logger.error("Validation failed for %s: %s", in_file, ex)
        except Exception as ex:
            processing_failed.append(in_file)
            logger.exception("Failed to process %s: %s", in_file, ex)
        finally:
            processed_files.append(in_file)

    assert len(processed_files) > 0, "No files were processed"
    assert len(processing_failed) == 0, f"Failed to process files: {processing_failed}"

    logger.info(
        "Successfully processed files: %s", list(map(lambda x: x.name, processed_files))
    )


def main():
    parser = argparse.ArgumentParser(description="Convert CSV files to JSON.")
    parser.add_argument("--verify", action="store_true", help="Run in verify mode")
    args = parser.parse_args()

    mode = "verify" if args.verify else "export"

    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(run(mode))
    except AssertionError as ex:
        logger.error(ex)
        exit(1)


if __name__ == "__main__":
    main()
