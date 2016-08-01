#!/usr/bin/perl -w

# This file is part of sqtpm v6.
# Copyright 2003-2016 Guilherme P. Telles.
# sqtpm is distributed under WTFPL v2.

use CGI qw(:cgi Link start_html);
use CGI::Session qw/-ip-match/;
use CGI::Carp 'fatalsToBrowser';
use CGI::Session::Driver::file; 
use LWP::Simple qw(head);

$CGI::POST_MAX = 1000000;
$CGI::Session::Driver::file::FileName = 'sqtpm-sess-%s';  
$sessiond = '/tmp';

use Cwd;
use Time::Local;
use POSIX qw(ceil floor);
use Fcntl ':flock';
use File::Path;
use File::Find;
use GD;

use sqtpm;

umask(0007);

# Some globals:
%sys_cfg = ();
$session = 0;
$cgi = CGI->new;

# Try to retrieve session id from user agent:
$sid = $cgi->cookie('CGISESSID') || $cgi->param('CGISESSID') || undef;

# If the session id exists but the file don't then it must get a new session:
(defined($sid) && !-f "$sessiond/sqtpm-sess-$sid") && (undef $sid);
$action = param('action');

if (!defined($sid)) {

  if (!defined($action)) {
    login_form();    
  }
  elsif ($action eq 'in') {
    $uid = param('uid');
    $pwd = param('pwd');

    ($utype,$upassf) = authenticate($uid,$pwd);

    # authenticate() will accept if the typed and stored passwords are
    # both blank because sqtpm-pwd needs it this way, but not in login:
    ($pwd =~ /^\s*$/) && ($utype = '');  

    if ($utype ne '') {
      $session = new CGI::Session("driver:File",undef,{Directory=>$sessiond});
      $session->expire('+60m');
      $session->param('uid',$uid);
      $session->param('utype',$utype);
      $session->param('upassf',$upassf);
      wlog($uid,'','login');
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
    abort_login($uid,"Erro ao recuperar a sessão ($!).");

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
    $session->delete();
    wlog($session->param('uid'),'','logout');
    login_form();
  }
  elsif ($action eq 'scr') {
    show_scores_table();
  }
  elsif ($action eq 'asc') {
    show_all_scores_table();
  }
  elsif ($action eq 'dwn') {
    download_file();
  }
  elsif ($action eq 'hlp') {
    show_help(param('arg1').'.html');
  }
  elsif ($action eq 'moss') {
    moss($session->param('uid'),param('arg1'));
  }
  else {
    home(0);
  }
}

exit(0);




################################################################################
sub login_form {

  print header();
  print start_html(-title=>'sqtpm', -style=>{-src=>['sqtpm.css'], -media=>'all'},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'./icon.png'})]);

  print <<'  END';
    <script src="sqtpm.js"></script>
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
    <input type="hidden" name="arg2"><hr>
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



################################################################################
sub home {

  my ($DIR, $first_login, $group, $i, $j, $lang_tags, $scr, $tab,
      $uid, $upassf, $utype, %cfg, %groups, %rep, @assign, @aux, @group,
      @groups, @open, @open_langs);

  $uid = $session->param('uid');
  $utype = $session->param('utype');
  $upassf = $session->param('upassf');

  $first_login = shift;

  $scr = $session->param('screen');

  if (!defined($scr)) {
    %sys_cfg = load_keys_values('sqtpm.cfg');

    # Grab assignments for the user:
    opendir($DIR,'.') || abort('','','home : opendir root : $!).');
    @assign = sort(grep { -d $_ && !/^\./ && !/^\_/ && -e "$_/config" && -l "$_/$upassf" } 
		   readdir($DIR));
    close($DIR);

    # Assignments table.  Table header:
    $tab = '<b>Trabalhos:</b>';
    $tab .= '<p></p><div class="f95"><table class="grid">';
    $tab .= '<tr><th class="grid">Enunciado</th>';
    ($utype eq 'prof') && ($tab .= '<th class="grid">Abertura</th>');
    $tab .= '<th class="grid">Data limite</th>';
    $tab .= '<th class="grid">Estado</th>';
    ($utype eq 'prof') && ($tab .= '<th class="grid">Grupos</th>');
    ($utype eq 'capivara') && ($tab .= '<th class="grid">Último envio</th></tr>');
    ($utype eq 'prof') && ($tab .= '<th class="grid">Moss</th></tr>');
    
    @open = ();
    @open_langs = ();
    %groups = ();
    
    # Table rows:
    for ($i=0; $i<@assign; $i++) {
      %cfg = (%sys_cfg, load_keys_values("$assign[$i]/config"));
      
      # If this is not a professor and the assignment is still closed, skip it:
      ($utype ne 'prof') && (exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) && next;
      
      # Assignment tag:
      $tab .= '<tr align="center"><td class="grid">' .
	"<a href=\"javascript:;\" onclick=\"wrap('stm','$assign[$i]');\">$assign[$i]</a></td>";

      # Startup for profs:
      if ($utype eq 'prof') {
	$tab .= "<td class=\"grid\">";
	$tab .= (exists($cfg{startup}) ? $cfg{startup} : 'não há');
	$tab .= '</td>';
      }
      
      # Deadline:
      $tab .= "<td class=\"grid\">";
      $tab .= exists($cfg{deadline}) ? "$cfg{deadline} " : 'não há ';
      $tab .= '</td>';

      # State:
      $tab .= "<td class=\"grid\">";
      if (exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) {
	$tab .= 'fechado';
      }
      elsif (exists($cfg{deadline})) {
	$tab .= (elapsed_days($cfg{deadline})*$cfg{penalty} < 100 ? 'aberto' : 'encerrado');
      }
      else {
	$tab .= 'aberto';
      }
      $tab .= '</td>';

      if ($utype ne 'prof') {
	if (!exists($cfg{deadline}) || elapsed_days($cfg{deadline})*$cfg{penalty} < 100) {
	  push(@open,$assign[$i]);
	  push(@open_langs,$cfg{languages});
	}

	# Current score:
	%rep = get_rep_data("$assign[$i]/$uid/$uid.rep");
      
	if (exists($rep{score})) {
	  $tab .= '<td class="grid"><a href="javascript:;"' . 
	    "onclick=\"wrap('rep','$assign[$i]');\">$rep{score}</a>";
	}
	else {
	  $tab .= '<td class="grid">não houve';
	}
	$tab .= '</td>';
      }
      else {
	push(@open,$assign[$i]);
	push(@open_langs,$cfg{languages});
	
	opendir($DIR,$assign[$i]) || abort($uid,$assign[$i],"home : opendir $assign[$i] : $!.");
	@group = sort(grep {/\.pass$/ && -l "$assign[$i]/$_"} readdir($DIR));
	close($DIR);
	
	# Groups:
	$tab .= "<td class=\"grid\">";
	for ($j=0; $j<@group; $j++) {
	  $group = $group[$j];
	  $group =~ s/\.pass$//;
	  $tab .= "<a href=\"javascript:;\"" . 
	    "onclick=\"wrap('scr','$group','$assign[$i]');\">$group</a>&nbsp; ";
	  $groups{$group} = 1;
	}
	$tab .= '</td>';

	# Moss launcher:
	$tab .= "<td class=\"grid\"><a href=\"javascript:;\"" . 
	  " onclick=\"wrap('moss','$assign[$i]');\">comparar</a></td>";
      }
   
      $tab .= '</tr>';
     }

    $tab .= '</table></div>';
    
    # Score table links for prof:
    if ($utype eq 'prof') {
      #$tab .= '<div style="margin-top:20px"></div>';
      $tab .= "<p><b>Tabelas de acertos:</b></p>";
      $tab .= '<div class="f95">';
      $tab .= "Por grupo: ";
      
      @groups = sort keys(%groups);
      for ($j=0; $j<@groups; $j++) {
	$tab .= "<a href=\"javascript:;\"" . 
	  "onclick=\"wrap('asc','$groups[$j]');\">$groups[$j]</a>&nbsp; ";
      }
      $tab .= '</div>';
    }
  
    # "No assignments" message or submission controls:
    if (@assign == 0) {
      $scr = "<p>Não há trabalhos para $uid.</p>";
    }
    else {

	if (@open == 0) {
	    $scr .= $tab;
	}
	else {
      # js to force page reload:                                                
      $scr = '<script language=\"javascript\">' .                               
        'window.onpageshow = function(e) {' .                                   
        'if (e.persisted) { document.body.style.display = \"none\"; location.reload(); } };' .
        '</script>';                                                            
                       
      $scr .= $tab;

      # The assignments and languagess are added as variables loaded dinamically by JS.  
      # The assignment names, the language tags and the language labels go in
      # arrays of strings.  Languages for each statement are separated by |:
      $scr .= '<script type="text/javascript">';
      $scr .= 'var assignments = new Array(';      
  
      for ($i=0; $i<@open-1; $i++) {
	$scr .= "\"$open[$i]\",";
      }
      $scr .= "\"$open[$#open]\");";
     
      $scr .= 'var language_tags = new Array();';
      $scr .= 'var language_labels = new Array();';
      $scr .= 'language_tags[0] = "";';
      $scr .= 'language_labels[0] = "";';
      
      for ($i=0; $i<@open_langs; $i++) {
	@aux = split(/\s+/,$open_langs[$i]);
	
	$lang_tags = ''; 
	
	for ($j=0; $j<@aux-1; $j++) {
	  $lang_tags .= "$aux[$j]|";
	}
	$lang_tags .= "$aux[$j]";
	
	$j = $i+1;
	$scr .= "language_tags[$j] = \"$lang_tags\";";
	$scr .= "language_labels[$j] = \"$lang_tags\";";
      }

      $scr .= '</script>' .
	#'<div style="margin-top:20px"></div>' .
	'<p><b>Enviar:</b></p>' .
	'<div class="f95">' .
	'<table cellspacing="1" border="0">' .
	'<tr><td>Trabalho:</td><td><select name="submassign" id="submassign" ' .
	'  onchange="javascript:fill_langs(\'submassign\',\'language\')"></select></td></tr>' .
	'<tr><td>Linguagem:</td><td><select name="language" id="language"></select></td></tr>' .
	'<tr><td>Arquivos:</td><td>' .
	'  <input type="file" name="source" multiple size="30" maxlength="80"></td></tr>' .
	'<tr><td>&nbsp;</td><td>&nbsp;</td></tr>' .
	'<tr><td><input type="submit" class="button" name="subm" value="Enviar" ' .
	'  onclick="javascript:wrap(\'sub\')"></td><td></td></tr>'.
	'</table>' .
	'<script>fill_assigns("submassign","language");</script>' .
	'</div>';
    }
    }
    $session->param('screen',$scr);
  }

  print_start_html($first_login,'envio',0);
  print $scr;
  print_end_html();
}



