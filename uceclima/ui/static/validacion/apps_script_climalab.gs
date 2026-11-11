function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var form = (e.parameter.form || 'general');
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(form);
    if (!sheet) {
      sheet = ss.insertSheet(form);
    }
    var data = JSON.parse(e.postData.contents);
    data['_recibido_servidor'] = new Date().toISOString();

    var lastRow = sheet.getLastRow();
    var header = [];
    if (lastRow > 0) {
      header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    }
    var keys = Object.keys(data);
    var newKeys = keys.filter(function (k) { return header.indexOf(k) === -1; });

    if (header.length === 0) {
      header = keys;
      sheet.appendRow(header);
    } else if (newKeys.length > 0) {
      header = header.concat(newKeys);
      sheet.getRange(1, 1, 1, header.length).setValues([header]);
    }

    var row = header.map(function (h) {
      var v = data[h];
      if (Array.isArray(v)) v = v.join('; ');
      return (v === undefined || v === null) ? '' : v;
    });
    sheet.appendRow(row);

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({ ok: true, msg: 'Servidor activo' }))
    .setMimeType(ContentService.MimeType.JSON);
}
