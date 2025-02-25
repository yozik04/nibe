
## Pull Request Type

Please select the type of your PR:

- [ ] Add/Update Registries
- [ ] Feature
- [ ] Bug Fix

## Description

**Heatpump model**: <!-- e.g. F1145-6, F1255-6, F2040-6, S1155-6, S1255-6 -->

**Firmware version**: <!-- e.g. 5.3.11, 5.4.4 -->

<!-- Please describe your changes here. -->

<!-- IF THIS PR CHANGES REGISTERS. FOLLOW THE INSTRUCTIONS BELOW.

## How to add/update registers in the library

To add/edit registers in the library first of all you need to find documentation how these parameters are officially called. There will be a backward compatibility break if a name will change.

The process contains of mainly next steps: 1. Update source CSV files. 2. Convert CSV files to JSON. 3. Edit extensions.json if needed. 4. Submit PR.

### 1.A For F series pumps

Use [ModbusManager](https://professional.nibe.eu/sv/proffshjalp/kommunikation/nibe-modbus). Do CSV export for the unit you want to update. Find the correct file in `nibe/data` folder. Merge data into that file (Do not change/update any lines. All CSV files are source files they must not be changed).

### 1.B For S serires pumps

Change your pump language to English and do registers export. Merge that data into the correct file in `nibe/data` folder (Do not change/update any lines. All CSV files are source files they must not be changed).

### 2. Convert source CSV files to JSON

```bash
python3 -m nibe.console_scripts.convert_csv
```

### 3. Verify JSON files

Verify that conversion was successful and required lines correctly appeared in the json files. If some modifications are required you need to edit `extensions.json` to fix these.

### 4. Submit PR

Attach your source CSV file for reference so we could verify as well.
-->

## Checklist

- [ ] I have followed the instructions
- [ ] I ensured that my changes are well tested
