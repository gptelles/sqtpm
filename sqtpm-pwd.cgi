#!/usr/bin/perl -w
# This file is part of sqtpm 10.
# Copyright 2003-2022 Guilherme P. Telles.
# sqtpm is distributed under the terms of WTFPL v2.

use CGI qw(:standard -no_xhtml);
use CGI::Carp 'fatalsToBrowser';

use Fcntl ':flock';
use Digest::SHA qw(sha512_base64);
use File::Basename;

use lib dirname(__FILE__);
use sqtpm;


if (request_method() eq 'POST') {
  setpasswd();
}
else {
  passwd_form();
}

exit(0);



################################################################################
sub setpasswd {

  my $uid = param('uid');
  my $oldplain = param('oldpwd');
  my $newplain = param('newpwd');
  my $replain = param('repwd');

  $uid =~ s/\s//g;

  # JS in the form will filter an empty uid, but just in case:
  if ($uid eq '') {
    passwd_form();
    return;
  }

  print header();
  print start_html(-title=>'senhas sqtpm', -style=>{-src=>['sqtpm.css']},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'}),
			   meta({-name=>'robots',-content=>'noindex'}),
			   meta({-name=>'googlebot',-content=>'noindex'})]);
  
  print '<div class="f85"><h1>senhas sqtpm</h1>';

  # Check user and passwords:
  my ($utype,$upassf) = authenticate($uid,$oldplain);

  ($utype eq '') and abort_pwd($uid,'Dados incorretos.');
  ($newplain eq '') and abort_pwd($uid,'A nova senha não pode ser vazia.');
  ($newplain ne $replain) and abort_pwd($uid,'A nova senha e a confirmação devem ser iguais.');

  # Update the password file:
  $newenc = sha512_base64($newplain);

  open(my $PASS,'+<',$upassf) or abort_pwd($uid,"setpasswd : open : $upassf : $!");
  flock($PASS,LOCK_EX);
    
  my $lines = '';
  my $got = 0;

  while (<$PASS>) {
    (/^([\*@]?)$uid:/ || /^([\*@]?)$uid\s*$/) && do {
      $lines .= "$1$uid:$newenc\n";
      $got = 1;
      next;
    };

    s/\s+//g;
    $_ and ($lines .= "$_\n");
  }

  if ($got) {
    seek($PASS,0,0);
    print $PASS $lines;
  }
  else {
    abort_pwd($uid,"setpasswd : $uid not in $upassf : $!");
  }

  flock($PASS,LOCK_UN);
  close($PASS);

  print "A senha foi ", ($oldplain ? 'alterada.' : 'cadastrada.');
  print '<hr><a href="sqtpm.cgi">sqtpm</a></div>';
  print end_html();

  add_to_log($uid,'',($oldplain ? 'Senha alterada.' : 'Senha cadastrada.'));
}



################################################################################
sub passwd_form {

  print header();
  print start_html(-title=>'senhas sqtpm', -style=>{-src=>['sqtpm.css']},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'}),
			   meta({-name=>'robots',-content=>'noindex'}),
			   meta({-name=>'googlebot',-content=>'noindex'})]);
  
  print '<div class="f85"><h1>senhas sqtpm</h1>';

  print <<END;
<script type="text/javascript">
  function setpwd() { 
    if (document.pass.uid.value == null || document.pass.uid.value == "") { 
	document.pass.uid.focus(); 
    }
    else if (document.pass.newpwd.value == null || document.pass.newpwd.value == "") { 
	document.pass.newpwd.focus(); }
    else if (document.pass.repwd.value == null || document.pass.repwd.value == "") { 
	document.pass.repwd.focus(); 
    }
    else { document.pass.setpwd.value = 1; document.pass.submit(); }
  }
  function enterh(e,name) {
    if (e.which == 13) { 
	if (name == 'u') { document.pass.oldpwd.focus(); } 
	else if (name == 'o') { document.pass.newpwd.focus(); } 
	else if (name == 'n') { document.pass.repwd.focus(); } 
	else { setpwd(); } 
    }
  }
</script>
<form name="pass" action="sqtpm-pwd.cgi" method="POST" enctype="multipart/form-data">
<table cellspacing=5 border=0>
<tr><td>usuário:<td>
<input onkeypress="enterh(event,'u')" type="text" name="uid" size="10" maxlength="20">
<tr><td>senha atual:<td>
<input onkeypress="enterh(event,'o')" type="password" name="oldpwd" size="10" maxlength="20">
<tr><td>senha nova:<td>
<input onkeypress="enterh(event,'n')" type="password" name="newpwd" size="10" maxlength="20">
<tr><td>confirmação:<td>
<input onkeypress="enterh(event,'c')" type="password" name="repwd" size="10" maxlength="20">
</table>
<input type="hidden" name="setpwd" value=0>
<hr>
<a href="javascript:setpwd()">enviar</a> &nbsp; &#8226; &nbsp; 
<a href="sqtpm.cgi">sqtpm</a>
<noscript><p>Seu browser não tem javascript.  Boa sorte na próxima!</noscript>
</form>
<script type="text/javascript">document.pass.uid.focus();</script>
</div>
END

  print end_html();
}
