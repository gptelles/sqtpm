#!/usr/bin/perl -w
# This file is part of sqtpm 9.
# Copyright 2003-2021 Guilherme P. Telles.
# sqtpm is distributed under the terms of WTFPL v2.

use CGI qw(:standard -no_xhtml);
use CGI::Carp 'fatalsToBrowser';
use CGI::Session qw/-ip-match/;
use CGI::Session::Driver::file; 
$CGI::LIST_CONTEXT_WARN = 0; 

use LWP::Simple ();
use Cwd qw(cwd getcwd);
use Fcntl ':flock';
use File::Basename;
use File::Find;
use File::Copy;
use open ":encoding(Latin1)";
use MIME::Base64 qw(encode_base64);
use Time::Local;

use lib dirname(__FILE__);
use sqtpm;

$CGI::POST_MAX = 100000; # bytes

umask(0007);


# Globals:
my %sys_cfg = ();

my $cgi = CGI->new;
my $session = 0;

my $sprefix = getcwd();
$sprefix =~ s/^\///;
$sprefix =~ s/\//-/g;
$sprefix = "sqtpm-$sprefix";

my $sessiond = '/tmp';
$CGI::Session::Driver::file::FileName = $sprefix . '-%s';  

# Try to retrieve session id:
my $sid = $cgi->cookie('CGISESSID') || $cgi->param('CGISESSID') || undef;

# If the session id exists but the file don't then it must get a new session:
(defined($sid) && !-f "$sessiond/$sprefix-$sid") && (undef $sid);

my $action = param('action');

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
    ($pwd =~ /^\s*$/) && ($utype = '');  
    
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
      # Sleep for a while, so trying to break a password will take longer:
      sleep(2);
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
    abort_login('',"Erro ao recuperar a sessão: $!");
  
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
    invoke_moss($session->param('uid'),param('arg1'));
  }
  else {
    home(0);
  }
}

exit(0);



