<?php
if (!isConnect('admin')) {
    throw new Exception('{{401 - Accès non autorisé}}');
}
$plugin = plugin::byId('roborock');
sendVarToJS('eqType', $plugin->getId());
$eqLogics = eqLogic::byType($plugin->getId());
?>

<div class="row row-overflow">

    <!-- ══ LISTE ══ -->
    <div class="col-xs-12 eqLogicThumbnailDisplay">
        <legend><i class="fas fa-robot"></i> {{Gestion}}</legend>
        <div class="eqLogicThumbnailContainer">
            <div class="cursor eqLogicAction logoSecondary" data-action="gotoPluginConf">
                <i class="fas fa-wrench"></i><br>
                <span>{{Configuration}}</span>
            </div>
        </div>

        <legend><i class="fas fa-robot"></i> {{Mes aspirateurs Roborock}}</legend>
        <div class="eqLogicThumbnailContainer">
            <?php foreach ($eqLogics as $eq): ?>
            <div class="eqLogicDisplayCard cursor <?php echo $eq->getIsEnable() ? '' : 'opacity05'; ?>"
                 data-eqLogic_id="<?php echo $eq->getId(); ?>">
                <img src="plugins/roborock/plugin_info/roborock_icon.png"
                     onerror="this.src='core/img/no_image.gif'" style="width:80px;height:80px;" />
                <br>
                <span class="name"><?php echo $eq->getHumanName(true, true); ?></span>
                <span class="hiddenAsCard displayTableRight">
                    <span class="label label-default"><?php echo $eq->getConfiguration('model', 'Roborock'); ?></span>
                </span>
            </div>
            <?php endforeach; ?>
        </div>
        <div style="margin-top:15px;">
            <a class="btn btn-success" id="bt_synchronize">
                <i class="fas fa-sync"></i> {{Synchroniser}}
            </a>
        </div>
    </div>

    <!-- ══ FORMULAIRE ÉQUIPEMENT ══ -->
    <div class="col-xs-12 eqLogic" style="display:none;">
        <div class="input-group pull-right" style="display:inline-flex;">
            <span class="input-group-btn">
                <a class="btn btn-sm btn-default eqLogicAction roundedLeft" data-action="configure">
                    <i class="fas fa-cogs"></i><span class="hidden-xs"> {{Configuration avancée}}</span>
                </a><a class="btn btn-sm btn-success eqLogicAction" data-action="save">
                    <i class="fas fa-check-circle"></i> {{Sauvegarder}}
                </a><a class="btn btn-sm btn-danger eqLogicAction roundedRight" data-action="remove">
                    <i class="fas fa-minus-circle"></i> {{Supprimer}}
                </a>
            </span>
        </div>

        <ul class="nav nav-tabs" role="tablist">
            <li role="presentation">
                <a href="#" class="eqLogicAction" aria-controls="home" role="tab" data-toggle="tab" data-action="returnToThumbnailDisplay">
                    <i class="fas fa-arrow-circle-left"></i>
                </a>
            </li>
            <li role="presentation" class="active">
                <a href="#eqlogictab" aria-controls="home" role="tab" data-toggle="tab">
                    <i class="fas fa-robot"></i> {{Equipement}}
                </a>
            </li>
            <li role="presentation">
                <a href="#commandtab" aria-controls="profile" role="tab" data-toggle="tab">
                    <i class="fas fa-list"></i> {{Commandes}}
                </a>
            </li>
        </ul>

        <div class="tab-content">

            <!-- ─ Onglet Équipement ─ -->
            <div role="tabpanel" class="tab-pane active" id="eqlogictab">
                <br>
                <form class="form-horizontal">
                    <input type="hidden" class="eqLogicAttr" data-l1key="id" />
                    <div class="col-lg-6">
                        <fieldset>
                            <legend><i class="fas fa-wrench"></i> {{Paramètres généraux}}</legend>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{Nom}}</label>
                                <div class="col-sm-8">
                                    <input type="text" class="eqLogicAttr form-control" data-l1key="name" placeholder="{{Nom de l'équipement}}" />
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{Objet parent}}</label>
                                <div class="col-sm-8">
                                    <select class="eqLogicAttr form-control" data-l1key="object_id">
                                        <option value="">{{Aucun}}</option>
                                        <?php foreach (jeeObject::buildTree(null, false) as $o): ?>
                                        <option value="<?php echo $o->getId(); ?>">
                                            <?php echo str_repeat('&nbsp;&nbsp;', $o->getConfiguration('parentNumber')); ?>
                                            <?php echo $o->getName(); ?>
                                        </option>
                                        <?php endforeach; ?>
                                    </select>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{Catégorie}}</label>
                                <div class="col-sm-8">
                                    <?php foreach (jeedom::getConfiguration('eqLogic:category') as $key => $value): ?>
                                    <label class="checkbox-inline">
                                        <input type="checkbox" class="eqLogicAttr"
                                               data-l1key="category" data-l2key="<?php echo $key; ?>" />
                                        <?php echo $value['name']; ?>
                                    </label>
                                    <?php endforeach; ?>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="col-sm-4 control-label"></label>
                                <div class="col-sm-8">
                                    <label class="checkbox-inline">
                                        <input type="checkbox" class="eqLogicAttr" data-l1key="isEnable" /> {{Activer}}
                                    </label>
                                    <label class="checkbox-inline">
                                        <input type="checkbox" class="eqLogicAttr" data-l1key="isVisible" /> {{Visible}}
                                    </label>
                                </div>
                            </div>
                        </fieldset>

                        <fieldset>
                            <legend><i class="fas fa-info-circle"></i> {{Informations appareil}}</legend>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{Modèle}}</label>
                                <div class="col-sm-8">
                                    <input type="text" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="model" readonly />
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{IP locale}}</label>
                                <div class="col-sm-8">
                                    <input type="text" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="ip" readonly />
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{Firmware}}</label>
                                <div class="col-sm-8">
                                    <input type="text" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="firmware" readonly />
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="col-sm-4 control-label">{{ID appareil}}</label>
                                <div class="col-sm-8">
                                    <input type="text" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="device_id" readonly />
                                </div>
                            </div>
                        </fieldset>
                    </div>
                </form>
            </div><!-- /.tabpanel #eqlogictab -->

            <!-- ─ Onglet Commandes ─ -->
            <div role="tabpanel" class="tab-pane" id="commandtab">
                <br>
                <a class="btn btn-success btn-sm" id="bt_recreate_cmds">
                    <i class="fas fa-sync"></i> {{Recreer les commandes}}
                </a>
                <a class="btn btn-info btn-sm" id="bt_sync_routines" style="margin-left:5px;">
                    <i class="fas fa-robot"></i> {{Synchroniser les routines}}
                </a>
                <a class="btn btn-info btn-sm" id="bt_sync_rooms" style="margin-left:5px;">
                    <i class="fas fa-map"></i> {{Synchroniser les pieces}}
                </a>
                <br><br>
                <div class="table-responsive">
                    <table id="table_cmd" class="table table-bordered table-condensed">
                        <thead>
                            <tr>
                                <th class="hidden-xs" style="min-width:50px;width:70px;">ID</th>
                                <th style="min-width:200px;width:350px;">{{Nom}}</th>
                                <th>{{Type}}</th>
                                <th style="min-width:260px;">{{Options}}</th>
                                <th>{{Etat}}</th>
                                <th style="min-width:80px;width:200px;">{{Actions}}</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div><!-- /.tabpanel #commandtab -->

        </div><!-- /.tab-content -->
    </div><!-- /.eqLogic -->
</div><!-- /.row -->

<?php include_file('desktop', 'roborock', 'js', 'roborock'); ?>
<?php include_file('core', 'plugin.template', 'js'); ?>