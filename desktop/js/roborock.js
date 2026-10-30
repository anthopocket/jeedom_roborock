/* Plugin Roborock – desktop/js/roborock.js */
'use strict';

$(function () {

    var AJAX = 'plugins/roborock/core/ajax/roborock.ajax.php';

    function roborockAjax(data, ok, ko) {
        $.ajax({
            type    : 'POST',
            url     : AJAX,
            data    : data,
            dataType: 'json',
            success : function (r) {
                if (r.state !== 'ok') {
                    $.fn.showAlert({ message: r.result, level: 'danger' });
                    if (typeof ko === 'function') { ko(r.result); }
                    return;
                }
                if (typeof ok === 'function') { ok(r.result); }
            },
            error: function (xhr) {
                var msg = 'Erreur HTTP ' + xhr.status;
                $.fn.showAlert({ message: msg, level: 'danger' });
                if (typeof ko === 'function') { ko(msg); }
            }
        });
    }

    /* ── Synchroniser les appareils ── */
    $(document).on('click', '#bt_synchronize', function () {
        var btn = $(this).prop('disabled', true).html('<i class="fas fa-spin fa-spinner"></i>');
        roborockAjax({ action: 'synchronize' }, function (result) {
            btn.prop('disabled', false).html('<i class="fas fa-sync"></i> {{Synchroniser}}');
            $.fn.showAlert({ message: result, level: 'success' });
            setTimeout(function () { location.reload(); }, 1500);
        }, function () {
            btn.prop('disabled', false).html('<i class="fas fa-sync"></i> {{Synchroniser}}');
        });
    });

    /* ── Recreer les commandes ── */
    $(document).on('click', '#bt_recreate_cmds', function () {
        var id = $('.eqLogicAttr[data-l1key=id]').value();
        if (!id) { return; }
        var btn = $(this).prop('disabled', true).html('<i class="fas fa-spin fa-spinner"></i>');
        roborockAjax({ action: 'recreateCommands', id: id }, function () {
            btn.prop('disabled', false).html('<i class="fas fa-sync"></i> {{Recreer les commandes}}');
            $.fn.showAlert({ message: '{{Commandes recréées}}', level: 'success' });
            roborockAjax({ action: 'get', id: id }, function (data) {
                $('#table_cmd tbody').empty();
                $.each(data.cmds || [], function (i, c) { addCmdToTable(c); });
            });
        }, function () {
            btn.prop('disabled', false).html('<i class="fas fa-sync"></i> {{Recreer les commandes}}');
        });
    });

    /* ── Synchroniser les routines ── */
    $(document).on('click', '#bt_sync_routines', function () {
        var id = $('.eqLogicAttr[data-l1key=id]').value();
        if (!id) { return; }
        var btn = $(this).prop('disabled', true).html('<i class="fas fa-spin fa-spinner"></i>');
        roborockAjax({ action: 'syncRoutines', id: id }, function (result) {
            btn.prop('disabled', false).html('<i class="fas fa-robot"></i> {{Synchroniser les routines}}');
            $.fn.showAlert({ message: result, level: 'success' });
            roborockAjax({ action: 'get', id: id }, function (data) {
                $('#table_cmd tbody').empty();
                $.each(data.cmds || [], function (i, c) { addCmdToTable(c); });
            });
        }, function () {
            btn.prop('disabled', false).html('<i class="fas fa-robot"></i> {{Synchroniser les routines}}');
        });
    });

    /* ── Synchroniser les pieces ── */
    $(document).on('click', '#bt_sync_rooms', function () {
        var id = $('.eqLogicAttr[data-l1key=id]').value();
        if (!id) { return; }
        var btn = $(this).prop('disabled', true).html('<i class="fas fa-spin fa-spinner"></i>');
        roborockAjax({ action: 'syncRooms', id: id }, function (result) {
            btn.prop('disabled', false).html('<i class="fas fa-map"></i> {{Synchroniser les pieces}}');
            $.fn.showAlert({ message: result, level: 'success' });
            roborockAjax({ action: 'get', id: id }, function (data) {
                $('#table_cmd tbody').empty();
                $.each(data.cmds || [], function (i, c) { addCmdToTable(c); });
            });
        }, function () {
            btn.prop('disabled', false).html('<i class="fas fa-map"></i> {{Synchroniser les pieces}}');
        });
    });

});

