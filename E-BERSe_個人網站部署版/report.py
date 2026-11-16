"""Fill designated inputs while leaving Excel's original formula and drawing parts intact."""
from io import BytesIO
import math
from pathlib import Path
import re
from xml.dom import minidom
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

TEMPLATE = Path(__file__).with_name('template.xlsx')
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
INVALID_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def text(value, limit=2000):
    return INVALID_XML.sub('', str(value if value is not None else ''))[:limit]


def numeric(value, positive=True, integer=False):
    try:
        if value is None or value == '' or isinstance(value, bool):
            return None
        result = float(value)
        if not math.isfinite(result) or (positive and result <= 0):
            return None
        if integer:
            return int(result) if result.is_integer() else None
        return result
    except (ValueError, TypeError, OverflowError):
        return None


def read_unit(value, units):
    match = re.fullmatch(r'\s*([\d.,]+)\s*(.+?)\s*', text(value))
    if match and match[2].upper().replace('³', '3').replace(' ', '') in units:
        factor = units[match[2].upper().replace('³', '3').replace(' ', '')]
        base = numeric(match[1].replace(',', ''))
        return base * factor if base is not None else None
    return None


def case_values(case):
    grid = {sheet: {} for sheet in (2, 3, 4, 5, 7, 12, 13)}
    header, survey, main, fan, pump, small, individual = grid.values()
    warnings = []
    header.update(G3=text(case.get('project')), O2=numeric(case.get('floors'), integer=True))
    for row in range(7, 10):
        for col in 'MN':
            survey[col + str(row)] = None
    for row in range(13, 18):
        for col in 'MN':
            survey[col + str(row)] = None
    for row in range(19, 21):
        for col in 'CJKMN':
            survey[col + str(row)] = None
    for row in range(33, 36):
        for col in 'EFGIJK':
            survey[col + str(row)] = None
        survey[f'L{row}'] = None
    for row in range(6, 15):
        for col in ('A', 'B', 'E', 'W', 'Y'):
            fan[col + str(row)] = None
    for row in (4, 5, 6, 12, 13):
        for col in 'ABCJ':
            pump[col + str(row)] = None
    for row in range(13, 17):
        for col in 'EFGK':
            small[col + str(row)] = None
    for row in range(5, 12):
        for col in 'BCDFGHI':
            individual[col + str(row)] = None
    individual['L5'] = None  # Original demonstration count.

    slots = {
        'chiller': iter(range(8, 11)), 'vrf': iter(range(16, 19)),
        'ahu': iter(range(6, 11)), 'fcu': iter(range(11, 15)),
        'fund': iter((4, 5, 6)), 'cond': iter((12, 13)), 'tower': iter((19, 20)),
        'unit': iter(range(5, 12)), 'small': iter(range(13, 16)),
    }
    table5 = str(case.get('routing', {}).get('route', '')).startswith('中央空調總容量小於')
    devices = case.get('devices', [])
    if not isinstance(devices, list) or len(devices) > 200 or not all(isinstance(d, dict) for d in devices):
        raise ValueError('案件設備資料格式錯誤，或超過 200 筆。')
    for index, device in enumerate(devices, 1):
        name, kind = text(device.get('name'), 250), device.get('kind')
        category = device.get('assessment', {})
        kw = numeric(category.get('kw'))
        count = numeric(device.get('count'), integer=True)
        power = numeric(device.get('power'))
        visual = device.get('visual')
        label = name or f'設備 {index}'
        if not name or count is None or power is None:
            warnings.append(f'{label}：請核對設備編號、台數及單機輸入功率。')
        if kind in ('unit', 'water', 'air', 'vrf') and kw is None:
            warnings.append(f'{label}：額定冷房能力未確認，保留於照片辨識紀錄。')
            continue
        if category.get('classification') == '個別型':
            target = 'unit'
        elif kind in ('water', 'air'):
            target = 'chiller'
        else:
            target = kind
        if target not in slots or target == 'unit' and category.get('classification') != '個別型':
            warnings.append(f'{label}：設備類別或模板對應需覆核，請查看照片辨識紀錄。')
            continue
        row = next(slots[target], None)
        if row is None:
            warnings.append(f'{label}：超出範本可自動填寫的列數，請查看照片辨識紀錄。')
            continue
        if target == 'chiller':
            for col, value in zip('HJLM', (name, round(kw / 3.516, 8), power, count)):
                main[f'{col}{row}'] = value
            inspection = row + 25
            if visual in ('poor', 'fair', 'good'):
                survey[f'{dict(poor="E", fair="F", good="G")[visual]}{inspection}'] = 'V'
            condensation = category.get('condensation')
            if kind == 'water' and condensation in (0.8, 0.9, 1):
                survey[f'{ {0.8:"I", 0.9:"J", 1:"K"}[condensation]}{inspection}'] = 'V'
                survey[f'L{inspection}'] = condensation
            elif kind == 'water' and device.get('operation') == 'offline':
                survey[f'K{inspection}'] = 'V'
            elif kind == 'air':
                survey[f'L{inspection}'] = 1
            if table5:
                small[f'B{row + 5}'] = name
                if visual in ('poor', 'fair', 'good'):
                    small[f'{dict(poor="E", fair="F", good="G")[visual]}{row + 5}'] = 'V'
        elif target == 'vrf':
            for col, value in zip(('G','I','J','K','N','U'), (name, round(kw / 3.516, 8), kw, count,
                read_unit(device.get('efficiency'), {'CSPF':1}) or (
                    numeric(text(device.get('efficiency'))[4:].lstrip(' :=：')) if text(device.get('efficiency')).upper().startswith('CSPF') else None), power)):
                main[f'{col}{row}'] = value
            warnings.append(f'{label}：VRF 的散熱係數、CSPF 及冷媒管路損失須覆核。')
        elif target in ('ahu','fcu'):
            flow = read_unit(device.get('flow'), {'CMH':1, 'M3/H':1, 'CFM':1.699, 'L/S':3.6, 'LPS':3.6, 'CMM':60})
            if flow is None:
                warnings.append(f'{label}：請補風量及明確單位，再核對風機效率輸入。')
            for col, value in zip(('A','B','E','W'), (name, count, flow, power)):
                fan[f'{col}{row}'] = value
        elif target in ('fund','cond'):
            for col, value in zip('ABCJ', (name, round(kw / 3.516, 8) if kw else None, count, power)):
                pump[f'{col}{row}'] = value
            if row != 4:
                survey[f'C{row + 9 if row < 10 else row + 4}'] = name
            if kw is None:
                warnings.append(f'{label}：請補所服務的單機冷房能力，以計算水泵耗電基準。')
        elif target == 'tower':
            for col, value in zip('CJK',(name,power,count)):
                survey[f'{col}{row}'] = value
        else:
            year = re.fullmatch(r'(?:民國\s*)?(\d{2,4})(?:\s*年)?', text(device.get('year')).strip())
            year_value = int(year[1]) if year else None
            if year_value and year_value > 1911:
                year_value -= 1911
            grade = re.fullmatch(r'(?:第\s*)?([1-5])(?:\s*級)?', text(device.get('grade')).strip())
            for col,value in zip('BCDFG', (name, power, count, year_value, int(grade[1]) if grade else None)):
                individual[f'{col}{row}'] = value
            if visual in ('poor','fair','good'):
                individual[f'{"I" if visual == "good" else "H"}{row}'] = 'V'
    return grid, warnings, devices


