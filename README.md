[![Test and Lint](https://github.com/yozik04/nibe/actions/workflows/test.yml/badge.svg)](https://github.com/yozik04/nibe/actions/workflows/test.yml)
![PyPI - Status](https://img.shields.io/pypi/status/nibe)
![PyPI - Downloads](https://img.shields.io/pypi/dm/nibe)
[![PyPI](https://img.shields.io/pypi/v/nibe)](https://pypi.org/project/nibe/)
![PyPI - License](https://img.shields.io/pypi/l/nibe)
[![Codecov](https://codecov.io/gh/yozik04/nibe/branch/master/graph/badge.svg?token=ZJIOTGLNW5)](https://codecov.io/gh/yozik04/nibe)

# Nibe library

Library for communication with Nibe heatpumps.

### Supported heatpump models

 - F1145
 - F1245
 - F1155
 - F1255
 - F1345
 - F1355
 - F370
 - F470
 - F730
 - F750
 - S320
 - S325
 - S330
 - S735
 - S1156
 - S1256
 - S2125
 - SMO20
 - SMO40
 - SMOS40
 - VVM225
 - VVM310
 - VVM320
 - VVM325
 - VVM500

## Connection methods

- RS485 hardwired using NibeGW on Arduino or RPi. NibeGW was developed by Pauli Anttila for [Openhab's integration](https://www.openhab.org/addons/bindings/nibeheatpump/).
- **(Not yet tested)** TCP Modbus for S Models
- **(Not yet tested)** Serial Modbus for Nibe Modbus 40)

### NibeGW

For this connection method to work you will need to connect an Arduino with special firmware that will act as a proxy between Heatpump RS485 and this library. Some details regarding how this method works can be found [here](https://www.openhab.org/addons/bindings/nibeheatpump/#prerequisites).

NibeGW firmware for Arduino or RPi can be [download here](https://github.com/openhab/openhab-addons/tree/3.2.x/bundles/org.openhab.binding.nibeheatpump/contrib/NibeGW).

- Library will open 9999 UDP listening port to receive packets from NibeGW.
- For read commands library will send UDP packets to NibeGW port 9999.
- For write commands library will send UDP packets to NibeGW port 10000.

Ports are configurable

```python3
import asyncio
import logging

from nibe.coil import CoilData
from nibe.connection.nibegw import NibeGW
from nibe.heatpump import HeatPump, Model

logger = logging.getLogger("nibe").getChild(__name__)

def on_coil_update(coil_data: CoilData):
    logger.debug(coil_data)

async def main():
    heatpump = HeatPump(Model.F1255)
    # heatpump.word_swap = False  # uncomment if you have word swap disabled in 5.3.11 service menu
    await heatpump.initialize()

    heatpump.subscribe(HeatPump.COIL_UPDATE_EVENT, on_coil_update)

    connection = NibeGW(heatpump=heatpump, remote_ip="192.168.1.2")
    await connection.start()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
```

### TCP Modbus

With S series heatpumps

```python3
import asyncio
import logging

from nibe.coil import CoilData
from nibe.connection.modbus import Modbus
from nibe.heatpump import HeatPump, Model

logger = logging.getLogger("nibe").getChild(__name__)

def on_coil_update(coil_data: CoilData):
    logger.debug(f"on_coil_update: {coil_data}")

async def main():
    heatpump = HeatPump(Model.F1255)
    # heatpump.word_swap = False  # uncomment if you have word swap disabled in 5.3.11 service menu
    await heatpump.initialize()

    heatpump.subscribe(HeatPump.COIL_UPDATE_EVENT, on_coil_update)

    connection = Modbus(heatpump=heatpump, url="tcp://192.168.1.2:502", slave_id=1)

    coil = heatpump.get_coil_by_name('bt50-room-temp-s1-40033')
    coil_data = await connection.read_coil(coil)

    logger.debug(f"main: {coil_data}")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
```

### Serial Modbus

With NIBE MODBUS 40

```python3
import asyncio
import logging

from nibe.coil import CoilData
from nibe.connection.modbus import Modbus
from nibe.heatpump import HeatPump, Model

logger = logging.getLogger("nibe").getChild(__name__)

def on_coil_update(coil_data: CoilData):
    logger.debug(f"on_coil_update: {coil_data}")

async def main():
    heatpump = HeatPump(Model.F1255)
    # heatpump.word_swap = False  # uncomment if you have word swap disabled in 5.3.11 service menu
    await heatpump.initialize()

    heatpump.subscribe(HeatPump.COIL_UPDATE_EVENT, on_coil_update)

    connection = Modbus(heatpump=heatpump, url="serial:///dev/ttyS0", slave_id=1, conn_options={"baudrate": 9600})

    coil = heatpump.get_coil_by_name('bt50-room-temp-s1-40033')
    coil_data = await connection.read_coil(coil)

    logger.debug(f"main: {coil_data}")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
```

### Model auto detection

With NibeGW it is possible to auto identify heatpump model.
Heatpump sends information about model every 15 seconds.
```
heatpump = HeatPump()  # Note that we do not specify model here

# ...

connection = NibeGW(heatpump=heatpump, remote_ip="192.168.1.2")
await connection.start()
heatpump.product_info = await connection.read_product_info()
await heatpump.initialize()
```

## Disclaimer

Nibe is registered mark of NIBE Energy Systems.

The code was developed as a way of integrating personally owned Nibe heatpump, and it cannot be used for other purposes. It is not affiliated with any company, and it doesn't have commercial intent.

The code is provided AS IS and the developers will not be held responsible for failures in the heatpump operation or any other malfunction.

# HOWTOs for developers

## How to capture and replay traffic from NibeGW

### Requirements

APT:
 - tcpdump
 - tcpreplay

On recipient device run:
```bash
sudo tcpdump -i eth0 udp port 9999 -w nibe-9999.pcap

tcprewrite --infile=nibe-9999.pcap --outfile=nibe-9999rw.pcap --dstipmap=192.168.1.3:192.168.1.2 --enet-dmac=CC:CC:CC:CC:CC:CC --fixcsum

sudo tcpreplay --intf1=eth0 nibe-9999rw.pcap
```

You will need to replace IP addresses for rewrite and Mac address of new recipient device

## I want to add/update registers in the library

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

Verify that conversion was successful and required lines correctly appeared in the json files. If some modifications are required you need to edit `extensions.json` to fix these. Do not edit source CSV files.

### 4. Submit PR

Attach your source CSV file for reference so we could verify as well.
