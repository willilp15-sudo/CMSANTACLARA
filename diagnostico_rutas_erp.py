"""Diagnóstico no destructivo: ejecutar con `python diagnostico_rutas_erp.py`.
No ejecuta operaciones POST ni modifica datos. Requiere las dependencias de requirements.txt.
"""
import importlib, traceback, json, datetime
from pathlib import Path

TARGETS = ['/operacion-clinica', '/mapa-sistema', '/administracion-integral']

def main():
    result = {'fecha': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'rutas': [], 'importacion': None}
    try:
        module = importlib.import_module('app')
        flask_app = module.app
        result['importacion'] = 'OK'
    except Exception:
        result['importacion'] = traceback.format_exc()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    for path in TARGETS:
        item = {'ruta': path}
        try:
            with flask_app.test_request_context(path):
                rule = flask_app.url_map.bind('localhost').match(path)
                item['endpoint'] = rule[0]
                view = flask_app.view_functions[rule[0]]
                # Solo se prueban vistas GET de navegación; sin autenticación ni escritura.
                with flask_app.app_context():
                    response = view(**rule[1])
                    item['renderizado'] = 'OK'
                    item['tipo_respuesta'] = type(response).__name__
        except Exception:
            item['renderizado'] = 'ERROR'
            item['detalle'] = traceback.format_exc()
        result['rutas'].append(item)
    output = Path('diagnostico_rutas_resultado.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(x.get('renderizado') == 'ERROR' for x in result['rutas']) else 0

if __name__ == '__main__':
    raise SystemExit(main())
