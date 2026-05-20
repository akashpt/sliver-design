#!/bin/bash

rm -rf build dist *.spec

python3 -m PyInstaller \
    --onedir \
    --name sliver_app \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --add-data "MVSDK:MVSDK" \
    --collect-submodules classes \
    --hidden-import=cv2 \
    --hidden-import=numpy \
    --hidden-import=PyQt5 \
    --hidden-import=PyQt5.sip \
    --hidden-import=serial \
    --hidden-import=serial.tools.list_ports \
    --collect-all cv2 \
    app.py