/* ── addCmdToTable standard Jeedom ── */
function addCmdToTable(_cmd) {
    if (!isset(_cmd)) { var _cmd = { configuration: {} }; }
    if (!isset(_cmd.configuration)) { _cmd.configuration = {}; }

    var tr = '<tr class="cmd" data-cmd_id="' + init(_cmd.id) + '">';
    tr += '<td class="hidden-xs"><span class="cmdAttr" data-l1key="id"></span></td>';
    tr += '<td>';
    tr += '<div class="input-group">';
    tr += '<input class="cmdAttr form-control input-sm roundedLeft" data-l1key="name" placeholder="{{Nom de la commande}}">';
    tr += '<span class="input-group-btn"><a class="cmdAction btn btn-sm btn-default" data-l1key="chooseIcon" title="{{Choisir une icone}}"><i class="fas fa-icons"></i></a></span>';
    tr += '<span class="cmdAttr input-group-addon roundedRight" data-l1key="display" data-l2key="icon" style="font-size:19px;padding:0 5px 0 0!important;"></span>';
    tr += '</div>';
    tr += '</td>';
    tr += '<td>';
    tr += '<span class="type" type="' + init(_cmd.type) + '">' + jeedom.cmd.availableType() + '</span>';
    tr += '<span class="subType" subType="' + init(_cmd.subType) + '"></span>';
    tr += '</td>';
    tr += '<td>';
    tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isVisible" checked/>{{Afficher}}</label> ';
    if (init(_cmd.type) == 'info') {
        tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isHistorized" checked/>{{Historiser}}</label> ';
    }
    tr += '<div style="margin-top:5px;">';
    tr += '<input class="tooltips cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="minValue" placeholder="{{Min}}" title="{{Min}}" style="width:30%;max-width:80px;display:inline-block;margin-right:2px;">';
    tr += '<input class="tooltips cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="maxValue" placeholder="{{Max}}" title="{{Max}}" style="width:30%;max-width:80px;display:inline-block;margin-right:2px;">';
    tr += '<input class="tooltips cmdAttr form-control input-sm" data-l1key="unite" placeholder="{{Unite}}" title="{{Unite}}" style="width:30%;max-width:80px;display:inline-block;">';
    tr += '</div>';
    tr += '<input class="cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="listValue" placeholder="{{Liste des valeurs}}" style="margin-top:5px;" title="{{Format: valeur|label;valeur2|label2}}">';
    tr += '</td>';
    tr += '<td><span class="cmdAttr" data-l1key="htmlstate"></span></td>';
    tr += '<td>';
    if (is_numeric(init(_cmd.id))) {
        tr += '<a class="btn btn-default btn-xs cmdAction" data-action="configure"><i class="fas fa-cogs"></i></a> ';
        tr += '<a class="btn btn-default btn-xs cmdAction" data-action="test"><i class="fas fa-rss"></i> {{Tester}}</a>';
    }
    tr += '<i class="fas fa-minus-circle pull-right cmdAction cursor" data-action="remove"></i>';
    tr += '</td>';
    tr += '</tr>';

    $('#table_cmd tbody').append(tr);
    var jqTr = $('#table_cmd tbody tr:last');
    jqTr.setValues(_cmd, '.cmdAttr');
    if (isset(_cmd.type)) {
        jqTr.find('.cmdAttr[data-l1key=type]').value(init(_cmd.type));
    }
    jeedom.cmd.changeType(jqTr, init(_cmd.subType));
}
/* ══════════════════════ Onglet Carte ══════════════════════ */
var rbMap = { data: null, sel: null, drag: null, timer: null };

function rbMapEqId() { return $('.eqLogicAttr[data-l1key=id]').value(); }

function rbMapToMm(px, py) {
    var a = rbMap.data.meta.affine;
    var det = a[0] * a[4] - a[1] * a[3];
    var dx = px - a[2], dy = py - a[5];
    return { x: Math.round((a[4] * dx - a[1] * dy) / det), y: Math.round((-a[3] * dx + a[0] * dy) / det) };
}
function rbMapToPx(x, y) {
    var a = rbMap.data.meta.affine;
    return { x: a[0] * x + a[1] * y + a[2], y: a[3] * x + a[4] * y + a[5] };
}
function rbMapRoomAt(x, y) {
    var best = null, bestArea = Infinity;
    $.each(rbMap.data.meta.rooms || [], function (i, r) {
        if (x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1) {
            var area = (r.x1 - r.x0) * (r.y1 - r.y0);
            if (area < bestArea) { best = r; bestArea = area; }
        }
    });
    return best;
}

