import sqlite3

conn = sqlite3.connect('data/trades.db')
cursor = conn.cursor()

print("=== RESUMEN GENERAL DE LA PRUEBA EN VIVO (8 HORAS) ===")
cursor.execute('''
SELECT 
    COUNT(*),
    SUM(pnl),
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END),
    SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END),
    SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END),
    AVG(pnl)
FROM trades
''')
tot, pnl, wins, losses, gwins, glosses, avg_pnl = cursor.fetchone()
wins = wins or 0
losses = losses or 0
tot = tot or 0
pnl = pnl or 0.0
gwins = gwins or 0.0
glosses = glosses or 0.0
avg_pnl = avg_pnl or 0.0

win_rate = (wins / tot * 100) if tot > 0 else 0
pf = (gwins / abs(glosses)) if glosses and glosses != 0 else (gwins if gwins else 0)

print(f"Total de Operaciones: {tot}")
print(f"Tasa de Acierto (Win Rate): {win_rate:.2f}% ({wins} Ganadas / {losses} Perdidas)")
print(f"PnL Neto Total: ${pnl:.4f}")
print(f"Ganancia Bruta: +${gwins:.4f}")
print(f"Pérdida Bruta: -${abs(glosses):.4f}")
print(f"Profit Factor: {pf:.2f}")
print(f"PnL Promedio por Trade: ${avg_pnl:.4f}")

print("\n=== DESGLOSE POR ACTIVO ===")
cursor.execute('''
SELECT symbol, COUNT(*), SUM(pnl), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END)
FROM trades GROUP BY symbol
''')
for r in cursor.fetchall():
    sym_tot, sym_pnl, sym_w, sym_l = r[1], r[2] or 0.0, r[3] or 0, r[4] or 0
    wr = (sym_w / sym_tot * 100) if sym_tot > 0 else 0
    print(f"Par {r[0]}: {sym_tot} trades | PnL: ${sym_pnl:.4f} | Win Rate: {wr:.1f}% ({sym_w}W / {sym_l}L)")

print("\n=== HISTORIAL COMPLETO DE OPERACIONES REGISTRADAS ===")
cursor.execute('''
SELECT id, symbol, strategy, side, entry_price, exit_price, quantity, pnl, exit_reason, created_at 
FROM trades ORDER BY id ASC
''')
for t in cursor.fetchall():
    print(f"ID #{t[0]} | {t[9]} | {t[1]} ({t[2]}) | {t[3]} @ ${t[4]:.2f} -> ${t[5]:.2f} | Qty: {t[6]:.4f} | PnL: ${t[7]:.4f} ({t[8]})")

conn.close()
