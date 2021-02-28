# This file is part of sqtpm 9.
# Copyright 2003-2021 Guilherme P. Telles.
# sqtpm is distributed under WTFPL v2.

package sqtpm;

require Exporter;
@ISA = qw(Exporter);

@EXPORT = qw(
             authenticate
             check_assign_access

             add_to_log

             format_epoch
             elapsed_days
             dow

             load_keys_values
             load_keys
             load_file

             load_rep_data
             write_lc_file

             abort_login
             abort
             abort_pwd

             histogram
             );


use Encode;
use Time::Local;
use open ":encoding(Latin1)";
use Fcntl ':flock';
use Digest::SHA qw(sha512_base64);
use POSIX qw(ceil floor);
use GD;



####################################################################################################
# (string, string) authenticate($user, $typed_password)
#
# Return the user type and the name of the pass file that contains the user.  
# The user type may be 'S' or 'P'.
#
# Return ('','') in authentication failure.  If typed and stored passwords are both blank, 
# it will return a valid authentication pair.  

sub authenticate {

  my $uid = shift;
  my $typedpwd = shift;

  ($uid =~ /^\s*$/) && return ('','');

  # Search for the password file holding the user id, and get its prefix and password:
  opendir(my $DIR,'.');
  my @dir = grep(/\.pass$/ && -f $_,readdir($DIR));
  close($DIR);

  my ($prefix, $encpwd, $file);
  my $got = 0;
  my $i = 0;
  
  while ($i <= $#dir && !$got) {

    my $PASS;
    open($PASS,'<',$dir[$i]) || abort($uid,'',"Erro ao abrir o arquivo $dir[$i].");
    
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

  # If the user does not exist, reject:
  !$got && (return ('',''));

  # Set user type:
  my $utype = ($prefix eq '*') ? 'P' : 'S';

  # If typed and stored are both blank, accept. 
  $encpwd eq '' && $typedpwd eq '' && (return ($utype,$file));

  # If typed and stored differ, reject:
  $encpwd ne sha512_base64($typedpwd) && (return ('',''));

  return ($utype,$file);
}



####################################################################################################
# int check_assign_access($user, $pass_file, $assignment)
#
# Verify whether the user has an assignment, that is, whether the pass file
# (that should contain the user) is linked to an assignment.
# Return 1 if it is or invoke block_user() on the user otherwise.

sub check_assign_access {

  my $uid = shift;
  my $upassf = shift;
  my $assign = shift;

  (-d $assign && -e "$assign/$upassf") && (return 1);

  block_user($uid,$upassf,"check_assign: $upassf não está em $assign.");
}



####################################################################################################
# add_to_log($uid, $assignment, $message)
#
# Add an entry to sqtpm.log.

sub add_to_log {

  my $uid = shift;
  my $assign = shift;
  my $mess = shift;

  !$uid && ($uid = '');
  !$assign && ($assign = '');
  !$mess && ($mess = '');

  my $LOG;
  if (!open($LOG,'>>','sqtpm.log')) {
    print '<p>Erro ao abrir sqtpm.log.', '<hr><a href="sqtpm.cgi">sqtpm</a></div></body></html>';
    exit(1);
  }
  flock($LOG,LOCK_EX);
  seek($LOG,0,2);

  printf $LOG "%s %s port %s %s %s %s\n",format_epoch(time),$ENV{REMOTE_ADDR},$ENV{REMOTE_PORT},
	      $uid,$assign,encode("ASCII",$mess);

  flock($LOG,LOCK_UN);
  close($LOG);
}



####################################################################################################
# string format_epoch($seconds)
#
# Format seconds from epoch as aaaa/mm/dd hh:mm:ss.

sub format_epoch {

  my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime( shift );

  return sprintf("%04.0f/%02.0f/%02.0f %02.0f:%02.0f:%02.0f",
                 $year+1900,$mon+1,$mday,$hour,$min,$sec);
}



####################################################################################################
# int elapsed_days($date)
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



####################################################################################################
# string dow($date)
#
# Return the day of week of date.
# Expected date format is aaaa/mm/dd hh:mm:ss

sub dow {

  my $date = shift;

  my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = 
    localtime(timelocal(substr($date,17,2),substr($date,14,2),substr($date,11,2), 
                        substr($date,8,2),substr($date,5,2)-1,substr($date,0,4)-1900));

  my @days = ( 'dom','seg','ter','qua','qui','sex','sáb' );

  return $days[$wday];
}



####################################################################################################
# hash load_keys_values($file, $separator)
#
# Read a file with lines in format ^\s*key\s*=\s*value\s* and return a
# hash with pairs key->value.
#
# If a separator is given, then it is used instead of '='.  If '#'
# occurs in a line, line contents from '#' to the end of the line is
# discarded.  Keys and values are trimmed for blanks on both ends.
#
# Empty keys and empty values are allowed.  Multiply defined keys
# retain the last value in file order.
#
# If an error occurs while opening the file then it invokes abort().

sub load_keys_values {

  my $file = shift;
  my $sep = shift;

  (!$sep) && ($sep = '=');

  open(my $FILE,'<',$file) || abort('','',"load_keys_values: open $file: $!");

  my %hash = ();

  while (<$FILE>) {
    chomp;
    $_ = (split(/#/,$_,2))[0];
    (/^\s*$/) && next;
    my ($key,$value) = split(/${sep}/,$_,2);
    $key =~ s/^\s+//;
    $key =~ s/\s+$//;
    $value =~ s/^\s+//;
    $value =~ s/\s+$//;
    $hash{$key} = $value;
  }

  close($FILE);

  $! = 0;
  return %hash;
}



####################################################################################################
# array load_keys($file, $separator)
#
# Read a file with lines in format ^\s*key\s*=\s*value\s* and return an
# array with keys in the same order as they appear in the file.
#
# If a separator is given, then it is used instead of '='.
#
# If '#' occurs in a line, line contents from '#' to the end of the
# line is discarded.  Keys are trimmed for blanks on both ends.  Lines
# with an empty key will be disregarded.
#
# If an error occurs while opening the file then it invokes abort().

sub load_keys {

  my $file = shift;
  my $sep = shift;

  (!$sep) && ($sep = '=');
  
  open(my $FILE,'<',$file) || abort('','',"load_keys: open $file: $!");

  my @A = ();
  
  while (<$FILE>) {
    chomp;
    $_ = (split(/#/,$_,2))[0];
    $_ = (split(/${sep}/,$_,2))[0];
    s/^\s+//;
    s/\s+$//;
    /^\s*$/ && next; 
    $_ && (push(@A,$_));
  }
  
  close($FILE);

  return @A;
}



####################################################################################################
# string load_file($uid, $assignment, $file, $is_pre, $limit)
#
# Load a limited number of characters from a file into a string.
#
# file     The name of the file. 
# is_pre   If true, substitutes < by &lt; and > by &gt;.  May be undef.
# limit    The maximum number of characters to write. If undef or 0, load the whole file.
#
# If an error occurs while opening the file then it invokes abort().

sub load_file {

  my $uid = shift;
  my $assign = shift;
  my $file = shift;
  my $is_pre = shift;
  my $limit = shift;

  (!defined $is_pre) && ($is_pre = 0);
  (!defined $limit || $limit == 0) && ($limit = 1e9);

  open(my $FILE,'<',$file) || abort($uid,$assign,"load_file: open $file: $!");

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

  ($n == $limit) && ($buf .= "\n...\n");
  close($FILE);

  $! = 0;
  return $buf;
}



####################################################################################################
# hash load_rep_data($file)
# 
# Get data on an assignment report, returning a hash with the
# following fields: tries, grade, lang, at (with format yyyy-mm-dd hh:mm:ss).
#
# The field tries is set to 0 if the report file does not exist.

sub load_rep_data {
 
  my ($REPORT, $file, %get);
 
  $file = shift;

  %get = ();
  $get{tries} = 0;

  open($REPORT,'<',"$file") || (return %get);

  $_ = <$REPORT>;
  /<!--lang:([\w\+]*)-->/;
  $get{lang} = $1;

  $_ = <$REPORT>;
  /<!--grade:([^-]*)-->/;
  $get{grade} = $1;

  $_ = <$REPORT>;
  /<!--tries:([\d]*)-->/;
  $get{tries} = $1;

  $_ = <$REPORT>;
  /<!--at:([\d\:\/ ]*)-->/;
  $get{at} = $1;

  close($REPORT);

  return %get;
}



####################################################################################################
# int write_lc_file($uid, $assign, $file, $limit)
#
# Create a version of a file without blanks and lowercase characters.
# The new file is named "$file.lc" and is created only if it does not
# exist or if $file is newer than an existing "$file.lc".
#
# file     The name of the source file. 
# limit    The maximum number of characters to write.
#
# Return 1 if file.lc is created or updated and return 0 otherwise. If
# an error occurs while opening the file then it invokes abort().

sub write_lc_file {

  my $uid = shift;
  my $assign = shift;  
  my $filin = shift;
  my $limit = shift;

  my $filout = "$filin.lc";

  if (-e $filout && (stat($filin))[9] < (stat($filout))[9]) {
    return 0;
  }
  
  open(my $FIN,'<',$filin) || abort($uid,$assign,"lc_file: open $filin: $!");
  open(my $FOUT,'>',$filout) || abort($uid,$assign,"lc_file: open $filout: $!");
  
  my $n = 0;
  while (<$FIN>) {
    chomp;
    s/[ \t]//g;

    if ($n + length($_) > $limit) {
      $_ = substr($_,0,$limit-$n+10);
      print $FOUT lc($_);
      last;
    }

    print $FOUT lc($_);
    $n += length($_);
  }
  
  close($FIN);
  close($FOUT);
  
  return 1;
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
# abort($uid, $assignment, $message)
#
# Print message, remove $assignment/_$uid_tmp_ and its contents, write to log and exit.

sub abort {

  my $uid = shift;
  my $assign = shift;
  my $mess = shift;

  print '<p>', $mess, '<hr></form></div></div></body></html>';

  if ($assign && -d "$assign/_${uid}_tmp_") {
    unlink glob "$assign/_${uid}_tmp_/*";
    rmdir "$assign/_${uid}_tmp_";
  }

  add_to_log($uid,$assign,$mess);

  exit(1);
}



####################################################################################################
# abort_pwd($uid, $message)
#
# Print message, write to log and exit.

sub abort_pwd {

  my $uid = shift;
  my $mess = shift;

  print '<p>', $mess, '<hr><a href="sqtpm-pwd.cgi">senhas</a></div></body></html>';
  add_to_log($uid,'',$mess);
  exit(1);
}



####################################################################################################
# png-image histogram($png_width, $png_height, \%data1, \%data2)
# 
# A histogram for two data series.  Each data series is a hash with
# key->value pairs.  Both data series must have the same set of keys.
# The values in the second data series should be smaller than those in
# the first.
#
# This function was written in 1999 or 2000 for a single series and
# adapted for two series.

sub histogram {

  my $png_width = shift;
  my $png_height = shift;
  my $data1 = shift;
  my $data2 = shift;

  my $im = new GD::Image($png_width,$png_height);

  my $black = $im->colorAllocate(0,0,0);
  my $darkgreen = $im->colorAllocate(0,150,0);
  my $blue = $im->colorAllocate(0,0,220);
  my $gray = $im->colorAllocate(225,225,225);
  my $white = $im->colorAllocate(255,255,255);
  my $red = $im->colorAllocate(180,0,0);
  my $purple = $im->colorAllocate(146,50,172);

  my ($tfw,$tfh) = (gdSmallFont->width,gdSmallFont->height);
  
  # Draw a border:
  $im->rectangle(0,0,$png_width-1,$png_height-1,$black);
  $im->rectangle(1,1,$png_width-2,$png_height-2,$gray);
  $im->fill(10,10,$gray);

  ### Find maximum in y:
  my $max_y = 0;
  my $max_x = 0; 
  my $pairs_total = 0;
  foreach my $value (keys(%$data1)) {
    $pairs_total++;
    my $l = length($value);
    if ($max_x < $l) {
      $max_x = $l;
    }
    if ($max_y < $$data1{$value}) {
      $max_y = $$data1{$value};
    }
  }

  ### Set margins and such:
  my $x_margin = 10;
  my $y_margin = 10;
  my $free_axis_end = 5;
  my $y_text_area = 4+(length("$max_y")*$tfw);
  my $x_text_area = 4+($max_x*$tfw);

  ### Eval x and y scales:
  my $x_scale = ($png_width-(2*$x_margin)-$y_text_area-(2*$free_axis_end)) / $pairs_total;

  ($x_scale > 30) && ($x_scale = 30);

  my $up_text = 0;
  if ($x_scale < $max_x*1.2*$tfw) {
    $up_text = 1;
    $x_text_area = $max_x*1.2*$tfw;
  }
  else{
    $up_text = 0;
    $x_text_area = 20;
  }

  my $y_scale = ($png_height-(2*$y_margin)-(2*$free_axis_end)-$x_text_area) / $max_y;
  
  ### Print y axis:
  my $x_zero = $x_margin + $free_axis_end + $y_text_area;
  my $y_zero = $png_height - $y_margin - $free_axis_end - $x_text_area;

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
  my @y = values(%$data1);
  push(@y,values(%$data2));
  my $filled_y = 0;
  my $aux1 = length("$max_y");
  foreach my $value (sort {$b <=> $a} @y) {

    if ($value > 0) {
      $im->rectangle($x_zero - 3, 
		     $y_zero-$value*$y_scale, 
		     $x_zero, 
		     $y_zero-$value*$y_scale, 
		     $black);
      
      if ($y_zero-($value*$y_scale)-$tfh > $filled_y && 
	  $y_zero-($value*$y_scale)-$tfh < $y_zero - 1.5*$tfh) {
	
	$im->string(gdSmallFont, $x_margin+$free_axis_end, $y_zero-$value*$y_scale-($tfh/2), 
		    sprintf("%${aux1}i",$value), $blue);
	$filled_y = $y_zero-$value*$y_scale;
      }
    }
  }

  my $bar_separation = 7;
  
  ### Print x values:
  my @x = sort {$a cmp $b} keys(%$data1);
  my $filled_x = $x_zero;
  $aux1 = $max_x;
  my $i = 1;

  if (!$up_text) {
    foreach my $value (@x) {
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
    foreach my $value (@x) {
      $im->stringUp(gdSmallFont, 
		    $x_zero+($bar_separation/2)+(($i-1)*$x_scale)+($x_scale/2)
		    -$tfh/2,
		    $png_height-$y_margin-$free_axis_end, 
		    sprintf("%${aux1}s",$value),
		    $blue);
      $i++;
    }
  }

  ### Print bars for data1:
  $i = 1;
  my $value = 0;
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
    ($$data2{$value} > 0) && 
      $im->filledRectangle($x_zero + $bar_separation + (($i-1)*$x_scale)+1,
			   $y_zero - 1,
			   $x_zero + ($i*$x_scale)-1,
			   $y_zero - ($$data2{$value}*$y_scale) +1,
			   $darkgreen);
    $i++;
  }

  ### Drop to file:
  #open($PNG, ">$png_file") || die("Unable to write $png_file");
  #print $PNG $im->png;
  #close($PNG);

  return $im->png;
}


1;
