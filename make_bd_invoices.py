"""Synthetic Bangladeshi invoices (Mushak-6.3 layout, a supermarket and a restaurant receipt) with their answers.

python make_bd_invoices.py   -> data/synthetic_bd/NN.html + truth.json; render the HTML to PNG in a browser.
Fictional companies and BINs. The same numbers fill the page and the answer key, so they cannot disagree.
Mushak-6.3: prices exclude tax, supplementary duty (SD) first, VAT on price + SD (VAT & SD Rules 2016, Rule 40).
The answer key maps SD + VAT to `tax`, since the schema has one tax field.
"""
import json
from decimal import ROUND_HALF_UP, Decimal as D
from pathlib import Path

OUT = Path(__file__).parent / 'data' / 'synthetic_bd'
BN_DIGITS = str.maketrans('0123456789', '০১২৩৪৫৬৭৮৯')


def r2(x):
    return D(x).quantize(D('0.01'), ROUND_HALF_UP)


def taka(x, lakh=False, bangla=False):
    """1234.5 -> '1,234.50'; lakh=True groups the Bangladeshi way (1,23,456.00)."""
    whole, frac = f'{r2(x):.2f}'.split('.')
    if lakh and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ','.join([head] + groups + [tail])
    else:
        whole = f'{int(whole):,}'
    s = f'{whole}.{frac}'
    return s.translate(BN_DIGITS) if bangla else s


CSS = """body{margin:0;background:#fff;font-family:'Segoe UI','Nirmala UI',Arial,sans-serif;color:#111}
#doc{width:980px;padding:36px 40px;box-sizing:border-box;font-size:14px}
.c{text-align:center}.r{text-align:right}h1{font-size:18px;margin:4px 0}h2{font-size:15px;margin:2px 0 14px}
table{border-collapse:collapse;width:100%;margin-top:14px}td,th{border:1px solid #333;padding:5px 6px;vertical-align:top}
th{font-size:12px;background:#f3f3f3}.meta td{border:none;padding:2px 4px}.sig{margin-top:40px;font-size:13px}
#doc.pos{width:420px;font-family:'Courier New',monospace;font-size:14px;padding:28px}.pos td{border:none;padding:1px 0}
.pos table{margin-top:6px}.dash{border-top:1px dashed #333;margin:8px 0}"""


def page(body, cls=''):
    return f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><div id="doc" class="{cls}">{body}</div>'


def mushak(t, bangla=False, lakh=False):
    """Mushak-6.3 page. t: seller, bin, address, buyer, buyer_bin, number, date_text, lines[(desc, unit, qty, price, sd%, vat%)]."""
    n = (lambda s: str(s).translate(BN_DIGITS)) if bangla else str
    money = lambda x: taka(x, lakh, bangla)
    rows, sub, sd_sum, vat_sum = [], D(0), D(0), D(0)
    items = []
    for i, (desc, unit, qty, price, sd_rate, vat_rate) in enumerate(t['lines'], 1):
        value = r2(D(qty) * D(price))
        sd = r2(value * D(sd_rate) / 100)
        vat = r2((value + sd) * D(vat_rate) / 100)
        sub, sd_sum, vat_sum = sub + value, sd_sum + sd, vat_sum + vat
        items.append({'description': desc, 'quantity': str(qty), 'unit_price': str(r2(price)), 'amount': str(value)})
        rows.append(f'<tr><td class="c">{n(i)}</td><td>{desc}</td><td class="c">{unit}</td><td class="r">{n(qty)}</td>'
                    f'<td class="r">{money(price)}</td><td class="r">{money(value)}</td><td class="r">{money(sd)}</td>'
                    f'<td class="c">{n(vat_rate)}%</td><td class="r">{money(vat)}</td><td class="r">{money(value + sd + vat)}</td></tr>')
    total = sub + sd_sum + vat_sum
    L = t['labels']
    body = f"""<div class="c"><div>{L['gov']}</div><div>{L['nbr']}</div><h1>{L['title']}</h1>
<div style="font-size:12px">{L['rule']}</div><h2>{L['form']}</h2></div>
<table class="meta"><tr><td>{L['seller']}: <b>{t['seller']}</b></td><td>{L['number']}: <b>{t['number']}</b></td></tr>
<tr><td>{L['bin']}: {n(t['bin'])}</td><td>{L['date']}: {n(t['date_text'])}</td></tr>
<tr><td>{L['address']}: {t['address']}</td><td>{L['time']}: {n(t['time'])}</td></tr>
<tr><td>{L['buyer']}: {t['buyer']}</td><td>{L['buyer_bin']}: {n(t['buyer_bin'])}</td></tr></table>
<table><tr>{''.join(f'<th>{h}</th>' for h in L['cols'])}</tr>{''.join(rows)}
<tr><td colspan="5" class="r"><b>{L['total']}</b></td><td class="r"><b>{money(sub)}</b></td><td class="r"><b>{money(sd_sum)}</b></td>
<td></td><td class="r"><b>{money(vat_sum)}</b></td><td class="r"><b>{money(total)}</b></td></tr></table>
<div class="sig">{L['officer']}<br>{L['sign']}</div>"""
    truth = {'doc_type': 'invoice', 'vendor': t['seller'], 'doc_number': t['number'], 'issue_date': t['iso'],
             'currency': 'BDT', 'subtotal': str(sub), 'tax': str(sd_sum + vat_sum), 'total': str(total), 'items': items}
    return page(body), truth


