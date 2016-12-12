# This file is part of sqtpm v6.
# Copyright 2003-2016 Guilherme P. Telles.
# sqtpm is distributed under WTFPL v2.

package sqtpm;

require Exporter;
@ISA = qw(Exporter);

@EXPORT = qw(abort
             abort_login
             abort_pwd 
             wlog

             cat
             load
             print_html
             load_keys_values

             elapsed_days
             format_epoch
             dow

             authenticate
             get_rep_data 
             );

use open ":encoding(Latin1)";
use CGI qw(:standard);
use CGI::Carp 'fatalsToBrowser';
use Time::Local;
use POSIX qw(ceil floor);
use Fcntl ':flock';
use Encode;
use MIME::Base64 qw();


######################################################################
# abort($uid, $assignment, $message)
#
# Print message, removes $assignment/_$uid_tmp_ and its contents,
# write to log and exits.

sub abort {

  my $uid = shift;
  my $assign = shift;
  my $mess = shift;

  print '<p>', $mess, '</form></div></div></body></html>';

  if (-d "$assign/_${uid}_tmp_") {
    unlink glob "$assign/_${uid}_tmp_/*";
    rmdir "$assign/_${uid}_tmp_";
  }

  wlog($uid,'',$mess);

  exit(1);
}



################################################################################
# abort_pwd($uid, $message)
#
# Print message, write to log and exits.

sub abort_pwd {

  my $uid = shift;
  my $mess = shift;

  print '<p>', $mess, '<hr><a href="sqtpm-pwd.cgi">senhas</a></div></body></html>';

  wlog($uid,'',$mess);

  exit(1);
}



################################################################################
# abort_login($uid, $message)
#
# Print an html error page with the message, write to log and exit.

sub abort_login {

  my $uid = shift;
  my $mess = shift;
  
  print header();
  print start_html(-title=>'sqtpm', -style=>{-src=>['sqtpm.css'], -media=>'all'},
		   -head=>[Link({-rel=>'icon',-type=>'image/png',-href=>'icon.png'})]);
  
  print '<div class="f85"><h1>sqtpm</h1>';
  print '<p>', $mess, '</p><hr><a href="sqtpm.cgi">sqtpm</a></div>';
  print end_html();
  wlog($uid,'',$mess);

  exit(1);
}



################################################################################
# wlog($uid, $assignment, $message)
#
# Write an entry to sqtpm.log.

sub wlog {

  my $uid = shift;
  my $assign = shift;
  my $mess = shift;

  !$uid && ($uid = '');
  !$assign && ($assign = '');
  !$mess && ($mess = '');

  local (*LOG);
  if (!open(LOG,">>sqtpm.log")) {
    print '<p>Erro ao abrir sqtpm.log.', '<hr><a href="sqtpm.cgi">sqtpm</a></div></body></html>';
    exit(1);
  }
  flock(LOG,LOCK_EX);
  seek(LOG,0,2);

  printf LOG ("%s %s port %s %s %s %s\n",format_epoch(time),$ENV{REMOTE_ADDR},$ENV{REMOTE_PORT},
	      $uid,$assign,encode("ASCII",$mess));

  flock(LOG,LOCK_UN);
  close(LOG);
}



################################################################################
# load($uid, $assignment, $filename, $is_pre, $limit)
#
# Load a limited number of characters from a file into a buffer.
#
# filename  The name of the source file. 
# is_pre  If true, substitutes < by &lt; and > by &gt;.  May be undef.
# limit  The maximum number of characters to write, If undef or 0, print the whole source file.
#
# If an error occurs while opening the file then invokes abort.

sub load {

  my $uid = shift;
  my $assign = shift;
  my $file = shift;
  my $is_pre = shift;
  my $limit = shift;

  (!defined $is_pre) && ($is_pre = 0);
  (!defined $limit || $limit == 0) && ($limit = 1e9);

  open(my $FILE,'<',$file) || abort($uid,$assign,"Erro ao carregar $file.");

  my $buf = '';
  my $c = getc($FILE);
  my $n = 0;
  while (defined $c && $n < $limit) {
    ($is_pre && $c eq '<') && ($c = '&lt;');
    ($is_pre && $c eq '>') && ($c = '&gt;');
    $buf .= $c;
    $c = getc($FILE);
    $n++;
  }

  $n == $limit && ($buf .= "\n...\n");
  close($FILE);

  $! = 0;
  return $buf;
}



################################################################################
# print_html($path, $file)
#
# Print an html file, encoding image files and printing them too.
# If an error occurs while opening the file then invoke abort.

