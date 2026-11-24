@echo off
cd /d "%~dp0"
set PY=python
py -3.12 --version >nul 2>&1 && set PY=py -3.12
if not exist .venv (
    echo Creating virtual environment...
    %PY% -m venv .venv || goto :err
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err

echo Generating icon and building WhisperType.exe...
.venv\Scripts\python.exe -c "import whisper_type; whisper_type.ensure_ico_file()"
if exist "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe" (
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /out:WhisperType.exe /win32icon:app.ico /r:System.Windows.Forms.dll launcher.cs
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$wsh = New-Object -ComObject WScript.Shell; " ^
  "$dir = (Get-Location).Path; " ^
  "$exe = Join-Path $dir 'WhisperType.exe'; " ^
  "$ico = Join-Path $dir 'app.ico'; " ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { " ^
  "  if ($d -and (Test-Path $d)) { " ^
  "    $s = $wsh.CreateShortcut((Join-Path $d 'Whisper Type.lnk')); " ^
  "    $s.TargetPath = $exe; $s.WorkingDirectory = $dir; $s.IconLocation = $ico; $s.Save() " ^
  "  } " ^
  "}"

echo.
echo Setup complete! Double-click WhisperType.exe (or use the Desktop / Start Menu shortcut) to start.
pause
exit /b 0
:err
echo Setup failed.
pause
exit /b 1