function rbMapDraw() {
    var cv = document.getElementById('cv_map');
    if (!cv || !rbMap.data || !rbMap.data.meta || !rbMap.data.meta.affine) return;
    var ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    var fs = Math.max(11, Math.round(cv.width / 60));
    ctx.font = 'bold ' + fs + 'px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    $.each(rbMap.data.meta.rooms || [], function (i, r) {
        var p = rbMapToPx((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2);
        var cur = (rbMap.data.meta.current_segment === r.segment_id);
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(0,0,0,0.6)';
        ctx.strokeText(r.name, p.x, p.y);
        ctx.fillStyle = cur ? '#ffeb3b' : '#ffffff';
        ctx.fillText(r.name, p.x, p.y);
    });
    if (rbMap.sel && rbMap.sel.type === 'point') {
        ctx.beginPath();
        ctx.arc(rbMap.sel.px, rbMap.sel.py, Math.max(6, cv.width / 120), 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(255,87,34,0.9)';
        ctx.fill();
        ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke();
    }
    var z = rbMap.drag || (rbMap.sel && rbMap.sel.type === 'zone' ? rbMap.sel : null);
    if (z) {
        ctx.fillStyle = 'rgba(76,175,80,0.25)';
        ctx.strokeStyle = '#4caf50';
        ctx.lineWidth = 3;
        ctx.fillRect(Math.min(z.px1, z.px2), Math.min(z.py1, z.py2), Math.abs(z.px2 - z.px1), Math.abs(z.py2 - z.py1));
        ctx.strokeRect(Math.min(z.px1, z.px2), Math.min(z.py1, z.py2), Math.abs(z.px2 - z.px1), Math.abs(z.py2 - z.py1));
    }
}

function rbMapUpdateButtons() {
    var s = rbMap.sel;
    $('#bt_mapGoto, #bt_mapRoom, #bt_mapZone').hide();
    if (!s) { $('#in_mapCoords').val(''); return; }
    if (s.type === 'point') {
        $('#in_mapCoords').val(s.x + ',' + s.y);
        if (rbMap.data.cmds.goto_position) $('#bt_mapGoto').show();
        if (s.room && rbMap.data.roomCmds[String(s.room.segment_id)]) {
            $('#bt_mapRoom').html('<i class="fas fa-broom"></i> {{Nettoyer}} ' + $('<span>').text(s.room.name).html()).show();
        }
    } else {
        $('#in_mapCoords').val(s.x1 + ',' + s.y1 + ',' + s.x2 + ',' + s.y2);
        if (rbMap.data.cmds.clean_zone) $('#bt_mapZone').show();
    }
}

function rbMapLoad(refresh) {
    var id = rbMapEqId();
    if (!id) return;
    if (refresh) $('#bt_mapRefresh').find('i').addClass('fa-spin');
    $.ajax({
        type: 'POST', url: 'plugins/roborock/core/ajax/roborock.ajax.php', dataType: 'json',
        data: { action: 'getMap', id: id, refresh: refresh ? 1 : 0 },
        success: function (r) {
            $('#bt_mapRefresh').find('i').removeClass('fa-spin');
            if (r.state !== 'ok') { $.fn.showAlert({ message: r.result, level: 'danger' }); return; }
            if (!r.result.available) {
                $('#div_mapInfo').text('{{Pas encore de carte : cliquez sur « Relire la carte » (robot en ligne).}}');
                $('#img_map').removeAttr('src');
                return;
            }
            rbMap.data = r.result;
            var m = r.result.meta;
            $('#div_mapInfo').text('{{Carte du}} ' + (m.updated || '?') + ' — {{Pièce courante}} : ' + (m.current_room || '?')
                + (m.affine ? '' : ' — {{repère indisponible, clic désactivé}}'));
            var img = document.getElementById('img_map');
            img.onload = function () {
                var cv = document.getElementById('cv_map');
                cv.width = img.naturalWidth; cv.height = img.naturalHeight;
                rbMapDraw();
            };
            if ($(img).attr('src') !== r.result.url) img.src = r.result.url; else rbMapDraw();
        },
        error: function (xhr) {
            $('#bt_mapRefresh').find('i').removeClass('fa-spin');
            $.fn.showAlert({ message: 'Erreur HTTP ' + xhr.status, level: 'danger' });
        }
    });
}

function rbMapEvtPx(e) {
    var cv = document.getElementById('cv_map');
    var rect = cv.getBoundingClientRect();
    return { x: (e.clientX - rect.left) * cv.width / rect.width, y: (e.clientY - rect.top) * cv.height / rect.height };
}