EN = dict(gov='Government of the People\'s Republic of Bangladesh', nbr='National Board of Revenue', title='Tax Invoice',
          rule='[See clauses (c) and (f) of sub-rule (1) of rule 40]', form='Mushak-6.3', seller='Name of registered person',
          bin='BIN', address='Invoice issuing address', buyer='Name of purchaser', buyer_bin='BIN of purchaser',
          number='Invoice No', date='Date of issue', time='Time of issue', total='Total',
          cols=['SL', 'Description of goods/services', 'Unit', 'Quantity', 'Unit price (Tk)', 'Total price (Tk)',
                'Supplementary duty (Tk)', 'VAT rate', 'VAT amount (Tk)', 'Total incl. all duties and taxes (Tk)'],
          officer='Officer-in-charge: Md. Karim Hossain, Accounts Manager', sign='Signature & seal')
BN = dict(gov='গণপ্রজাতন্ত্রী বাংলাদেশ সরকার', nbr='জাতীয় রাজস্ব বোর্ড', title='কর চালানপত্র',
          rule='[বিধি ৪০ এর উপ-বিধি (১) এর দফা (গ) ও দফা (চ) দ্রষ্টব্য]', form='মূসক-৬.৩', seller='নিবন্ধিত ব্যক্তির নাম',
          bin='বিআইএন', address='চালানপত্র ইস্যুর ঠিকানা', buyer='ক্রেতার নাম', buyer_bin='ক্রেতার বিআইএন',
          number='চালানপত্র নম্বর', date='ইস্যুর তারিখ', time='ইস্যুর সময়', total='সর্বমোট',
          cols=['ক্রমিক', 'পণ্য বা সেবার বর্ণনা', 'একক', 'পরিমাণ', 'একক মূল্য (টাকা)', 'মোট মূল্য (টাকা)',
                'সম্পূরক শুল্ক (টাকা)', 'মূসক হার', 'মূসক (টাকা)', 'সকল প্রকার শুল্ক ও করসহ মূল্য (টাকা)'],
          officer='দায়িত্বপ্রাপ্ত কর্মকর্তা: মোঃ রফিকুল ইসলাম', sign='স্বাক্ষর ও সিল')


def pos_receipt():
    """Supermarket receipt: prices include 15% VAT, printed as 'VAT (included)' with subtotal = total."""
    lines = [('Rice Miniket 5kg', 1, '415.00'), ('Soybean Oil 2L', 1, '380.00'), ('Lentil (Masur) 1kg', 2, '130.00'),
             ('Tea 400g', 1, '95.00')]
    items = [{'description': d, 'quantity': str(q), 'unit_price': p, 'amount': str(r2(D(p) * q))} for d, q, p in lines]
    total = sum(D(i['amount']) for i in items)
    vat = r2(total * 15 / 115)
    rows = ''.join(f'<tr><td>{d}<br>&nbsp;&nbsp;{q} x {p}</td><td class="r">{taka(D(p) * q)}</td></tr>' for d, q, p in lines)
    body = f"""<div class="c"><b>GREEN BASKET SUPERSHOP</b><br>Branch: Dhanmondi 27<br>BIN: 004567891-0102<br>Mushak-6.3 (EFD)</div>
<div class="dash"></div>Invoice: GB-DH-88213<br>Date: 18/09/2026 19:42<div class="dash"></div><table>{rows}</table>
<div class="dash"></div><table><tr><td>Subtotal</td><td class="r">{taka(total)}</td></tr>
<tr><td>VAT 15% (included)</td><td class="r">{taka(vat)}</td></tr><tr><td><b>TOTAL</b></td><td class="r"><b>{taka(total)}</b></td></tr>
<tr><td>Cash</td><td class="r">{taka(2000)}</td></tr><tr><td>Change</td><td class="r">{taka(2000 - total)}</td></tr></table>
<div class="dash"></div><div class="c">Prices include VAT. Thank you!</div>"""
    truth = {'doc_type': 'receipt', 'vendor': 'Green Basket Supershop', 'doc_number': 'GB-DH-88213',
             'issue_date': '2026-09-18', 'currency': 'BDT', 'subtotal': str(total), 'tax': str(vat), 'total': str(total),
             'items': items}
    return page(body, 'pos'), truth