####################################################################################################
sub login_form {

  print header();
  print start_html(-title=>'sqtpm', 
		   -style=>{-src=>['sqtpm.css']},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'})]);

  print <<END;
<script type="text/javascript" src="sqtpm.js?61"></script>
<div class="f85">
<h1>sqtpm</h1>
<form method="post" action="sqtpm.cgi" enctype="multipart/form-data" name="sqtpm">
<table cellspacing="5" border="0">
<tr><td>usuário:</td><td>
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
<a href="javascript:;" onclick="about()">bula</a>
<noscript><p>Seu browser não tem javascript.  Boa sorte na próxima!</noscript>
</form>
<script type="text/javascript">document.sqtpm.uid.focus();</script>
</div>
END

  print end_html();
}



####################################################################################################
sub home {

  my $first_login = shift;

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');
  my $scr = $session->param('screen');

  print_html_start($first_login,'envio',0);
  
  if (!defined($scr)) {
    %sys_cfg = load_keys_values('sqtpm.cfg');
    
    # Grab assignments for the user:
    opendir(my $DIR,'.') || abort('','','home: opendir root: $!');
    my @assign = sort(grep {-d $_ && !/^\./ && -e "$_/config" && -l "$_/$upassf" && stat("$_/$upassf")} 
		      readdir($DIR));
    close($DIR);
    
    # Assignments table header:
    my $tab = '<b>Trabalhos:</b>';
    $tab .= '<p></p><table class="grid"><tr> <th class="grid">Enunciado</th>';
    ($utype eq 'P') && ($tab .= '<th class="grid">Grupos</th>');
    $tab .= '<th class="grid">Estado</th>';
    ($utype eq 'P') && ($tab .= '<th class="grid">Abertura</th>');    
    $tab .= '<th class="grid">Data limite</th>';
    ($utype eq 'S') && ($tab .= '<th class="grid">Último envio</th></tr>');
    ($utype eq 'P') && ($tab .= '<th class="grid">Moss</th></tr>');
    
    my %groups = ();

    # Assignments table rows:
    for (my $i=0; $i<@assign; $i++) {
      my %cfg = (%sys_cfg, load_keys_values("$assign[$i]/config"));

      # If this is a student and the assignment is still closed, skip it:
      ($utype eq 'S' && exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) && next;
      
      # Assignment tag:
      $tab .= '<tr align="center"><td class="grid">' .
	"<a href=\"javascript:;\" onclick=\"wrap('stm','$assign[$i]');\">$assign[$i]</a></td>";

      opendir($DIR,$assign[$i]) || abort($uid,$assign[$i],"home: opendir $assign[$i]: $!");
      my @group = sort(grep {/\.pass$/ && -l "$assign[$i]/$_" && stat("$assign[$i]/$_")} readdir($DIR));
      close($DIR);
      
      # Groups:
      if ($utype eq 'P') {
	$tab .= "<td class=\"grid\">";
	for (my $j=0; $j<@group; $j++) {
	  my $group = $group[$j];
	  $group =~ s/\.pass$//;
	  $tab .= '<a href="javascript:;" ' . 
	    "onclick=\"wrap('scr','$group','$assign[$i]');\">$group</a>&nbsp; ";
	  $groups{$group} = 1;
	}
	$tab .= '</td>';
      }

      # State:
      $tab .= "<td class=\"grid\">";
      if (exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) {
	$tab .= '<font color="Tomato">fechado</font>';
      }
      elsif (exists($cfg{deadline})) {
	my $days = elapsed_days($cfg{deadline});
	if ($days*$cfg{penalty} < 100) {
	  $tab .= '<font color="MediumBlue">aberto</font>';
	}
	elsif ($days <= $cfg{'keep-open'}) {
	  $tab .= '<font color="MediumBlue">encerrado</font>';
	}
	else {
	  $tab .= 'encerrado';
	}	  
      }
      else {
	$tab .= '<font color="MediumBlue">aberto</font>'
      }
      $tab .= '</td>';

      # Startup:
      if ($utype eq 'P') {
	$tab .= "<td class=\"grid\">";
	$tab .= (exists($cfg{startup}) ? dow($cfg{startup}) . " &nbsp;$cfg{startup}" : 'não há');
	$tab .= '</td>';
      }
      
      # Deadline:
      $tab .= "<td class=\"grid\">";
      $tab .= exists($cfg{deadline}) ? dow($cfg{deadline}) . " &nbsp;$cfg{deadline}" : 'não há ';
      $tab .= '</td>';

      if ($utype eq 'S') {
	# Last submisson grade:
	my %rep = load_rep_data("$assign[$i]/$uid/$uid.rep");
	
	if (exists($rep{grade})) {
	  $tab .= '<td class="grid"><a href="javascript:;" ' .
	    "onclick=\"wrap('rep','$assign[$i]');\">$rep{grade}</a>";
	}
	else {
	  $tab .= '<td class="grid">não houve';
	}
	$tab .= '</td>';
      }
      else {
	# Moss launcher:
	$tab .= '<td class="grid"><a href="javascript:;" ' . 
	  "onclick=\"wrap('moss','$assign[$i]');\">comparar</a></td>";
      }
    }
    $tab .= '</table>';

    # If there are no assignments, drop tab:
    if (@assign == 0) {
      $tab = "<p>Não há trabalhos para $uid.</p>";
    }

    # Links for grade tables:
    my @groups = sort keys(%groups);
    
    if ($utype eq 'P' && @groups) {
      $tab .= "<p><b>Tabelas de acertos:</b>";
      $tab .= '<br>&nbsp;&nbsp;';
      
      for (my $j=0; $j<@groups; $j++) {
      	$tab .= '<a href="javascript:;" ' .
	  "onclick=\"wrap('asc','$groups[$j]');\">$groups[$j]</a>&nbsp;";
      }
      $tab .= '';#'</p>';
    }

    $scr .= $tab;
    $session->param('screen',$scr);
  }

  print $scr;
  print_html_end();
}



####################################################################################################
sub show_subm_report {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $assign = param('arg1');
  my $user = param('arg2');

  print_html_start(0,'saida',0);
  
  check_assign_access($uid,$upassf,$assign);

  ($utype eq 'P' && $user ne 'undefined') && ($uid = $user);

  my $userd = "$assign/$uid";
  my $reportf = "$userd/$uid.rep";

  (!-e $reportf) && 
    block_user($uid,$upassf,"show_report: não existe arquivo $reportf.");

  # Print report:
  open(my $FILE,'<',$reportf) || abort($uid,$assign,"show_subm_report: open $reportf: $!");
  while (<$FILE>) {
    print $_;
  }
  close($FILE);

  print_html_end();
}



####################################################################################################
sub show_statement {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');
  my $assign = param('arg1');

  print_html_start();

  check_assign_access($uid,$upassf,$assign);

  (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));
  my %cfg = (%sys_cfg, load_keys_values("$assign/config"));

  # If the assignment is not open yet and the user is a student, this is strange:
  ($utype ne 'P' && exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) && 
    block_user($uid,$upassf,"show_st: o prazo para enviar $assign não começou.");

  print "<b>Trabalho:</b> $assign" .
    '<table><tr><td style="vertical-align:top">' .
    "Linguagens: $cfg{languages}";

  # Pascal, Fortran and Python3 are limited to a sigle source file:
  ($cfg{languages} eq 'Pascal' || $cfg{languages} eq 'Fortran' || $cfg{languages} eq 'Python3') &&
    ($cfg{sources} = '1,1');

  if (exists($cfg{sources})) {
    my @aux = split(/,/,$cfg{sources});
    print "<br>Arquivos-fonte a enviar: " . 
      ($aux[0] == $aux[1] ? "$aux[0]" : "entre $aux[0] e $aux[1]");
  }

  if (exists($cfg{pdfs})) {
    my @aux = split(/,/,$cfg{pdfs});
    print "<br>Arquivos pdf a enviar: " . 
      ($aux[0] == $aux[1] ? "$aux[0]" : "entre $aux[0] e $aux[1]");
  }

  if (exists($cfg{filenames})) {
    my @aux = split(/ +/,$cfg{filenames});
    for (my $i=0; $i<@aux; $i++) {
      $aux[$i] =~ s/\{uid\}/$uid/;
      $aux[$i] =~ s/\{assign\}/$assign/;
    }
    print "<br>Envie arquivos com nomes: @aux.";
  }

  (exists($cfg{startup})) && print "<br>Data de abertura: $cfg{startup}";

  my $days = 0;

  if (exists($cfg{deadline})) {
    $days = elapsed_days($cfg{deadline}); 
    print "<br>Data limite para envio: $cfg{deadline}";
    ($days*$cfg{penalty} >= 100) && print ' (encerrado)';
    ($cfg{penalty} < 100) && print "<br>Penalidade por dia de atraso: $cfg{penalty}\%";
  }
  
  my $open = 0;
  if ($utype eq 'S' && exists($cfg{deadline})) {
    if ($days*$cfg{penalty} < 100 || ($days*$cfg{penalty} >= 100 && $days <= $cfg{'keep-open'})) {
      $open = 1;
    }
  }
  else {
    $open = 1;
  }

  if ($open) {
    print "<br>Número máximo de envios: $cfg{tries}";

    if (-f "$assign/casos-de-teste.tgz") {
      print '<br>Casos-de-teste abertos: <a href="javascript:;" ' .
	"onclick=\"wrap('dwn','$assign','','casos-de-teste.tgz')\";>casos-de-teste.tgz</a>";
    }
  }
  
  if ($utype eq 'S') {
    my %rep = load_rep_data("$assign/$uid/$uid.rep");
    if (exists($rep{grade})) {
      print "<p><b>Último envio:</b> " .
	"<a href=\"javascript:;\" onclick=\"wrap('rep','$assign');\">$rep{grade}</a> em $rep{at}" .
	"<br>Envios: $rep{tries}"; 
    }
  }
  
  print "</td>";
  
  if ($utype eq 'P') {
    print '<td>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</td>' .
      '<td style="vertical-align:top">' .
      "backup: $cfg{backup}<br>grading: $cfg{grading}<br>keep-open: $cfg{'keep-open'}</td>" ,      
      '<td>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</td>' . 
      '<td style="vertical-align:top">' .
      "cputime: $cfg{cputime} s<br>virtmem: $cfg{virtmem} kb<br>stkmem: $cfg{stkmem} kb</td>";
  }
  print '</tr></table>';


  # Groups:
  if ($utype eq 'P') {
    opendir(my $DIR,$assign) || abort($uid,$assign,"home: opendir $assign: $!");
    my @aux = sort(grep {/\.pass$/ && -l "$assign/$_" && stat("$assign/$_")} readdir($DIR));
    close($DIR);
    
    print '<p><b>Grupos:</b><br>&nbsp;';
    for (my $i=0; $i<@aux; $i++) {
      my $group = $aux[$i];
      $group =~ s/\.pass$//;
      print '<a href="javascript:;"' .
	"onclick=\"wrap('scr','$group','$assign');\">$group</a>&nbsp; ";
    }
  }

  if ($open) {
    my @aux = split(/ +/,$cfg{languages});

    print "<input type=\"hidden\" name=\"submassign\" value=\"$assign\">" .
      '<p><b>Enviar:</b></p>' .
      '<div class="f95">' .
      '<table cellspacing="0" border="0">' .
      '<tr> <td>Linguagem:&nbsp;&nbsp;';   
    
    print $cgi->popup_menu('language', \@aux);
    
    print '</td><td>&nbsp;&nbsp;&nbsp;&nbsp;</td><td>Arquivos:&nbsp;&nbsp;' .
      '<input type="file" name="source" multiple></td>' .
      '<td><input type="submit" class="button" name="subm" value="Enviar"' .
      ' onclick="javascript:wrap(\'sub\')"></td>'.
      '</table>' .
      '</div><p>';
  }

  if (exists($cfg{description})) {
    if ($cfg{description} =~ /^http/) {
      print "<p><hr>Enunciado: <a href=\"$cfg{description}\">$cfg{description}</a><hr>";
    }
    elsif (-f "$assign/$cfg{description}") {
      print '<p><hr>';
      print_html_file($assign,$cfg{description});
      print '<hr>';
    }
    else {
      abort($uid,$assign,"description em config de $assign não é http nem arquivo.");
    }
  }
  else {
    print "<p>Não há enunciado para $assign.";
  }

  print_html_end();
}



####################################################################################################
sub show_about {

  print header();
  print start_html(-title=>'sqtpm', 
		   -style=>{-src=>['sqtpm.css']},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);

  print '<div class="f85">';
  print_html_file('','bula.html');
  print '<hr><a href="sqtpm.cgi">sqtpm</a></div>';
  print end_html();
}  



####################################################################################################
sub show_help {

  my $file = shift;

  print_html_start();
  print_html_file('',$file);
  print_html_end();
}  