# Only these cells contain case-specific sample expressions on the supplied template.
EXAMPLE_FORMULAS = {(3,'J19'),(3,'J20'),(7,'J4'),(7,'J5')} | {
    (5,f'{col}{row}') for row in range(6,15) for col in ('E','W')
}


def excel_col(value):
    result = 0
    for char in re.match(r'[A-Z]+', value)[0]:
        result = result * 26 + ord(char) - ord('A') + 1
    return result


def patch_sheet(raw, sheet, values):
    doc = minidom.parseString(raw)
    data = doc.getElementsByTagName('sheetData')[0]
    rows = {int(row.getAttribute('r')): row for row in data.getElementsByTagName('row')}
    cells = {cell.getAttribute('r'): cell for cell in data.getElementsByTagName('c')}
    for address, value in values.items():
        cell = cells.get(address)
        if cell is not None and cell.getElementsByTagName('f') and (sheet,address) not in EXAMPLE_FORMULAS:
            continue
        if cell is None:
            if value is None or value == '':
                continue
            row_number = int(re.search(r'\d+$', address)[0])
            row = rows.get(row_number)
            if row is None:
                row = doc.createElement('row')
                row.setAttribute('r', str(row_number))
                data.insertBefore(row, next((node for key,node in sorted(rows.items()) if key>row_number), None))
                rows[row_number] = row
            cell = doc.createElement('c')
            cell.setAttribute('r', address)
            row.insertBefore(cell, next((node for node in row.getElementsByTagName('c')
                                         if excel_col(node.getAttribute('r')) > excel_col(address)), None))
        for child in list(cell.childNodes):
            if child.nodeName in ('f','v','is'):
                cell.removeChild(child)
        if cell.hasAttribute('t'):
            cell.removeAttribute('t')
        if value is None or value == '':
            continue
        if isinstance(value,(int,float)):
            node = doc.createElement('v')
            node.appendChild(doc.createTextNode(str(value)))
            cell.appendChild(node)
        else:
            cell.setAttribute('t','inlineStr')
            inline = doc.createElement('is')
            node = doc.createElement('t')
            node.setAttribute('xml:space','preserve')
            node.appendChild(doc.createTextNode(text(value)))
            inline.appendChild(node)
            cell.appendChild(inline)
    return doc.toxml(encoding='utf-8')


