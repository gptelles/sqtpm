#!/usr/bin/perl -w
# This file is part of sqtpm 10.
# Copyright 2003-2024 Guilherme P. Telles.
# sqtpm is distributed under the terms of WTFPL v2.

use CGI qw(:standard -no_xhtml);
use CGI::Carp 'fatalsToBrowser';
use CGI::Session qw/-ip-match/;
use CGI::Session::Driver::file; 
$CGI::LIST_CONTEXT_WARN = 0; 

use POSIX qw(ceil);
use LWP::Simple ();
use Cwd qw(cwd getcwd);
use Fcntl ':flock';
use File::Basename;
use File::Find;
use File::Copy;
use open ":encoding(UTF-8)";
use MIME::Base64 qw(encode_base64);
use Time::Local;

use lib dirname(__FILE__);
use sqtpm;

$CGI::POST_MAX = 50000; # bytes

umask(0007);

# Flags:
$sort_tables = 1;  # sort grades tables of assignments and groups by username.
$break_tables = 1; # break grades tables of assignments at every 28 lines.


# Globals:
my %sys_cfg = ();

my $cgi = CGI->new;
my $session = 0;

# Session file prefix:
my $sprefix = getcwd();
$sprefix =~ s/^\///;
$sprefix =~ s/\//-/g;
$sprefix = "sqtpm-$sprefix";

my $sessiond = '/tmp';
$CGI::Session::Driver::file::FileName = $sprefix . '-%s';  

my $sid = $cgi->cookie('CGISESSID') || $cgi->param('CGISESSID') || undef;

# If the session id exists but the file don't then it must get a new session:
(defined($sid) && !-f "$sessiond/$sprefix-$sid") and (undef $sid);

my $action = param('action');

# If there is an offline file, show a notice screen and close all sessions:
if (-f 'offline') {
  offline();
  unlink(glob "$sessiond/$sprefix*");
  exit(0);
}

if (!defined($sid)) {
  if (!defined($action)) {
    login_form();    
  }
  elsif ($action eq 'in') {
    my $uid = param('uid');
    my $pwd = param('pwd');
    
    my ($utype,$upassf) = authenticate($uid,$pwd);
    
    # authenticate() will accept if the typed and stored passwords are both blank because 
    # sqtpm-pwd needs it this way, but it is not ok to login with an empty password:
    ($pwd =~ /^\s*$/) and ($utype = '');  
    
    if ($utype ne '') {
      $session = new CGI::Session("driver:File",undef,{Directory=>$sessiond});
      $session->expire('+60m');
      $session->param('uid',$uid);
      $session->param('utype',$utype);
      $session->param('upassf',$upassf);
      add_to_log($uid,'','login');
      home(1);
    }
    else {
      sleep(3);
      abort_login($uid,'Dados incorretos.');
    }
  }
  elsif ($action eq 'about') {
    show_about();
  }
  else {
    login_form();
  }
}
else {
  $session = new CGI::Session("driver:File",$sid,{Directory=>$sessiond}) ||
    abort_login('',"Erro ao recuperar a sess�o : $!");
  
  if (!$session->param('uid')) {
    $session->delete();
    login_form();
  }
  elsif (!$action) {
    home(0);
  }
  elsif ($action eq 'rep') {
    show_subm_report();
  }
  elsif ($action eq 'stm') {
    show_statement();
  }
  elsif ($action eq 'sub') {
    submit_assignment();
  }
  elsif ($action eq 'out') {
    add_to_log($session->param('uid'),'','logout');
    $session->delete();
    login_form();
  }
  elsif ($action eq 'scr') {
    show_grades_table();
  }
  elsif ($action eq 'asc') {
    show_all_grades_table();
  }
  elsif ($action eq 'dwn') {
    download_file();
  }
  elsif ($action eq 'hlp') {
    show_help(param('arg1').'.html');
  }
  elsif ($action eq 'moss') {
    invoke_moss($session->param('uid'),$session->param('utype'),$session->param('upassf'),
		param('arg1'),param('arg2'));
  }
  else {
    home(0);
  }
}

exit(0);



################################################################################
sub offline {

  print header();
  print start_html(-title => 'sqtpm', 
		   -style => {-src=>['sqtpm.css']},
		   -Cache_Control => 'public',
		   -head => [Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'}),
			    meta({-name=>'robots',-content=>'noindex'}),
			    meta({-name=>'googlebot',-content=>'noindex'})]);

  print '<div class="f85"><h1>sqtpm</h1>O sqtpm est� indispon�vel no momento.<hr></div>';

  print end_html();
}



################################################################################
sub login_form {

  print header();
  print start_html(-title=>'sqtpm', 
		   -style=>{-src=>['sqtpm.css']},
		   -Cache_Control => 'public',
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'}),
			   meta({-name=>'robots',-content=>'noindex'}),
			   meta({-name=>'googlebot',-content=>'noindex'})]);

  print <<END;
<script type="text/javascript" src="sqtpm.js?61"></script>
<div class="f85">
<h1>sqtpm</h1>
<form method="post" action="sqtpm.cgi" enctype="multipart/form-data" name="sqtpm">
<table cellspacing="5" border="0">
<tr><td>usu�rio:</td><td>
<input onkeypress="enterh(event,'u')" type="text" name="uid" size="10" maxlength="20">
</td></tr>
<tr><td>senha:</td><td>
<input onkeypress="enterh(event,'p')" type="password" name="pwd" size="10" maxlength="20">
</td></tr>
</table>
<input type="hidden" name="action">
<input type="hidden" name="arg1">
<input type="hidden" name="arg2">
<input type="hidden" name="arg3">
<hr>
<a href="javascript:;" onclick="login()">entrar</a> &nbsp; &#8226; &nbsp; 
<a href="sqtpm-pwd.cgi">senhas</a> &nbsp; &#8226; &nbsp; 
<a href="javascript:;" onclick="wrap('about','','','')">bula</a>
<noscript><p>Seu browser n�o tem javascript.  Boa sorte na pr�xima!</noscript>
</form>
<script type="text/javascript">document.sqtpm.uid.focus();</script>
</div>
END

  print end_html();
}



################################################################################
sub home {

  my $first_login = shift;

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');
  my $scr = $session->param('screen');

  print_html_start($first_login,'home','x');
  
  if (!defined($scr)) {
    %sys_cfg = load_keys_values('sqtpm.cfg');
    
    # Summon assignments for the user:
    opendir(my $DIR,'.') or abort('','','home : opendir root : $!');
    my @assign = sort(grep
		      {-d $_ && !/^\./ && -e "$_/config" && -l "$_/$upassf" && stat("$_/$upassf")} 
		      readdir($DIR));
    close($DIR);

    my %groups = (); # a hash for pass files linked by any assignment.
    my %ast = (); # a hash with the state of each assignment.

    # The assignments table in home window:
    my $tab = ''; 

    # Assignments table header:
    $tab = '<table class="grid"><tr><th>Trabalho</th>';
    ($utype ne 'aluno') and ($tab .= '<th>Grupos</th>');
    $tab .= '<th>Estado</th>';
    ($utype ne 'aluno') and ($tab .= '<th>Abertura</th>');    
    $tab .= '<th>Data limite</th>';
    ($utype ne 'prof') and ($tab .= '<th>�ltimo envio</th></tr>');
    ($utype eq 'prof') and ($tab .= '<th>Moss</th></tr>');
    
    # Assignments table rows:
    for (my $i=0; $i<@assign; $i++) {
      my %cfg = load_configs($assign[$i],$uid,$utype,$upassf,1);
      my $state = %cfg ? assignment_state(\%cfg) : 1;
      
      $ast{$assign[$i]} = $state;

      # If the user is a student and the assignment is still closed or has an error, skip it:
      if ($utype eq 'aluno' && $state <= 2) {
	splice(@assign,$i,1);
	$i--;  
	next;
      }

      # Assignment name:
      $tab .= '<tr align="center"><td>' .
	"<a href=\"javascript:;\" onclick=\"wrap('stm','$assign[$i]');\">$assign[$i]</a></td>";
	
      # Groups, ie, pass files linked from the assignment:
      if ($utype ne 'aluno') {
	opendir($DIR,$assign[$i]) or abort($uid,$assign[$i],"home : opendir $assign[$i] : $!");
	my @group = sort(grep {/\.pass$/ && -l "$assign[$i]/$_" && stat("$assign[$i]/$_")}
		       readdir($DIR));
	close($DIR);
      
	$tab .= '<td>';
	for (my $j=0; $j<@group; $j++) {
	  my $group = $group[$j];
	  $group =~ s/\.pass$//;
	  $tab .= '<a href="javascript:;" ' .
	    "onclick=\"wrap('scr','$group','$assign[$i]');\">$group</a>&nbsp; ";
	  $groups{$group} = 1;
	}
	$tab =~ s/&nbsp; $/<\/td>/;
      }
      
      # Assignment state:
      if ($state == 1) {
	$tab .= '<td><font color="DarkRed">inconsistente</font></td>'
      }
      elsif ($state == 2) {
	$tab .= '<td><font color="DarkOrange">fechado</font></td>';
      }
      elsif ($state == 3) {
	$tab .= '<td><font color="Teal">aberto</font></td>';
      }
      elsif ($state == 4) {
	my $days = elapsed_days($cfg{deadline});
	$tab .= "<td><font color=\"Teal\">aberto (+$days)</font></td>";
      }
      elsif ($state == 5) {
	$tab .= '<td><font color="MediumBlue">dry-run</font></td>';
      }
      elsif ($state == 6) {
	$tab .= '<td>encerrado</td>';
      }
      
      # Startup:
      if ($utype ne 'aluno') {
	if (exists($cfg{startup})) {
	  if ($state == 1) {
	    $tab .= "<td>$cfg{startup}</td>";
	  }
	  else {
	    $tab .= '<td>' . dow($cfg{startup}) . " &nbsp;" . br_date($cfg{startup});
	  }
	}
	else {
	  $tab .= '<td>n�o h�</td>';
	}
      }
      
      # Deadline:
      if (exists($cfg{deadline})) {
	if ($state == 1) {
	  $tab .= "<td>$cfg{deadline}</td>";
	}
	else {
	  $tab .= '<td>' . dow($cfg{deadline}) . "&nbsp;" . br_date($cfg{deadline});
	}
      }
      else {
	$tab .= '<td>n�o h�</td>';
      }
      
      if ($utype ne 'prof') {
	# Last submisson grade:
	my %rep = load_rep_data("$assign[$i]/$uid/$uid.rep");
	
	if (exists($rep{grade})) {
	  ($state >= 10) and ($rep{grade} = 'recebido');
	  $tab .= '<td class="grid"><a href="javascript:;" ' .
	    "onclick=\"wrap('rep','$assign[$i]','$uid');\">$rep{grade}</a>";
	}
	else {
	  $tab .= '<td class="grid">n�o houve';
	}
	$tab .= '</td>';
      }
      elsif ($utype eq 'prof') { 
	# Moss launchers:
	my @aux = split(/ +/,$cfg{languages});
	(!@aux) && (@aux = split(/ +/,$sys_cfg{languages}));
	
	for ($j=@aux-1; $j>=0; $j--) {
	  if (lc($aux[$j]) eq 'pdf') {
	    splice(@aux,$j,1);
	  }
	}
	
	$tab .= '<td>';
	if (@aux) {
	  my $j;
	  for ($j=0; $j<@aux-1; $j++) {
	    $tab .= '<a href="javascript:;" ' . 
	      "onclick=\"wrap('moss','$assign[$i]','$aux[$j]');\">$aux[$j]</a> &nbsp;";
	  }
	  $tab .= '<a href="javascript:;" ' . 
	    "onclick=\"wrap('moss','$assign[$i]','$aux[$j]');\">$aux[$j]</a>";
	}
	else {
	  $tab .= '-';
	}
	$tab .= '</td>';
      }
    }
    $tab .= '</table>';

    if (@assign == 0) {
      $tab = "<p>N�o h� trabalhos para $uid.</p>";
    }
    
    # Links for grade tables:
    if ($utype eq 'prof') {
      my @groups = sort keys(%groups);
      if (@groups) {
	$tab .= "<p><b>Tabelas de acertos:</b>";
	$tab .= '<br>&nbsp;&nbsp;';
	for (my $j=0; $j<@groups; $j++) {
	  $tab .= '<a href="javascript:;" ' .
	    "onclick=\"wrap('asc','$groups[$j]');\">$groups[$j]</a>&nbsp; ";
	}
	$tab .= ''; #'</p>';
      }
    }

    $scr .= $tab;
    $session->param('assign_states',\%ast);
    $session->param('screen',$scr);
  }

  print $scr;
  print_html_end();
}



