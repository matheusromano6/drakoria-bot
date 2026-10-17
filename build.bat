@echo off
rem Gera dist\DrakoriaBot.exe (so Windows). Precisa de: pip install -r requirements.txt pyinstaller
python -c "import playwright, os; print(os.path.join(os.path.dirname(playwright.__file__), 'driver'))" > "%TEMP%\pw_driver.txt"
set /p PLAYWRIGHT_DRIVER=<"%TEMP%\pw_driver.txt"
python -m PyInstaller --onefile --windowed --name DrakoriaBot --icon "%CD%\icon.ico" ^
  --add-data "%PLAYWRIGHT_DRIVER%;playwright\driver" ^
  --add-data "%CD%\drakoria_bot\data;drakoria_bot\data" ^
  --add-data "%CD%\icon.ico;." ^
  --hidden-import pystray --hidden-import pystray._win32 ^
  --distpath dist --workpath build --specpath spec --noconfirm drakoria_bot.pyw
