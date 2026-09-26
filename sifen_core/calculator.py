from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
Q8=Decimal('0.00000001')

def D(v, default='0'):
    try: return Decimal(str(default if v in (None,'') else v))
    except (InvalidOperation, ValueError, TypeError): return Decimal(str(default))

def q8(v): return D(v).quantize(Q8, rounding=ROUND_HALF_UP)
def fmt(v): return format(q8(v), 'f')

def calculate_item(quantity, unit_price, iva_rate, proportion=100):
    qty=D(quantity,1); price=D(unit_price); rate=D(iva_rate); prop=D(proportion,100)
    if qty <= 0: raise ValueError('Cantidad SIFEN debe ser mayor a cero.')
    if price < 0: raise ValueError('Precio SIFEN no puede ser negativo.')
    if rate not in (Decimal('0'),Decimal('5'),Decimal('10')): raise ValueError('IVA SIFEN permitido: 0, 5 o 10.')
    total=q8(qty*price)
    if rate == 0:
        return dict(qty=qty,price=price,total=total,rate=rate,prop=prop,affectation=3,base=Decimal('0'),iva=Decimal('0'),base_exempt=total)
    # NT13 E735: [100 * EA008 * E733] / [10000 + (E734 * E733)]
    base=q8((Decimal('100')*total*prop)/(Decimal('10000')+(rate*prop)))
    # E736: base gravada * tasa / 100
    iva=q8(base*rate/Decimal('100'))
    base_exempt=Decimal('0')
    return dict(qty=qty,price=price,total=total,rate=rate,prop=prop,affectation=1,base=base,iva=iva,base_exempt=base_exempt)

def calculate_totals(items):
    z=Decimal('0'); out=dict(sub_exe=z,sub5=z,sub10=z,total=z,iva5=z,iva10=z,base5=z,base10=z)
    for x in items:
        out['total'] += x['total']
        if x['rate']==0: out['sub_exe'] += x['total']
        elif x['rate']==5:
            out['sub5'] += x['total']; out['iva5'] += x['iva']; out['base5'] += x['base']
        elif x['rate']==10:
            out['sub10'] += x['total']; out['iva10'] += x['iva']; out['base10'] += x['base']
    for k in out: out[k]=q8(out[k])
    out['tot_iva']=q8(out['iva5']+out['iva10']); out['tot_base']=q8(out['base5']+out['base10'])
    return out
