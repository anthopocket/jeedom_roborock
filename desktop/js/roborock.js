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