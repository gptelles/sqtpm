#!/usr/bin/perl

# Removes expired sqtpm sessions.  If no session is left returns 1,
# otherwise returns 0.

# Guilherme P. Telles, 2015.

use File::Find;
$/;

use constant SESSION_DIR => '/tmp/';

$left = 0;
find(\&wanted,SESSION_DIR);

exit($left ? 0 : 1);


sub wanted {

  !/^sqtpm-sess-.*/ && return;

  open(my $fh,'<',SESSION_DIR . $_) or die("Unable to open $_ : $!");
  my $data = <$fh>;    
  close($fh);
  
  my $D;
  eval($data);

  if (time() >= $D->{_SESSION_ETIME} + $D->{_SESSION_ATIME}) {
    unlink(SESSION_DIR . $_) or print "Unable to delete $_ : $!\n";
  }
  else {
    $left++;
  }
}