################################################################################
sub show_subm_report {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $assign = param('arg1');
  my $suid = param('arg2');

  print_html_start(0,'saida','b');

  # Check if user is in the assignment and his type:
  passf_in_assign($uid,$upassf,$assign);

  if ($utype eq 'aluno') {
    ($uid ne $suid) and block_user($uid,$upassf,"show_report : aluno $uid n�o pode ver $suid.");
  }
  else {
    # * and @ users may see reports of other users:
    $uid = $suid;
  }

  my $userd = "$assign/$uid";
  my $reportf = "$userd/$uid.rep";

  (!-e $reportf) and 
    block_user($uid,$upassf,"show_report : n�o existe arquivo $reportf.");

  if ($utype eq 'aluno') {
    my %ast  = %{ $session->param('assign_states') };

    if ($ast{$assign} >= 10) {
      open(my $FILE,'<',$reportf) or abort($uid,$assign,"show_report : open $reportf : $!");
      
      while (<$FILE>) {
	/^<\!--/ && do {
	  next;
	};
	/^<p><b>Execu/ && do {
	  last;
	};
	/^<p><b>Compila/ && do {
	  last;
	};
	print $_;
      }
      close($FILE);

      print '<br><b>Recebido.</b><hr>';
      print_html_end();
      return;
    }
  }
  
  open(my $FILE,'<',$reportf) or abort($uid,$assign,"show_report : open $reportf : $!");
  while (<$FILE>) {
    print $_;
  }
  close($FILE);

  print_html_end();
}



################################################################################
sub show_statement {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');
  my $assign = param('arg1');

  print_html_start(0,'envio','b');

  # Check if the user is in the assignment:
  passf_in_assign($uid,$upassf,$assign);

  # Configs and assignment state:
  my %cfg = load_configs($assign,$uid,$utype,$upassf);
  my $state = assignment_state(\%cfg);

  # If state has changed, force reloading the home table:
  my %ast = %{ $session->param('assign_states') };
  if ($ast{$assign} != $state) {
    $ast{$assign} = $state;
    $session->param('screen',undef);
  }
  
  # If the assignment is not open yet and the user is a student, this is strange:
  ($utype eq 'aluno' && $ast{$assign} == 2) and
    block_user($uid,$upassf,"show_st : o prazo para enviar $assign n�o come�ou");

  # Octave, Fortran and Pascal are limited to a single source file:
  if ($cfg{languages} eq 'Octave' || $cfg{languages} eq 'Fortran' || $cfg{languages} eq 'Pascal') {
    $cfg{files} = '1,1';
  }

  print "<b>Trabalho:</b> $assign";

  my $p = 0;
  my $open = 1; # Whether the assignment accepts submissions or not.

  if (exists($cfg{startup})) {
    print '<p>Data de abertura: ', br_date($cfg{startup});
    $p = 1;
  }

  if (exists($cfg{deadline})) {
    print $p ? '<br>' : '<p>';
    print "Data limite para envio: ", br_date($cfg{deadline});

    if ($ast{$assign} == 2) {
      print ' (<font color="DarkOrange">fechado</font>)';
    }
    elsif ($ast{$assign} == 3 || $ast{$assign} == 13) {
      print ' (<font color="Teal">aberto</font>)';
    }
    elsif ($ast{$assign} == 4 || $ast{$assign} == 14) {
      my $days = elapsed_days($cfg{deadline}); 
      print " (<font color=\"Teal\">aberto +$days</font>)";
    }
    elsif ($ast{$assign} == 5 || $ast{$assign} == 15) {
      print '<br><font color="MediumBlue">dry-run: � poss�vel enviar at� ',
	br_date($cfg{'keep-open'}),
	' mas sem substituir o �ltimo envio no prazo.</font>';
      $cfg{tries} += 10;
    }
    elsif ($ast{$assign} == 6) {
      print ' (encerrado)';
      ($utype eq 'aluno') and ($open = 0);
    }
  
    ($cfg{penalty} < 100) and print "<br>Penalidade por dia de atraso: $cfg{penalty}\%";
  }


  print "<p>N�mero m�ximo de envios: ", $cfg{tries};

  
  my @nf = split(/,/,$cfg{files});
  my @reqfiles = ();

  if (exists($cfg{filenames})) {
    if (exists($cfg{filenames})) {
      @reqfiles = split(/ +/,$cfg{filenames});
      for (my $i=0; $i<@reqfiles; $i++) {
	$reqfiles[$i] =~ s/\{uid\}/$uid/;
	$reqfiles[$i] =~ s/\{assign\}/$assign/;
      }
      
      (@reqfiles > $nf[0]) and ($nf[0] = scalar @reqfiles);
      (@reqfiles > $nf[1]) and ($nf[1] = scalar @reqfiles);
    }
  }
  
  print '<br>N�mero de arquivos a enviar: ',
    $nf[0] == $nf[1] ? "$nf[0]" : "entre $nf[0] e $nf[1]";
  
  (@reqfiles) and print "<br>Nomes dos arquivos a enviar: @reqfiles<br>";
  $p = 1;

  
  my $tryed = 0;
  my $tryed_at = undef;
  my $tryed_grade;
    
  my $repf = "$assign/$uid/$uid.rep";
  if (-e $repf) {
    my %rep = load_rep_data($repf);
    $tryed = $rep{tries};
    $tryed_at = $rep{at};
    $tryed_grade = $rep{grade};
  }
  
  my $dryf = "$assign/$uid/$uid.dryrun.rep";
  if (-e $dryf) {
    %rep = load_rep_data($dryf);
    $tryed = $rep{tries};
  }
  
  print "<p>N�mero de envios de $uid: $tryed";
  
  if (defined $tryed_at) {
      print '<br>�ltimo envio:</b> ',
	'<a href="javascript:;" ', "onclick=\"wrap('rep','$assign','$uid');\">",
	br_date($tryed_at),
	($ast{$assign} < 10 && $tryed_grade ne 'recebido') ? " ($tryed_grade)" : '',
	'</a>';
  }
  
  $p = 0;

  if (-f "$assign/casos-de-teste.tgz") {
    print '<p>Casos-de-teste abertos: <a href="javascript:;" ',
      "onclick=\"wrap('dwn','$assign','','casos-de-teste.tgz')\";>casos-de-teste.tgz</a>";
    $p = 1;
  }
  
  if ($utype ne 'aluno' && -f "$assign/casos-de-teste-todos.tgz") {
    print $p ? '<br>' : '<p>',
      'Casos-de-teste: <a href="javascript:;" ',
      "onclick=\"wrap('dwn','$assign','','casos-de-teste-todos.tgz')\";>",'casos-de-teste.tgz</a>';
    $p = 1;
  }

  if (-f "$assign/include.tgz") {
    print $p ? '<br>' : '<p>',
      'Arquivos auxiliares: <a href="javascript:;" ',
      "onclick=\"wrap('dwn','$assign','','include.tgz')\";>include.tgz</a>";
  }
  
  if ($utype eq 'prof') {
    opendir(my $DIR,$assign) or abort($uid,$assign,"home : opendir $assign : $!");
    my @aux = sort(grep {-f "$assign/$_" && /^config/ && !/~$/} readdir($DIR));
    close($DIR);
    
    print '<p><b>Diretivas:&nbsp; </b> <a href="javascript:;" ',
      "onclick=\"toggleDiv('configs');\">todas</a>&nbsp;&nbsp;";

    for (my $i=0; $i<@aux; $i++) {
      print '<a href="javascript:;" ',
	"onclick=\"toggleDiv('$aux[$i]');\">$aux[$i]</a>&nbsp;&nbsp;";
    }

    print "<div id='configs' style='display:none' class='src'><b>diretivas correntes</b>";
    print "<pre class='prettyprint'>";
    print "languages: $cfg{languages}\n",
      "backup: $cfg{backup}\n",
      "grading: $cfg{grading}\n",
      exists($cfg{'keep-open'}) ? "keep-open: $cfg{'keep-open'}\n" : '',
      exists($cfg{'hide-grades'}) ? "hide-grades: $cfg{'hide-grades'}\n" : '',
      "cputime: $cfg{cputime} s, virtmem: $cfg{virtmem} kb, stkmem: $cfg{stkmem} kb\n",
      exists($cfg{'limits'}) ? "limits: $cfg{limits}\n" : '';
    
    print "\n<b>todas:</b>\n";
    for $k (sort(keys(%cfg))) {
      print "$k: $cfg{$k}\n";
    }
    print "</pre></div>";

    for (my $i=0; $i<@aux; $i++) {
      print "<div id='$aux[$i]' style='display:none' class='src'><b>$aux[$i]</b>";
      print "<pre class='prettyprint'>";
      print load_file($uid,$assign,"$assign/$aux[$i]",0);
      print "</pre></div>";
    }    
  }

  # Groups:
  if ($utype ne 'aluno') {
    opendir(my $DIR,$assign) or abort($uid,$assign,"home : opendir $assign : $!");
    @aux = sort(grep {/\.pass$/ && -l "$assign/$_" && stat("$assign/$_")} readdir($DIR));
    close($DIR);
    
    print '<p><b>Grupos:&nbsp; </b>';
    for (my $i=0; $i<@aux; $i++) {
      my $group = $aux[$i];
      $group =~ s/\.pass$//;
      print '<a href="javascript:;"',
	"onclick=\"wrap('scr','$group','$assign');\">$group</a>&nbsp; ";
    }
  }

  # Submit:
  if ($open) {
    @aux = $utype eq 'prof' ? split(/ +/,$sys_cfg{languages}) : split(/ +/,$cfg{languages});
    
    print "<input type='hidden' name='submassign' value='$assign'>",
      '<p><b>Enviar:</b></p>',
      '<table cellspacing="0" border="0">',
      '<tr><td>Linguagem: &nbsp;';   
    
    print $cgi->popup_menu('language', \@aux);
    
    print '</td>',
      '<td style="padding-left:30px">Arquivos: &nbsp;',
      '<input type="file" name="source" multiple></td>',
      '<td style="padding-left:30px">',
      '<input type="submit" class="button" name="subm" value="Enviar"',
      ' onclick="javascript:wrap(\'sub\')"></td>',
      '</table>',
      '<p>';
  }

  # Description:
  if (exists($cfg{description})) {
    if ($cfg{description} =~ /^http/) {
      print "<p><hr>Enunciado: <a href='$cfg{description}'>$cfg{description}</a><hr>";
    }
    elsif (-f "$assign/$cfg{description}") {
      print '<p><hr>';
      print_html_file($assign,$cfg{description});
      print '<hr>';
    }
    else {
      abort($uid,$assign,"description em config de $assign n�o � http nem arquivo.");
    }
  }
  else {
    print '<p><hr>';
  }

  ($utype eq 'aluno') && add_to_log($uid,$assign,'');
  print_html_end();
}