def restaurant():
    """Restaurant bill: service charge 10% and VAT 5% on (food + service), both added on top."""
    lines = [('Kacchi Biryani (Full)', 2, '420.00'), ('Chicken Roast', 2, '260.00'), ('Borhani', 3, '80.00'),
             ('Firni', 2, '90.00')]
    items = [{'description': d, 'quantity': str(q), 'unit_price': p, 'amount': str(r2(D(p) * q))} for d, q, p in lines]
    sub = sum(D(i['amount']) for i in items)
    service = r2(sub * D('0.10'))
    vat = r2((sub + service) * D('0.05'))
    total = sub + service + vat
    rows = ''.join(f'<tr><td>{d}</td><td class="r">{q}</td><td class="r">{taka(D(p) * q)}</td></tr>' for d, q, p in lines)
    body = f"""<div class="c"><b>SHAHI DASTARKHAN RESTAURANT</b><br>House 12, Road 7, Mirpur 10, Dhaka<br>BIN: 003345678-0201</div>
<div class="dash"></div>Bill No: SD-7719 &nbsp; Table: 6<br>Date: 26/09/2026 21:05<div class="dash"></div>
<table>{rows}</table><div class="dash"></div><table><tr><td>Subtotal</td><td class="r">{taka(sub)}</td></tr>
<tr><td>Service Charge 10%</td><td class="r">{taka(service)}</td></tr><tr><td>VAT 5%</td><td class="r">{taka(vat)}</td></tr>
<tr><td><b>Grand Total</b></td><td class="r"><b>{taka(total)}</b></td></tr></table><div class="dash"></div>
<div class="c">Thank you, come again</div>"""
    truth = {'doc_type': 'receipt', 'vendor': 'Shahi Dastarkhan Restaurant', 'doc_number': 'SD-7719',
             'issue_date': '2026-09-26', 'currency': 'BDT', 'subtotal': str(sub), 'tax': str(vat),
             'service_charge': str(service), 'total': str(total), 'items': items}
    return page(body, 'pos'), truth


DOCS = {
    '01_mushak_vat15': lambda: mushak(dict(
        labels=EN, seller='Rahman Office Supplies Ltd.', bin='000123456-0101', address='45 Motijheel C/A, Dhaka-1000',
        buyer='Northstar Garments Ltd.', buyer_bin='000987654-0203', number='ROS/2026/0417', date_text='25/09/2026',
        iso='2026-09-25', time='11:20',
        lines=[('A4 Paper 80gsm (ream)', 'Ream', 20, '520.00', 0, 15), ('Stapler HD-45', 'Pcs', 5, '350.00', 0, 15),
               ('Toner Cartridge 85A', 'Pcs', 2, '4800.00', 0, 15)])),
    '02_mushak_sd_vat_lakh': lambda: mushak(dict(
        labels=EN, seller='Meghna Beverage Distributors', bin='000456789-0102', address='Plot 9, Tejgaon I/A, Dhaka-1208',
        buyer='City Mart Ltd.', buyer_bin='000321987-0101', number='MBD-2026-1193', date_text='05/09/2026',
        iso='2026-09-05', time='16:05',
        lines=[('Soft Drink 250ml (carton of 24)', 'Carton', 120, '480.00', 25, 15),
               ('Energy Drink 250ml (carton of 24)', 'Carton', 40, '1150.00', 25, 15)]), lakh=True),
    '03_supershop_vat_included': pos_receipt,
    '04_mushak_bangla': lambda: mushak(dict(
        labels=BN, seller='সোনালী কৃষি সরবরাহ', bin='000654321-0301', address='কলেজ রোড, বগুড়া',
        buyer='মেসার্স হক ট্রেডার্স', buyer_bin='000112233-0101', number='SKS-0921', date_text='22/09/2026',
        iso='2026-09-22', time='10:15',
        lines=[('জৈব সার (৫০ কেজি বস্তা)', 'বস্তা', 10, '1250.00', 0, 15), ('ধানের বীজ (১০ কেজি)', 'প্যাকেট', 8, '900.00', 0, 15)]),
        bangla=True),
    '05_restaurant_service_vat': restaurant,
}

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    truth = {}
    for name, make in DOCS.items():
        html, truth[name] = make()
        (OUT / f'{name}.html').write_text(html, encoding='utf8')
    (OUT / 'truth.json').write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding='utf8')
    # self-check: every answer key adds up (items = subtotal; subtotal + tax + service = total, except VAT included)
    for name, t in truth.items():
        assert sum(D(i['amount']) for i in t['items']) == D(t['subtotal']), name
        added = D(t['subtotal']) + D(t['tax']) + D(t.get('service_charge', 0))
        assert added == D(t['total']) or name.startswith('03'), (name, added, t['total'])
    assert taka(123456, lakh=True) == '1,23,456.00' and taka(1234.5, bangla=True) == '১,২৩৪.৫০'
    for name, t in truth.items():
        print(name, 'subtotal', t['subtotal'], 'tax', t['tax'], 'total', t['total'])
