import datetime

def next_month_date(date_obj):
    """Devuelve la fecha correspondiente al siguiente mes, con día=1."""
    year = date_obj.year
    month = date_obj.month + 1
    if month > 12:
        month = 1
        year += 1
    # Si tus lecturas siempre se guardan con day=1, puedes forzarlo a 1:
    return datetime.date(year, month, 1)