################################################################################
sub show_subm_report {

  my ($FILE, $assign, $reportf, $uid, $upassf, $user, $userd, $utype, @files);

  $uid = $session->param('uid');
  $utype = $session->param('utype');
  $upassf = $session->param('upassf');

  $assign = param('arg1');
  $user = param('arg2');

  check_assign_access($uid,$upassf,$assign);

  ($utype eq 'prof' && $user ne 'undefined') && ($uid = $user);

  $userd = "$assign/$uid";
  $reportf = "$userd/$uid.rep";

  (!-e $reportf) && block_user($uid,$upassf,"Não existe arquivo $reportf, bloqueado.");

  # Print report:
  print_start_html(0,'saida',0);

  open($FILE,'<',$reportf) || abort($uid,$assign,"show_subm_report : open $reportf : $!");
  while (<$FILE>) {
    print $_;
  }
  close($FILE);

  print_end_html();
}



################################################################################
sub show_statement {

  my ($assign, $i, $uid, $upassf, $utype, %cfg, @aux);

  $uid = $session->param('uid');
  $utype = $session->param('utype');
  $upassf = $session->param('upassf');
  $assign = param('arg1');

  check_assign_access($uid,$upassf,$assign);

  print_start_html();

  (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));
  %cfg = (%sys_cfg, load_keys_values("$assign/config"));

  # If the assignment is not open yet for students, this is strange:
  ($utype ne 'prof' && exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) && 
    block_user($uid,$upassf,"O prazo para enviar $assign não começou, bloqueado.");

  print "<b>Trabalho:</b> $assign";
  print "<br>Linguagens: $cfg{languages}";
  
  # Pascal and Fortran are limited to a sigle source file:
  ($cfg{languages} eq 'Pascal' || $cfg{languages} eq 'Fortran') && ($cfg{sources} = '1,1');

  if (exists($cfg{sources})) {
    @aux = split(/,/,$cfg{sources});
    print "<br>Arquivos-fonte a enviar: " . 
      ($aux[0] == $aux[1] ? "$aux[0]." : "entre $aux[0] e $aux[1].");
  }

  if (exists($cfg{pdfs})) {
    @aux = split(/,/,$cfg{pdfs});
    print "<br>Arquivos pdf a enviar: " . 
      ($aux[0] == $aux[1] ? "$aux[0]." : "entre $aux[0] e $aux[1].");
  }

  if (exists($cfg{filenames})) {
    @aux = split(/ +/,$cfg{filenames});
    for ($i=0; $i<@aux; $i++) {
      $aux[$i] =~ s/\{uid\}/$uid/;
      $aux[$i] =~ s/\{assign\}/$assign/;
    }
    print "<br>Envie arquivos com nomes: @aux.";
  }

  exists($cfg{startup}) && print "<br>Data de abertura: $cfg{startup}";

  if (exists($cfg{deadline})) {
    print "<br>Data limite para envio: $cfg{deadline}";
    (elapsed_days($cfg{deadline})*$cfg{penalty} >= 100) && print ' (encerrado)';
    ($cfg{penalty} < 100) && print "<br>Multa por dia de atraso: $cfg{penalty}\%";
  }

  print "<br>Número máximo de envios: $cfg{tries}";

  if (-f "$assign/casos-de-teste.tgz") {
    print "<br>Casos-de-teste abertos: <a href=\"javascript:;\" " .
      "onclick=\"wrap('dwn','$assign','$assign/casos-de-teste.tgz')\";>casos-de-teste.tgz</a><br>";
  }

  if (exists($cfg{description})) {
    if ($cfg{description} =~ /^http/) {
      print "<p>Enunciado: <a href=\"$cfg{description}\">$cfg{description}</a>";
    }
    elsif (-f "$assign/$cfg{description}") {
      print '<hr>';
      print_html($assign,$cfg{description});
    }
    else {
      abort($uid,$assign,"description em config de $assign não é http nem arquivo.");
    }
  }
  else {
    print "<p>Não há enunciado para $assign.";
  }

  print_end_html();
}



################################################################################
sub show_about {

  print header();
  print start_html(-title=>'sqtpm', -style=>{-src=>['sqtpm.css'], -media=>'all'},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);

  print '<div class="f85">';
  print_html('','bula.html');
  print '<hr><a href="sqtpm.cgi">sqtpm</a></div>';
  print end_html();
}  



