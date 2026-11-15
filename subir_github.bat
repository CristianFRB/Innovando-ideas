@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Subiendo FireCal a GitHub ===
if not exist ".git" (
  git init
  git branch -M main
)
git remote get-url origin >nul 2>&1 || git remote add origin https://github.com/Fernanda-2703/Espace-Apps-Ideas-Innovadoras.git
git add -A
rem Seguridad: nunca subir claves
git rm --cached -q --ignore-unmatch .env js/config.js Manual_despliegue_FireCal_PRIVADO.docx >nul 2>&1
git ls-files | findstr /i /c:".env" /c:"config.js" /c:"PRIVADO" | findstr /v /i /c:".env.example" /c:"config.ejemplo.js" >nul && (
  echo ERROR: hay un archivo con claves en la lista. No se sube nada.
  pause
  exit /b 1
)
git commit -m "FireCal: riesgo Peru/Amazonia, lluvia robusta, listas desplegables, panel plegable"
git pull origin main --allow-unrelated-histories --no-edit
git push -u origin main
echo.
if errorlevel 1 (echo Algo fallo: copia el mensaje de arriba y pasaselo a Claude.) else (echo Listo: subido a GitHub.)
pause
