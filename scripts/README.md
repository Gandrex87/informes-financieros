# Castellón mes catastrófico (no llega ni al BE)
python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --arras 5000

# Castellón mes mediocre (supera BE, no llega a M10)
python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --arras 20000

# Castellón mes excelente (supera todos los umbrales)
python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --arras 50000

# Castellón superávit completo (arras + ingresos altos)
python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --arras 50000 --ingresos 45000

# Solo simular el slide 8 BE proyectado (cuando junio esté cargado)
python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --objetivo-proy 80000

# Valencia con el patrón antiguo (forma nueva)
python scripts/simular_break_even.py --sede Valencia --anyo 2026 --mes 4 --ingresos 320000