sub print_html {

  my $path = shift;
  my $file = shift;

  ($path) && ($path = "$path/");

  open(my $HTML,'<',"$path$file") || abort('','',"print_html $path$file : $!");

  while (<$HTML>) {
    /<img / && / src=\"([^\"]*)\"/ && do {
   
      my $fig = $1;
      my $type = (split(/\./,$fig))[-1];

      ($fig !~ /^\//) && ($fig = "$path$fig");

      open(my $FIG, '<', $fig) or abort('','',"print_html $path$fig : $!");
      
      binmode($FIG);
      my $image = do { local $/; <$FIG> };
      close($FIG);
      
      my $enc = MIME::Base64::encode($image);

      s{ src=\"([^\"]*)\"}{ src=\"data:image/${type};base64,${enc}\"};
    };

    print $_;
  }

  close($HTML);
}



################################################################################
# load_keys_values($file, $separator)
#
# Read a file with lines in format key=value and returns a hash with
# pairs key->value.  If a separator is given, then it is used instead
# of '='.  If # occurs in a line, line contents from # to the end of
# the line is discarded.  Keys an values are trimmed for blanks on
# both ends.  Blank lines are ignored.  Lines without a separator are
# set with an empty value in the returning hash.
#
# If an error occurs while opening the file then invokes abort.

sub load_keys_values {

  my $file = shift;
  my $sep = shift;

  !$sep && ($sep = '=');

  open(my $FILE,'<',$file) || abort('','',"Erro ao abrir $file ($!).");

  my %hash = ();

  while (<$FILE>) {
    chomp;
    (/^\s*$/) && next;
    $_ = (split('#',$_,2))[0];

    /^\s*$/ && next; 

    /${sep}/ && do {
      my ($key,$value) = split(/${sep}/,$_,2);
      $key =~ s/^\s+//;
      $key =~ s/\s+$//;
      $value =~ s/^\s+//;
      $value =~ s/\s+$//;
      $hash{$key} = $value;
      next;
    };

    # no separator in the line:
    $hash{$_} = '';
  }
  close($FILE);

  $! = 0;
  return %hash;
}



################################################################################
# elapsed_days($date)
#
# Return the integral number of days elapsed from date.
#
# Return > 0 if date is past, < 0 if date is future or 0 if date
# matches current time.  Any fraction of a day counts -1 or +1.
# Expected date format is aaaa/mm/dd hh:mm:ss

sub elapsed_days {

  my $date = shift;

  $date = timelocal(substr($date,17,2),substr($date,14,2),substr($date,11,2),
		    substr($date,8,2),substr($date,5,2)-1,substr($date,0,4)-1900);
  
  my $delta = time - $date;

  if ($delta > 0) {
    return ceil($delta / 86400);
  }
  elsif ($delta < 0) {
    return floor($delta / 86400);
  }

  return 0;
}



################################################################################
# dow($date)
#
# Return the name of the day of week of date.
# Expected date format is aaaa/mm/dd hh:mm:ss

sub dow {

  my $date = shift;

  my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = 
    localtime(timelocal(substr($date,17,2),substr($date,14,2),substr($date,11,2), 
			substr($date,8,2),substr($date,5,2)-1,substr($date,0,4)-1900));

  # my @days = ( 'domingo','segunda','terça','quarta','quinta','sexta','sábado' );
  my @days = ( 'dom','seg','ter','qua','qui','sex','sáb' );

  return $days[$wday];
}



################################################################################
# format_epoch($seconds)
#
# Format seconds from epoch as aaaa/mm/dd hh:mm:ss.

sub format_epoch {

  my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime( shift );

  return sprintf("%04.0f/%02.0f/%02.0f %02.0f:%02.0f:%02.0f",
		 $year+1900,$mon+1,$mday,$hour,$min,$sec);
}



################################################################################
# (user_type,pass_file) = authenticate($user_id, $typed_password)
#
# Return the user type and the name of the pass file that contains that user.
# The returning user type may be '', 'A' or 'P'.

sub authenticate {

  my $uid = shift;
  my $typedpwd = shift;

  ($uid =~ /^\s*$/) && return ('','');

  # Searches for the password file holding the user id, and gets its
  # prefix and password:
  opendir(my $DIR,'.');
  my @dir = grep(/\.pass$/ && -f $_,readdir($DIR));
  close($DIR);

  my ($prefix, $encpwd, $file);
  my $got = 0;
  my $i = 0;
  while ($i<=$#dir && !$got) {
 
   open(my $PASS,'<',$dir[$i]) || abort($uid,'',"Erro ao abrir o arquivo $dir[$i].");
    while (<$PASS>) {
      $_ = (split('#',$_,2))[0];
      (/^([\*\@]?)$uid:(\S*)/ || /^([\*\@]?)$uid(\s*)$/) && do {
	$prefix = $1;
	$encpwd = $2;
	$prefix =~ s/\s+//g;
	$encpwd =~ s/\s+//g;
	$file = $dir[$i]; 
	$got = 1;
	last;
      };
    }

    close($PASS);
    $i++;
  }

  # If the user does not exist, rejects:
  !$got && return ('','');

  # Sets user type:
  my $utype = 'A';

  ($prefix eq '*') && ($utype = 'P');

  # If typed and stored are both blank, accepts.  If stored is blank
  # and typed is not, rejects:
  if ($encpwd eq '') {
    if ($typedpwd eq '') {
      return ($utype,$file);  
    }
    else {
      return ('','');
    }
  }

  # If typed and stored differ, rejects:
  $encpwd ne crypt($typedpwd,$encpwd) && return ('','');

  return ($utype,$file);
}



################################################################################
# get_rep_data($file)
# 
# Get data on an assignment report, returning a hash with the
# following fields: tries, score, lang, at (yyyy-mm-dd hh:mm:ss).
# Tries is set to 0 if the report file does not exist.

sub get_rep_data {
 
  my ($REPORT, $file, %get);
 
  $file = shift;

  %get = ();
  $get{tries} = 0;

  open($REPORT,'<',"$file") || (return %get);

  $_ = <$REPORT>;
  /<!--lang:([\w\+]*)-->/;
  $get{lang} = $1;

  $_ = <$REPORT>;
  /<!--score:([^-]*)-->/;
  $get{score} = $1;

  $_ = <$REPORT>;
  /<!--tries:([\d]*)-->/;
  $get{tries} = $1;

  $_ = <$REPORT>;
  /<!--at:([\d\:\/ ]*)-->/;
  $get{at} = $1;

  close($REPORT);

  return %get;
}


1;