####################################################################################################
sub download_file {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $assign = param('arg1');
  my $suid = param('arg2');
  my $file = param('arg3');

  # Check user access rights to assignment:
  check_assign_access($uid,$upassf,$assign);

  # Check file existance:
  if ($file eq "casos-de-teste.tgz") {
    $file = "$assign/$file";
  }
  else {
    if ($utype eq 'S') {
      $file = "$assign/$uid/$file";
      if (!-f $file) {
	block_user($uid,$upassf,"download_file: $assign/$uid/$file não existe.");
      }
    }
    elsif ($utype eq 'P') {
      $file = "$assign/$suid/$file";
    }
  }

  # Download:
  print "Content-Type:application/x-download\nContent-Disposition:attachment;filename=$file\n\n";
  
  open(my $FILE,'<',$file) || abort($uid,$assign,"download_file: open $file: $!");
  binmode $FILE;
  while (<$FILE>) {
    print $_;
  }
  close($FILE);
}



####################################################################################################
sub show_grades_table {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $passf = param('arg1').'.pass';
  my $assign = param('arg2');

  print_html_start();

  check_assign_access($uid,$upassf,$assign);

  my $tabfile = "$assign/grades.$passf";
  $tabfile =~ s/\.pass$//;

  my $tab;

  # If the table exists already, load it from file.
  if (-f $tabfile) {
    open(my $F,'<',$tabfile) || abort($uid,$assign,"show_grades_table: open $tabfile: $!");
    {
      local $/;
      $tab = <$F>;
    }
    close($F);
  }
  else {
    $tab = "<p><b>Acertos para $passf em $assign:</b>";

    my @langs;
    my %langs;
    my %grades;
    
    # Get users:
    my @users = load_keys($passf,':');
    if (@users == 0) {
      $tab .= '<p>Nenhum usuário em $passf.</p>';
    }
    else {
      (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));
      my %cfg = (%sys_cfg, load_keys_values("$assign/config"));

      # Get users grades and build a hash having an array of student ids for each language:
      %grades = ();
      %langs = ();

      for (my $i=0; $i<@users; $i++) {
	$users[$i] =~ s/^[\*@]?//;
      }    

      foreach my $user (@users) {
	my %rep = load_rep_data("$assign/$user/$user.rep");

	if (exists($rep{grade})) {

	  my $g = $rep{grade};
	  $g =~ s/\%//;
	  
	  $grades{$user} = '<a href="javascript:;"' . 
	    "onclick=\"wrap('rep','$assign','$user');\">$g</a>";

	  (!exists($langs{$rep{lang}})) && ($langs{$rep{lang}} = ());
	  push(@{$langs{$rep{lang}}},$user);
	}
	else {
	  $grades{$user} = '-';
	}
      }

      # Produce a report with a table with tuples {user,grade} and a
      # histogram.  They are both in an outer table.
      my $show = 0;
      my $show100 = 0;
      my $rows = '';
      
      foreach my $user (@users) {
	$rows .= "<tr align=center>" . 
	  "<td class=\"grid\"><b>$user</b></td><td class=\"grid\">$grades{$user}</td></tr>";
	($grades{$user} ne '-') && ($show++);
	($grades{$user} =~ '>100</a>$') && ($show100++);
      }

      my $n = @users;

      $tab .= '<div class="f95" style="overflow-x:scroll">'.
	'<table border=0><tr><td valign=\'top\'>' .
	'<table class="grid">' .
	'<tr align=center>' . 
	"<td class=\"grid\"><b>Total</b></td><td class=\"grid\" colspan=0>$n</td></tr>" .
	'<tr align=center><td class="grid"><b>Submetidos</b></td>' .
	sprintf("<td class=\"grid\">%i (%.0f%%)</td></tr>",$show,$n>0?100*$show/$n:0) .
	'<tr align=center><td class="grid"><b>100</b></td>' .
	sprintf("<td class=\"grid\">%i (%.0f%%)</td></tr>",$show100,$show>0?100*$show100/$show:0) .
	"<tr><th class=\"grid\">Usuário</th><th class=\"grid\">$assign</th></tr>" .
	$rows .
	'</table>';

      @langs = keys(%langs);
      (@langs == 1) && ($tab .= "<p>Todos em $langs[0].");
      $tab .= '</td>';

      # Submission histogram per day:
      if ($cfg{backup} eq 'on') {
	%gusers = map { $_ => 1 } @users; # %gusers is used by wanted_hist
	@ggrades = ();                    # @ggrades is modified by wanted_hist, it holds the grades.    

	find(\&wanted_hist,"$assign");
	
	if (@ggrades) {
	  my %freq = ();
	  my %freq100 = ();
	  my %frequniq = ();
	  my %freq100uniq = ();

	  my %uniq = ();
	  my %uniq100 = ();
	  
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

	    if (!exists($uniq{"$ggrades[$i]$ggrades[$i+2]"}) && $ggrades[$i+1] ne '100%') {
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
	    ($first gt $1) && ($first = $1);
	  }
	  
	  if (exists($cfg{deadline})) {
	    $cfg{deadline} =~ /(.*) .*/;
	    ($last lt $1) && ($last = $1);
	    $last =~ s/-/\//g;
	  }
	  
	  my ($y, $m, $d) = split(/\//,$first);
	  $first = timelocal(0, 0, 12, $d, $m - 1, $y - 1900);
	  ($y, $m, $d) = split(/\//,$last);
	  $last = timelocal(0, 0, 12, $d, $m - 1, $y - 1900);
	  
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
	  
	  $tab .= '<td valign=\'top\'>' .
	    '<img src="data:image/png;base64,' .
	    encode_base64(histogram($size<30 ? 600 : $size*25,360,\%freq,\%freq100)) .
	    '" style="border:0;padding: 0px 0px 0px 20px">' .
	    '';

	  $tab .= '<img src="data:image/png;base64,' .
	    encode_base64(histogram($size<30 ? 600 : $size*25,360,\%frequniq,\%freq100uniq)) .
	    '" style="border:0;padding: 0px 0px 0px 20px">' .
	    '</td>';
	}
      }
      $tab .= '</tr></table></div>';
    }

    if (@langs > 1) {
      # Produce a report with a table with tuples {user,grade} for each language:  
      $tab .= "<p>&nbsp;</p><b>Acertos para $passf em $assign por linguagem:</b>" .
	'<table border=0><tr>';

      for my $k (@langs) {
	$tab .= "<td valign='top'><b>$k:</b>" .
	  '<div class="f95"><table class="grid">' . 
	  "<tr><th class=\"grid\">Usuário</th><th class=\"grid\">$assign</th></tr>";

	my $show = 0;
	my $show100 = 0;
	@users = @{$langs{$k}};
	
	foreach my $user (@users) {
	  $tab .= '<tr align=center>' . 
	    "<td class=\"grid\"><b>$user</b></td><td class=\"grid\">$grades{$user}</td></tr>";
	  
	  ($grades{$user} ne '-') && ($show++);
	  ($grades{$user} =~ '>100%</a>$') && ($show100++);
	}
	
	my $n = @users;
	$tab .= "<tr align=center><td class=\"grid\"><b>Total</b></td><td class=\"grid\">$n</td></tr>" .
	  '<tr align=center><td class="grid"><b>Submetidos</b><br><b>%</b></td>' .
	  sprintf("<td class=\"grid\">%i<br>%.0f</td></tr>",$show,$n>0?100*$show/$n:0) .
	  '<tr align=center><td class="grid"><b>100</b><br><b>%</b></td>' .
	  sprintf("<td class=\"grid\">%i<br>%.0f</td></tr>",$show100,$show>0?100*$show100/$show:0) .
	  '</table></div>' .
	  '</td><td></td>';
      }
    }

    # Save table to file. submit_assignment() will remove it:
    open(my $F,'>',$tabfile) || abort($uid,$assign,"show_grades_table: open $tabfile: $!");
    print $F $tab;
    close($F);    
  }

  print $tab;
  print_html_end();
}



####################################################################################################
sub show_all_grades_table {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');

  my $passf = param('arg1').'.pass';

  print_html_start();
  
  ($utype ne 'P') && block_user($uid,$upassf,"show_all: $uid é estudante.");

  # Get a list of assignments for the user:
  opendir(my $DIR,'.') || abort($uid,'','all_grades: opendir root: $!');
  my @amnts = sort(grep { -d $_ && !/^\./ && -f "$_/config" && -l "$_/$upassf" } readdir($DIR));
  close($DIR);
  
  if (@amnts == 0) {
    print "Não há trabalhos para $passf.";
    print_html_end();
  }

  print "<p><b>Acertos para $passf:</b></p>";

  # Get users:
  my @users = load_keys($passf,':');

  for (my $i=0; $i<@users; $i++) {
    $users[$i] =~ s/^[\*@]?//;
  }    

  # Build the structure: $grades{assignment}{id} = grade.
  my %grades = ();

  for (my $i=@amnts-1; $i>=0; $i--) {
    $grades{$amnts[$i]} = { () };

    foreach my $user (@users) {
      my %rep = load_rep_data("$amnts[$i]/$user/$user.rep");

      if ($rep{tries} > 0) {
	$rep{grade} =~ s/%//;
	$rep{grade} =~ s/recebido/r/;
	$grades{$amnts[$i]}{$user} = '<a href="javascript:;"' . 
	  "onclick=\"wrap('rep','$amnts[$i]','$user');\">$rep{grade}</a>";
      }
      else {
	$grades{$amnts[$i]}{$user} = '-';
      }
    }
  }

  # Print a report with a table with tuples {user,grade,grade,...} and summaries:
  print '<div style="overflow-x:scroll"><div class="f95">' .
    '<table class="grid"><tr><th class="grid">Usuário</th>';

  my %show = ();
  my %show100 = ();

  foreach my $amnt (@amnts) {
    print "<th class=\"grid\">$amnt";
    $show{$amnt} = 0;
    $show100{$amnt} = 0;
  }

  foreach my $user (@users) {
    print "<tr align=center><td class=\"grid\"><b>$user</b>";
    foreach my $amnt (@amnts) {
      print "<td class=\"grid\">$grades{$amnt}{$user}</td>";
      ($grades{$amnt}{$user} ne '-') && ($show{$amnt}++);
      ($grades{$amnt}{$user} =~ '>100</a>$') && ($show100{$amnt}++);
    }
    print '</tr>';
  }

  my $n = @users;
  print "<tr align=center>" . 
    "<td class=\"grid\" colspan=$n></td></tr>" .
    '<tr align=center><td class="grid"><b>Submetidos</b><br><b>%</b></td>';

  foreach my $amnt (@amnts) {
    printf("<td class=\"grid\">%i / %i<br>%.0f</td>",
	   $show{$amnt},$n,$n>0?100*$show{$amnt}/$n:0);
  }

  print '</tr><tr align=center><td class="grid"><b>100</b><br><b>%</b></td>';
  foreach my $amnt (@amnts) {
    printf("<td class=\"grid\">%i / %i<br>%.0f</td>",
	   $show100{$amnt},$show{$amnt},$show{$amnt}>0?100*$show100{$amnt}/$show{$amnt}:0);
  }

  print '</tr></table></div></div>';
  print_html_end();
}



####################################################################################################
sub submit_assignment {

  my $uid = $session->param('uid');
  my $utype = $session->param('utype');
  my $upassf = $session->param('upassf');
  
  my $assign = param('submassign');
  my $language = param('language');

  my @uploads = param('source');
  @uploads = grep(/\S+/,@uploads);

  my $dryrun = 0;
  
  print_html_start(0,'saida',1);

  ### Checks:  
  # Check assign:
  (!$assign) && abort($uid,'',"Selecione um trabalho.");

  # Check access:
  check_assign_access($uid,$upassf,$assign);

  # Load system and assignment configs:
  (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));
  my %cfg = (%sys_cfg, load_keys_values("$assign/config"));

  my $deaddays = exists($cfg{deadline}) ? elapsed_days($cfg{deadline}) : 0;
  
  # Check whether the assignment is open:
  if ($utype eq 'S') {    
    if (exists($cfg{deadline}) && $deaddays*$cfg{penalty} >= 100) {
      if ($deaddays <= $cfg{'keep-open'}) { 
	$dryrun = 1;
      }
      else {
	abort($uid,$assign,"O prazo para enviar $assign terminou.");
      }
      
      if (exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) {
	block_user($uid,$upassf,"submit: o prazo para enviar $assign não começou.");
      }
    }
  }
  
  # Check language:
  (!$language) && abort($uid,$assign,'Selecione uma linguagem.');

  my %langs = ('C'=>0,'C++'=>0,'Fortran'=>0,'Pascal'=>0,'Python3'=>0,'Java'=>0,'PDF'=>0);
  
  (!exists($langs{$language})) && block_user($uid,$upassf,"submit: não há linguagem $language.");

  (!grep(/$language/,split(/\s+/,$cfg{languages}))) && 
    block_user($uid,$upassf,"submit: $assign não pode ser enviado em $language.");
  
  # Check the number of uploading files and their names: 
  my @pdfs = grep(/\.pdf$/ && /^[0-9a-zA-Z\_\.\-]+$/,@uploads);
  my %exts;
  my @sources;
  
  if ($language eq 'PDF') {
    $cfg{sources} = '0,0';
    (!exists($cfg{pdfs})) && ($cfg{pdfs} = '1,1');
  }
  else {
    (!exists($cfg{pdfs})) && ($cfg{pdfs} = '0,0');
    %exts = ('C'=>'(c|h)','C++'=>'(cpp|h)','Fortran'=>'(f|F)','Pascal'=>'pas',
	     'Python3'=>'py','Java'=>'java');
    @sources = grep(/$exts{$language}$/ && /^[0-9a-zA-Z\_\.\-]+$/,@uploads);  
    (!exists($cfg{sources})) && ($cfg{sources} = '1,9');
    
    # Pascal, Fortran and Python are limited to a sigle source file:
    ($language eq 'Pascal' || $language eq 'Fortran' || $language eq 'Python3') &&
      ($cfg{sources} = '1,1');
  }

  $cfg{sources} =~ /(\d+),(\d+)/;
  (@sources < $1 || @sources > $2) && 
    abort($uid,$assign,'Envie ' . ($1 == $2 ? "$1" : "de $1 a $2") . ' arquivos-fonte. ' .
	  '<p>Veja detalhes sobre os nomes de arquivos válidos nesta ' .
	  "<a href=\"javascript:;\" onclick=\"wrap('hlp','envio')\">página</a>.");

  $cfg{pdfs} =~ /(\d+),(\d+)/;
  (@pdfs < $1 || @pdfs > $2) && 
    abort($uid,$assign,'Envie ' . ($1 == $2 ? "$1" : "de $1 a $2") . ' arquivos pdf. ' .
	  '<p>Veja detalhes sobre os nomes de arquivos válidos nesta ' .
	  "<a href=\"javascript:;\" onclick=\"wrap('hlp','envio')\">página</a>.");

  # A Main.java is required with Java:
  if ($language eq 'Java') {
    if (!exists($cfg{filenames})) {
      $cfg{filenames} = "Main.java";
    }
    else {
      if ($cfg{filenames} !~ /^Main.java / && $cfg{filenames} !~ / Main.java / && 
	  $cfg{filenames} !~ /Main.java$/) {
	$cfg{filenames} .= " Main.java";
      }
    }
  }	
  
  if (exists($cfg{filenames})) {
    my %names = ();
    my @aux = split(/ +/,$cfg{filenames});
    for (my $i=0; $i<@aux; $i++) {
      $aux[$i] =~ s/\{uid\}/$uid/;
      $aux[$i] =~ s/\{assign\}/$assign/;
      $names{$aux[$i]} = 1;
    }
    if (keys(%names) > 0) {
      for (my $i=0; $i<@uploads; $i++) {
	delete($names{$uploads[$i]});
      }
      (keys(%names) > 0) && abort($uid,$assign,"Envie arquivos com nomes: @aux.") ;
    }
  }
  
  # Read tries from the existing report file or set it to 0:
  my $tries = 0;
  if (-e "$assign/$uid/$uid.rep") {
    my %rep = load_rep_data("$assign/$uid/$uid.rep");
    $tries = $rep{tries};
  }

  # Submiting a non-updating assignment will only be possible if a valid submission 
  # has been done previously:
  ($dryrun && $tries == 0) &&
    abort($uid,$assign,"O prazo para $assign terminou. Você não pode enviá-lo pela primeira vez.");
  
  # Check the maximum number of submissions:
  ($utype eq 'S' && $tries >= $cfg{tries}) && 
    abort($uid,$assign,"Você não pode enviar $assign mais uma vez.");
  
  ### Create a directory:
  my $userd = "$assign/_${uid}_tmp_";
  mkdir($userd) || abort($uid,$assign,"submit: mkdir " . cwd() . " $userd: $!");
  

  ### Report header:
  my $rep = "<b>Usuário: $uid</b>";
  $rep .= "\n<br><b>Trabalho: $assign</b>";

  if (exists($cfg{deadline})) {
    $rep .= "\n<br>Data limite para envio: $cfg{deadline}";
    ($deaddays*$cfg{penalty} >= 100) && ($rep .= ' (encerrado)');
    ($cfg{penalty} < 100) && ($rep .= "\n<br>Penalidade por dia de atraso: $cfg{penalty}%");
  }

  ($utype eq 'S' && $dryrun) && 
    ($rep .= "\n<br><b>O prazo terminou. Este envio não será registrado.</b>");
  
  ($utype eq 'P') && ($rep .= "\n<br>$uid: envios sem restrições de linguagem e prazo.");

  my $now = format_epoch(time);

  $tries++;
  $rep .= "\n<br>Este envio: $tries&ordm;, $now";

  $rep .= "\n<br>Linguagem: $language";
  $rep .= (@uploads == 1 ? "<br>Arquivo: " : "\n<br>Arquivos: ");

  ### Get uploaded source files and documents:
  if (@pdfs) {
    %exts = ('PDF'=>'pdf', 'C'=>'(c|h|pdf)', 'C++'=>'(cpp|h|pdf)',
	     'Pascal'=>'(pas|pdf)', 'Fortran'=>'(f|F|pdf)', 
	     'Python3'=>'(py|pdf)', 'Java'=>'(java|pdf)');
  }

  my @fh = upload('source');
  @sources = ();
  @pdfs = ();
  for (my $i=0; $i<@fh; $i++) {
    ($uploads[$i] !~ /\.$exts{$language}$/ || $uploads[$i] !~ /^[a-zA-Z0-9_\.\-]+$/) && next;

    open(my $SOURCE,'>',"$userd/$uploads[$i]") || 
      abort($uid,$assign,"submit: open $userd/$uploads[$i]: $!");

    my $fh = $fh[$i];
    if ($uploads[$i] =~ /\.pdf$/) {
      binmode $SOURCE;
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

  ### Include links for sources and documents:
  for (my $i=0; $i<@sources; $i++) {
    $rep .= '<a href="javascript:;" ' . 
      "onclick=\"toggleDiv('$sources[$i]');\">$sources[$i]</a>&nbsp;";
  }
  for (my $i=0; $i<@pdfs; $i++) {
    $rep .= '<a href="javascript:;" ' . 
      "onclick=\"wrap('dwn','$assign','$uid','$pdfs[$i]');\">$pdfs[$i]</a>&nbsp; ";
  }

  $rep .= "\n<script type=\"text/javascript\" src=\"google-code-prettify/run_prettify.js?61\"></script>";
  
  ### Include source files:
  for (my $i=0; $i<@sources; $i++) {
    $rep .= "\n<div id=\"$sources[$i]\" style=\"display:none\" class=\"src\">" . 
      "<b>$sources[$i]</b>&nbsp;&nbsp;" . 
      "<a href=\"javascript:;\" onclick=\"wrap('dwn','$assign','$uid','$sources[$i]')\">download</a>";

    my $source = "$userd/$sources[$i]";
    if ($sources[$i] =~ /\.c$/ || $sources[$i] =~ /\.h$/) {
      $rep .= "\n<pre class=\"prettyprint lang-c\" id=\"C_lang\">";
      if (-x "$cfg{indent}") {
	system("$cfg{indent} -kr $source -o $source.indent 2>/dev/null");
	$rep .= load_file($uid,$assign,"$source.indent",1);
      }
      else {
	$rep .= load_file($uid,$assign,"$source",1);
      }
    }
    else {
      $rep .= "\n<pre class=\"prettyprint\">";
      $rep .= load_file($uid,$assign,"$source",1);
    }
    
    $rep .= "\n</pre></div>"; 
  }

  my $grade;
  my $full_grade;
  my @test_cases = ();
  
  ### If this is a PDF statement, there is nothing else to do:
  if ($language eq 'PDF') {
    if ($utype eq 'S' && exists($cfg{deadline}) && !$dryrun && $deaddays > 0) {
      $rep .= "<b>Recebido com atraso de $deaddays " . ($deaddays>1 ? "dias" : "dia") . ".</b><br>";
      $grade = "recebido +$deaddays";
    }
    else {
      $rep .= "<b>Recebido.</b><br>";
      $grade = 'recebido';
    }
  }
  else {
    # Load test-case names early to produce correct messages for compiling errors:
    opendir(my $DIR,"$assign") || abort($uid,$assign,"submit: opendir $assign: $!");
    @test_cases = sort(grep {/\.in$/ && -f "$assign/$_"} readdir($DIR));
    close($DIR);

    my $ncases = @test_cases;

    for (my $i=0; $i<$ncases; $i++) {
      $test_cases[$i] =~ s/\.in$//;
    }

    $grade = 0;

    # Compile:
    $rep .= "\n<p><b>Compilação:</b>&nbsp;";
    my $compcmd;
    
    if ($language eq 'C') {
      (!-x $cfg{gcc}) && abort($uid,$assign,"submit: $cfg{gcc} inválido");
      (!exists($cfg{'gcc-args'})) && ($cfg{'gcc-args'} = '');
      
      open(my $MAKE,'>',"$userd/Makefile") || 
	abort($uid,$assign,"submit: write $userd/Makefile: $!");

      print $MAKE "CC = $cfg{gcc}\n" .
	'CFLAGS = ' . $cfg{'gcc-args'} . "\n" .
	'SRC = $(wildcard *.c)' . "\n" .
	'elf: $(SRC:%.c=%.o)' . "\n" .
	"\t" . '$(CC) $(CFLAGS) -o $@ $^' . "\n";

      close($MAKE);    
      $compcmd = "$cfg{'make'}";
    }
    elsif ($language eq 'Python3') {
      (!-x $cfg{python3}) && abort($uid,$assign,"submit: $cfg{python3} inválido");

      (!exists($cfg{'python3-args'})) && ($cfg{'python3-args'} = '');
      $compcmd = "$cfg{python3} $cfg{'python3-args'} -m py_compile $sources[0]";
    }
    elsif ($language eq 'Java') {
      (!-x "$cfg{jdk}/javac") && abort($uid,$assign,"submit: $cfg{jdk}/javac inválido");
      (!-x "$cfg{jdk}/jar") && abort($uid,$assign,"submit: $cfg{jdk}/jar inválido");

      (!exists($cfg{'javac-args'})) && ($cfg{'javac-args'} = '');

      open(my $MF,'>',"$userd/manifest.txt") ||
	abort($uid,$assign,"submit: write $userd/manifest.txt: $!");
      print $MF "Main-Class: Main\n";
      close($MF);

      open(my $MAKE,'>',"$userd/Makefile") ||
	abort($uid,$assign,"submit: write $userd/Makefile: $!");

      print $MAKE "elf: \n" . 
	 "\t$cfg{'jdk'}/javac $cfg{'javac-args'} *.java; $cfg{'jdk'}/jar cvfm elf manifest.txt *.class\n";

      close($MAKE);
      $compcmd = "$cfg{'make'}";
    }
    elsif ($language eq 'C++') {
      (!-x $cfg{'g++'}) && abort($uid,$assign,"submit: $cfg{'g++'} inválido");

      (!exists($cfg{'g++-args'})) && ($cfg{'g++-args'} = '');
      open(my $MAKE,'>',"$userd/Makefile") || 
	abort($uid,$assign,"submit: write $userd/Makefile: $!");
      
      print $MAKE "CC = $cfg{'g++'}\n" .
	'CFLAGS = ' . $cfg{'g++-args'} . "\n" .
	'SRC = $(wildcard *.cpp)' . "\n" .
	'elf: $(SRC:%.cpp=%.o)' . "\n" .
	"\t" . '$(CC) $(CFLAGS) -o $@ $^' . "\n";

      close($MAKE);
      $compcmd = "$cfg{'make'}";
    }
    elsif ($language eq 'Fortran') {
      (!-x $cfg{gfortran}) && abort($uid,$assign,"submit: $cfg{gfortran} inválido");

      (!exists($cfg{'gfortran-args'})) && ($cfg{'gfortran-args'} = '');
      $compcmd = "$cfg{gfortran} $cfg{'gfortran-args'} $sources[0] -o elf";
    }
    elsif ($language eq 'Pascal') {
      (!-x $cfg{gpc}) && abort($uid,$assign,"submit: $cfg{gpc} inválido");

      (!exists($cfg{'gpc-args'})) && ($cfg{'gpc-args'} = '');
      $compcmd = "$cfg{gpc} $cfg{'gpc-args'} --executable-file-name=elf --automake $sources[0]";
    }


    my $status = system("cd $userd; $compcmd 1>out 2>err");
    my $elff = "$userd/elf";
    my $outf = "$userd/out";
    my $errf = "$userd/err";

    if ($status) {
      $rep .= 'com erros.<br>' . "\n<div class=\"io\">"; 
      $rep .= load_file($uid,$assign,$outf,1);
      $rep .= load_file($uid,$assign,$errf,1,2500);
      $rep .= "</div>\n<p><b>Acerto:</b> 0%";
      $grade = 0;
    }
    else {
      if (-s "$errf") {
	$rep .= "com warnings." . "\n<div class=\"io\">"; 
	$rep .= load_file($uid,$assign,$outf,1);
	$rep .= load_file($uid,$assign,$errf,1,2500);
	$rep .= "</div>\n";
      }
      else {
	$rep .= "bem sucedida.";
      }

      # No test cases:
      if ($ncases == 0) {
	$rep .= "<p><b>Nenhum caso-de-teste.</b><br>";

	if ($utype eq 'S' && exists($cfg{deadline}) && !$dryrun && $deaddays > 0) {
	  $rep .= "<b>Recebido com atraso de $deaddays " . ($deaddays>1 ? "dias" : "dia") . ".</b><br>";
	  $grade = "recebido +$deaddays";
	}
	else {
	  $rep .= "<b>Recebido.</b><br>";
	  $grade = 'recebido';
	}
      }

      # Dispatch test cases execution:
      else {

	# Python requires renaming after compiling:
	if ($language eq 'Python3') {
	  @pyc = glob("$userd/__pycache__/*.pyc");
	  rename($pyc[0],"$userd/elf") || abort($uid,$assign,"rename: $pyc[0] elf: $!");
	  unlink(glob "$userd/__pycache__/*");
	  rmdir("$userd/__pycache__") || abort($uid,$assign,"rmdir: $userd/__pycache__: $!");
	}

	$rep .= "\n<p><b>Execução dos casos-de-teste:</b>\n<p>";

	my $cmd = "./sqtpm-etc.sh $uid $assign $language $cfg{cputime} $cfg{virtmem} $cfg{stkmem} >/dev/null 2>&1";
	system($cmd);

	my $status = $? >> 8;
	($status) && abort($uid,$assign,"submit: system $cmd (status $status): $!");

	# Adjust verifier path:
	(exists $cfg{verifier}) && ($cfg{verifier} =~ s/\@/$assign\//);

	# Process every test case result:
	my %failed = ();
	my $passed = 0;
	my $casei = 1;

	foreach my $case (@test_cases) {
	  my $case_in = "$assign/$case.in";
	  my $case_out = "$assign/$case.out";
	  my $exec_st = "$userd/$case.run.st";
	  my $exec_out = "$userd/$case.run.out";
	  my $exec_err = "$userd/$case.run.err";

	  (!-r $case_in) && abort($uid,$assign,"submit: sem permissão para $case_in.");
	  (-s $exec_st && !-r $exec_st) && abort($uid,$assign,"submit: sem permissão para $exec_st.");
	  (!-r $exec_out) && abort($uid,$assign,"submit: sem permissão para $exec_out.");

	  $failed{$case} = $casei;
	  my $status;
	  
	  if (open(my $STATUS,'<',"$exec_st")) {
	    $status = <$STATUS>;
	    chomp($status);
	    $status -= 128;
	    close($STATUS);
	  }
	  else {
	    $status = 9;
	  }

	  $rep .= sprintf("\n%.02d: &nbsp;",$casei);

	  if ($status == 11) {
	    $rep .= 'violação de memória.<br>';
	  }
	  elsif ($status == 9) {
	    $rep .= 'limite de tempo ou memória excedido.<br>';
	  }
	  elsif ($status == 8) {
	    $rep .= 'erro de ponto flutuante.<br>';
	  }
	  elsif ($status > 0 || -s $exec_err) {
	    (-s $exec_err && !-r $exec_err) && abort($uid,$assign,"submit: sem permissão para $exec_err.");
	    $rep .= "erro de execução ($status).<br>";
	    (-s $exec_err) && 
	      ($rep .= "\n<div class=\"io\">" . load_file($uid,$assign,$exec_err,0,1000) . "</div>\n");
	  }
	  else {
	    if (exists($cfg{verifier})) {
	      my $cmd = "$cfg{verifier} $case_in $exec_out >/dev/null 2>&1";
	      system($cmd);
	      $status = $? >> 8;

	      if ($status == 0) {
		$rep .= "bem sucedido.<br>";
		$failed{$case} = 0;
		$passed++;
	      }
	      elsif ($status == 1) {
		$rep .= "saída incorreta.<br>";
	      }
	      elsif ($status == 2) {
		$rep .= 'saída com formatação incorreta.<br>';
	      }
	      else {
		abort($uid,$assign,"submit: Erro ao executar o verificador $cmd.");
	      }
	    }
	    else {
	      (!-r $case_out) && abort($uid,$assign,"submit: sem permissão para $case_out.");

	      system("$cfg{diff} -q $case_out $exec_out >/dev/null 2>&1");
	      $status = $? >> 8;

	      if ($status == 0) {
		$rep .= 'saída correta.<br>';
		$failed{$case} = 0;
		$passed++;
	      }
	      elsif ($status == 1) {
	        write_lc_file($uid,$assign,$case_out,-s $case_out);
		write_lc_file($uid,$assign,$exec_out,-s "$case_out.lc");
		
		system("$cfg{diff} -q $case_out.lc $exec_out.lc >/dev/null 2>&1");
		$status = $? >> 8;
		
		if ($status == 0) {
		  $rep .= 'saída com formatação incorreta.<br>';
		}
		elsif ($status == 1) {
		  $rep .= 'saída incorreta.<br>';
		}
		else {
		  abort($uid,$assign,"submit: erro ao executar diff $case_out.lc $exec_out.lc.");
	        }
	      }
	      else {
		abort($uid,$assign,"submit: erro ao executar diff $case_out $exec_out.");
	      }
	    }
	  }
	  $casei++;
	}
	
	$rep .= "\n<br>Número de casos-de-teste: $ncases." .
	        "\n<br>Casos-de-teste bem sucedidos: $passed.";
	
	if ($cfg{'grading'} eq 'total') {
	  $full_grade = ($passed == $ncases ? 100 : 0);
	}
	else {
	  $full_grade = $passed/$ncases*100;
	}
	
	$grade = $full_grade;
	
	my $discount = 0;
	if ($utype eq 'S' && exists($cfg{deadline}) && $grade > 0 && !$dryrun) {
	  $discount = $deaddays * $cfg{penalty} / 100;
	  ($discount > 0) && ($grade = $full_grade * (1 - $discount));
	  ($grade < 0) && ($grade = 0);
	}
	
	$rep .= "\n<br><b>Acerto:</b> " . sprintf("%.0f%%", $grade);
	
	if ($discount > 0 && $full_grade > 0) {
	  $rep .= sprintf(", desconto de %.0f%% sobre %.0f%% por atraso desde %s.", 
			  100*$discount, $full_grade, $cfg{deadline});
	}
	$rep .= "<br>\n";

	# Show the cases that failed and are supposed to be shown:
	if (exists($cfg{showcases})) {
	  my @show = split(/\s+/,$cfg{showcases});

	  for (my $i=0; $i<@show; $i++) {
	    if ($failed{$show[$i]}) {
	      $rep .= sprintf("\n<br><b>Execução do caso %.02d:</b>",$failed{$show[$i]});

	      $rep .= "\n<p>Entrada:<br><div class=\"io\">";
	      $rep .= load_file($uid,$assign,"$assign/$show[$i].in",0);
	      $rep .= "</div>";

	      if (!exists($cfg{verifier})) {
		$rep .= "\n<p>Saída esperada:<br><div class=\"io\">";
		$rep .= load_file($uid,$assign,"$assign/$show[$i].out",0);
		$rep .= "</div>";
	      }

	      $rep .= "\n<p>Saída produzida:<br><div class=\"io\">";
	      if (-f "$userd/$show[$i].run.out") {
		$rep .= load_file($uid,$assign,"$userd/$show[$i].run.out",0,
			     int((-s "$assign/$show[$i].out")*1.2));
	      }
	      $rep .= "</div>";
	      $rep .= "\n<hr>";
	    }
	  }
	}
	$grade = sprintf("%.0f%%",$grade);
      }
    }
    
    ### Clean-up:
    (-e $elff) && unlink($elff);  
    (-e $outf) && unlink($outf);
    (-e $errf) && unlink($errf);
    
    ($language eq 'Java') && unlink(glob "$userd/*.class");

    ($language ne 'Python3') && unlink(glob "$userd/*.o");
      
    foreach my $case (@test_cases) {
      (-e "$userd/$case.run.st")  && unlink("$userd/$case.run.st");
      (-e "$userd/$case.run.out") && unlink("$userd/$case.run.out");
      (-e "$userd/$case.run.out.lc") && unlink("$userd/$case.run.out.lc");
      (-e "$userd/$case.run.err") && unlink("$userd/$case.run.err");
    }
  }

  ### Add data to ease parsing the report later and a QED:
  $rep = "<!--lang:$language-->\n<!--grade:$grade-->\n<!--tries:$tries-->\n<!--at:$now-->\n" . 
         $rep .
	 "<p>&#9744;";
  
  if (!$dryrun) {
    open(my $REPORT,'>',"$userd/$uid.rep") || abort($uid,$assign,"submit: open $userd/$uid.rep: $!");
    print $REPORT $rep;
    close($REPORT);
  }
  
  print $rep;
  print end_html();

  # Remove grades report to force future update, if any:
  my $tabfile = "$assign/grades.$upassf";
  $tabfile =~ s/\.pass$//;
  (-f $tabfile) && unlink($tabfile);
  
  ### Move previous assignment and rename $userd:
  if (!$dryrun) {
    if ($tries > 1) {
      if ($cfg{backup} eq 'on') {
	my $date = format_epoch((stat("$assign/$uid/$uid.rep"))[9]);
	$date =~ s/[:\/]//g;
	$date =~ s/ /-/g;
	
	my $backupd = "$assign/backup";
	if (!-d $backupd) {
	  (-e $backupd) && abort($uid,$assign,"submit: $backupd is a file");
	  mkdir($backupd) || abort($uid,$assign,"submit: mkdir $backupd: $!");
	}

	$tries--;
	rename("$assign/$uid","$backupd/$uid.$tries.$date") || 
	  abort($uid,$assign,"submit: rename $assign/$uid $backupd/$uid.$tries.$date: $!");
      }
      else {
	unlink(glob "$assign/$uid/*");
	rmdir("$assign/$uid");
      }
    }
    rename($userd,"$assign/$uid") || abort($uid,$assign,"submit: rename $userd $assign/$uid: $!");
  }
  else {
    unlink(glob "$userd/*");
    rmdir("$userd");

    my $rep = load_file($uid,$assign,"$assign/$uid/$uid.rep",0);
    $rep =~ s/--tries:\d+--/--tries:$tries--/;
    
    open(my $REPORT,'>',"$assign/$uid/$uid.rep") || 
      abort($uid,$assign,"submit: open $assign/$uid/$uid.rep: $!");
    print $REPORT $rep;
    close($REPORT);
  }
  
  ### Write log:  
  add_to_log($uid,$assign,$grade);

  ### Update home screen:
  if ($utype eq 'S' && !$dryrun) {
    my $scr = $session->param('screen');
    
    my $i = index($scr,">$assign<");
    $i += index(substr($scr,$i),'<td ') + 3;
    ($utype eq 'P') && ($i += index(substr($scr,$i),'<td ') + 3);
    ($utype eq 'P') && ($i += index(substr($scr,$i),'<td ') + 3);
    $i += index(substr($scr,$i),'<td ') + 3;
    $i += index(substr($scr,$i),'<td ');

    my $j = index(substr($scr,$i),'<tr ');
    ($j == -1) && ($j = index(substr($scr,$i),'</table>'));
    $j += $i;
    
    $session->param('screen', 
		    substr($scr,0,$i) . "<td class=\"grid\"><a href=\"javascript:;\"" .
		    " onclick=\"wrap('rep','$assign');\">$grade</a></td>" . substr($scr,$j));
  }
}



####################################################################################################
sub invoke_moss {

  my $uid = shift;
  my $assign = shift;
  my $recursive = shift;

  (!$recursive) && print_html_start();

  (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));
  
  @gsources = ();  # @gsources is modified by wanted_moss.
  find(\&wanted_moss,"./$assign");

  (@gsources < 2) && abort($uid,$assign,"Deve haver pelo menos dois arquivos para comparar.");

  my $url = '';
  
  if (-f "$assign/moss.run") {
    # Check if last moss run is up and whether there is a newer source:
    open(my $OUT,'<',"$assign/moss.run") || abort($uid,$assign,"moss: open $assign/moss.run: $!");
    my @out = <$OUT>;
    close($OUT);
    $url = $out[-1];

    if (LWP::Simple::head("$url")) {
      my $run_age = (stat "$assign/moss.run")[9];
      for (my $i=0; $i<@gsources; $i++) {
	if ($run_age < (stat $gsources[$i])[9]) {
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
    my $LOCK;
    open($LOCK,'>',"$assign/moss.lock") || abort($uid,$assign,"moss: open $assign/moss.lock: $!");
    flock($LOCK,LOCK_EX|LOCK_NB) || abort($uid,$assign,"Comparando $assign, aguarde.");
    
    my $cmd = "perl moss-sqtpm $sys_cfg{'moss-id'} -m $sys_cfg{'moss-m'} " .
      "-d @gsources 1>$assign/moss.run 2>$assign/moss.err";
    system($cmd);
    my $st = $? >> 8;

    flock($LOCK,LOCK_UN);
    close($LOCK);
    unlink("$assign/moss.lock");

    ($st) && abort($uid,$assign,"moss: system $cmd: $!");

    open(my $OUT,'<',"$assign/moss.run") || abort($uid,$assign,"moss: open $assign/moss.run: $!");
    my @out = <OUT>;
    close(OUT);
    $url = $out[-1];

    if ($url !~ /^http:/) {
      unlink("$assign/moss.run");
      invoke_moss($uid,$assign,1);
      abort($uid,$assign,"A execução do Moss falhou.");
    }
  }
  
  # Redirect:
  print "<meta http-equiv=\"refresh\" content=\"0; url=$url\">";
  print_html_end();
}



####################################################################################################
# A wanted function to find sources for moss.  It uses @sources from
# an outer scope.

sub wanted_moss {
  -f && 
  !($File::Find::name =~ /\/backup\//) && 
  (/\.c$/ || /\.cpp$/ || /\.h$/ || /\.pas$/ || /\.f$/ || /\.F$/ || /\.py$/) && 
  (push(@gsources,"$File::Find::name"));
}



####################################################################################################
# A wanted function to collect data for the histogram.  Each report
# file for a user in %gusers is visited and (submission date, grade, user) 
# are pushed into @ggrades.

sub wanted_hist {
  
  /\.rep$/ && do {
    my $file = $_;
    /^(\w+)\./;

    (!$1 || (!exists($gusers{$1}) && !exists($gusers{"*$1"}))) && return;

    my %rep = load_rep_data($file);
    push(@ggrades,(split(/ /,$rep{at}))[0]);
    push(@ggrades,$rep{grade});
    push(@ggrades,$1);
  };

  return;
}



####################################################################################################
# print_html_start($first-login, $help, $back-link)
#
# first-login: 1 if the session is starting, 0 if it existed already.
# help: the help html file.
# back-link: 0 or null is back to previous page, 1 is forced back to sqtpm.cgi.

sub print_html_start {

  my $first_login = shift;
  my $help = shift;
  my $back = shift;

  if ($first_login) {
    print header(-cookie=>$cgi->cookie(CGISESSID => $session->id));
  }
  else {
    print header();
  }

  if ($help && $help eq 'saida') {
    print start_html(-title=>'sqtpm', 
		     -style=>{-src=>['sqtpm.css','google-code-prettify/prettify.css']},
		     -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);
  }
  else {
    print start_html(-title=>'sqtpm', 
		     -style=>{-src=>['sqtpm.css']},
		     -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);
  }
  
  print '<div id="wrapper"><div id="sidebar"><h1>sqtpm</h1>';
  print '<p style="margin-top:-15px"><small>[',substr($session->param('uid'),0,13),']</small></p>';
  ($help) && print "<a href=\"javascript:;\" onclick=\"wrap('hlp','$help')\">ajuda</a><br>";
  
  if ($help && $help eq 'envio') {
    print '<a href="javascript:;" onclick="wrap(\'out\');">sair</a>';
  }
  elsif ($back) {
    print '<a href="sqtpm.cgi">voltar</a>';
  }
  else {
    print '<a href="javascript:;" onclick="window.history.go(-1); return false;">voltar</a>';
  }    
  
  print '</div><div id="content">';
  
  # There will always be a form named sqtpm with hidden fields to handle actions through wrap():
  print '<form method="post" action="sqtpm.cgi" enctype="multipart/form-data" name="sqtpm">' .
    '<script type="text/javascript" src="sqtpm.js"></script>' .
    '<input type="hidden" name="action">' .
    '<input type="hidden" name="arg1">' . 
    '<input type="hidden" name="arg2">' .
    '<input type="hidden" name="arg3">';
}



####################################################################################################
# print_html_end()

sub print_html_end {

  print '</form></div></div>';
  print end_html();
}



####################################################################################################
# print_html_file($path, $file)
#
# Print an html file to stdout, encoding image files in base64 and printing them too.
# If an error occurs while opening a file then it invokes abort().

sub print_html_file {

  my $path = shift;
  my $file = shift;

  ($path) && ($path = "$path/");

  open(my $HTML,'<',"$path$file") || abort('','',"print_html_file: open $path$file: $!");

  while (<$HTML>) {
    /<img / && / src=\"([^\"]*)\"/ && do {
   
      my $fig = $1;
      my $type = (split(/\./,$fig))[-1];

      ($fig !~ /^\//) && ($fig = "$path$fig");

      open(my $FIG,'<',$fig) || abort('','',"print_html_file: open $fig: $!");
      
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



####################################################################################################
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



####################################################################################################
# block_user($user, $pass_file, $messsage)
#
# Block a user by commenting its line in the pass file, write message
# to the log and silently logout.

sub block_user {

  my $uid = shift;
  my $upassf = shift;
  my $mess = shift;

  my $PASS;
  open($PASS,'+<',$upassf) || abort($uid,,"block_user: open $upassf");

  my $lines = '';
  while (<$PASS>) {
    (/^([\*\@]?)$uid:?/) && ($_ = "# blocked! $_");
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
