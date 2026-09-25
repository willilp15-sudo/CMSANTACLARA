@echo off
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --windowed --name "Santa_Clara_Llamador" llamador_santa_clara.py
copy llamador_config.json dist\llamador_config.json
pause
