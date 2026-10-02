#!/usr/bin/env bash
# ==============================================================================
# A3 AlphaEdge PRO HFT Engine — Script de Monitoreo y Estado
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "================================================================="
echo "📊 A3 ALPHAEDGE PRO HFT ENGINE — REPORTE DE ESTADO"
echo "================================================================="

PIDS=$(pgrep -f "server.py" | grep -v "status.sh" | grep -v "grep")
PORT_CHECK=$(curl -s --connect-timeout 1 http://localhost:8005/proxy/status 2>/dev/null)

if [ -n "$PIDS" ] || [ -n "$PORT_CHECK" ]; then
    echo "🟢 ESTADO: EN LÍNEA (ONLINE)"
    SERVICE_STATE=$(systemctl --user is-active a3-motor-trade.service 2>/dev/null || echo "offline")
    if [ "$SERVICE_STATE" = "active" ]; then
        echo "   ⚡ Modo: Systemd 24/7 Daemon (Auto-Restart Activo, Persistente sin terminal)"
    else
        echo "   ⚡ Modo: Proceso Background Estándar"
    fi
    for PID in $PIDS; do
        MEM=$(ps -o rss= -p "$PID" 2>/dev/null | tail -n 1 | awk '{printf "%.1f MB", $1/1024}')
        CPU=$(ps -o %cpu= -p "$PID" 2>/dev/null | tail -n 1 | awk '{print $1" %"}')
        TIME=$(ps -o etime= -p "$PID" 2>/dev/null | tail -n 1 | awk '{print $1}')
        echo "   • PID: $PID | CPU: $CPU | Memoria RAM: $MEM | Tiempo Activo: $TIME"
    done
    echo "-----------------------------------------------------------------"
    echo "🌐 Dashboard Web: http://localhost:8005"
    echo "📋 Verificando respuesta de la API..."
    FEEDS=$(echo "$PORT_CHECK" | grep -o -E '"(is_)?fresh":\s*true' | wc -l)
    echo "   • Feeds de Mercado Bybit L2 activos: $FEEDS"
else
    echo "🔴 ESTADO: DETENIDO (OFFLINE)"
    echo "   Para iniciar: ./start.sh"
fi

echo "-----------------------------------------------------------------"
echo "📜 ÚLTIMAS LÍNEAS DEL LOG (server.log):"
if [ -f server.log ]; then
    tail -n 8 server.log
else
    echo "   (No hay archivo server.log aún)"
fi
echo "================================================================="
