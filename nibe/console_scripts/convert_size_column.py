"""Convert Size of variable column in CSV files to standardized format."""

import argparse
from pathlib import Path
import sys

SIZE_MAPPING = {
    "1.0": "s8",
    "2.0": "s16",
    "3.0": "s32",
    "4.0": "u8",
    "5.0": "u16",
    "6.0": "u32",
    "1": "s8",
    "2": "s16",
    "3": "s32",
    "4": "u8",
    "5": "u16",
    "6": "u32",
    "s8": "s8",
    "s16": "s16",
    "s32": "s32",
    "u8": "u8",
    "u16": "u16",
    "u32": "u32",
}


def convert_size_column(file_path: Path) -> bool:
    """Convert Size of variable column in CSV file."""
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Detect delimiter
    delimiter = "\t" if "\t" in lines[0] else ";"

    # Find header row (skip ModbusManager rows if present)
    header_row_idx = 4 if lines[0].startswith("ModbusManager") else 0
    header = lines[header_row_idx]
    columns = header.split(delimiter)

    # Find "Size of variable" column
    size_column_idx = None
    for idx, col in enumerate(columns):
        if col.strip().lower() in ["size of variable", "size"]:
            size_column_idx = idx
            break

    if size_column_idx is None:
        print("Error: Could not find 'Size of variable' column")
        return False

    # Process data rows
    modified_lines = []
    changes_made = 0

    for line_idx, line in enumerate(lines):
        if line_idx <= header_row_idx or not line.strip():
            modified_lines.append(line)
            continue

        cells = line.split(delimiter)
        if len(cells) <= size_column_idx:
            modified_lines.append(line)
            continue

        current_value = cells[size_column_idx].strip()
        if current_value in SIZE_MAPPING:
            new_value = SIZE_MAPPING[current_value]
            if current_value != new_value:
                old_cell = cells[size_column_idx]
                value_start = old_cell.find(current_value)
                if value_start != -1:
                    cells[size_column_idx] = (
                        old_cell[:value_start]
                        + new_value
                        + old_cell[value_start + len(current_value) :]
                    )
                    line = delimiter.join(cells)
                    changes_made += 1

        modified_lines.append(line)

    if changes_made == 0:
        print(f"No changes needed for {file_path}")
        return True

    # Write back to file
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.writelines(modified_lines)

    print(f"Successfully converted {file_path} ({changes_made} changes)")
    return True


def main():
    """Main entry point for the console script."""
    parser = argparse.ArgumentParser(
        description="Convert 'Size of variable' column in CSV files to standardized format."
    )
    parser.add_argument("csv_file", type=Path, help="Path to the CSV file to convert")
    args = parser.parse_args()

    try:
        success = convert_size_column(args.csv_file)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
