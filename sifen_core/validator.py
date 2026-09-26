from decimal import Decimal
from .calculator import D, q8

def validate_fiscal_consistency(items, totals, payment=None):
    errors=[]
    for n,x in enumerate(items,1):
        if q8(x['qty']*x['price']) != q8(x['total']): errors.append(f'Item {n}: cantidad × precio no coincide con total.')
        if x['rate'] in (Decimal('5'),Decimal('10')):
            exp=q8((Decimal('100')*x['total']*x['prop'])/(Decimal('10000')+(x['rate']*x['prop'])))
            if exp != q8(x['base']): errors.append(f'Item {n}: dBasGravIVA no cumple NT13.')
            if q8(x['base']*x['rate']/Decimal('100')) != q8(x['iva']): errors.append(f'Item {n}: dLiqIVAItem no coincide con base × tasa.')
    if q8(totals['iva5']+totals['iva10']) != q8(totals['tot_iva']): errors.append('dTotIVA no coincide con IVA 5 + IVA 10.')
    if q8(totals['base5']+totals['base10']) != q8(totals['tot_base']): errors.append('dTBasGraIVA no coincide con bases gravadas.')
    if payment is not None and q8(D(payment)) != q8(totals['total']): errors.append('Monto de pago no coincide con total general.')
    return errors
