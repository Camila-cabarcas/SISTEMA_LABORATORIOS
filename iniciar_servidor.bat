@echo off
taskkill /F /IM ngrok.exe /T > nul 2>&1
taskkill /F /IM waitress-serve.exe /T > nul 2>&1
cd /d "C:\Users\Poderosisimo Robin\SISTEMA_LABORATORIOS"
start "Servidor Django" /B "venv\Scripts\waitress-serve.exe" --listen=0.0.0.0:8000 config.wsgi:application
timeout /t 3 /nobreak > nul
start "Tunel Ngrok" /B ngrok http --url=removable-nanny-emphases.ngrok-free.dev 172.21.35.40:8000