function rbMapExec(cmdId, title, message, label) {
    jeedom.cmd.execute({
        id: cmdId, value: { title: String(title), message: String(message) },
        error: function (err) { $.fn.showAlert({ message: err.message, level: 'danger' }); },
        success: function () { $.fn.showAlert({ message: label, level: 'success' }); }
    });
}

$(function () {
    $(document).on('shown.bs.tab', '#bt_tabMap', function () {
        rbMapLoad(false);
        clearInterval(rbMap.timer);
        rbMap.timer = setInterval(function () {
            if ($('#maptab').is(':visible')) rbMapLoad(false); else clearInterval(rbMap.timer);
        }, 30000);
    });
    $(document).on('click', '#bt_mapRefresh', function () { rbMapLoad(true); });
    $(document).on('change', 'input[name=rbMapMode]', function () { rbMap.sel = null; rbMapUpdateButtons(); rbMapDraw(); });

    var cv = document.getElementById('cv_map');
    if (cv) {
        cv.addEventListener('pointerdown', function (e) {
            if (!rbMap.data || !rbMap.data.meta || !rbMap.data.meta.affine) return;
            var p = rbMapEvtPx(e);
            if ($('input[name=rbMapMode]:checked').val() === 'zone') {
                rbMap.drag = { type: 'zone', px1: p.x, py1: p.y, px2: p.x, py2: p.y };
                cv.setPointerCapture(e.pointerId);
            } else {
                var mm = rbMapToMm(p.x, p.y);
                rbMap.sel = { type: 'point', px: p.x, py: p.y, x: mm.x, y: mm.y, room: rbMapRoomAt(mm.x, mm.y) };
                rbMapUpdateButtons();
            }
            rbMapDraw();
        });
        cv.addEventListener('pointermove', function (e) {
            if (!rbMap.drag) return;
            var p = rbMapEvtPx(e);
            rbMap.drag.px2 = p.x; rbMap.drag.py2 = p.y;
            rbMapDraw();
        });
        cv.addEventListener('pointerup', function () {
            if (!rbMap.drag) return;
            var z = rbMap.drag; rbMap.drag = null;
            if (Math.abs(z.px2 - z.px1) < 4 || Math.abs(z.py2 - z.py1) < 4) { rbMapDraw(); return; }
            var a = rbMapToMm(z.px1, z.py1), b = rbMapToMm(z.px2, z.py2);
            z.x1 = Math.min(a.x, b.x); z.x2 = Math.max(a.x, b.x);
            z.y1 = Math.min(a.y, b.y); z.y2 = Math.max(a.y, b.y);
            rbMap.sel = z;
            rbMapUpdateButtons();
            rbMapDraw();
        });
    }

    $(document).on('click', '#bt_mapCopy', function () {
        var v = $('#in_mapCoords').val();
        if (!v) return;
        if (navigator.clipboard) navigator.clipboard.writeText(v);
        else { $('#in_mapCoords').select(); document.execCommand('copy'); }
        $.fn.showAlert({ message: '{{Copié}} : ' + v, level: 'info' });
    });
    $(document).on('click', '#bt_mapGoto', function () {
        var s = rbMap.sel; if (!s) return;
        rbMapExec(rbMap.data.cmds.goto_position, '', s.x + ',' + s.y, '{{Robot envoyé au point}}');
    });
    $(document).on('click', '#bt_mapRoom', function () {
        var s = rbMap.sel; if (!s || !s.room) return;
        var c = rbMap.data.roomCmds[String(s.room.segment_id)];
        // passages > 1 : on passe par la commande generique "Nettoyer segments"
        var rep = $('#sel_mapRepeat').val();
        if (rep !== '1' && rbMap.data.cmds.clean_segment) {
            rbMapExec(rbMap.data.cmds.clean_segment, rep, String(s.room.segment_id), '{{Nettoyage lancé}}');
        } else {
            rbMapExec(c.id, '', '', '{{Nettoyage lancé}} : ' + s.room.name);
        }
    });
    $(document).on('click', '#bt_mapZone', function () {
        var s = rbMap.sel; if (!s) return;
        rbMapExec(rbMap.data.cmds.clean_zone, $('#sel_mapRepeat').val(),
            s.x1 + ',' + s.y1 + ',' + s.x2 + ',' + s.y2, '{{Nettoyage de zone lancé}}');
    });
});

/* Changement d'equipement : on oublie la carte affichee */
function printEqLogic(_eqLogic) {
    rbMap.data = null; rbMap.sel = null; rbMap.drag = null;
    $('#img_map').removeAttr('src');
    $('#div_mapInfo').text('');
    rbMapUpdateButtons();
    if ($('#maptab').is(':visible')) rbMapLoad(false);
}