################################################################################
sub show_about {

  print header();
  print start_html(-title=>'sqtpm', 
		   -style=>{-src=>['sqtpm.css']},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'}),
			   meta({-name=>'robots',-content=>'noindex'}),
			   meta({-name=>'googlebot',-content=>'noindex'})]);

  print '<div class="f85">';
  print_html_file('','bula.html');
  print '<hr><a href="sqtpm.cgi">sqtpm</a></div>';
  print end_html();
}  



################################################################################
sub show_help {

  my $file = shift;

  print_html_start();
  print_html_file('',$file);
  print_html_end();
}  



################################################################################
sub download_file {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $assign = param('arg1');
  my $suid = param('arg2');
  my $file = param('arg3');

  # Check if the user is in the assignment and his type:
  passf_in_assign($uid,$upassf,$assign);

  # Check file existance:
  if ($file eq 'casos-de-teste.tgz') {
    $file = "$assign/$file";
  }
  elsif ($file eq 'include.tgz') {
    $file = "$assign/$file";
  }
  else {
    $file = "$assign/$suid/$file";
    
    # Students may not dig around:
    if ($utype eq 'aluno') {
      ($uid ne $suid) and block_user($uid,$upassf,"download_file : $uid n�o pode acessar $file.");
      (!-f $file) and block_user($uid,$upassf,"download_file : $assign/$uid/$file n�o existe.");
    }
  }
    
  # Download:
  print "Content-Type:application/x-download\nContent-Disposition:attachment;filename=$file\n\n";
  
  open(my $FILE,'<',$file) or abort($uid,$assign,"download_file : open $file : $!");
  binmode $FILE;
  while (<$FILE>) {
    print $_;
  }
  close($FILE);
}



