<?php
if (!isConnect('admin')) { throw new Exception('401 - Acces non autorise'); }
$apikey = jeedom::getApiKey('roborock');
?>
<div class="row">
 <div class="col-sm-8 col-sm-offset-2">
  <div class="panel panel-default">
   <div class="panel-heading"><h3 class="panel-title"><i class="fas fa-user-circle"></i> Compte Roborock</h3></div>
   <div class="panel-body">

    <div class="alert alert-info">
     Entrez votre e-mail, cliquez sur <strong>Envoyer le code</strong>, saisissez le code recu, puis <strong>Valider</strong>.<br>
     <strong>Important :</strong> saisissez le code immediatement a reception, il expire en 60 secondes.
    </div>

    <div class="form-group">
     <label class="col-sm-3 control-label">Adresse e-mail</label>
     <div class="col-sm-5">
      <input type="email" class="configKey form-control" data-l1key="roborock_email" placeholder="votre@email.com" />
     </div>
     <div class="col-sm-4">
      <a class="btn btn-warning" id="bt_sendCode"><i class="fas fa-paper-plane"></i> Envoyer le code</a>
     </div>
    </div>

    <div class="form-group" id="div_codeInput" style="display:none;">
     <label class="col-sm-3 control-label">Code recu</label>
     <div class="col-sm-3">
      <input type="text" class="form-control" id="in_loginCode" placeholder="123456" maxlength="8" />
     </div>
     <div class="col-sm-3">
      <a class="btn btn-success" id="bt_validateCode"><i class="fas fa-check"></i> Valider</a>
     </div>
    </div>

    <div class="form-group">
     <label class="col-sm-3 control-label">Region</label>
     <div class="col-sm-5">
      <select class="configKey form-control" data-l1key="roborock_region">
       <option value="">Automatique</option>
       <option value="https://euiot.roborock.com">Europe (EU)</option>
       <option value="https://usiot.roborock.com">Etats-Unis (US)</option>
       <option value="https://cniot.roborock.com">Chine (CN)</option>
      </select>
     </div>
    </div>

    <div class="form-group" style="margin-top:15px;">
     <label class="col-sm-3 control-label">Statut</label>
     <div class="col-sm-7">
      <?php if (!empty(config::byKey('roborock_user_data', 'roborock'))): ?>
       <span class="label label-success"><i class="fas fa-check"></i> Authentifie</span>
       <small class="text-muted" style="margin-left:10px;"><?php echo htmlspecialchars(config::byKey('roborock_email', 'roborock')); ?></small>
       <a class="btn btn-xs btn-danger" style="margin-left:10px;" id="bt_resetAuth"><i class="fas fa-times"></i> Reinitialiser</a>
      <?php else: ?>
       <span class="label label-default">Non authentifie</span>
      <?php endif; ?>
     </div>
    </div>

   </div>
  </div>
 </div>
</div>

<script>
var roborock_apikey = '<?php echo $apikey; ?>';

$(document).ready(function(){

 $('#bt_sendCode').on('click', function(){
  var email  = $('input.configKey[data-l1key="roborock_email"]').val().trim();
  var region = $('select.configKey[data-l1key="roborock_region"]').val();
  if (!email) { $.fn.showAlert({message:'Entrez votre adresse e-mail', level:'warning'}); return; }
  var btn = this;
  $(btn).prop('disabled', true).html('<i class="fas fa-spin fa-spinner"></i> Envoi...');
  $.ajax({
   type:'POST', url:'plugins/roborock/core/ajax/roborock.ajax.php',
   data:{action:'requestCode', email:email, region:region, apikey:roborock_apikey},
   dataType:'json', timeout:45000,
   success:function(r){
    $(btn).prop('disabled', false).html('<i class="fas fa-paper-plane"></i> Envoyer le code');
    if (r.state != 'ok') { $.fn.showAlert({message:r.result, level:'danger'}); return; }
    $.fn.showAlert({message:'Code envoye ! Saisissez-le IMMEDIATEMENT ci-dessous.', level:'success'});
    $('#div_codeInput').show();
    $('#in_loginCode').val('').focus();
   },
   error:function(e){
    $(btn).prop('disabled', false).html('<i class="fas fa-paper-plane"></i> Envoyer le code');
    $.fn.showAlert({message:'Erreur: ' + e.responseText, level:'danger'});
   }
  });
 });

 $('#bt_validateCode').on('click', function(){
  var email  = $('input.configKey[data-l1key="roborock_email"]').val().trim();
  var code   = $('#in_loginCode').val().trim();
  var region = $('select.configKey[data-l1key="roborock_region"]').val();
  if (!code) { $.fn.showAlert({message:'Entrez le code recu', level:'warning'}); return; }
  var btn = this;
  $(btn).prop('disabled', true).html('<i class="fas fa-spin fa-spinner"></i> Validation...');
  $.ajax({
   type:'POST', url:'plugins/roborock/core/ajax/roborock.ajax.php',
   data:{action:'codeLogin', email:email, code:code, region:region, apikey:roborock_apikey},
   dataType:'json', timeout:45000,
   success:function(r){
    $(btn).prop('disabled', false).html('<i class="fas fa-check"></i> Valider');
    if (r.state != 'ok') { $.fn.showAlert({message:r.result, level:'danger'}); return; }
    $.fn.showAlert({message:'Authentification reussie ! Demarrez le demon.', level:'success'});
    setTimeout(function(){ location.reload(); }, 2000);
   },
   error:function(e){
    $(btn).prop('disabled', false).html('<i class="fas fa-check"></i> Valider');
    $.fn.showAlert({message:'Erreur: ' + e.responseText, level:'danger'});
   }
  });
 });

 $('#bt_resetAuth').on('click', function(){
  if (!confirm('Reinitialiser l\'authentification ?')) return;
  $.ajax({
   type:'POST', url:'plugins/roborock/core/ajax/roborock.ajax.php',
   data:{action:'resetAuth', apikey:roborock_apikey},
   dataType:'json',
   success:function(){ location.reload(); }
  });
 });

});
</script>