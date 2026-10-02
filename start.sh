#!/usr/bin/env bash
# ==============================================================================
# A3 AlphaEdge PRO HFT Engine — Script de Inicio Seguro en Segundo Plano (Linux)
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Cargar variables de entorno si existe .env
if [ -f .env ]; then
    echo "📋 Cargando variables de entorno desde .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Verificar si ya está corriendo
RUNNING_PID=$(pgrep -f "server.py" | grep -v "start.sh" | grep -v "status.sh" | head -n 1)
if [ -n "$RUNNING_PID" ]; then
    echo "⚠️  A3 Motor Trade ya está en ejecución (PID: $RUNNING_PID)."
    echo "👉 Abre http://localhost:${PORT:-8005} en tu navegador."
    exit 0
fi

# Intentar inicio con systemd user service para persistencia 24/7
if systemctl --user list-unit-files a3-motor-trade.service >/dev/null 2>&1; then
    echo "🚀 Iniciando A3 AlphaEdge PRO HFT Engine vía systemd (Modo 24/7 Persistente)..."
    systemctl --user start a3-motor-trade.service
    sleep 1.5
    if systemctl --user is-active a3-motor-trade.service >/dev/null 2>&1; then
        PID=$(pgrep -f "server.py" | grep -v "start.sh" | head -n 1)
        echo "✅ Motor iniciado con éxito vía systemd (PID: $PID, Auto-Restart: SI)."
        echo "📊 Dashboard Web disponible en: http://localhost:${PORT:-8005}"
        echo "📋 Archivo de logs en tiempo real: tail -f server.log"
        exit 0
    fi
fi

# Fallback: Seleccionar intérprete Python (venv o sistema)
PYTHON_BIN="python3"
if [ -d "$DIR/.venv" ]; then
    PYTHON_BIN="$DIR/.venv/bin/python3"
fi

echo "🚀 Iniciando A3 AlphaEdge PRO HFT Engine (segundo plano con setsid)..."
setsid nohup "$PYTHON_BIN" server.py </dev/null >> server.log 2>&1 &
PID=$!

sleep 1.5

if ps -p $PID > /dev/null; then
    echo "✅ Motor iniciado con éxito en segundo plano (PID: $PID)."
    echo "📊 Dashboard Web disponible en: http://localhost:${PORT:-8005}"
    echo "📋 Archivo de logs en tiempo real: tail -f server.log"
else
    echo "❌ Error al iniciar el motor. Revisa server.log para más detalles:"
    cat server.log | tail -n 20
    exit 1
fi