################################################################################
sub show_grades_table {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $passf = param('arg1').'.pass';
  my $assign = param('arg2');

  print_html_start();

  # Check user type and whether he is in the assignment:
  ($utype eq 'aluno') and block_user($uid,$upassf,"grades_table: $uid n�o � prof ou monitor.");
  passf_in_assign($uid,$upassf,$assign);
  
  my $tabfile = "$assign/$passf";
  $tabfile =~ s/\.pass$//;
  $tabfile .= ".grades"; 
  
  my $tab;

  # If the table exists already, load it from file.
  if (-f $tabfile) {
    open(my $F,'<',$tabfile) or abort($uid,$assign,"show_grades_table : open $tabfile : $!");
    {
      local $/;
      $tab = <$F>;
    }
    close($F);
  }
  else {
    my @langs = ();
    my %langs = ();
    my %grades = ();
    
    # Get users:
    my @users = load_keys($passf,':');
    my $n = @users;

    my $grp = $passf =~ s/.pass$//r;
    
    if (@users == 0) {
      $tab = '<p><b>N�o h� usu�rios em $grp.</p>';
    }
    else {

      my %cfg = load_configs($assign,$uid,$utype,$upassf);

      # Get users grades and build a hash having an array of student ids for each language:
      %grades = ();
      %langs = ();

      for (my $i=0; $i<@users; $i++) {
	$users[$i] =~ s/^[\*@]?//;
      }    

      my $show = 0;
      my $show100 = 0;

      $tab = "<b>Acertos para os $n usu�rios de $grp em " .
	"<a href=\"javascript:;\" onclick=\"wrap('stm','$assign');\">$assign</a>:</b>";
	
      for my $user (@users) {
	my %rep = load_rep_data("$assign/$user/$user.rep");

	if (exists($rep{grade})) {
	  my $g = $rep{grade};
	  $g =~ s/\%//;
	  
	  $grades{$user} =
	    "<a href=\"sqtpm.cgi?action=rep&arg1=$assign&arg2=$user\">$rep{grade}</a>";

	  (!exists($langs{$rep{lang}})) and ($langs{$rep{lang}} = ());
	  push(@{$langs{$rep{lang}}},$user);

	  $show++;
	  ($g ne 'recebido' && $g == 100) and ($show100++);
	}
	else {
	  $grades{$user} = '-';
	}
      }

      @langs = sort(keys(%langs));

      # Produce a report with a table with tuples {user,grade} and a
      # histogram.  They are both in an outer table.

      $tab .= '<br><table border=0><tr><td><ul>' .
	sprintf("<li>Enviados: %i (%.0f%%)",$show,($n>0?100*$show/$n:0.0)) .
	sprintf("<li>100%%: %i (%.0f%%)",$show100,($show>0?100*$show100/$show:0.0));
      (@langs == 1) and ($tab .= "<li>Todos em $langs[0]");
      $tab .= '</ul></td><td><ul>';
      
      if (exists($cfg{deadline})) {
	$tab .= "<li>data limite: " . br_date($cfg{deadline});
      }
      if (exists($cfg{'keep-open'})) {
	$tab .= '<li>keep-open: ' . br_date($cfg{'keep-open'});
      }
      $tab .= '</ul></td></tr></table>';

      $tab .= '<p><table border=0>' .
	'<tr><td valign="top">' .
	'<table class="sgrid">' .
	'<tr><th>usu�rio</th><th>acertos</th></tr>';

      if ($sort_tables) {
	@users = sort(@users);
      }
      
      my $c = 0;
      my $d = 0;
      for my $user (@users) {
	$tab .= "<tr align=center><td><b>$user</b></td><td>$grades{$user}</td></tr>";
	$c++;
	$d++;
	if ($break_tables && $d == 28 && $c < @users) {
	  $tab .= '</table></td>' .
	    '<td valign="top"><table class="sgrid">' .
	    '<tr><th>usu�rio</th><th>acertos</th></tr>';
	  $d = 0;
	}
      }

      $tab .= '</table></td>';

      # Submission histogram per day:
      if ($cfg{backup} eq 'on') {
	%gusers = map { $_ => 1 } @users; # %gusers is used by wanted_hist.
	@ggrades = ();                    # @ggrades is modified by wanted_hist.    
	$st = 0; $dl = 0;                 # $st and $dl are used by wanted_hist.
	
	find(\&wanted_hist,"$assign");
	
	if (@ggrades) {
	  my %freq = ();
	  my %freq100 = ();
	  my %frequniq = ();
	  my %freq100uniq = ();

	  my %uniq = ();
	  my %uniq100 = ();

	  # The order is date,grade,user:
	  for (my $i=0; $i<@ggrades; $i+=3) {
  
	    if (exists($freq{"$ggrades[$i]"})) {
	      $freq{"$ggrades[$i]"}++;
	    }
	    else {
	      $freq{"$ggrades[$i]"} = 1;
	      $freq100{"$ggrades[$i]"} = 0;
	      $frequniq{"$ggrades[$i]"} = 0;
	      $freq100uniq{"$ggrades[$i]"} = 0;
	    }
	    
	    if ($ggrades[$i+1] eq '100%') {
	      $freq100{"$ggrades[$i]"}++;
	    }

	    if (!exists($uniq{"$ggrades[$i]$ggrades[$i+2]"})) {
	      $frequniq{"$ggrades[$i]"}++;
	      $uniq{"$ggrades[$i]$ggrades[$i+2]"} = 1;
	    }

	    if (!exists($uniq100{"$ggrades[$i]$ggrades[$i+2]"}) && $ggrades[$i+1] eq '100%') {
	      $freq100uniq{"$ggrades[$i]"}++;
	      $uniq100{"$ggrades[$i]$ggrades[$i+2]"} = 1;
	    }
	  }
	  
	  my @aux = sort { $a cmp $b } keys(%freq);
	  my $first = $aux[0];
	  my $last = $aux[$#aux];

	  if (exists($cfg{startup})) {
	    $cfg{startup} =~ /(.*) .*/;
	    ($first gt $1) and ($first = $1);
	  }
	  
	  if (exists($cfg{deadline})) {
	    $cfg{deadline} =~ /(.*) .*/;
	    ($last lt $1) and ($last = $1);
	  }

	  my ($y, $m, $d) = split(/\//,$first);
	  $first = timelocal(0, 0, 12, $d, $m-1, $y-1900);
	  ($y, $m, $d) = split(/\//,$last);
	  $last = timelocal(0, 0, 12, $d, $m-1, $y-1900);
	  
	  my $curr = $first;
	  while ($curr le $last) {
	    my @aux = localtime($curr);
	    my $date = sprintf("%04.0f/%02.0f/%02.0f",$aux[5]+1900,$aux[4]+1,$aux[3]);
	    
	    if (!exists($freq{$date})) {
	      $freq{$date} = 0;
	      $freq100{$date} = 0;
	      $frequniq{$date} = 0;
	      $freq100uniq{$date} = 0;
	    }
	    else {
	      if ($freq{$date} < $freq100{$date}) {
		$freq{$date} = $freq100{$date};
	      }
	      if ($frequniq{$date} < $freq100uniq{$date}) {
		$frequniq{$date} = $freq100uniq{$date};
	      }
	    }
	    
	    $curr += 24 * 60 * 60;
	  }
	  
	  my $size = keys %freq;
	  
	  $tab .= '<td valign=\'top\'><table><tr><td style="border:0;padding: 0px 0px 0px 20px">' .
	    '<img src="data:image/png;base64,' .
	    encode_base64(histogram($size<25 ? 500 : $size*20,360,\%freq,\%freq100)) . '">' .
	    '<p>Envios e envios 100% (verde) por dia.';

	  $tab .= '</td></tr><tr><td style="border:0;padding: 0px 0px 0px 20px">' .
	    '<br><img src="data:image/png;base64,' .
	    encode_base64(histogram($size<25 ? 500 : $size*20,360,\%frequniq,\%freq100uniq)) .
	    '"><p>Usu�rios que enviaram e que enviaram com 100% (verde) por dia.' .
	    '</td></tr></table></td>';
	}
      }
      $tab .= '</tr></table>';
    }

    if (@langs > 1) {
      # Produce the report with a table with tuples {user,grade} for each language:  
      $tab .= "<p>&nbsp;</p><b>Acertos para $grp em $assign por linguagem de programa��o:</b>" .
	'<p><table border=0><tr>';

      for my $k (@langs) {
	$tab .= '<td valign="top"><table class="sgrid">' . 
	  "<tr><th>usu�rio</th><th>$k</th></tr>";

	my $show = 0;
	my $show100 = 0;
	@users = @{$langs{$k}};
	
	for my $user (sort(@users)) {
	  $tab .= '<tr align=center>' . 
	    "<td><b>$user</b></td><td>$grades{$user}</td></tr>";
	  ($grades{$user} ne '-') and ($show++);
	  ($grades{$user} =~ '>100</a>$') and ($show100++);
	}
	
	my $n = @users;
	$tab .= '<tr><td><b>100%</b><br><b>%</b></td>' .
	  sprintf("<td>%i / %i<br>%.0f%%</td></tr>",$show100,$show,($show>0?100*$show100/$show:0)) .
	  '</table>' .
	  '</td><td></td>';
      }
    }

    # Save table to file. submit_assignment() will remove it:
    open(my $F,'>',$tabfile) or abort($uid,$assign,"show_grades_table : open $tabfile : $!");
    print $F $tab;
    close($F);    
  }

  print $tab;
  print_html_end();
}



################################################################################
sub show_all_grades_table {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $passf = param('arg1').'.pass';

  print_html_start();
  
  # Check user type:
  ($utype ne 'prof') and block_user($uid,$upassf,"all_grades: $uid n�o � prof.");

  # Get a list of assignments for the user:
  opendir(my $DIR,'.') or abort($uid,'','all_grades : opendir root : $!');
  my @amnts = sort(grep { -d $_ && !/^\./ && -f "$_/config" && -l "$_/$passf" } readdir($DIR));
  close($DIR);
  
  if (@amnts == 0) {
    print "N�o h� trabalhos para $passf.";
    print_html_end();
  }

  # Get users:
  my @users = load_keys($passf,':');

  for (my $i=0; $i<@users; $i++) {
    $users[$i] =~ s/^[\*@]?//;
  }

  # Build the structure: $grades{assignment}{id} = grade.
  my %grades = ();

  for (my $i=@amnts-1; $i>=0; $i--) {
    $grades{$amnts[$i]} = { () };

    for my $user (@users) {
      my %rep = load_rep_data("$amnts[$i]/$user/$user.rep");

      if ($rep{tries} > 0) {
	$rep{grade} =~ s/%//;
	$rep{grade} =~ s/recebido/r/;
	$grades{$amnts[$i]}{$user} =
	  "<a href=\"sqtpm.cgi?action=rep&arg1=$amnts[$i]&arg2=$user\">$rep{grade}</a>";
      }
      else {
	$grades{$amnts[$i]}{$user} = '-';
      }
    }
  }

  my %show = ();
  my %show100 = ();
  my $n = @users;

  for my $amnt (@amnts) {
    $show{$amnt} = 0;
    $show100{$amnt} = 0;
  }
    
  for my $user (@users) {
    for my $amnt (@amnts) {
      ($grades{$amnt}{$user} ne '-') and ($show{$amnt}++);
      ($grades{$amnt}{$user} =~ '>100</a>$') and ($show100{$amnt}++);
    }
  }

  # Print a table with tuples {user,grade,grade,...} and summaries:
  print "<b>Acertos para $n usu�rios em $passf:</b></p>";

  print '<table class="sgrid"><tr><td><b>enviados</b></td>';
  
  for my $amnt (@amnts) {
    printf("<td>%i (%.0f%%)</td>",$show{$amnt},($n>0 ? 100*$show{$amnt}/$n : 0.0));
  }
  print '</tr>';
    
  print '<tr><td><b>100%</b></td>';
  for my $amnt (@amnts) {
    printf("<td>%i (%.0f%%)</td>",
	   ($show100{$amnt},($show{$amnt}>0 ? 100*$show100{$amnt}/$show{$amnt} : 0.0)));
  }
  print '</tr>';

  print '<tr><th>usu�rio</th>';
  for my $amnt (@amnts) {
    #print "<th><a href=\"javascript:;\" onclick=\"wrap('stm','$amnt');\">$amnt</a></th>";
    print "<th>$amnt</th>";
  }
  print '</tr>';

  if ($sort_tables) {
    @users = sort(@users);
  }

  for my $user (@users) {
    print "<tr><td><b>$user</b>";
    for my $amnt (@amnts) {
      print "<td>$grades{$amnt}{$user}</td>";
    }
    print '</tr>';
  }

  print '</table>';
  print_html_end();
}



################################################################################
sub submit_assignment {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');
  
  my $assign = param('submassign');
  my $language = param('language');
  my @uploads = param('source');

  my $dryrun = 0;
  
  print_html_start(0,'saida','h');

  ### Checks:  
  # Check assignment:
  (!$assign) and abort($uid,'',"Selecione um trabalho.");

  # Check if the user is in the assignment:
  passf_in_assign($uid,$upassf,$assign);

  # Configs:
  my %cfg = load_configs($assign,$uid,$utype,$upassf);

  my $days = (exists($cfg{deadline}) ? elapsed_days($cfg{deadline}) : 0);

  # Check language:
  ($language) or abort($uid,$assign,'Selecione uma linguagem.');

  # Check assignment state:
  my %ast  = %{ $session->param('assign_states') };

  my $state = assignment_state(\%cfg);
  if ($ast{$assign} != $state) {
    $ast{$assign} = $state;
    $session->param('screen',undef);
  }
  
  if ($utype eq 'aluno') {
    if ($state == 5 || $state == 15) {
      $dryrun = 1;
    }
    elsif ($state == 6) {
      abort($uid,$assign,"O prazo para enviar $assign terminou.");
    }
    elsif ($state == 1) {
      block_user($uid,$upassf,"submit : $assign tem erros de configura��o.");
    }
    elsif ($state == 2) {
      block_user($uid,$upassf,"submit : o prazo para enviar $assign n�o come�ou.");
    }
  }

  my %langs = ('C'=>0,'PDF'=>0,'Fortran'=>0,'C++'=>0,'Pascal'=>0,
	       'Python3'=>0,'Java'=>0,'Octave'=>0);
  
  (exists($langs{$language})) or
    block_user($uid,$upassf,"submit : n�o h� linguagem $language.");

  if ($utype ne 'prof' and ! grep(/$language/,split(/\s+/,$cfg{languages}))) {
    block_user($uid,$upassf,"submit : $assign n�o pode ser enviado em $language.");
  }
 
  # Check the number of files to be uploaded and their names: 
  my %exts = ('C'=>'(c|h)','C++'=>'(cpp|h)','Fortran'=>'(f|F)','Pascal'=>'pas',
	      'Python3'=>'py','Java'=>'java','Octave'=>'m','PDF'=>'pdf');

  @uploads = grep(/\S+/,@uploads);
  my @sources = grep(/\.$exts{$language}$/ && /^[0-9a-zA-Z\_\.\-]+$/,@uploads);  
  
  # Octave, Fortran and Pascal are limited to a single source file:
  if ($language eq 'Octave' || $language eq 'Fortran' || $language eq 'Pascal') {
    ($cfg{files} = '1,1');
  }

  # A Main.java is required for Java:
  if ($language eq 'Java') {
    if (!exists($cfg{filenames})) {
      $cfg{filenames} = "Main.java";
    }
    else {
      if (" $cfg{filenames} " !~ / Main.java /) {
	$cfg{filenames} .= " Main.java";
      }
    }
  }

  # A main.py is required for python if there is more than one source file:
  if ($language eq 'Python3' && @sources > 1) {
    if (!exists($cfg{filenames})) {
      $cfg{filenames} = "main.py";
    }
    else {
      if (" $cfg{filenames} " !~ / main.py /) {
	$cfg{filenames} .= " main.py";
      }
    }
  }

  my $mess = '';
  my %names = ();
  my @nf = split(/,/,$cfg{files});
  my @reqfiles;

  if (exists($cfg{filenames})) {
    @reqfiles = split(/ +/,$cfg{filenames});
    
    for (my $i=0; $i<@reqfiles; $i++) {
      $reqfiles[$i] =~ s/\{uid\}/$uid/;
      $reqfiles[$i] =~ s/\{assign\}/$assign/;
      $names{$reqfiles[$i]} = 1;
    }
    
    for (my $i=0; $i<@sources; $i++) {
      delete($names{$sources[$i]});
    }

    (@reqfiles > $nf[0]) and ($nf[0] = scalar @reqfiles);
    (@reqfiles > $nf[1]) and ($nf[1] = scalar @reqfiles);
  }


  if (@sources < $nf[0] || @sources > $nf[1]) {
    $mess = 'Envie ' .
      ($nf[0]==$nf[1] ?
       ($nf[0]==1 ? "1 arquivo." : "$nf[1] arquivos.") :
       "de $nf[0] a $nf[1] arquivos.") . '<p>';
  }

  if (keys(%names) > 0) {
    $mess = "Envie arquivos com nomes: @reqfiles.<p>";
  }

  if ($mess) {
    print $mess, 'Veja detalhes sobre os nomes de arquivos v�lidos nesta ',
	  "<a href=\"javascript:;\" onclick=\"wrap('hlp','envio')\">p�gina</a>.";
    abort($uid,$assign,"N�mero ou nomes de arquivos incorretos",1);
  }


  # Get the number of previous submissions from an existing dry-run or report file:
  my $tryed = 0;
  my $tryed_at = undef;
  
  my $dryf = "$assign/$uid/$uid.dryrun.rep";
  if (-e $dryf) {
    my %rep = load_rep_data($dryf);
    $tryed = $rep{tries};
    $tryed_at = $rep{at};
  }
  else {
    my $repf = "$assign/$uid/$uid.rep";
    if (-e $repf) {
      my %rep = load_rep_data($repf);
      $tryed = $rep{tries};
      $tryed_at = $rep{at};
    }
  }
  
  my $try = $tryed+1;

  # Check the maximum number of submissions:
  ($dryrun) and ($cfg{tries} += 10);
  ($utype eq 'aluno' && $tryed >= $cfg{tries}) and 
    abort($uid,$assign,"Voc� n�o pode enviar $assign mais uma vez.");


  ### Create a temp directory:
  my $userd = "$assign/_${uid}_tmp_";
  mkdir($userd) or abort($uid,$assign,"submit : mkdir $userd : $!");
  
  my $now = format_epoch(time);

  ### Report header:
  my $rep = '';
  my $reph = "<b>Usu�rio: $uid</b>";
  $reph .= '<br><b>Trabalho: ' .
    "<a href=\"javascript:;\" onclick=\"wrap('stm','$assign');\">$assign</a></b>";

  if (exists($cfg{deadline})) {
    $reph .= "<p>Data limite para envio: " . br_date($cfg{deadline});
    ($days*$cfg{penalty} >= 100) and ($reph .= ' (encerrado)');
    ($cfg{penalty} < 100) and ($reph .= "<br>Penalidade por dia de atraso: $cfg{penalty}%");
  }

  $reph .= "<p>Este envio: ${try}&ordm;, " . br_date($now);
  if ($utype eq 'aluno') {
    if ($dryrun) {
      $reph .= '<br><font color="MediumBlue">O prazo para enviar terminou. ' .
	'Este envio n�o substitui o �ltimo envio no prazo.</font>';
    }
  }
  else {
    $reph .= "<br>$uid: envio sem restri��o de prazo ou de quantidade.";
  }
  
  $reph .= "<br>Linguagem: $language";
  $reph .= (@sources == 1 ? "<br>Arquivo: " : "<br>Arquivos: ");

  ### Get uploaded source files and pdfs:
  @sources = ();
  @pdfs = ();
  my @fh = upload('source');

  for (my $i=0; $i<@fh; $i++) {
    (!$uploads[$i]) and next;
    ($uploads[$i] !~ /\.$exts{$language}$/ || $uploads[$i] !~ /^[a-zA-Z0-9_\.\-]+$/) and next;

    open(my $SOURCE,'>',"$userd/$uploads[$i]") or 
      abort($uid,$assign,"submit : open $userd/$uploads[$i] : $!");

    binmode $SOURCE;
    my $fh = $fh[$i];

    if ($uploads[$i] =~ /\.pdf$/) {
      while (<$fh>){
	print $SOURCE $_;
      }
      push(@pdfs,$uploads[$i]);
    }
    else {
      while (<$fh>) {
	s/\x1A//g; # ^Z
	s/\x0D//g; # ^M
	print $SOURCE $_;
      }
      push(@sources,$uploads[$i]);
    }

    close($fh[$i]);
    close($SOURCE);
  }

  @sources = sort { $a cmp $b } @sources;  

  ### Insert links for sources and documents:
  for (my $i=0; $i<@sources; $i++) {
    $reph .= '<a href="javascript:;" ' . 
      "onclick=\"toggleDiv('$sources[$i]');\">$sources[$i]</a>&nbsp;";
  }
  for (my $i=0; $i<@pdfs; $i++) {
    $reph .= '<a href="javascript:;" ' . 
      "onclick=\"wrap('dwn','$assign','$uid','$pdfs[$i]');\">$pdfs[$i]</a>&nbsp; ";
  }

  $reph .= '<script type="text/javascript" ' .
    'src="google-code-prettify/run_prettify.js?61"></script>';
  
  ### Insert source files:
  for (my $i=0; $i<@sources; $i++) {
    $reph .= "<div id='$sources[$i]' style='display:none' class='src'>" . 
      "<b>$sources[$i]</b>&nbsp;&nbsp;" .
      "<a href=\"javascript:;\" " .
      "onclick=\"wrap('dwn','$assign','$uid','$sources[$i]')\">download</a>";
    #$reph .= "<style> .prettyprint ol.linenums > li { list-style-type: decimal; } </style>";
    
    my $source = "$userd/$sources[$i]";
    if ($sources[$i] =~ /\.c$/ || $sources[$i] =~ /\.h$/) {
      #$reph .= "<pre class='prettyprint linenums lang-c' id='C_lang'>";
      $reph .= "<pre class='prettyprint lang-c' id='C_lang'>";
      if (-x "$cfg{indent}") {
	system("$cfg{indent} -kr $source -o $source.indent 2>/dev/null");
	$reph .= load_file($uid,$assign,"$source.indent",1);
      }
      else {
	$reph .= load_file($uid,$assign,$source,1);
      }
    }
    else {
      #$reph .= "<pre class='prettyprint linenums'>";
      $reph .= "<pre class='prettyprint'>";
      $reph .= load_file($uid,$assign,$source,1);
    }
    
    $reph .= "</pre></div>"; 
  }

  my $grade = 0;
  my @test_cases = ();
  
  ### If this is a PDF statement, there is nothing else to do:
  if ($language eq 'PDF') {
    if ($utype eq 'aluno' && exists($cfg{deadline}) && $days > 0) {
      $rep .= "<p><b>Recebido com atraso de $days " . ($days>1 ? "dias" : "dia") . ".</b>";
      $grade = "recebido +$days";
    }
    else {
      $rep .= "<p><b>Recebido.</b>";
      $grade = 'recebido';
    }
  }
  else {
    # Load test-case names early to produce correct error messages:
    opendir(my $DIR,"$assign") or abort($uid,$assign,"submit : opendir $assign : $!");
    @test_cases = sort(grep {/\.in$/ && -f "$assign/$_"} readdir($DIR));
    close($DIR);

    my $ncases = @test_cases;
    for (my $i=0; $i<$ncases; $i++) {
      $test_cases[$i] =~ s/\.in$//;
    }

    # Compile:
    if ($language ne 'Octave' && $language ne 'Python3') {
      $rep .= "\n<p><b>Compila��o:</b>&nbsp;";
    }
    
    # Copy files from directory include if one exists:
    my @included = ();
    if (-d "$assign/include") {
      @included = glob("$assign/include/*");
      for my $file (@included) {
	copy($file, $userd) or abort($uid,$assign,"submit : copy : $!");
      }
    }

    # Setup compilation by language:
    my $compcmd;
    my $srcname = 'elf';
    
    if ($language eq 'C') {
      (-x $cfg{gcc}) or abort($uid,$assign,"submit : gcc $cfg{gcc} inv�lido");
      (exists($cfg{'gcc-args'})) or ($cfg{'gcc-args'} = '');
      
      open(my $MAKE,'>',"$userd/Makefile") or abort($uid,$assign,"submit : write Makefile : $!");
      print $MAKE "CC = $cfg{gcc}\n",
	"CFLAGS = $cfg{'gcc-args'}\n",
	"SRC = \$(wildcard *.c)\n",
	"elf: \$(SRC:%.c=%.o)\n",
	"\t\$(CC) \$(CFLAGS) -o \$@ \$^ $cfg{'gcc-ld-args'}\n";
      close($MAKE);    
      $compcmd = "$cfg{'make'}";
    }

    elsif ($language eq 'Python3') {
      if (@sources == 1) {
	$srcname = $sources[0];
      }
      else {
	$cmd = "cd $userd; $cfg{tar} -cf elf.tar *.py";
	system($cmd);
	my $status = ($? >> 8) & 0x00FF;
	($status) and abort($uid,undef,"submit : system $cmd ($status) : $!");
	$srcname = 'elf.tar';
      }
    }

    elsif ($language eq 'Octave') {
      $srcname = $sources[0];
    }
    
    elsif ($language eq 'Java') {
      (-x "$cfg{jdk}/javac") or abort($uid,$assign,"submit : javac $cfg{jdk}/javac inv�lido");
      (-x "$cfg{jdk}/jar") or abort($uid,$assign,"submit : $cfg{jdk}/jar inv�lido");
      (exists($cfg{'javac-args'})) or ($cfg{'javac-args'} = '');

      open(my $MF,'>',"$userd/manifest.txt") or	abort($uid,$assign,"submit : write manifest: $!");
      print $MF "Main-Class: Main\n";
      close($MF);

      open(my $MAKE,'>',"$userd/Makefile") or abort($uid,$assign,"submit : write Makefile: $!");
      print $MAKE "elf: \n", 
	"\t$cfg{'jdk'}/javac $cfg{'javac-args'} *.java; ",
	"$cfg{'jdk'}/jar cvfm elf.jar manifest.txt *.class\n";
      close($MAKE);
      $compcmd = "$cfg{'make'}";
      $srcname = 'elf.jar';
    }
    
    elsif ($language eq 'C++') {
      (-x $cfg{'g++'}) or abort($uid,$assign,"submit : g++ $cfg{'g++'} inv�lido");
      (exists($cfg{'g++-args'})) or ($cfg{'g++-args'} = '');

      open(my $MAKE,'>',"$userd/Makefile") or abort($uid,$assign,"submit : write Makefile: $!");
      print $MAKE "CC = $cfg{'g++'}\n",
	"CFLAGS = $cfg{'g++-args'}\n",
	"SRC = \$(wildcard *.cpp)\n",
	"elf: \$(SRC:%.cpp=%.o)\n",
	"\t\$(CC) \$(CFLAGS) -o \$@ \$^ $cfg{'g++-ld-args'}\n";
      close($MAKE);
      $compcmd = "$cfg{'make'}";
    }
    
    elsif ($language eq 'Fortran') {
      (-x $cfg{gfortran}) or abort($uid,$assign,"submit : gfortran $cfg{gfortran} inv�lido");
      (exists($cfg{'gfortran-args'})) or ($cfg{'gfortran-args'} = '');
      $compcmd = "$cfg{gfortran} $cfg{'gfortran-args'} $sources[0] -o elf";
    }
    
    elsif ($language eq 'Pascal') {
      (-x $cfg{gpc}) or abort($uid,$assign,"submit : gpc $cfg{gpc} inv�lido");
      (exists($cfg{'gpc-args'})) or ($cfg{'gpc-args'} = '');
      $compcmd = "$cfg{gpc} $cfg{'gpc-args'} --executable-file-name=elf --automake $sources[0]";
    }

    # Compile:
    my $status;
    if ($language ne 'Octave' && $language ne 'Python3') {
      $status = system("cd $userd; $compcmd 1>out 2>err");
    }
    else {
      $status = 0;
    }

    my $elff = "$userd/elf";
    my $outf = "$userd/out";
    my $errf = "$userd/err";

    if ($status) {
      $rep .= 'com erros.<br><div class="io">'; 
      $rep .= load_file($uid,$assign,$outf,1);
      $rep .= load_file($uid,$assign,$errf,1,2500);
      $rep .= '</div>';
      
      if ($ncases == 0) {
	if ($utype eq 'aluno' && exists($cfg{deadline}) && !$dryrun && $days > 0) {
	  $rep .= "<p><b>Recebido com atraso de $days " . ($days>1 ? "dias" : "dia") . ".</b><br>";
	  $grade = "recebido +$days";
	}
	else {
	  $rep .= '<p><b>Recebido.</b><br>';
	  $grade = 'recebido';
	}
      }
      else {
	$rep .= '<p><b>Acerto:</b> 0%';
	$grade = 0;
      }
    }
    else {
      if (-s $errf) {
	$rep .= 'com warnings <div class="io">'; 
	$rep .= load_file($uid,$assign,$outf,1);
	$rep .= load_file($uid,$assign,$errf,1,2500);
	$rep .= '</div>';
      }
      else {
	if ($language ne 'Octave' && $language ne 'Python3') {
	  $rep .= 'bem sucedida.';
	}
      }

      # No test cases:
      if ($ncases == 0) {
	$rep .= '<p><b>Nenhum caso-de-teste.</b><br>';

	if ($utype eq 'aluno' && exists($cfg{deadline}) && !$dryrun && $days > 0) {
	  $rep .= "<b>Recebido com atraso de $days " . ($days>1 ? "dias" : "dia") . ".</b><br>";
	  $grade = "recebido +$days";
	}
	else {
	  $rep .= '<b>Recebido.</b><br>';
	  $grade = 'recebido';
	}
      }

      # Dispatch test cases execution:
      else {

	$rep .= "\n<p><b>Execu��o dos casos-de-teste:</b><p>";

	# Per test case limits:
	my $lim = '';
	if (exists($cfg{limits})) {
	  my @c = split(/ +/,$cfg{limits});
	  for ($i=0; $i<@c; $i++) {
	    my %h = ();
	    $h{t} = $cfg{cputime};
	    $h{v} = $cfg{virtmem};
	    $h{s} = $cfg{stkmem};

	    my @l = split(/:/,$c[$i]);
	    
	    for ($j=1; $j<@l; $j++) {
	      my ($k,$v) = split(/=/,$l[$j]);
	      $h{$k} = $v;
	    }

	    $lim .= "$l[0] $h{t} $h{v} $h{s} ";
	  }
	}
	
	my $cmd = "./sqtpm-etc.sh $uid $assign $language $srcname " .
	  " $cfg{cputime} $cfg{virtmem} $cfg{stkmem} $lim >/dev/null 2>&1";

	system($cmd);
	
	my $status = ($? >> 8) & 0x00FF;
	($status) and abort($uid,$assign,"submit : system $cmd ($status) : $!");

	# Adjust verifier path:
	(exists $cfg{verifier}) and ($cfg{verifier} =~ s/\@/$assign\//);

	# Process every test case result:
	my %failed = ();
	my $passed = 0;
	my $casei = 1;

	for my $case (@test_cases) {
	  my $case_in = "$assign/$case.in";
	  my $case_out = "$assign/$case.out";
	  my $exec_st = "$userd/$case.run.st";
	  my $exec_out = "$userd/$case.run.out";
	  my $exec_err = "$userd/$case.run.err";

	  (!-r $case_in) and abort($uid,$assign,"submit : sem permiss�o $case_in.");
	  (-s $exec_st && !-r $exec_st) and abort($uid,$assign,"submit : sem permiss�o $exec_st.");
	  (!-r $exec_out) and abort($uid,$assign,"submit : sem permiss�o $exec_out.");

	  $failed{$case} = $casei;
	  my $status = 9;
	  
	  if (open(my $STATUS,'<',"$exec_st")) {
	    $status = <$STATUS>;
	    chomp($status);
	    $status -= 128;
	    close($STATUS);
	  }

	  $rep .= sprintf("%.02d: &nbsp;",$casei);

	  if ($status == 11) {
	    $rep .= 'viola��o de mem�ria.<br>';
	  }
	  elsif ($status == 9) {
	    $rep .= 'limite de tempo ou mem�ria excedido.<br>';
	  }
	  elsif ($status == 24) {
	    $rep .= 'limite de tempo excedido.<br>';
	  }
	  elsif ($status == 8) {
	    $rep .= 'erro de ponto flutuante.<br>';
	  }
	  elsif ($status > 0 || -s $exec_err) {
	    (-s $exec_err && !-r $exec_err) and
	      abort($uid,$assign,"submit : sem permiss�o $exec_err.");
	    $rep .= "erro de execu��o ($status).<br>";
	    (-s $exec_err) and ($rep .= '<div class="io">' .
				load_file($uid,$assign,$exec_err,0,1000) . '</div>');
	  }
	  else {
	    if (exists($cfg{verifier})) {
	      my $cmd = "$cfg{verifier} $case_in $exec_out $case_out >/dev/null 2>&1";
	      system($cmd);
	      $status = ($? >> 8) & 0x00FF;

	      if ($status == 0) {
		$rep .= 'bem sucedido.<br>';
		$failed{$case} = 0;
		$passed++;
	      }
	      elsif ($status == 1) {
		$rep .= 'sa�da incorreta.<br>';
	      }
	      elsif ($status == 2) {
		$rep .= 'sa�da com formata��o incorreta.<br>';
	      }
	      else {
		abort($uid,$assign,"submit : Erro ao executar o verificador $cmd.");
	      }
	    }
	    else {
	      (!-r $case_out) and abort($uid,$assign,"submit : sem permiss�o $case_out.");

	      system("$cfg{diff} -q $case_out $exec_out >/dev/null 2>&1");
	      $status = ($? >> 8) & 0x00FF;

	      if ($status == 0) {
		$rep .= 'sa�da correta.<br>';
		$failed{$case} = 0;
		$passed++;
	      }
	      elsif ($status == 1) {
	        write_lc_file($uid,$assign,$case_out,-s $case_out);
		write_lc_file($uid,$assign,$exec_out,-s "$case_out.lc");
		
		system("$cfg{diff} -q $case_out.lc $exec_out.lc >/dev/null 2>&1");
		$status = ($? >> 8) & 0x00FF;
		
		if ($status == 0) {
		  $rep .= 'sa�da com formata��o incorreta.<br>';
		}
		elsif ($status == 1) {
		  $rep .= 'sa�da incorreta.<br>';
		}
		else {
		  abort($uid,$assign,"submit : erro ao executar diff $case_out.lc $exec_out.lc.");
	        }
	      }
	      else {
		abort($uid,$assign,"submit : erro ao executar diff $case_out $exec_out.");
	      }
	    }
	  }
	  $casei++;
	}
	
	$rep .= "<br>N�mero de casos-de-teste: $ncases." .
	        "<br>Casos-de-teste bem sucedidos: $passed.";

	my $full_grade ;
	if ($cfg{'grading'} eq 'total') {
	  $full_grade = ($passed == $ncases ? 100 : 0);
	}
	else {
	  $full_grade = $passed/$ncases*100;
	}
	
	$grade = $full_grade;
	
	my $discount = 0;
	if ($utype eq 'aluno' && exists($cfg{deadline}) && $grade > 0 && !$dryrun) {
	  $discount = $days * $cfg{penalty} / 100;
	  ($discount > 0) and ($grade = $full_grade * (1 - $discount));
	  ($grade < 0) and ($grade = 0);
	}
	
	$rep .= '<br><b>Acerto:</b> ' . sprintf("%.0f%%", $grade);
	
	if ($discount > 0 && $full_grade > 0) {
	  $rep .= sprintf(" (desconto de %.0f%% sobre %.0f%% por atraso desde %s.)", 
			  100*$discount, $full_grade, br_date($cfg{deadline}));
	}
	$rep .= '<br>';

	# Show the cases that failed and are supposed to be shown:
	if (exists($cfg{showcases})) {
	  my @show = split(/\s+/,$cfg{showcases});

	  for (my $i=0; $i<@show; $i++) {
	    if ($failed{$show[$i]}) {
	      $rep .= sprintf("<br><b>Execu��o do caso %.02d:</b>",$failed{$show[$i]});

	      $rep .= '<p>Entrada:<br><div class="io">';
	      $rep .= load_file($uid,$assign,"$assign/$show[$i].in",0);
	      $rep =~ s/\n$/\n\n/;
	      $rep .= '</div>';

	      if (!exists($cfg{verifier})) {
		$rep .= '<p>Sa�da esperada:<br><div class="io">';
		$rep .= load_file($uid,$assign,"$assign/$show[$i].out",0);
		$rep =~ s/\n$/\n\n/;
		$rep .= '</div>';
	      }

	      if (-s "$userd/$show[$i].run.out" == 0) {
		$rep .= '<p>Sa�da produzida: n�o houve<hr>';
	      }
	      else {
		$rep .= '<p>Sa�da produzida:<br><div class="io">';
		
		if (-f "$userd/$show[$i].run.out") {
		  my $size = (-f "$assign/$show[$i].out") ?
		    int((-s "$assign/$show[$i].out") * 1.2) : 1024;
		  $rep .= load_file($uid,$assign,"$userd/$show[$i].run.out",0,$size);
		  $rep =~ s/\n$/\n\n/;
		}
		$rep .= '</div><hr>';
	      }
	    }
	  }
	}
      }
    }

    $grade = sprintf("%.0f%%",$grade);

    ### Clean-up:
    (-e $elff) and unlink($elff);  
    (-e $outf) and unlink($outf);
    (-e $errf) and unlink($errf);
    
    if (@included) {
      for my $file (@included) {
	unlink("$userd/" . basename($file));
      }
    }
    
    if ($language eq 'Java') {
      unlink(glob "$userd/*.class");
    }
    elsif ($language eq 'Python3') {
      unlink("$userd/elf.tar");
    }
    else {
      unlink(glob "$userd/*.o");
    }
    
    for my $case (@test_cases) {
      (-e "$userd/$case.run.st")  and unlink("$userd/$case.run.st");
      (-e "$userd/$case.run.out") and unlink("$userd/$case.run.out");
      (-e "$userd/$case.run.out.lc") and unlink("$userd/$case.run.out.lc");
      (-e "$userd/$case.run.err") and unlink("$userd/$case.run.err");
    }
  }
  
  ### Add data to ease parsing the report later:
  my $reptag = "<!--lang:$language-->\n<!--grade:$grade-->\n<!--tries:$try-->\n<!--at:$now-->\n";
  
  if ($rep !~ /<hr>$/) {
    $rep .= '<hr>';
  }

  ### Remove grades report to force future update, if any:
  my $tabfile = "$assign/$upassf";
  $tabfile =~ s/\.pass$/.grades/;
  (-f $tabfile) and unlink($tabfile);

  ### If backup is on but the directory doesn't exist, create it:
  my $backupd = "$assign/backup";
  if ($cfg{backup} eq 'on' && !-d $backupd) {
    (-e $backupd) and abort($uid,$assign,"submit : $backupd is not a directory.");
    mkdir($backupd) or abort($uid,$assign,"submit : mkdir $backupd : $!");
  }

  ### Save report:
  my $repf = "$userd/$uid.rep";
  open(my $REPORT,'>',$repf) or abort($uid,$assign,"submit : open $repf : $!");
  print $REPORT "$reptag $reph $rep";
  close($REPORT);

  ### Backup:
  $prevd = "$assign/$uid";
  
  if ($utype ne 'aluno' || ($utype eq 'aluno' && !$dryrun)) {
    # Backup or remove the previous submission:
    if (-d $prevd) {
      if ($cfg{backup} eq 'on') {
	$tryed_at =~ s/[:\/]//g;
	$tryed_at =~ s/ /-/g;
	rename($prevd,"$backupd/$uid.$tryed.$tryed_at") or 
	  abort($uid,$assign,"submit : mv prev $prevd $backupd/$uid.$tryed.$tryed_at : $!");
      }
      else {
	unlink(glob "$prevd/*");
	rmdir($prevd);
      }
    }

    # Rename the current submission:
    rename($userd,$prevd) or abort($uid,$assign,"submit $tryed : mv curr $userd $prevd : $!");

    add_to_log($uid,$assign,"$try $grade");
  }  
  else {
    # Dry-run. The previous submission will prevail, save dryrun.rep in it:
    if (!-d $prevd) {
      mkdir($prevd) or abort($uid,$assign,"submit dry-run : mkdir $prevd : $!");
    }
    
    my $repf = "$prevd/$uid.dryrun.rep";
    open(my $REPORT,'>',$repf) or abort($uid,$assign,"submit : open $repf : $!");
    print $REPORT "$reptag $reph $rep";
    close($REPORT);
    
    # Move the current submission to backup or remove it: 
    if ($cfg{backup} eq 'on') {
      $now =~ s/[:\/]//g;
      $now =~ s/ /-/g;
      rename("$userd","$backupd/$uid.$try.$now.dry") or
	abort($uid,$assign,"submit : mv backup $userd $backupd/$uid.$try.$now.dry : $!");
    }
    else {
      unlink(glob "$userd/*");
      rmdir("$userd");
    }
    
    add_to_log($uid,$assign,"$try $grade dry-run");
  }

  ### Output to browser:
  print $reph;

  if ($utype eq 'aluno') {
    if ($ast{$assign} >= 10) {
      print '<br><b>Recebido.</b><hr>';
      $grade = 'recebido';
    }
    else {
      print $rep;
    }
  }
  else {
    print $rep;
  }
  
  print end_html();
  
  ### Update home screen:
  if ($utype ne 'prof' && !$dryrun) {
    my $scr = $session->param('screen');

    if (defined $scr) {
      my $i = index($scr,">$assign<");
      $i += index(substr($scr,$i),'<td>') + 3;
      $i += index(substr($scr,$i),'<td>') + 3;
      $i += index(substr($scr,$i),'<td ');
      
      my $j = index(substr($scr,$i),'<tr ');
      ($j == -1) and ($j = index(substr($scr,$i),'</table>'));
      $j += $i;
      
      $session->param('screen', substr($scr,0,$i) .
		      "<td class=\"grid\"><a href=\"javascript:;\"" .
		      " onclick=\"wrap('rep','$assign','$uid');\">$grade</a></td>" .
		      substr($scr,$j));
    }
  }
}



################################################################################
sub invoke_moss {

  my $uid = shift;
  my $utype = shift;
  my $upassf = shift;
  my $assign = shift;
  my $lang = shift;

  print_html_start();

  # Check user type:
  ($utype ne 'prof') and block_user($uid,$upassf,"invoke_moss: $uid n�o � prof.");

  # Load cfg, adjust language:
  (!%sys_cfg) and (%sys_cfg = load_keys_values('sqtpm.cfg'));

  $lang = lc($lang);
  $lang =~ s/c\+\+/cc/;
  $lang =~ s/python3/python/;
  $lang =~ s/octave/matlab/;

  # Get a list of sources:
  $gregex = '';  # $gregex is used by wanted_moss.

  if ($lang eq 'c') { $gregex = qr/(\.c$)|(\.h$)/; }
  elsif ($lang eq 'cc') { $gregex = qr/(\.cpp$)|(\.h$)/; }
  elsif ($lang eq 'python') { $gregex = qr/.py$/; }
  elsif ($lang eq 'java') { $gregex = qr/.java$/; }
  elsif ($lang eq 'matlab') { $gregex = qr/.m$/; }
    
  @gsources = ();  # @gsources is modified by wanted_moss.
  find(\&wanted_moss,"./$assign");
  (@gsources < 2) and abort($uid,$assign,"Deve haver pelo menos dois envios para comparar.");

  my $url = '';

  my $runf = "$assign/moss.$lang.run";
  my $errf = "$assign/moss.$lang.err";
  my $lockf = "$assign/moss.$lang.lock";
  
  if (-f $runf) {
    # Check whether last moss run is up or there is a newer source:
    open(my $MOSS,'<',$runf) or abort($uid,$assign,"moss : open $runf : $!");
    my @out = <$MOSS>;
    close($MOSS);
    
    my $k = $#out;
    do {
      $url = $out[$k--];
    } while ($k>=0 && $url !~ /^http\:\/\/moss\.stanford\.edu\/results/);

    if ($k >= 0 && LWP::Simple::head($url)) {
      my $age = (stat $runf)[9];
      for (my $i=0; $i<@gsources; $i++) {
	if ($age < (stat $gsources[$i])[9]) {
	  $url = '';
	  last;
	}
      }
    }
    else {
      $url = '';
    }
  }

  if ($url eq '') {
    # Run Moss:
    my $LOCK;
    open($LOCK,'>',$lockf) or abort($uid,$assign,"moss : open $lockf : $!");
    flock($LOCK,LOCK_EX|LOCK_NB) or abort($uid,$assign,"Comparando $assign, aguarde.");
        
    my $cmd = "perl moss-sqtpm $sys_cfg{'moss-id'} -l $lang -m $sys_cfg{'moss-m'} " .
      "-d @gsources 1>$runf 2>$errf";

    system($cmd);
    my $st = ($? >> 8) & 0x00FF;

    flock($LOCK,LOCK_UN);
    close($LOCK);
    # $lockf is intentionally left there.

    if ($st) {
      $st = $!;
      (-s $errf) and ($st = load_file($uid,$assign,$errf) . " : $st");
      abort($uid,$assign,"moss : $st");
    }
    
    open(my $MOSS,'<',$runf) or abort($uid,$assign,"moss : open $runf : $!");
    my @out = <$MOSS>;
    close($MOSS);
    $url = $out[-1];

    if ($url !~ /^http:/) {
      unlink($runf);
      abort($uid,$assign,"A execu��o do Moss falhou.");
    }
  }
  
  # Redirect:
  print "<meta http-equiv='refresh' content='0; url=$url'>";
  print_html_end();
}



################################################################################
# A wanted function to find sources for moss.  It add files that match
# $gregex to @gsources, both from an outer scope.

sub wanted_moss {
  -f && 
  !($File::Find::name =~ /\/backup\//) && 
  /$gregex/ && 
  (push(@gsources,"$File::Find::name"));
}



################################################################################
# A wanted function to collect data for the histogram.
# Each report file for a user in %gusers is visited and
# (date, grade, user) are pushed into @ggrades.

sub wanted_hist {
  
  /\.rep$/ && !/.dryrun.rep$/ && do {
    my $file = $_;
    /^(\w+)\./;

    (!$1 || (!exists($gusers{$1}) && !exists($gusers{"*$1"}))) and return;

    my %rep = load_rep_data($file);

    (!exists($rep{at})) and abort("","","wanted_list : $file");
    
    ($st && $rep{at} lt $st) and return;
    ($dl && $rep{at} gt $dl) and return;
    
    push(@ggrades,(split(/ /,$rep{at}))[0]);
    push(@ggrades,$rep{grade});
    push(@ggrades,$1);
  };

  return;
}



################################################################################
# print_html_start($first-login, $help, $back-link)
#
# first-login: 1 if the session is starting, 0 if it existed already.
# help: the help html file.
# back-link: 'x' is exit, 'h' is forced back to sqtpm.cgi, 'b' or anything else is back.

sub print_html_start {

  my $first_login = shift;
  my $help = shift;
  my $back = shift;

  (!defined($back)) and ($back = '');

  if ($first_login) {
    print header(-cookie=>$cgi->cookie(CGISESSID => $session->id));
  }
  else {
    print header();
  }

  print start_html(-title => 'sqtpm', 
		   -style => {-src=>['sqtpm.css','google-code-prettify/prettify.css']},
		   -meta => {charset=>'UTF-8'},
		   -head => [Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);
  
  # print '<div id="wrapper"><div id="sidebar"><h1>sqtpm</h1>';
  print '<div id="sidebar"><h1>sqtpm</h1>';
  print '<p style="margin-top:-15px"><small>[',substr($session->param('uid'),0,13),']</small></p>';
  ($help) and print "<a href=\"javascript:;\" onclick=\"wrap('hlp','$help')\">ajuda</a><br>";
  
  if ($back eq "x") {
    print '<a href="javascript:;" onclick="wrap(\'out\');">sair</a>';
  }
  elsif ($back eq "h") {
    print '<a href="sqtpm.cgi">voltar</a>';
  }
  else { # 'b'
    print '<a href="javascript:;" onclick="window.history.go(-1); return false;">voltar</a>';
  }    
  
  print '</div><div class="content">';
  
  # There will always be a form named sqtpm with hidden fields to handle actions through wrap():
  print '<form method="post" action="sqtpm.cgi" enctype="multipart/form-data" name="sqtpm">',
    '<script type="text/javascript" src="sqtpm.js"></script>',
    '<input type="hidden" name="action">',
    '<input type="hidden" name="arg1">', 
    '<input type="hidden" name="arg2">',
    '<input type="hidden" name="arg3">';
}



################################################################################
# print_html_end()

sub print_html_end {

  print '</form></div></div>';
  print end_html();
}



################################################################################
# print_html_file($path, $file)
#
# Print an html file to stdout, encoding image files in base64 and printing them too.
# If an error occurs while opening a file then it invokes abort().

sub print_html_file {

  my $path = shift;
  my $file = shift;

  ($path) and ($path = "$path/");

  open(my $HTML,'<',"$path$file") or abort('','',"print_html_file : open $path$file : $!");

  while (<$HTML>) {
    /<img / && / src=\"([^\"]*)\"/ && do {
   
      my $fig = $1;
      my $type = (split(/\./,$fig))[-1];

      ($fig !~ /^\//) and ($fig = "$path$fig");

      open(my $FIG,'<',$fig) or abort('','',"print_html_file : open $fig : $!");
      binmode($FIG);
      my $image = do { local $/; <$FIG> };
      close($FIG);
      
      $enc = encode_base64($image);

      s{ src=\"([^\"]*)\"}{ src=\"data:image/${type};base64,${enc}\"};
    };

    print $_;
  }

  close($HTML);
}



################################################################################
# abort_login($uid, $message)
#
# Print an html error page with message, write to log and exit.

sub abort_login {

  my $uid = shift;
  my $mess = shift;
  
  print header();
  print start_html(-title=>'sqtpm', 
		   -style=>{-src=>['sqtpm.css']},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);
  
  print '<div class="f85"><h1>sqtpm</h1>';
  print '<p>', $mess, '</p><hr><a href="sqtpm.cgi">sqtpm</a></div>';
  print end_html();
  add_to_log($uid,'',$mess);

  exit(1);
}



################################################################################
# int passf_in_assign($user, $pass_file, $assignment)
#
# Verify whether pass_file is linked to an assignment.
# Return 1 if it is or invoke block_user() on the user otherwise.

sub passf_in_assign {

  my $uid = shift;
  my $upassf = shift;
  my $assign = shift;

  (-d $assign && -e "$assign/$upassf") and (return 1);

  block_user($uid,$upassf,"check_assign: $upassf n�o est� em $assign.");
}



################################################################################
# block_user($user, $pass_file, $messsage)
#
# Block a user by commenting its line in the pass file, write message
# to the log and silently logout.

sub block_user {

  my $uid = shift;
  my $upassf = shift;
  my $mess = shift;

  my $PASS;
  open($PASS,'+<',$upassf) or abort($uid,,"block_user : open $upassf");

  my $lines = '';
  while (<$PASS>) {
    (/^([\*\@]?)$uid:?/) and ($_ = "# blocked! $_");
    $lines .= $_;
  }

  flock($PASS,LOCK_EX);
  seek($PASS,0,0);
  print $PASS $lines;
  flock($PASS,LOCK_UN);
  close($PASS);

  add_to_log($uid,$upassf,"$mess Bloqueado.");
  $session->delete();
  exit(0);
}



################################################################################
# assignment_state(\%config)
#
# Return the state of an assignment.
#
# undefined, error, closed -> open -> delayed -> dry-run -> finished
#     0        1      2        3         4          5          6

sub assignment_state {

  my $cfg = shift;
  my $state = 0;

  if (exists($cfg->{startup})) {
    my $days = elapsed_days($cfg->{startup});
    if (!defined($days)) {
      $state = 1; # config error
    }
    elsif ($days < 0) {
      $state = 2; # closed
    }
  }

  if ($state == 0 && exists($cfg->{'keep-open'}) &&
      !defined(elapsed_days($cfg->{'keep-open'}))) {
    $state = 1; # config error
  }
  
  if ($state == 0) {
    if (exists($cfg->{deadline})) {
      my $days = elapsed_days($cfg->{deadline});
            
      if (!defined($days)) {
	$state = 1; # config error
      }
      elsif ($days <= 0) {
	$state = 3; # open
      }
      elsif ($days*$cfg->{penalty} < 100) {
	$state = 4; # delayed
      }
      elsif (exists($cfg->{'keep-open'}) && elapsed_days($cfg->{'keep-open'}) <= 0 &&
	     $cfg->{languages} !~ /PDF/) {
	$state = 5; # dry-run;
      }
      else {
	$state = 6; # finished
      }   
    }
    else {
      $state = 3; # open
    }
  }
  
  if (exists($cfg->{'hide-grades'}) && $cfg->{'hide-grades'} eq 'on' &&
      $state >= 3 && $state <= 5) {
    $state += 10; 
  }

  return $state;
}



################################################################################
# hash load_configs($assign, $uid, $utype, $upassf, $dont_abort)
#
# Load system, assignment and group config files.
#
# If an error occurs at file opening then abort() will be invoked by
# load_keys_values(), but if dont_abort is true then () is returned.

sub load_configs {
  
  my $assign = shift;
  my $uid = shift;
  my $utype = shift;
  my $upassf = shift;
  my $dont_abort = shift;

  (!%sys_cfg) and (%sys_cfg = load_keys_values('sqtpm.cfg'));

  my (%cfga, %cfgg, %cfg);
  
  %cfga = load_keys_values("$assign/config",'=',$dont_abort);
  (!%cfga) and return ();
  %cfg = (%sys_cfg,%cfga);

  if ($utype eq 'aluno') {
    my $file = "$assign/config-" . $upassf =~ s/.pass$//r;
    if (-e $file) {
      %cfgg = load_keys_values($file,'=',$dont_abort);
      (!%cfgg) and return ();
      %cfg = (%cfg,%cfgg);
    }
    
    (exists($cfg{"startup-$uid"})) and ($cfg{startup} = $cfg{"startup-$uid"});
    (exists($cfg{"deadline-$uid"})) and ($cfg{deadline} = $cfg{"deadline-$uid"});
  }

  return %cfg;
}

