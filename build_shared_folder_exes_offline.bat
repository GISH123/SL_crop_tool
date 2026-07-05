@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo Poker Crop Tool - shared-folder offline PyInstaller build
echo ============================================================
echo.

echo [1/5] Python environment
where python
python -V
if errorlevel 1 goto :error

echo.
echo [2/5] Checking required installed packages
python -c "import PyInstaller, cv2, numpy, tkinter; print('PyInstaller:', PyInstaller.__version__); print('cv2:', cv2.__version__); print('numpy:', numpy.__version__); print('tkinter ok')"
if errorlevel 1 (
    echo.
    echo [ERROR] Missing PyInstaller / cv2 / numpy / tkinter in this Python environment.
    echo Please install requirements first:
    echo   python -m pip install -r requirements.txt
    goto :error
)

echo.
echo [3/5] Cleaning old build output
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [4/5] Building all four EXEs into one shared folder
python -m PyInstaller --clean -y Poker_Crop_Tool_All_In_One_Folder.spec
if errorlevel 1 goto :error

echo.
echo [5/5] Copying docs, creating launchers, and creating working folders
if not exist "dist\Poker_Crop_Tool" goto :error

if exist README.md copy /y README.md "dist\Poker_Crop_Tool\README.md" >nul
if exist README_USAGE.md copy /y README_USAGE.md "dist\Poker_Crop_Tool\README_USAGE.md" >nul
if exist ref_img.jpg copy /y ref_img.jpg "dist\Poker_Crop_Tool\ref_img.jpg" >nul

echo @echo off> "dist\Poker_Crop_Tool\run_step1_from_cmd.bat"
echo cd /d "%%~dp0">> "dist\Poker_Crop_Tool\run_step1_from_cmd.bat"
echo Step1_Annotation_Tool.exe>> "dist\Poker_Crop_Tool\run_step1_from_cmd.bat"
echo pause>> "dist\Poker_Crop_Tool\run_step1_from_cmd.bat"

echo @echo off> "dist\Poker_Crop_Tool\run_step2_from_cmd.bat"
echo cd /d "%%~dp0">> "dist\Poker_Crop_Tool\run_step2_from_cmd.bat"
echo Step2_Crop_By_Annotation.exe>> "dist\Poker_Crop_Tool\run_step2_from_cmd.bat"
echo pause>> "dist\Poker_Crop_Tool\run_step2_from_cmd.bat"

echo @echo off> "dist\Poker_Crop_Tool\run_step3_from_cmd.bat"
echo cd /d "%%~dp0">> "dist\Poker_Crop_Tool\run_step3_from_cmd.bat"
echo Step3_YOLO11_HTTP_Predict.exe>> "dist\Poker_Crop_Tool\run_step3_from_cmd.bat"
echo pause>> "dist\Poker_Crop_Tool\run_step3_from_cmd.bat"

echo @echo off> "dist\Poker_Crop_Tool\run_step4_from_cmd.bat"
echo cd /d "%%~dp0">> "dist\Poker_Crop_Tool\run_step4_from_cmd.bat"
echo Step4_Build_Classified_Labels.exe>> "dist\Poker_Crop_Tool\run_step4_from_cmd.bat"
echo pause>> "dist\Poker_Crop_Tool\run_step4_from_cmd.bat"

if not exist "dist\Poker_Crop_Tool\outputs" mkdir "dist\Poker_Crop_Tool\outputs"
if not exist "dist\Poker_Crop_Tool\videos" mkdir "dist\Poker_Crop_Tool\videos"
if not exist "dist\Poker_Crop_Tool\datasets" mkdir "dist\Poker_Crop_Tool\datasets"
if not exist "dist\Poker_Crop_Tool\runtime_logs" mkdir "dist\Poker_Crop_Tool\runtime_logs"

echo.
echo ============================================================
echo DONE.
echo Send this whole folder:
echo   dist\Poker_Crop_Tool\
echo.
echo If double-click does nothing, run:
echo   run_step1_from_cmd.bat
echo   run_step2_from_cmd.bat
echo   run_step3_from_cmd.bat
echo   run_step4_from_cmd.bat
echo ============================================================
pause
exit /b 0

:error
echo.
echo ============================================================
echo BUILD FAILED. See the error above.
echo ============================================================
pause
exit /b 1
