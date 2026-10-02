#!/usr/bin/env bash
# ==============================================================================
# A3 AlphaEdge PRO HFT Engine — Script de Detención Seguro (Linux)
# ==============================================================================

echo "🛑 Deteniendo A3 AlphaEdge PRO HFT Engine..."

# Detener servicio systemd si está activo
if systemctl --user is-active a3-motor-trade.service >/dev/null 2>&1; then
    echo "• Deteniendo servicio systemd a3-motor-trade..."
    systemctl --user stop a3-motor-trade.service
fi

PIDS=$(pgrep -f "server.py" | grep -v "stop.sh" | grep -v "grep")

if [ -z "$PIDS" ]; then
    echo "ℹ️  No hay instancias activas de server.py en ejecución."
    exit 0
fi

for PID in $PIDS; do
    echo "• Enviando señal SIGTERM a proceso PID: $PID"
    kill "$PID" 2>/dev/null
done

sleep 1

# Verificar si sigue corriendo y forzar si es necesario
PIDS_REMAINING=$(pgrep -f "server.py" | grep -v "stop.sh" | grep -v "grep")
if [ -n "$PIDS_REMAINING" ]; then
    echo "⚠️  Forzando cierre de procesos restantes..."
    for PID in $PIDS_REMAINING; do
        kill -9 "$PID" 2>/dev/null
    done
fi

echo "✅ Servidor detenido correctamente."
