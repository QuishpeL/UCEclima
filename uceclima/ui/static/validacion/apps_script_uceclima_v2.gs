/**
 * UCEclima · receptor de la encuesta «¿Se inunda?» (versión 2, 31-oct-2026).
 * Pégalo en una hoja de Google NUEVA, solo para la validación (Extensiones › Apps Script),
 * e impleméntalo como «Aplicación web» (ejecutar como: yo; acceso: cualquier persona).
 * No lo pegues en un Apps Script que ya uses para otras encuestas: lo reemplazarías.
 *
 * Qué hace:
 *  - POST ?form=<pestaña>                 guarda cada respuesta como una fila (crea la pestaña y las columnas que falten).
 *  - POST ?accion=publicar&clave=…        UCEclima guarda aquí una encuesta (mapas del modelo y textos) para abrirla desde el sitio.
 *  - GET  ?accion=encuesta&z=<zona>       la página del sitio lee esa encuesta (es pública, como la propia encuesta).
 *  - GET  ?accion=respuestas&form=…&clave=…   UCEclima lee las respuestas para importarlas (solo con la clave).
 * La CLAVE la generó tu UCEclima y solo está aquí y en tu computadora; no va dentro de las encuestas.
 */
var CLAVE = '{{CLAVE}}';
var TROZO = 45000;  // una celda admite 50 000 caracteres

function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function slug_(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 60); }
function hoja_(s) { return String(s || '').replace(/[^A-Za-z0-9_]/g, '').slice(0, 60); }  // nombre de pestaña: se respeta tal cual (p. ej. milagro_marcas)

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var p = e.parameter || {};
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    if (p.accion === 'publicar') {
      if (!CLAVE || p.clave !== CLAVE) return json_({ok: false, error: 'clave'});
      var d = JSON.parse(e.postData.contents), z = slug_(d.slug);
      if (!z) return json_({ok: false, error: 'zona'});
      var txt = JSON.stringify(d), partes = [];
      for (var i = 0; i < txt.length; i += TROZO) partes.push(txt.substring(i, i + TROZO));
      var sh = ss.getSheetByName('_encuestas') || ss.insertSheet('_encuestas');
      var filas = sh.getLastRow() ? sh.getRange(1, 1, sh.getLastRow(), 1).getValues() : [];
      var r = 0;
      for (var k = 0; k < filas.length; k++) if (filas[k][0] === z) { r = k + 1; break; }
      if (!r) r = sh.getLastRow() + 1;
      if (sh.getLastColumn() > 0) sh.getRange(r, 1, 1, sh.getLastColumn()).clearContent();
      var faltan = 3 + partes.length - sh.getMaxColumns();
      if (faltan > 0) sh.insertColumnsAfter(sh.getMaxColumns(), faltan);   // una hoja nueva trae solo 26 columnas
      sh.getRange(r, 1, 1, 3 + partes.length).setValues([[z, new Date().toISOString(), partes.length].concat(partes)]);
      return json_({ok: true, z: z, trozos: partes.length});
    }
    var form = hoja_(p.form) || 'general';
    var sheet = ss.getSheetByName(form) || ss.insertSheet(form);
    var data = JSON.parse(e.postData.contents);
    data['_recibido_servidor'] = new Date().toISOString();
    var header = sheet.getLastRow() > 0 ? sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0] : [];
    var keys = Object.keys(data), nuevas = keys.filter(function (k) { return header.indexOf(k) === -1; });
    if (header.length === 0) { header = keys; sheet.appendRow(header); }
    else if (nuevas.length > 0) { header = header.concat(nuevas); sheet.getRange(1, 1, 1, header.length).setValues([header]); }
    sheet.appendRow(header.map(function (h) { var v = data[h]; if (Array.isArray(v)) v = v.join('; '); return (v === undefined || v === null) ? '' : v; }));
    return json_({ok: true});
  } catch (err) {
    return json_({ok: false, error: String(err)});
  } finally {
    lock.releaseLock();
  }
}

function doGet(e) {
  var p = (e && e.parameter) || {};
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (p.accion === 'encuesta') {
    var sh = ss.getSheetByName('_encuestas'), z = slug_(p.z);
    if (!sh || !z || !sh.getLastRow()) return json_({ok: false, error: 'no existe'});
    var filas = sh.getRange(1, 1, sh.getLastRow(), 3).getValues();
    for (var k = 0; k < filas.length; k++) if (filas[k][0] === z) {
      var n = Number(filas[k][2]) || 0;
      var txt = sh.getRange(k + 1, 4, 1, n).getValues()[0].join('');
      return json_({ok: true, datos: JSON.parse(txt), publicada: filas[k][1]});
    }
    return json_({ok: false, error: 'no existe'});
  }
  if (p.accion === 'respuestas') {
    if (!CLAVE || p.clave !== CLAVE) return json_({ok: false, error: 'clave'});
    var hoja = ss.getSheetByName(hoja_(p.form));
    if (!hoja || hoja.getLastRow() < 2) return json_({ok: true, filas: []});
    var v = hoja.getRange(1, 1, hoja.getLastRow(), hoja.getLastColumn()).getValues(), cab = v[0], out = [];
    for (var i = 1; i < v.length; i++) { var o = {}; for (var j = 0; j < cab.length; j++) o[cab[j]] = v[i][j]; out.push(o); }
    return json_({ok: true, filas: out});
  }
  return json_({ok: true, msg: 'Servidor activo', version: 2});
}