################################################################################
sub show_help {

  my $file = shift;

  print_start_html();
  print_html('',$file);
  print_end_html();
}  



################################################################################
sub download_file {

  my ($FILE, $assign, $file, $uid, $upassf);

  $uid = $session->param('uid');
  $upassf = $session->param('upassf');

  $assign = param('arg1');
  $file = param('arg2');

  # Check user access rights to assignment:
  check_assign_access($uid,$upassf,$assign);

  # Check file existance:
  if ($file ne "$assign/casos-de-teste.tgz") {
    $file = "$assign/$uid/$file";
    if (!-f $file) {
      block_user($uid,$upassf,"O arquivo $file não existe, bloqueado.");
    }
  }
  # Download:
  print "Content-Type:application/x-download\nContent-Disposition:attachment;filename=$file\n\n";

  open($FILE,'<',$file) || abort($uid,$assign,"download_file : open $file : $!");
  binmode $FILE;
  while (<$FILE>) {
    print $_;
  }
  close($FILE);
}



################################################################################
sub show_scores_table {

  my ($assign, $curr, $d, $date, $first, $i, $k, $last, $m, $n,
      $passf, $show, $show100, $size, $uid, $upassf, $user, $usersuf,
      $utype, $y, %cfg, %freq, %freq100, %langs, %rep, %scores, @aux,
      @f, @langs, @users);

  $uid = $session->param('uid');
  $utype = $session->param('utype');
  $upassf = $session->param('upassf');

  $passf = param('arg1').'.pass';
  $assign = param('arg2');

  check_assign_access($uid,$upassf,$assign);
  
  print_start_html();
  print "<p><b>Acertos para $passf em $assign:</b>";

  # Get users:
  @users = sort keys %{{load_keys_values($passf,':')}};
  if (@users == 0) {
    print '<p>Nenhum usuário em $passf.</p>';
    print_end_html();
    return;
  }

  (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));

  # Get users scores and build a hash having an array of student ids for each language:
  %scores = ();
  %langs = ();

  foreach $user (@users) {
    $usersuf = $user;
    $usersuf =~ s/^[\*@]?//;

    %rep = get_rep_data("$assign/$usersuf/$usersuf.rep");

    if (exists($rep{score})) { 
      $scores{$user} = '<a href="javascript:;"' . 
	"onclick=\"wrap('rep','$assign','$usersuf');\">$rep{score}</a>";

      (!exists($langs{$rep{lang}})) && ($langs{$rep{lang}} = ());
      push(@{$langs{$rep{lang}}},$user);
    }
    else {
      $scores{$user} = '-';
    }
  }

  @langs = keys(%langs);

  # Produce a report with a table with tuples {user,score}  
  print '<div class="f95" style="overflow-x:scroll">'.
    '<table border=0><tr><td valign=\'top\'>' .
    '<table class="grid">' . 
    "<tr><th class=\"grid\">Usuário</th><th class=\"grid\">$assign</th></tr>";

  $show = 0;
  $show100 = 0;

  foreach $user (@users) {
    print "<tr align=center>" . 
      "<td class=\"grid\"><b>$user</b></td><td class=\"grid\">$scores{$user}</td></tr>";
    ($scores{$user} ne '-') && ($show++);
    ($scores{$user} =~ '>100%</a>$') && ($show100++);
  }

  $n = @users;
  print '<tr align=center>' . 
    "<td class=\"grid\"><b>Total</b></td><td class=\"grid\" colspan=0>$n</td></tr>" .
    '<tr align=center><td class="grid"><b>Submetidos</b><br><b>%</b></td>';
 
  printf("<td class=\"grid\">%i<br>%.0f</td></tr>",$show,$n>0 ? 100*$show/$n : 0);
  print '<tr align=center><td class="grid"><b>100</b><br><b>%</b></td>';
  printf("<td class=\"grid\">%i<br>%.0f</td></tr>",$show100,$show>0 ? 100*$show100/$show : 0);
  print '</table>';


  @langs == 1 && print "<p>Todos em $langs[0].";

  print '</td><td valign=\'top\'>';

  # Submission histogram per day:
  %users = map { $_ => 1 } @users; # used by wanted_hist
  @grades = ();                    # modified by wanted_hist, holds the grades.    
  find(\&wanted_hist,"$assign");

  if (@grades) {

   %freq = ();
   %freq100 = ();

    for ($i=0; $i<@grades; $i+=2) {
      if (exists($freq{"$grades[$i]"})) {
	$freq{"$grades[$i]"}++;
      }
      else {
	$freq{"$grades[$i]"} = 1;
	$freq100{"$grades[$i]"} = 0;
      }

      if ($grades[$i+1] eq '100%') {
	$freq100{"$grades[$i]"}++;
      }
    }
    
    @f = sort { $a cmp $b } keys(%freq);
    $first = $f[0];
    $last = $f[$#f];
    
    %cfg = (%sys_cfg, load_keys_values("$assign/config"));
    
    if (exists($cfg{startup})) {
      $cfg{startup} =~ /(.*) .*/;
      $first gt $1 && ($first = $1);
    }

    if (exists($cfg{deadline})) {
      $cfg{deadline} =~ /(.*) .*/;
      $last lt $1 && ($last = $1);
      $last =~ s/-/\//g;
    }

    ($y, $m, $d) = split(/\//,$first);
    $first = timelocal(0, 0, 12, $d, $m - 1, $y - 1900);
    ($y, $m, $d) = split(/\//,$last);
    $last = timelocal(0, 0, 12, $d, $m - 1, $y - 1900);
    
    $curr = $first;
    while ($curr le $last) {
      
      @aux = localtime($curr);
      $date = sprintf("%04.0f/%02.0f/%02.0f",$aux[5]+1900,$aux[4]+1,$aux[3]);
      
      if (!exists($freq{$date})) {
	$freq{$date} = 0;
	$freq100{$date} = 0;
      }
      $curr += 24 * 60 * 60;
    }

    $size = keys %freq;
    histogram("$assign/histogram.png",$size<30?600:$size*25,360,\%freq,\%freq100);
    print "<img src=\"$assign/histogram.png\" style=\"border:0;padding: 0px 0px 0px 20px\">";
    print '</td></tr></table></div>';
  }

  if (@langs > 1) {
    # Produce a report with a table with tuples {user,score} for each language:  
    print "<p>&nbsp;</p><b>Acertos para $passf em $assign por linguagem:</b>";
    print '<table border=0><tr>';

    for $k (@langs) {
      print "<td valign='top'><b>$k:</b>" .
	'<div class="f95"><table class="grid">' . 
	"<tr><th class=\"grid\">Usuário</th><th class=\"grid\">$assign</th></tr>";

      $show = 0;
      $show100 = 0;
      @users = @{$langs{$k}};

      foreach $user (@users) {
	print '<tr align=center>' . 
	  "<td class=\"grid\"><b>$user</b></td><td class=\"grid\">$scores{$user}</td></tr>";
	
	($scores{$user} ne '-') && ($show++);
	($scores{$user} =~ '>100%</a>$') && ($show100++);
      }
      
      $n = @users;
      print "<tr align=center><td class=\"grid\"><b>Total</b></td><td class=\"grid\">$n</td></tr>";
      print '<tr align=center><td class="grid"><b>Submetidos</b><br><b>%</b></td>';
      printf("<td class=\"grid\">%i<br>%.0f</td></tr>",$show,$n>0 ? 100*$show/$n : 0);
      print '<tr align=center><td class="grid"><b>100</b><br><b>%</b></td>';
      printf("<td class=\"grid\">%i<br>%.0f</td></tr>",$show100,$show>0 ? 100*$show100/$show : 0);
      print '</table></div>';
      print '</td><td></td>';
    }
  }

  print_end_html();
}



################################################################################
sub show_all_scores_table {

  my ($DIR, $amnt, $i, $n, $passf, $uid, $upassf, $user,
      $usersuf, $utype, %rep, %scores, %show, %show100, @amnts, @users);

  $uid = $session->param('uid');
  $utype = $session->param('utype');
  $upassf = $session->param('upassf');

  $passf = param('arg1').'.pass';

  ($utype ne 'prof') && block_user($uid,$upassf,"$uid não é prof, bloqueado.");

  print_start_html();
  
  # Get a list of assignments for the user:
  opendir($DIR,'.') || abort($uid,'','all_scores : opendir root : $!).');
  @amnts = sort(grep { -d $_ && !/^\./ && -f "$_/config" && -l "$_/$passf" } readdir($DIR));
  close($DIR);
  
  if (@amnts == 0) {
    print "Não há trabalhos para $passf.";
    print_end_html();
  }

  print "<p><b>Acertos para $passf:</b></p>";

  # Get users:
  @users = sort keys %{{load_keys_values($passf,':')}};

  # Build the structure: $scores{assignment}{id} = score.
  %scores = ();

  for ($i=@amnts-1; $i>=0; $i--) {
    $scores{$amnts[$i]} = { () };

    foreach $user (@users) {
      $usersuf = $user;
      $usersuf =~ s/^[\*@]?//;

      %rep = get_rep_data("$amnts[$i]/$usersuf/$usersuf.rep");

      if ($rep{tries} > 0) {
	$rep{score} =~ s/%//;
	$rep{score} =~ s/recebido/r/;
	$scores{$amnts[$i]}{$user} = '<a href="javascript:;"' . 
	  "onclick=\"wrap('rep','$amnts[$i]','$usersuf');\">$rep{score}</a>";
      }
      else {
	$scores{$amnts[$i]}{$user} = '-';
      }
    }
  }

  # Print a report with a table with tuples {user,score,score,...} and summaries:
  print '<div style="overflow-x:scroll"><div class="f95">' .
    '<table class="grid"><tr><th class="grid">Usuário</th>';

  %show = ();
  %show100 = ();

  foreach $amnt (@amnts) {
    print "<th class=\"grid\">$amnt";
    $show{$amnt} = 0;
    $show100{$amnt} = 0;
  }

  foreach $user (@users) {
    print "<tr align=center><td class=\"grid\"><b>$user</b>";
    foreach $amnt (@amnts) {
      print "<td class=\"grid\">$scores{$amnt}{$user}</td>";
      ($scores{$amnt}{$user} ne '-') && ($show{$amnt}++);
      ($scores{$amnt}{$user} =~ '>100</a>$') && ($show100{$amnt}++);
    }
    print '</tr>';
  }

  $n = @users;
  print "<tr align=center>" . 
    "<td class=\"grid\"><b>Total</b></td><td class=\"grid\" colspan=0>$n</td></tr>" .
    '<tr align=center><td class="grid"><b>Submetidos</b><br><b>%</b></td>';

  foreach $amnt (@amnts) {
    printf("<td class=\"grid\">%i<br>%.0f</td>",$show{$amnt},$n>0 ? 100*$show{$amnt}/$n : 0);
  }

  print '</tr><tr align=center><td class="grid"><b>100</b><br><b>%</b></td>';
  foreach $amnt (@amnts) {
    printf("<td class=\"grid\">%i<br>%.0f</td>",
	   $show100{$amnt},$show{$amnt}>0 ? 100*$show100{$amnt}/$show{$amnt} : 0);
  }

  print '</tr></table></div></div>';
  print_end_html();
}



################################################################################
sub submit_assignment {

  my ($DIR, $MAKE, $REPORT, $SOURCE, $STATUS, $assign, $backupd,
      $case, $case_out, $casei, $cmd, $compcmd, $date, $discount,
      $elff, $errf, $exec_err, $exec_out, $exec_st, $fh, $full_score,
      $href, $i, $j, $language, $ncases, $newd, $now, $outf, $passed,
      $rep, $score, $scr, $source, $status, $tries, $uid, $upassf, $userd,
      $utype, %cfg, %exts, %failed, %names, %rep, @aux, @fh, @pdfs, @show,
      @sources, @test_cases, @uploads);

  $uid = $session->param('uid');
  $utype = $session->param('utype');
  $upassf = $session->param('upassf');

  $assign = param('submassign');
  $language = param('language');
  @uploads = param('source');
  @uploads = grep(/\S+/,@uploads);

  print_start_html(0,'saida',1);

  # Check assign:
  (!$assign) && abort($uid,'',"Selecione um trabalho.");

  # Check access:
  check_assign_access($uid,$upassf,$assign);

  # Load system and assignment configs:
  (!%sys_cfg) && (%sys_cfg = load_keys_values('sqtpm.cfg'));
  %cfg = (%sys_cfg, load_keys_values("$assign/config"));

  # Check if the assignment is open:
  ($utype eq 'capivara' && 
   exists($cfg{deadline}) && elapsed_days($cfg{deadline})*$cfg{penalty} >= 100) && 
   abort($uid,$assign,"O prazo para enviar $assign terminou.");
  
  ($utype ne 'prof' && exists($cfg{startup}) && elapsed_days($cfg{startup}) < 0) && 
    block_user($uid,$upassf,"O prazo para enviar $assign não começou, bloqueado.");

  # Check language:
  (!$language) && abort($uid,$assign,'Selecione uma linguagem.');
  
  (!grep(/$language/,split(/\s+/,$cfg{languages}))) && 
    abort($uid,$assign,"$assign não pode ser enviado em $language.");
  
  # Check the number of uploading files and their names: 
  @pdfs = grep(/\.pdf$/ && /^[0-9a-zA-Z_\.\-]+$/,@uploads);
  
  if ($language eq 'PDF') {
    ($cfg{sources} = '0,0');
    (!exists($cfg{pdfs})) && ($cfg{pdfs} = '1,999');
  }
  else {
    (!exists($cfg{pdfs})) && ($cfg{pdfs} = '0,0');
    %exts = ('C'=>'(c|h)','C++'=>'(cpp|h)','Pascal'=>'pas','Fortran'=>'(f|F)');
    @sources = grep(/$exts{$language}$/ && /^[0-9a-zA-Z_\.\-]+$/,@uploads);  
    (!exists($cfg{sources})) && ($cfg{sources} = '1,999');
    # Pascal and Fortran are limited to a sigle source file:
    ($language eq 'Pascal' || $language eq 'Fortran') && ($cfg{sources} = '1,1');
  }

  $cfg{sources} =~ /(\d+),(\d+)/;
  (@sources < $1 || @sources > $2) && 
    abort($uid,$assign,"Envie o número correto de arquivos-fonte.");

  $cfg{pdfs} =~ /(\d+),(\d+)/;
  (@pdfs < $1 || @pdfs > $2) && 
    abort($uid,$assign,"Envie o número correto de arquivos pdf.");

  if (exists($cfg{filenames})) {
    %names = ();
    @aux = split(/ +/,$cfg{filenames});
    for ($i=0; $i<@aux; $i++) {
      $aux[$i] =~ s/\{uid\}/$uid/;
      $aux[$i] =~ s/\{assign\}/$assign/;
      $names{$aux[$i]} = 1;
    }
    if (keys(%names) > 0) {
      for ($i=0; $i<@uploads; $i++) {
	delete($names{$uploads[$i]});
      }
      (keys(%names) > 0) && abort($uid,$assign,"Envie arquivos com nomes: @aux.") ;
    }
  }
  
  # Read tries from the existing report file or set it to 0:
  $tries = 0;
  if (-e "$assign/$uid/$uid.rep") {
    %rep = get_rep_data("$assign/$uid/$uid.rep");
    $tries = $rep{tries};
  }
  $tries++;

  # Check the maximum number of submissions:
  ($utype eq 'capivara' && $tries >= $cfg{tries}) && 
    abort($uid,$assign,"Você não pode enviar $assign mais uma vez.");

  # Create a directory:
  $userd = "$assign/_${uid}_tmp_";
  mkdir($userd) || abort($uid,$assign,"submit : mkdir $userd : $!");
 

  # Report header:
  $rep = "<b>Usuário: $uid</b><br>\n";
  $rep .= "<b>Trabalho: $assign</b><br>\n";
  
  if (exists($cfg{deadline})) {
    $rep .= "Data limite para envio: $cfg{deadline}<br>\n";
    ($cfg{penalty} < 100) && ($rep .= "Penalidade por dia de atraso: $cfg{penalty}%<br>\n");
  }
  
  ($utype ne 'capivara') && ($rep .= "$uid: envios sem restrições de linguagem e prazo.<br>\n");
  $rep .= "Número máximo de envios: $cfg{tries}<br>\n";

  $now = format_epoch(time);
  $rep .= "Este envio: $tries&ordm;, $now<br>\n", ;

  $rep .= "Linguagem: $language<br>\n";
  $rep .= (@uploads == 1 ? "Arquivo: " : "Arquivos: ");

  # Upload source files and documents:
  if (@pdfs) {
    %exts = ('PDF'=>'pdf', 'C'=>'(c|h|pdf)', 'C++'=>'(cpp|h|pdf)',
	     'Pascal'=>'(pas|pdf)', 'Fortran'=>'(f|F|pdf)');
  }

  @fh = upload('source');    
  @sources = ();
  @pdfs = ();
  for ($i=0; $i<@fh; $i++) {
    ($uploads[$i] !~ /\.$exts{$language}$/ || $uploads[$i] !~ /^[a-zA-Z0-9_\.\-]+$/) && next;

    open($SOURCE,'>',"$userd/$uploads[$i]") || 
      abort($uid,$assign,"submit : open $userd/$uploads[$i] : $!");

    $fh = $fh[$i];
    if ($uploads[$i] =~ /\.pdf$/) {
      binmode $SOURCE;
      while (<$fh>){
	print $SOURCE;
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

  # Include links for sources and documents:
  for ($i=0; $i<@sources; $i++) {
    $rep .= '<a href="javascript:;" ' . 
      "onclick=\"toggleDiv('$sources[$i]');\">$sources[$i]</a>&nbsp;";
  }
  for ($i=0; $i<@pdfs; $i++) {
    $rep .= '<a href="javascript:;" ' . 
      "onclick=\"wrap('dwn','$assign','$pdfs[$i]');\">$pdfs[$i]</a>&nbsp; ";
  }

  $href = $cgi->url();
  $href =~ s/\/[^\/]+$//;
  $href .= '/google-code-prettify';
  $rep .= "<link href=\"$href/prettify.css\" type=\"text/css\" rel=\"stylesheet\">" .
    "<script type=\"text/javascript\" src=\"$href/run_prettify.js\"></script>";

  # Include source files:
  for ($i=0; $i<@sources; $i++) {
    $rep .= "<div id=\"$sources[$i]\" style=\"display:none\" class=\"src\">" . 
      "<b>$sources[$i]</b>&nbsp;&nbsp;" . 
      "<a href=\"javascript:;\" onclick=\"wrap('dwn','$assign','$sources[$i]')\">download</a>";

    $source = "$userd/$sources[$i]";
    if ($sources[$i] =~ /\.c$/ || $sources[$i] =~ /\.h$/) {
      $rep .= '<pre class="prettyprint lang-c" id="C_lang">';
      if (-x "$cfg{indent}") {
	system("$cfg{indent} -kr $source -o $source.indent 2>/dev/null");
	$rep .= load($uid,$assign,"$source.indent",1);
      }
      else {
	$rep .= '<pre class="prettyprint">';
	$rep .= load($uid,$assign,"$source",1);
      }
    }
    else {
      $rep .= '<pre class="prettyprint">';
      $rep .= load($uid,$assign,"$source",1);
    }
    
    $rep .= '</pre></div>'; 
  }

  # If this is a PDF statement, there is nothing else to do:
  if ($language eq 'PDF') {
    $rep .= "<br>\nRecebido.<br>\n";
    $score = 'recebido';
    @test_cases = ();
  }
  else {
    # Load test-case names early to produce correct messages for compiling errors:
    opendir($DIR,"$assign") || abort($uid,$assign,"submit : opendir $assign : $!");
    @test_cases = sort(grep {/\.in$/ && -f "$assign/$_"} readdir($DIR));
    close($DIR);

    $ncases = @test_cases;

    for ($i=0; $i<$ncases; $i++) {
      $test_cases[$i] =~ s/\.in$//;
    }

    $score = 0;

    # Compile the program:
    $rep .= '<p><b>Compilação:</b>&nbsp;';

    if ($language eq 'C') {
      (!-x $cfg{gcc}) && abort($uid,$assign,"submit : $cfg{gcc} inválido");

      (!exists($cfg{'gcc-args'})) && ($cfg{'gcc-args'} = '');
      open($MAKE,'>',"$userd/Makefile") || 
	abort($uid,$assign,"submit : write $userd/Makefile : $!");

      print $MAKE "CC=$cfg{gcc}\n" .
	'SRC=$(wildcard *.c)' . "\n" .
	'elf: $(SRC:%.c=%.o)' . "\n" .
	"\t" . '$(CC) ' . $cfg{'gcc-args'} . ' -o $@ $^' . "\n" .
	"clean:\n" .
	"\t/bin/rm -r *.o\n";

      close($MAKE);    
      $compcmd = "$cfg{'make'}";
    }
    elsif ($language eq 'C++') {
      (!-x $cfg{'g++'}) && abort($uid,$assign,"submit : $cfg{'g++'} inválido");

      (!exists($cfg{'g++-args'})) && ($cfg{'g++-args'} = '');
      open($MAKE,'>',"$userd/Makefile") || 
	abort($uid,$assign,"submit : write $userd/Makefile : $!");

      print $MAKE "CC=$cfg{'g++'}\n" .
	'SRC=$(wildcard *.cpp)' . "\n" .
	'elf: $(SRC:%.cpp=%.o)' . "\n" .
	"\t" . '$(CC) ' . $cfg{'g++-args'} . ' -o $@ $^' . "\n" .
	"clean:\n" .
	"\t/bin/rm -r *.o\n";

      close($MAKE);
      $compcmd = "$cfg{'make'}";
    }
    elsif ($language eq 'Fortran') {
      (!-x $cfg{gfortran}) && abort($uid,$assign,"submit : $cfg{gfortran} inválido");

      (!exists($cfg{'gfortran-args'})) && ($cfg{'gfortran-args'} = '');
      $compcmd = "$cfg{gfortran} $cfg{'gfortran-args'} $sources[0] -o elf";
    }
    elsif ($language eq 'Pascal') {
      (!-x $cfg{gpc}) && abort($uid,$assign,"submit : $cfg{gpc} inválido");

      (!exists($cfg{'gpc-args'})) && ($cfg{'gpc-args'} = '');
      $compcmd = "$cfg{gpc} $cfg{'gpc-args'} --executable-file-name=elf --automake $sources[0]";
    }
    else {
      block_user($uid,$upassf,"$language não existe, bloqueado.");
    }

    $status = system("cd $userd; $compcmd 1>out 2>err");
    $elff = "$userd/elf";
    $outf = "$userd/out";
    $errf = "$userd/err";

    if ($status) {
      $rep .= 'com erros.<br>' . "<div class=\"io\">$compcmd<br>"; 
      $rep .= load($uid,$assign,$outf,0);
      $rep .= load($uid,$assign,$errf,0,2500);
      $rep .= "</div><p>\n<b>Acerto:</b> 0%<br>\n";
      $score = 0;
    }
    else {
      if (-s "$errf") {
	$rep .= "com warnings.<br>" . "<div class=\"io\">$compcmd<br>"; 
	$rep .= load($uid,$assign,$outf,0);
	$rep .= load($uid,$assign,$errf,0,2500);
	$rep .= "</div>\n";
      }
      else {
	$rep .= "bem sucedida.<br>\n";
      }

      # No test cases:
      if ($ncases == 0) {
	$rep .= "<p><b>Nenhum caso de teste.</b><br>";

	$score = $full_score = 100;	
	$discount = 0;
	if ($utype eq 'capivara' && exists($cfg{deadline})) {
	  $discount = elapsed_days($cfg{deadline}) * $cfg{penalty} / 100;
	  ($discount > 0) && ($score = $full_score * (1 - $discount));
	  ($score < 0) && ($score = 0);
	}

	$rep .= "\n<b>Acerto:</b> " . sprintf("%.0f%%", $score);

	if ($discount > 0 && $full_score > 0) {
	  $rep .= sprintf(", desconto de %.0f%% sobre %.0f%% por atraso desde %s.", 
			  100*$discount, $full_score, $cfg{deadline});
	}
	$rep .= "<br>\n";
      }

      # Dispatch test cases execution:
      else {
	$rep .= "<p><b>Execução dos casos-de-teste:</b><p>\n";

	$cmd = "./sqtpm-etc.sh $uid $assign $cfg{cputime} $cfg{virtmem} $cfg{stkmem} >/dev/null 2>&1";
	system($cmd);
	($? >> 8) && abort($uid,$assign,"submit : system $cmd : $!");

	# Adjust verifier path:
	(exists $cfg{verifier}) && ($cfg{verifier} =~ s/\@/$assign\//);

	# Process every test case result:
	%failed = ();
	$passed = 0;
	$casei = 1;

	foreach $case (@test_cases) {

	  $case_out = "$assign/$case.out";
	  $exec_st = "$userd/$case.run.st";
	  $exec_out = "$userd/$case.run.out";
	  $exec_err = "$userd/$case.run.err";

	  $failed{$case} = $casei;

	  if (open($STATUS,"<$exec_st")) {
	    $status = <$STATUS>;
	    chomp($status);
	    $status -= 128;
	    close($STATUS);
	  }
	  else {
	    $status = 11;
	  }

	  $rep .= sprintf("%.02d:&nbsp;",$casei);

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
	    $rep .= "erro de execução ($status).<br>";
	    (-s $exec_err) && 
	      ($rep .= '<div class="io">' . load($uid,$assign,$exec_err,0,1000) . "</div>\n");
	  }
	  else {
	    if (exists($cfg{verifier})) {

	      system("$cfg{verifier} $assign/$case.in $exec_out >/dev/null 2>&1");
	      $status = $? >> 8;

	      if ($status == 0) {
		$rep .= 'bem sucedido.<br>';
		$failed{$case} = 0;
		$passed++;
	      }
	      elsif ($status == 1) {
		$rep .= 'saída incorreta.<br>';
	      }
	      elsif ($status == 2) {
		$rep .= 'saída com formatação incorreta.<br>';
	      }
	      else {
		abort($uid,$assign,'Erro ao executar o verificador.');
	      }
	    }
	    else {
	      system("$cfg{diff} -q $case_out $exec_out >/dev/null 2>&1");
	      $status = $? >> 8;

	      if ($status == 0) {
		$rep .= 'saída correta.<br>';
		$failed{$case} = 0;
		$passed++;
	      }
	      elsif ($status == 1) {
		system("$cfg{diff} -q -b -B -i -w $case_out $exec_out >/dev/null 2>&1");
		$status = $? >> 8;

		if ($status == 0) {
		  $rep .= 'saída com formatação incorreta.<br>';
		}
		elsif ($status == 1) {
		  $rep .= 'saída incorreta.<br>';
		}
	      }
	      else {
		abort($uid,$assign,"Erro ao executar diff $case_out $exec_out.");
	      }
	    }
	  }
	  $casei++;
	}

	$rep .= "<br>Número de casos-de-teste: $ncases.<br>\n" .
	  "Casos-de-teste bem sucedidos: $passed.<br>\n";

	if ($cfg{'scoring'} eq 'total') {
	  $full_score = ($passed == $ncases ? 100 : 0);
	}
	else {
	  $full_score = $passed/$ncases*100;
	}

	$score = $full_score;

	$discount = 0;
	if ($utype eq 'capivara' && exists($cfg{deadline}) && $score > 0) {
	  $discount = elapsed_days($cfg{deadline}) * $cfg{penalty} / 100;
	  $discount > 0 && ($score = $full_score * (1 - $discount));
	  ($score < 0) && ($score = 0);
	}

	$rep .= "\n<b>Acerto:</b> " . sprintf("%.0f%%", $score);

	if ($discount > 0 && $full_score > 0) {
	  $rep .= sprintf(", desconto de %.0f%% sobre %.0f%% por atraso desde %s.", 
			  100*$discount, $full_score, $cfg{deadline});
	}
	$rep .= "<br>\n";

	# Show the cases that have failed and are supposed to be shown:
	if (exists($cfg{showcases})) {
	  @show = split(/\s+/,$cfg{showcases});

	  for ($i=0; $i<@show; $i++) {
	    if ($failed{$show[$i]}) {

	      $rep .= sprintf("<br><b>Execução do caso %.02d:</b><p>",$failed{$show[$i]});

	      $rep .= 'Entrada:<br><div class="io">';
	      $rep .= load($uid,$assign,"$assign/$show[$i].in",0);
	      $rep .= "\n</div>";

	      if (!exists($cfg{verifier})) {
		$rep .= '<p>Saída esperada:<br><div class="io">';
		$rep .= load($uid,$assign,"$assign/$show[$i].out",0);
		$rep .= "\n</div>";
	      }

	      $j = (-s "$userd/$show[$i].run.out")*2;
	      ($j < 2500) && ($j = 2500);

	      $rep .= '<p>Saída produzida:<br><div class="io">';
	      $rep .= load($uid,$assign,"$userd/$show[$i].run.out",0,$j);
	      $rep .= "\n</div>";
	      $rep .= '<hr>';
	    }
	  }
	}
      }
    }
    $score = sprintf("%.0f%%",$score);
  }

  # Add data to parse easily later:
  $rep = "<!--lang:$language-->\n" . "<!--score:$score-->\n" . 
    "<!--tries:$tries-->\n" . "<!--at:$now-->\n" . $rep;

  open($REPORT,'>',"$userd/$uid.rep") || abort($uid,$assign,"submit : write $userd/$uid.rep : $!");
  print $REPORT $rep;
  close($REPORT);

  print $rep;
  print end_html();

  # Clean-up:
  ($elff && -e $elff) && unlink($elff);
  ($outf && -e $outf) && unlink($outf);
  ($errf && -e $errf) && unlink($errf);

  foreach $case (@test_cases) {
    (-e "$userd/$case.run.st")  && unlink("$userd/$case.run.st");
    (-e "$userd/$case.run.out") && unlink("$userd/$case.run.out");
    (-e "$userd/$case.run.err") && unlink("$userd/$case.run.err");
  }

  (-e "$userd/Makefile") && (system("cd $userd; $cfg{'make'} clean 1>/dev/null 2>&1"));

  # Move previous assignment and rename $userd:
  $tries--;
  if ($tries > 0) {
    if ($cfg{backup} eq 'on') {

      $date = format_epoch((stat("$assign/$uid/$uid.rep"))[9]);
      $date =~ s/[:\/]//g;
      $date =~ s/ /-/g;
      
      $backupd = "$assign/backup";
      if (!-d $backupd) {
	(-e $backupd) && abort($uid,$assign,"submit : $backupd is a file");
	mkdir($backupd) || abort($uid,$assign,"submit : mkdir $backupd : $!");
      }
      
      $newd = "$backupd/$uid.$tries.$date";
      rename("$assign/$uid",$newd) || abort($uid,$assign,"submit : mv $assign/$uid $newd : $!");
    }
    else {
      unlink glob "$assign/$uid/*";
      rmdir "$assign/$uid";
    }
  }

  rename($userd,"$assign/$uid") || abort($uid,$assign,"submit : mv '$userd' '$assign/$uid' : $!");

  # Write log:  
  wlog($uid,$assign,$score);

  if ($utype eq 'capivara') {
    # Update home screen:
    $scr = $session->param('screen');

    $i = index($scr,">$assign<");
    $i += index(substr($scr,$i),'<td ') + 3;
    ($utype eq 'prof') && ($i += index(substr($scr,$i),'<td ') + 3);
    ($utype eq 'prof') && ($i += index(substr($scr,$i),'<td ') + 3);
    $i += index(substr($scr,$i),'<td ') + 3;
    $i += index(substr($scr,$i),'<td ');

    $j = index(substr($scr,$i),'<tr ');
    ($j == -1) && ($j = index(substr($scr,$i),'</table>'));
    $j += $i;
  
    $session->param('screen',substr($scr,0,$i) . 
	       "<td class=\"grid\"><a href=\"javascript:;\" onclick=\"wrap('rep','$assign');\">" . 
		  "$score</a></td>" . substr($scr,$j));
  }
}



################################################################################
sub moss {

  my ($assign, $cmd, $url, $i, $recursive, $run_age, $st, $uid, @out);

  $uid = shift;
  $assign = shift;
  $recursive = shift;

  %sys_cfg = load_keys_values('sqtpm.cfg');

  (!$recursive) && print_start_html();
  
  @sources = ();
  find(\&wanted_moss,"./$assign");

  (@sources < 2) && abort($uid,$assign,"Deve haver pelo menos dois arquivos para comparar.");

  $url = '';
  if (-f "$assign/moss.run") {

    # Check if last moss run is up and whether there is a newer source:
    open(OUT,"<","$assign/moss.run") || abort($uid,$assign,"moss : open $assign/moss.run : $!");
    @out = <OUT>;
    close(OUT);
    $url = $out[-1];

    if (head("$url")) {
      $run_age = (stat "$assign/moss.run")[9];
      for ($i=0; $i<@sources; $i++) {
	if ($run_age < (stat $sources[$i])[9]) {
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
    open(LOCK,'>',"$assign/moss.lock") || abort($uid,$assign,"moss : open $assign/moss.lock : $!");
    flock(LOCK,LOCK_EX|LOCK_NB) || abort($uid,$assign,"Comparando $assign, aguarde.");
      
    $cmd = "perl moss-sqtpm $sys_cfg{'moss-id'} -m $sys_cfg{'moss-m'} " .
      "-d @sources 1>$assign/moss.run 2>$assign/moss.err";
    system($cmd);
    $st = $? >> 8;

    flock(LOCK,LOCK_UN);
    close(LOCK);
    unlink("$assign/moss.lock");

    $st && abort($uid,$assign,"moss : system $cmd : $!.");

    open(OUT,"<","$assign/moss.run") || abort($uid,$assign,"moss : open $assign/moss.run : $!");
    @out = <OUT>;
    close(OUT);
    $url = $out[-1];

    if ($url !~ /^http:/) {
      unlink("$assign/moss.run");
      moss($uid,$assign,1);
      abort($uid,$assign,"A execução do Moss falhou.");
    }
  }
  
  # Redirect:
  print "<meta http-equiv=\"refresh\" content=\"0; url=$url\" />";
  print_end_html();
}



################################################################################
# print_start_html($first_login,$help,$back)
#
# first_login: 1 if the session is starting, 0 if it existed already.
# help: the help html file.
# back link: 0 or null is back to previous page, 1 is forced back to sqtpm.cgi.

sub print_start_html {

  my $first_login = shift;
  my $help = shift;
  my $back = shift;

  if ($first_login) {
    print header(-cookie=>$cgi->cookie(CGISESSID => $session->id));
  }
  else {
    print header();
  }

  print start_html(-title=>'sqtpm', -style=>{-src=>['sqtpm.css'], -media=>'all'},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);
  
  print '<div id="wrapper"><div id="sidebar"><h1>sqtpm</h1>';
  print '<p style="margin-top:-15px"><small>[',substr($session->param('uid'),0,7),']</small></p>';
  $help && print "<a href=\"javascript:;\" onclick=\"wrap('hlp','$help')\">ajuda</a><br>";
    
  if ($help && $help eq 'envio') {
    print '<a href="javascript:;" onclick="wrap(\'out\');">sair</a>';
  }
  elsif ($back) {
    print '<a href="sqtpm.cgi">voltar</a>';
  }
  else {
    print '<a href="javascript:;" onclick="history.go(-1); return false;">voltar</a>';
  }    
  
  print '</div><div id="content">';
  
  # There will always be a form named sqtpm with hidden fields to handle actions through wrap():
  print '<form method="post" action="sqtpm.cgi" enctype="multipart/form-data" name="sqtpm">' .
    '<script type="text/javascript" src="sqtpm.js"></script>' .
    '<input type="hidden" name="action">' .
    '<input type="hidden" name="arg1">' . 
    '<input type="hidden" name="arg2">';
}



################################################################################
# sub print_end_html(help)

sub print_end_html() {

  print '</form></div>';
  print end_html();
}



################################################################################
# check_assign_access(user,pass_file,assignment)
#
# Verify whether the user in the .pass file may access an assignment,
# blocking the user if he may not.

sub check_assign_access {

  my $uid = shift;
  my $upassf = shift;
  my $assign = shift;

  (-d $assign && -e "$assign/$upassf") && (return 1);

  block_user($uid,$upassf,"$upassf não está em $assign, bloqueado.");
}



################################################################################
# block_user(user,pass_file,messsage)
#
# Block user in .pass file and logout silently, writing the message to the log.

sub block_user {

  my ($PASS, $lines, $mess, $uid, $upassf);

  $uid = shift;
  $upassf = shift;
  $mess = shift;

  # If the user may not see the assignment, block him and logout:
  $lines = '';
  open($PASS,'+<',$upassf);
    
  while (<$PASS>) {
    (/^([\*\@]?)$uid:?/) && ($_ = "# blocked! $_");
    $lines .= $_;
  }

  flock($PASS,LOCK_EX);
  seek($PASS,0,0);
  print $PASS $lines;
  flock($PASS,LOCK_UN);
  close($PASS);

  wlog($uid,$upassf,$mess);
  $session->delete();
  exit(0);
}



################################################################################
# A wanted function to find sources for moss.  It uses @sources from
# an outer scope.

sub wanted_moss {
  -f && 
    !($File::Find::name =~ /\/backup\//) && 
    (/\.c$/ || /\.cpp$/ || /\.h$/ || /\.pas$/ || /\.f$/ || /\.F$/) && 
    (push(@sources,"$File::Find::name"));
}



################################################################################
# A wanted function to collect data for the histogram, using %users
# and @grades from an outer scope.

sub wanted_hist {
 
  /\.rep$/ && do {
    my $file = $_;
    /^(\w+)\./;

    !exists($users{$1}) && !exists($users{"*$1"}) && return;

    %rep = get_rep_data($file);
    push(@grades,(split(/ /,$rep{at}))[0]);
    push(@grades,$rep{score});
  };

  return;
}



################################################################################
# histogram($png_file, $png_width, $png_height, \%data1, \%data2)
# 
# A histogram for two data series.  Each data series is a hash with
# keys -> value.  The data series must have the same set of keys.  The
# values in the second data series should be smaller than those in the
# first.
#
# This function was written in 1999 or 2000 for a single series and
# adapted for two series.

sub histogram {

  my ($aux, $aux1, $bar_separation, $black, $blue, $darkgreen,
      $data1, $data2, $filled_x, $filled_y, $free_axis_end, $gray, $i, $im,
      $l, $max_x, $max_y, $pairs_total, $png_file, $png_height, $png_width,
      $purple, $red, $tfh, $tfw, $up_text, $value, $white, $x_margin,
      $x_scale, $x_text_area, $x_zero, $y_margin, $y_scale, $y_text_area,
      $y_zero, @x, @y);

  $png_file = shift;
  $png_width = shift;
  $png_height = shift;
  $data1 = shift;
  $data2 = shift;

  $im = new GD::Image($png_width, $png_height);

  $white = $im->colorAllocate(255,255,255);
  $black = $im->colorAllocate(0,0,0);
  $red = $im->colorAllocate(180,0,0);
  $darkgreen = $im->colorAllocate(0,180,0);
  $blue = $im->colorAllocate(0,0,220);
  $gray = $im->colorAllocate(225,225,225);
  $purple = $im->colorAllocate(146,50,172);

  ($tfw, $tfh) = (gdSmallFont->width, gdSmallFont->height);
  
  # Draw a border:
  $im->rectangle(0, 0, $png_width-1, $png_height-1, $black);
  $im->fill(1, 1, $gray);

  ### Find maximum in y:
  $max_y = 0;
  $max_x = 0; 
  $pairs_total = 0;
  foreach $value (keys(%$data1)) {
    $pairs_total++;
    $l = length($value);
    if ($max_x < $l) {
      $max_x = $l;
    }
    if ($max_y < $$data1{$value}) {
      $max_y = $$data1{$value};
    }
  }

  ### Set margins and such:
  $x_margin = 10;
  $y_margin = 10;
  $free_axis_end = 5;
  $y_text_area = 4+(length("$max_y")*$tfw);
  $x_text_area = 4+($max_x*$tfw);

  ### Eval x and y scales:
  $x_scale = ($png_width - (2*$x_margin) - $y_text_area
	      - (2*$free_axis_end)) / $pairs_total;

  if ($x_scale > 40) {
    $x_scale = 40;
  }

  $up_text = 0;
  if ($x_scale < $max_x*1.2*$tfw) {
    $up_text = 1;
    $x_text_area = $max_x*1.2*$tfw;
  }
  else{
    $up_text = 0;
    $x_text_area = 20;
  }

  $y_scale = ($png_height-(2*$y_margin)-(2*$free_axis_end)-
	      $x_text_area) / $max_y;
    

  ### Print y axis:
  $x_zero = $x_margin + $free_axis_end + $y_text_area;
  $y_zero = $png_height - $y_margin - $free_axis_end - $x_text_area;

  $im->line($x_zero, 
	    $y_margin, 
	    $x_zero,
	    $png_height - $y_margin, 
	    $black);


  ### Print x axis:
  $im->line($x_margin, 
		 $y_zero,
		 $png_width - $x_margin, 
		 $y_zero,
		 $black);


  ### Print y values:
  @y = values(%$data1);
  push(@y,values(%$data2));
  $filled_y = 0;
  $aux1 = length("$max_y");
  foreach $value (sort {$b <=> $a} @y) {

    if ($value > 0) {
      $im->rectangle($x_zero - 3, 
		     $y_zero-$value*$y_scale, 
		     $x_zero, 
		     $y_zero-$value*$y_scale, 
		     $black);
      
      if ($y_zero-($value*$y_scale)-$tfh > $filled_y && 
	  $y_zero-($value*$y_scale)-$tfh < $y_zero - 1.5*$tfh) {
	
	$aux = sprintf("%${aux1}i",$value);
	$im->string(gdSmallFont, $x_margin + $free_axis_end, 
		    $y_zero-$value*$y_scale-($tfh/2), 
		    "$aux",$blue);
	$filled_y = $y_zero-$value*$y_scale;
      }
    }
  }

  $bar_separation = 7;
 
  ### Print x values:
  @x = sort {$a cmp $b} keys(%$data1);
  $filled_x = $x_zero;
  $aux1 = $max_x;
  $i = 1;

  if (!$up_text) {
    foreach $value (@x) {
      $im->string(gdSmallFont, 
		  $x_zero+($bar_separation/2)+(($i-1)*$x_scale)+($x_scale/2)
		  -(length("$value")*$tfw/2), 
		  $y_zero+$tfh, 
		  "$value",
		  $blue);
      $i++;
    }
  }
  else{
    foreach $value (@x) {
      $aux = sprintf("%${aux1}s",$value);
      $im->stringUp(gdSmallFont, 
		    $x_zero+($bar_separation/2)+(($i-1)*$x_scale)+($x_scale/2)
		    -$tfh/2,
		    $png_height-$y_margin-$free_axis_end, 
		    "$aux",
		    $blue);
      $i++;
    }
  }

  ### Print bars for data1:
  $i = 1;
  $value = 0;
  foreach $value (sort {$a cmp $b} keys(%$data1)) {
    $im->filledRectangle($x_zero + $bar_separation + (($i-1)*$x_scale),
			 $y_zero,
			 $x_zero + ($i*$x_scale),
			 $y_zero - ($$data1{$value}*$y_scale),
			 $black);
    $i++;
  }

  ### Print bars for data2:
  $i = 1;
  $value = 0;
  foreach $value (sort {$a cmp $b} keys(%$data2)) {

    $$data2{$value} > 0 && 
    $im->filledRectangle($x_zero + $bar_separation + (($i-1)*$x_scale)+1,
			 $y_zero - 1,
			 $x_zero + ($i*$x_scale)-1,
			 $y_zero - ($$data2{$value}*$y_scale) +1,
			 $darkgreen);
    $i++;
  }


  ### Drop to the file:
  open(PNG, ">$png_file") || die("Unable to open $png_file");
  print PNG $im->png;
  close(PNG);
}