def evidence_sheet(case, warnings, devices):
    rows = [
        ('照片辨識紀錄及覆核事項',),
        ('案件',case.get('project',''), '現勘日期',case.get('date','')),
        ('評估路徑',case.get('routing',{}).get('route','')),
        ('報告狀態','現勘填報稿。請覆核原範本的 #REF!、表5固定倍率、表6統計範圍與未填寫的案例參數。'),
        ('計算及簽證','Excel 開啟後重新計算，評估結果與簽證須由專家確認。'),
        ('現勘補充',case.get('observations','')),
        ('辨識備註',case.get('notes','')),
    ]
    rows += [('覆核事項',warning) for warning in warnings]
    rows.append(('設備類別','設備編號／型號','系統','台數','單機額定容量','單位','輸入功率 kW',
                 '銘牌效率','風量／水量','出廠年','能效等級','變頻證明','冷媒','照片編號','散熱目視',
                 '冷凝溫度°C','出水溫度°C','運轉狀態','冷凝趨近°C','冷凝修正','資料來源或現況說明'))
    names = {'water':'水冷式冰水機','air':'氣冷式冰水機','vrf':'多聯變頻空調','unit':'其他空調主機',
             'fund':'冰水泵','cond':'冷卻水泵','tower':'冷卻水塔','ahu':'空調箱','fcu':'風機盤管'}
    for item in devices:
        values = tuple(item.get(k,'') for k in ('name','group','count','capacity','unit','power','efficiency',
                         'flow','year','grade','inverter','refrigerant','sources'))
        check = item.get('assessment',{})
        visual = {'poor':'極差','fair':'不佳','good':'合格'}.get(item.get('visual'),'')
        operation = {'running':'運轉中','offline':'無法開機'}.get(item.get('operation'),'')
        rows.append((names.get(item.get('kind'),'待分類'), *values, visual, item.get('condensing'),
                     item.get('outlet'), operation, check.get('approach'), check.get('condensation'), item.get('evidence')))
    rows += [('照片編號','檔名')]
    rows += [(item.get('id',''),item.get('name','')) for item in case.get('sources',[])[:500]]
    payload = []
    for r, record in enumerate(rows,1):
        cells = ''.join(f'<c r="{chr(65+c)}{r}" t="inlineStr"><is><t xml:space="preserve">{escape(text(value))}</t></is></c>'
                        for c,value in enumerate(record) if value is not None and value != '')
        payload.append(f'<row r="{r}">{cells}</row>')
    return (f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}">'
            '<cols><col min="1" max="1" width="24" customWidth="1"/>'
            '<col min="2" max="2" width="44" customWidth="1"/>'
            '<col min="3" max="20" width="17" customWidth="1"/>'
            '<col min="21" max="21" width="58" customWidth="1"/></cols>'
            '<sheetData>' + ''.join(payload) + '</sheetData></worksheet>').encode()


def generate(case):
    grid, warnings, devices = case_values(case)
    if not case.get('complete'):
        warnings.insert(0,'全棟設備清冊及主機台數尚未確認。')
    output = BytesIO()
    with ZipFile(TEMPLATE) as source, ZipFile(output,'w',ZIP_DEFLATED) as target:
        extras = {
            'xl/workbook.xml': (b'</sheets>', '<sheet name="照片辨識紀錄" sheetId="99" r:id="rIdEvidence"/></sheets>'.encode()),
            'xl/_rels/workbook.xml.rels': (b'</Relationships>', f'<Relationship Id="rIdEvidence" Type="{REL}/worksheet" Target="worksheets/sheet14.xml"/></Relationships>'.encode()),
            '[Content_Types].xml': (b'</Types>', b'<Override PartName="/xl/worksheets/sheet14.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'),
        }
        for name in source.namelist():
            if name == 'xl/calcChain.xml':
                continue
            raw = source.read(name)
            match = re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml',name)
            if match and int(match[1]) in grid:
                raw = patch_sheet(raw, int(match[1]), grid[int(match[1])])
            elif name in extras:
                before, after = extras[name]
                if before not in raw:
                    raise ValueError('Excel 範本結構不符。')
                raw = raw.replace(before, after, 1)
                if name == 'xl/_rels/workbook.xml.rels':
                    raw = re.sub(rb'<Relationship\b[^>]*Target="calcChain.xml"[^>]*/>', b'', raw)
                if name == '[Content_Types].xml':
                    raw = re.sub(rb'<Override\b[^>]*PartName="/xl/calcChain.xml"[^>]*/>', b'', raw)
                if name == 'xl/workbook.xml':
                    raw = re.sub(rb'<calcPr\b[^>]*/>', b'<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>', raw, count=1)
            target.writestr(name,raw)
        target.writestr('xl/worksheets/sheet14.xml', evidence_sheet(case,warnings,devices))
    return output.getvalue()
